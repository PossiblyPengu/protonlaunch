"""Headless tests for the install engine. A fake Proton stands in for the real one."""
import os
import struct
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from protonlaunch import core  # noqa: E402


def make_lnk(target: str) -> bytes:
    """Minimal Shell Link with only a LinkInfo local base path (what Wine writes)."""
    header = bytearray(0x4C)
    header[0:4] = b"L\x00\x00\x00"
    struct.pack_into("<I", header, 0x14, 0x02)  # HasLinkInfo
    volume = struct.pack("<IIII", 0x11, 3, 0, 0x10) + b"\x00"
    base = target.encode("cp1252") + b"\x00"
    hdr = 0x1C
    size = hdr + len(volume) + len(base) + 1
    info = struct.pack("<7I", size, hdr, 1, hdr, hdr + len(volume), 0, size - 1) + volume + base + b"\x00"
    return bytes(header) + info


FAKE_PROTON = """#!/bin/bash
[ "$1" = run ] || exit 2
[ -n "$FAKE_SLEEP" ] && sleep "$FAKE_SLEEP"
pfx="$STEAM_COMPAT_DATA_PATH/pfx"
c="$pfx/drive_c"
mkdir -p "$c/windows/system32" "$c/Program Files/Cool Game/bin" "$c/users/steamuser/Desktop" \\
         "$c/users/steamuser/AppData/Local/Temp"
touch "$c/windows/system32/notepad.exe" "$c/users/steamuser/AppData/Local/Temp/setup-helper.exe"
[ -n "$FAKE_NOTHING" ] && exit 0
head -c 3000000 /dev/zero > "$c/Program Files/Cool Game/bin/CoolGame.exe"
touch "$c/Program Files/Cool Game/unins000.exe" "$c/Program Files/Cool Game/bin/CrashReporter.exe"
[ -n "$FAKE_LNK" ] && cp "$FAKE_LNK" "$c/users/steamuser/Desktop/Cool Game Deluxe.lnk"
echo "installed $2"
"""


class Env(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.paths = core.Paths(self.tmp / "data")
        # Fake Steam with one user and one Proton
        self.steam = self.tmp / "Steam"
        (self.steam / "steamapps/common").mkdir(parents=True)
        (self.steam / "userdata/12345/config").mkdir(parents=True)
        proton_dir = self.steam / "compatibilitytools.d/GE-Proton9-20"
        (proton_dir / "files/bin").mkdir(parents=True)
        self.proton = proton_dir / "proton"
        self.proton.write_text(FAKE_PROTON)
        self.proton.chmod(0o755)
        ws = proton_dir / "files/bin/wineserver"
        ws.write_text("#!/bin/bash\nexit 0\n")
        ws.chmod(0o755)
        self.installer = self.tmp / "setup_cool_game_v1.2.3_(12345).exe"
        self.installer.write_bytes(b"MZ")
        self.env_backup = dict(os.environ)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.env_backup)
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def job(self, **kw):
        return core.Installer(self.installer, self.paths, steam_roots_override=[self.steam], **kw)


class TestNaming(unittest.TestCase):
    def test_guess_name(self):
        cases = {
            "setup_the_witcher_3_wild_hunt_goty_1.32_(a)_(10709).exe": "The Witcher 3 Wild Hunt Goty",
            "ChromeSetup.exe": "Chrome",
            "npp.8.6.Installer.x64.exe": "Npp",
            "Firefox Setup 120.0.exe": "Firefox",
            "7z2301-x64.exe": "7z2301",
            "setup.exe": "setup",
            "Battle.net-Setup.exe": "Battle Net",
        }
        for f, want in cases.items():
            self.assertEqual(core.guess_name(f), want, f)

    def test_slugify(self):
        self.assertEqual(core.slugify("The Witcher 3: GOTY"), "the-witcher-3-goty")
        self.assertEqual(core.slugify("!!!"), "app")


class TestLnk(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(core.lnk_target(make_lnk(r"C:\Program Files\X\x.exe")), r"C:\Program Files\X\x.exe")
        self.assertIsNone(core.lnk_target(b"garbage"))

    def test_windows_to_unix_case_insensitive(self):
        with tempfile.TemporaryDirectory() as d:
            pfx = Path(d)
            exe = pfx / "drive_c/Program Files/Game/Game.exe"
            exe.parent.mkdir(parents=True)
            exe.touch()
            self.assertEqual(core.windows_to_unix(pfx, r"c:\PROGRAM FILES\game\game.EXE"), exe)
            self.assertIsNone(core.windows_to_unix(pfx, r"C:\nope.exe"))


class TestVdf(unittest.TestCase):
    def test_roundtrip(self):
        data = {"shortcuts": {"0": {"appid": -5, "AppName": "Ä", "LastPlayTime": 7,
                                    "big": core.U64(2**40), "tags": {"0": "x"}}}}
        raw = core.vdf_dumps(data)
        self.assertEqual(core.vdf_loads(raw), data)
        self.assertEqual(core.vdf_dumps(core.vdf_loads(raw)), raw)

    def test_rejects_unknown_type(self):
        with self.assertRaises(ValueError):
            core.vdf_loads(b"\x00shortcuts\x00\x09x\x00\x08\x08")


class TestSteamShortcuts(Env):
    def test_add_replace_remove(self):
        cfg = self.steam / "userdata/12345/config"
        existing = {"shortcuts": {"0": {"appid": 1, "AppName": "Other", "Exe": '"/x"'}}}
        (cfg / "shortcuts.vdf").write_bytes(core.vdf_dumps(existing))
        appid, n = core.add_steam_shortcut("Cool", "/l/cool.sh", "/g", roots=[self.steam])
        self.assertEqual(n, 1)
        core.add_steam_shortcut("Cool", "/l/cool.sh", "/g", roots=[self.steam])  # no duplicate
        sc = core.vdf_loads((cfg / "shortcuts.vdf").read_bytes())["shortcuts"]
        self.assertEqual([e["AppName"] for e in sc.values()], ["Other", "Cool"])
        self.assertEqual(sc["1"]["appid"] & 0xFFFFFFFF, appid)
        self.assertTrue(appid & 0x80000000)
        self.assertTrue((cfg / "shortcuts.vdf.protonlaunch-bak").exists())
        core.remove_steam_shortcut(appid, roots=[self.steam])
        sc = core.vdf_loads((cfg / "shortcuts.vdf").read_bytes())["shortcuts"]
        self.assertEqual([e["AppName"] for e in sc.values()], ["Other"])


class TestRuntimes(Env):
    def test_prefers_ge(self):
        stock = self.steam / "steamapps/common/Proton 9.0"
        stock.mkdir(parents=True)
        (stock / "proton").write_text("")
        exp = self.steam / "steamapps/common/Proton - Experimental"
        exp.mkdir(parents=True)
        (exp / "proton").write_text("")
        old_ge = self.steam / "compatibilitytools.d/GE-Proton8-1"
        old_ge.mkdir(parents=True)
        (old_ge / "proton").write_text("")
        rts = core.find_runtimes([self.steam], extra_tool_dirs=[], include_system_wine=False)
        self.assertEqual([r.name for r in rts],
                         ["GE-Proton9-20", "GE-Proton8-1", "Proton - Experimental", "Proton 9.0"])
        self.assertTrue(rts[0].wineserver().endswith("files/bin/wineserver"))

    def test_none(self):
        empty = self.tmp / "empty"
        (empty / "steamapps").mkdir(parents=True)
        self.assertEqual(core.find_runtimes([empty], extra_tool_dirs=[], include_system_wine=False), [])


class TestInstallFlow(Env):
    def test_end_to_end_with_shortcut(self):
        lnk = self.tmp / "x.lnk"
        lnk.write_bytes(make_lnk(r"C:\Program Files\Cool Game\bin\CoolGame.exe"))
        os.environ["FAKE_LNK"] = str(lnk)
        statuses = []
        job = self.job(status=statuses.append)
        pending = job.run()
        self.assertEqual(pending.name, "Cool Game")
        self.assertTrue(core.is_confident(pending.candidates))
        top = pending.candidates[0]
        self.assertEqual(top.exe.name, "CoolGame.exe")
        names = [c.exe.name for c in pending.candidates]
        self.assertNotIn("notepad.exe", names)
        self.assertNotIn("setup-helper.exe", names)
        self.assertLess(names.index("CoolGame.exe"), names.index("unins000.exe"))

        app = job.finish(pending, top.exe, core.best_name(pending, top))
        self.assertEqual(app.name, "Cool Game Deluxe")
        self.assertTrue(any("installer" in s for s in statuses))
        script = Path(app.launcher).read_text()
        self.assertIn("STEAM_COMPAT_DATA_PATH=", script)
        self.assertIn("CoolGame.exe", script)
        self.assertTrue(os.access(app.launcher, os.X_OK))
        self.assertEqual([a.id for a in core.Library(self.paths).load()], ["cool-game"])
        sc = core.vdf_loads((self.steam / "userdata/12345/config/shortcuts.vdf").read_bytes())
        self.assertEqual(sc["shortcuts"]["0"]["AppName"], "Cool Game Deluxe")

        # Same installer again gets its own prefix
        self.assertEqual(core.Library(self.paths).unique_id("Cool Game"), "cool-game-2")

        core.uninstall(app, self.paths, roots=[self.steam])
        self.assertFalse(Path(app.prefix).exists())
        self.assertEqual(core.Library(self.paths).load(), [])
        sc = core.vdf_loads((self.steam / "userdata/12345/config/shortcuts.vdf").read_bytes())
        self.assertEqual(sc["shortcuts"], {})

    def test_without_shortcut_still_picks_program(self):
        job = self.job()
        pending = job.run()
        job.close()
        self.assertEqual(pending.candidates[0].exe.name, "CoolGame.exe")
        self.assertTrue(core.is_confident(pending.candidates))

    def test_installer_copy_is_never_the_program(self):
        # Installer drops a byte-identical copy of itself plus a setup tool, and nothing else.
        self.installer.write_bytes(b"MZ" + b"\x01" * 5_000_000)
        os.environ["FAKE_NOTHING"] = "1"
        job = self.job()
        pending = job.run()
        job.close()
        c = pending.pfx / "drive_c/Program Files/Cool Game"
        c.mkdir(parents=True, exist_ok=True)
        (c / "cache.exe").write_bytes(self.installer.read_bytes())  # renamed copy
        (c / "GameSetup.exe").write_bytes(b"MZ" + b"\x02" * 5_000_000)
        cands = core.find_program(pending.pfx, pending.name, pending.installer)
        self.assertNotIn("cache.exe", [x.exe.name for x in cands])
        self.assertFalse(core.is_confident(cands, pending.installer))

    def test_program_wins_over_installer_named_shortcut(self):
        lnk = self.tmp / "x.lnk"
        lnk.write_bytes(make_lnk(r"C:\Program Files\Cool Game\bin\CoolGame.exe"))
        os.environ["FAKE_LNK"] = str(lnk)
        job = self.job()
        pending = job.run()
        job.close()
        self.assertTrue(core.is_confident(pending.candidates, pending.installer))
        self.assertEqual(pending.candidates[0].exe.name, "CoolGame.exe")
        self.assertNotEqual(pending.candidates[0].exe.name, self.installer.name)

    def test_portable_program(self):
        os.environ["FAKE_NOTHING"] = "1"
        job = self.job()
        pending = job.run()
        self.assertFalse(core.is_confident(pending.candidates))
        exe = core.adopt_portable(pending)
        self.assertTrue(exe.is_file())
        app = job.finish(pending, exe, "Evil\nrm -rf ~")
        self.assertTrue(app.exe.endswith(self.installer.name))
        self.assertEqual(app.name, "Evil rm -rf ~")
        self.assertNotIn("\nrm", Path(app.launcher).read_text())

    def test_cancel_removes_prefix(self):
        os.environ["FAKE_SLEEP"] = "30"
        job = self.job()
        threading.Timer(0.5, job.cancel).start()
        t0 = time.time()
        with self.assertRaises(core.Cancelled):
            job.run()
        self.assertLess(time.time() - t0, 10)
        self.assertFalse((self.paths.prefixes / "cool-game").exists())

    def test_no_runtime(self):
        empty = self.tmp / "empty"
        (empty / "steamapps").mkdir(parents=True)
        os.environ["PATH"] = str(self.tmp)  # hide any system wine
        job = core.Installer(self.installer, self.paths, steam_roots_override=[empty])
        with self.assertRaises(core.InstallError) as ctx:
            job.run()
        self.assertEqual(str(ctx.exception), "NO_RUNTIME")

    def test_rejects_non_installer(self):
        bad = self.tmp / "notes.txt"
        bad.write_text("x")
        with self.assertRaises(core.InstallError):
            core.Installer(bad, self.paths, steam_roots_override=[self.steam]).run()

    def test_msi_command(self):
        rt = core.Runtime("P", "proton", "/p/proton")
        self.assertEqual(core.run_command(rt, Path("/d/a.msi")), ["/p/proton", "run", "msiexec", "/i", "/d/a.msi"])


if __name__ == "__main__":
    unittest.main()
