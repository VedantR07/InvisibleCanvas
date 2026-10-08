# Invisible Canvas

A vision-based spatial interaction platform. A laptop, a USB webcam and a projector turn an ordinary surface into an interactive digital workspace, with no touchscreen.

**Start with [brain.md](brain.md).** It holds the project's architecture, decisions, roadmap, current phase and test results.

## Setup (Windows)

Requires Python 3.12 (64-bit).

```
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -e .[dev]
```

## Layout

```
src/invisible_canvas/   application package
tests/                  unit tests
config/                 configuration (added in Phase 1)
data/                   runtime output: calibration, reports (not committed)
```
