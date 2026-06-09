# ProtonLaunch

A streamlined Windows game installer for Steam Deck and Linux — search store metadata, configure Proton, run installers, and add games to your Steam library.

See [protonlaunch/README.md](protonlaunch/README.md) for features, requirements, install steps, and usage.

## Quick start

```bash
pip install -r requirements.txt
python3 -m protonlaunch.protonlaunch
```

## Develop / test

```bash
export PYTHONPATH=.
pip install -r requirements.txt
PROTONLAUNCH_SKIP_NETWORK=1 python3 test_comprehensive.py
python3 -m unittest test_helpers_unit.py -v
QT_QPA_PLATFORM=offscreen python3 scripts/wsl_headless_smoke.py
```

## License

MIT — see [LICENSE](LICENSE).
