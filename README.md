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

Exact versions are in `requirements.lock` (`pip install -r requirements.lock`). The only OpenCV wheel is
`opencv-contrib-python` (MediaPipe needs it); never install `opencv-python` next to it.

The fingertip cursor (Phase 1D) also needs the MediaPipe hand model, downloaded once into `models/`
(not committed; its SHA-256 is checked when it is loaded, see brain.md D33):

```
mkdir models
curl.exe -L -o models\hand_landmarker.task https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task
```

## Commands

```
python -m invisible_canvas devices        # hardware diagnostics: displays, projector, cameras
python -m invisible_canvas projector      # alignment pattern on the projector
python -m invisible_canvas camera         # live feed, fps, saturation; --preview: large view; --seconds 60: report
python -m invisible_canvas latency        # display -> camera latency
python -m invisible_canvas calibrate      # automatic four-point calibration (--manual: click the corners)
python -m invisible_canvas validate       # held-out accuracy test, automatic (--manual: click the targets)
python -m invisible_canvas repeatability  # corner variation over recent calibrations of one method
python -m invisible_canvas mapdemo        # hover in the camera view -> crosshair on the surface
python -m invisible_canvas cursor         # index-fingertip cursor on the projection (--accuracy: 9-target test)
python -m invisible_canvas detect         # cross-detector diagnostic (read-only)
python -m invisible_canvas setupcheck     # repeated automatic setup checks (read-only)
python -m invisible_canvas gestures       # Phase 2: guided recording, pointing vs not (G1'; --angles: G1'',
                                          #          --video: save the camera video for replay; --busy --light ab: G8)
python -m invisible_canvas draw           # Phase 2: index finger = use the tool (pen / eraser / move),
                                          #          open hand or fist = cursor; hold on a button 1 s to press;
                                          #          a stroke stops at the toolbar; a slashed ring = not drawing:
                                          #          open the hand, then point again (D56); if the projector or
                                          #          camera is moved, it recalibrates by itself (D58: keep clear)
                                          #          --light: light the hand white, ring cursor (D50, off by default)
python -m invisible_canvas replay DIR     # Phase 2: replay a `gestures --video` recording offline (D48)
python -m invisible_canvas draw          # with the AI (on by default, D57; `draw --no-ai` for a session
                                          #          without it): SELECT a loop around writing, AI button -> the AI
                                          #          summarizes / explains / ... / explores the topic (EXPLORE:
                                          #          background, key facts, a connected concept; D54).
                                          #          Free and offline by default:
                                          #          Ollama + `ollama pull qwen3-vl:8b-instruct` (D52). Optional paid
                                          #          backend: [ai] backend = "claude" + `pip install -e .[ai]`.
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
