#!/usr/bin/env python3
"""Comprehensive test of ProtonLaunch components"""
import sys
import os
# Use local path for testing
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("=" * 50)
print("PROTONLAUNCH COMPONENT TESTS")
print("=" * 50)

# Test 1: Helpers import
print("\n[1] Testing helpers module...")
from protonlaunch.helpers.helpers import (
    steam_search, steam_app_details, download_cover,
    find_proton_versions, build_launcher_script, write_steam_shortcut
)
print("   ✓ All helper functions imported")

# Test 2: Steam API
print("\n[2] Testing Steam Store API...")
results = steam_search('hades')
print(f"   ✓ Search returned {len(results)} results")
if results:
    first = results[0]
    print(f"   ✓ First result: {first.get('name')}")
    
    # Test app details
    appid = first.get('id')
    details = steam_app_details(appid)
    print(f"   ✓ App details fetched: {details.get('name', 'N/A')}")

# Test 3: Proton version detection (will be empty without Steam)
print("\n[3] Testing Proton/Wine detection...")
from pathlib import Path
steam_dir = Path.home() / ".steam" / "steam"
proton_ge_dir = Path.home() / ".steam" / "root" / "compatibilitytools.d"
versions = find_proton_versions(steam_dir, proton_ge_dir)
print(f"   Found {len(versions)} Proton/Wine versions")
for name, path in versions.items():
    print(f"   - {name}: {path}")

# Test 4: Launcher script generation
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
        "mangohud": False
    }
    
    data_dir.mkdir(parents=True, exist_ok=True)
    script_path = build_launcher_script(game, prefixes_dir, data_dir, steam_dir)
    assert Path(script_path).exists()
    content = Path(script_path).read_text()
    assert "export WINEPREFIX" in content
    assert "d3d9,d3d10core,d3d11,dxgi=n,b" in content  # DXVK
    print("   ✓ Launcher script generated correctly")
    print(f"   Script preview:\n   ---")
    for line in content.split('\n')[:6]:
        print(f"   {line}")
    print("   ---")

print("\n" + "=" * 50)
print("ALL TESTS PASSED ✓")
print("=" * 50)
print("\nNote: ProtonLaunch is now a simplified install-only tool.")
print("No game library persistence - just install and add to Steam!")
