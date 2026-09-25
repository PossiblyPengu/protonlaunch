#!/bin/bash
# Build the single-file app into bin/ and write bin/latest.json, which get.sh and the in-app
# updater read. Usage: scripts/publish_bin.sh ["What's new, one line"]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
NOTES="${1:-}"
VERSION="$(python3 -c 'import protonlaunch; print(protonlaunch.__version__)')"

python3 -m PyInstaller --noconfirm --clean --onefile --windowed --strip --name protonlaunch \
  --paths . protonlaunch/__main__.py
cp dist/protonlaunch bin/protonlaunch-linux-x86_64
(cd bin && sha256sum protonlaunch-linux-x86_64 > protonlaunch-linux-x86_64.sha256)
SHA="$(cut -d' ' -f1 bin/protonlaunch-linux-x86_64.sha256)"
python3 - "$VERSION" "$SHA" "$NOTES" > bin/latest.json <<'PY'
import json, sys
version, sha, notes = sys.argv[1:4]
print(json.dumps({"version": version, "sha256": sha, "notes": notes}, indent=2))
PY
echo "bin/ now holds ProtonLaunch $VERSION ($SHA)"
