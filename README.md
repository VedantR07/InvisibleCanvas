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

## Commands (Phase 1A)

```
python -m invisible_canvas devices        # hardware diagnostics: displays, projector, cameras
python -m invisible_canvas projector      # alignment pattern on the projector
python -m invisible_canvas camera         # live feed, fps, saturation; --seconds 60 for a report
python -m invisible_canvas latency        # display -> camera latency
python -m invisible_canvas calibrate      # manual four-point calibration
python -m invisible_canvas repeatability  # corner variation over recent calibrations
python -m invisible_canvas validate       # held-out accuracy test
python -m invisible_canvas mapdemo        # hover in the camera view -> crosshair on the surface
python -m pytest                          # unit tests
```

The order of the hardware acceptance session is in brain.md §9.8.

## Layout

```
src/invisible_canvas/   application package
tests/                  unit tests
config/                 configuration (added in Phase 1)
data/                   runtime output: calibration, reports (not committed)
```
