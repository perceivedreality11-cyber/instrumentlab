# Development

Run from the repository root with Python 3.10+:

```bash
python -m unittest discover -s tests -v
python -m instrumentlab --headless --seconds 1 --csv data/check.csv
python -m compileall -q instrumentlab
```

With an available desktop and Tk support:

```bash
python tools/gui_smoke.py
```

To refresh the actual application screenshot on Windows, install Pillow in your development environment and run `python tools/gui_smoke.py --capture`. Pillow is only a documentation tool, not an application runtime dependency.

Keep drivers independent of Tk. Add numerical reference tests when changing DSP. Use actual loopback sockets for protocol changes. Do not commit recordings or machine-specific paths. Record real hardware verification separately from simulation results.
