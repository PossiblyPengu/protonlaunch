#!/usr/bin/env python3
"""Unit tests for protonlaunch helpers (no network, no display)."""
import os
import shlex
import sys
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from protonlaunch.helpers.helpers import (
    build_launcher_script,
    combined_store_search_with_diagnostics,
    parse_steam_launch_options_env,
    parse_winetricks_verbs_field,
    scan_prefix_for_game_exes,
    steam_shortcut_appid,
    strip_env_from_launch_options,
    suggest_deck_compatibility,
    write_steam_shortcut,
)


class ParseHelpersTests(unittest.TestCase):
    def test_winetricks_rejects_invalid_tokens(self):
        verbs = parse_winetricks_verbs_field("vcrun2019, rm -rf /, corefonts")
        self.assertEqual(verbs, ["vcrun2019", "corefonts"])

    def test_launch_options_env_extraction(self):
        env = parse_steam_launch_options_env("DXVK_ASYNC=1 %command% WINEDEBUG=-all")
        self.assertEqual(env, {"DXVK_ASYNC": "1", "WINEDEBUG": "-all"})

    def test_strip_env_from_launch_options(self):
        self.assertEqual(
            strip_env_from_launch_options("DXVK_ASYNC=1 %command% -someflag"),
            "-someflag",
        )


class LauncherScriptTests(unittest.TestCase):
    def test_shell_quoting_special_characters(self):
        with tempfile.TemporaryDirectory() as tmp:
            prefixes = Path(tmp) / "prefixes"
            data = Path(tmp) / "data"
            data.mkdir()
            game = {
                "id": 'game_"special"',
                "exe": '/tmp/My Game "Edition"/game.exe',
                "proton_bin": "/fake/proton",
                "dxvk": True,
                "esync": False,
                "fsync": False,
                "mangohud": False,
                "steam_launch_options": "DXVK_ASYNC=1",
            }
            script = build_launcher_script(game, prefixes, data, Path("/fake/steam"))
            content = Path(script).read_text()
            self.assertIn("export DXVK_ASYNC=", content)
            self.assertIn("run ", content)
            self.assertIn(shlex.quote(game["exe"]), content)


class ScanPrefixTests(unittest.TestCase):
    def test_skips_installer_and_system_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_dir = root / "drive_c" / "Games" / "Demo"
            game_dir.mkdir(parents=True)
            installer = game_dir / "setup.exe"
            game_exe = game_dir / "demo.exe"
            installer.write_bytes(b"x")
            game_exe.write_bytes(b"x")
            found = scan_prefix_for_game_exes(root, installer)
            self.assertEqual(found, [str(game_exe.resolve())])


class SuggestDeckTests(unittest.TestCase):
    def test_dx12_enables_vkd3d(self):
        suggest = suggest_deck_compatibility(
            {"tier": "gold"},
            {"short_description": "Requires DirectX 12"},
        )
        self.assertTrue(suggest["vkd3d"])


class CombinedSearchTests(unittest.TestCase):
    @patch("protonlaunch.helpers.helpers.lutris_search_with_status")
    @patch("protonlaunch.helpers.helpers.steam_search_with_status")
    def test_merges_and_dedupes_steam_ids(self, mock_steam, mock_lutris):
        mock_steam.return_value = (
            [{"id": 10, "name": "Alpha"}],
            "",
        )
        mock_lutris.return_value = (
            [
                {"kind": "lutris", "name": "Alpha", "steam_appid": 10, "display_suffix": "Steam"},
                {"kind": "lutris", "name": "Beta", "steam_appid": None, "display_suffix": "GOG"},
            ],
            "",
        )
        results, diag = combined_store_search_with_diagnostics("alpha")
        self.assertTrue(diag["steam_ok"])
        self.assertTrue(diag["lutris_ok"])
        kinds = [r.get("name") for r in results]
        self.assertIn("Alpha", kinds)
        self.assertIn("Beta", kinds)
        self.assertEqual(len([r for r in results if r.get("name") == "Alpha"]), 1)


class SteamShortcutTests(unittest.TestCase):
    def test_write_updates_all_userdata_dirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            steam_root = Path(tmp) / "steam"
            for user in ("111", "222"):
                (steam_root / "userdata" / user / "config").mkdir(parents=True)
            ok, msg = write_steam_shortcut(
                "Test Game",
                str(Path(tmp) / "launch.sh"),
                "",
                steam_root,
            )
            self.assertTrue(ok)
            self.assertIn("2 Steam profiles", msg)
            for user in ("111", "222"):
                sc = steam_root / "userdata" / user / "config" / "shortcuts.vdf"
                self.assertTrue(sc.is_file())

    def test_shortcut_dedup_by_appid(self):
        try:
            import vdf  # type: ignore
        except ImportError:
            self.skipTest("vdf not installed")

        with tempfile.TemporaryDirectory() as tmp:
            steam_root = Path(tmp)
            config = steam_root / "userdata" / "1" / "config"
            config.mkdir(parents=True)
            shortcuts = config / "shortcuts.vdf"
            appid = steam_shortcut_appid("Dup Game", "/tmp/launch.sh")
            data = {
                "shortcuts": {
                    "0": {
                        "appid": str(appid),
                        "AppName": "Old Name",
                        "Exe": '"/tmp/old.sh"',
                        "StartDir": "/tmp",
                        "icon": "",
                        "ShortcutPath": "",
                        "LaunchOptions": "",
                        "IsHidden": "0",
                        "AllowDesktopConfig": "1",
                        "AllowOverlay": "1",
                        "OpenVR": "0",
                        "LastPlayTime": "0",
                    }
                }
            }
            buf = BytesIO()
            vdf.binary_dump(data, buf)
            shortcuts.write_bytes(buf.getvalue())

            ok, _msg = write_steam_shortcut(
                "Dup Game",
                "/tmp/launch.sh",
                "",
                steam_root,
            )
            self.assertTrue(ok)
            loaded = vdf.binary_load(BytesIO(shortcuts.read_bytes()), raise_on_remaining=False)
            entries = loaded.get("shortcuts", {})
            matching = [
                e for e in entries.values()
                if isinstance(e, dict) and str(e.get("appid")) == str(appid)
            ]
            self.assertEqual(len(matching), 1)
            self.assertEqual(matching[0]["AppName"], "Dup Game")


if __name__ == "__main__":
    unittest.main()
