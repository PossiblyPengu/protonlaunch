#!/usr/bin/env python3
"""Comprehensive test of ProtonLaunch components."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("=" * 50)
print("PROTONLAUNCH COMPONENT TESTS")
print("=" * 50)

SKIP_NETWORK = os.environ.get("PROTONLAUNCH_SKIP_NETWORK", "").strip().lower() in (
    "1",
    "true",
    "yes",
)

print("\n[1] Testing helpers module...")
from protonlaunch.helpers.helpers import (
    build_launcher_script,
    find_proton_versions,
    steam_app_details,
    steam_search,
    write_steam_shortcut,
)

print("   ✓ All helper functions imported")

if SKIP_NETWORK:
    print("\n[2] Skipping live Steam API (PROTONLAUNCH_SKIP_NETWORK set)")
else:
    print("\n[2] Testing Steam Store API...")
    results = steam_search("hades")
    print(f"   ✓ Search returned {len(results)} results")
    if results:
        first = results[0]
        print(f"   ✓ First result: {first.get('name')}")
        appid = first.get("id")
        details = steam_app_details(appid)
        print(f"   ✓ App details fetched: {details.get('name', 'N/A')}")

print("\n[3] Testing Proton/Wine detection...")
from pathlib import Path

steam_dir = Path.home() / ".steam" / "steam"
proton_ge_dir = Path.home() / ".steam" / "root" / "compatibilitytools.d"
versions = find_proton_versions(steam_dir, proton_ge_dir)
print(f"   Found {len(versions)} Proton/Wine versions")
for name, path in versions.items():
    print(f"   - {name}: {path}")

print("\n[4] Testing launcher script generation...")
with tempfile.TemporaryDirectory() as tmpdir:
    prefixes_dir = Path(tmpdir) / "prefixes"
    data_dir = Path(tmpdir) / "data"
    steam_dir = Path.home() / ".steam" / "steam"

    game = {
        "id": "test_hades",
        "name": "Hades",
        "exe": "/fake/hades.exe",
        "proton_bin": "/fake/proton",
        "dxvk": True,
        "esync": True,
        "fsync": False,
        "mangohud": False,
        "steam_launch_options": "DXVK_ASYNC=1",
    }

    data_dir.mkdir(parents=True, exist_ok=True)
    script_path = build_launcher_script(game, prefixes_dir, data_dir, steam_dir)
    assert Path(script_path).exists()
    content = Path(script_path).read_text()
    assert "export WINEPREFIX=" in content
    assert "DXVK_ASYNC=" in content
    assert "d3d9,d3d10core,d3d11,dxgi=n,b" in content
    print("   ✓ Launcher script generated correctly")
    print("   Script preview:\n   ---")
    for line in content.split("\n")[:7]:
        print(f"   {line}")
    print("   ---")

print("\n[5] Running unit tests...")
import unittest

loader = unittest.TestLoader()
suite = loader.discover(os.path.dirname(__file__), pattern="test_helpers_unit.py")
runner = unittest.TextTestRunner(verbosity=0)
result = runner.run(suite)
if not result.wasSuccessful():
    raise SystemExit(1)
print(f"   ✓ {result.testsRun} unit tests passed")

print("\n" + "=" * 50)
print("ALL TESTS PASSED ✓")
print("=" * 50)
