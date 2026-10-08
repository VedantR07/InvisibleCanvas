# brain.md — Invisible Canvas / Smart Interactive Surface

> **Persistent engineering memory.** Read this whole file before starting any phase or any substantial change.
> It is the source of truth for scope, architecture, decisions and status.
> Update it at the end of every phase and whenever a decision changes.
> Git records *what* changed; brain.md records *why*, the decisions, the measurements and the current state. Git does not replace it.

| | |
|---|---|
| Last updated | 2026-10-08 |
| Current phase | **Phase 1A** (first half of P0 Foundation). **Software complete and tested without the projector/Brio; hardware acceptance run (A1–A8) NOT done yet.** Phase 1A is not complete until it is. |
| Next action | Connect the Brio 100 + WZATCO projector, then follow the runbook in §9.8 and record the numbers in §13.2 |

---

## 0. Working rules

1. Read `brain.md` completely before beginning any phase.
2. Build phase by phase. Never implement a later phase's features early. No AI, OCR, 3D, presentation mode, advanced gestures or the full canvas before their phase.
3. Before any substantial change, state the proposed architecture and files, then get approval.
4. Install only what the current phase needs. Every dependency needs a stated reason (§9.4 or the matching phase plan).
5. Never claim success without testing on the real hardware. Record the measured numbers in the test log (§13.2).
6. **Never tune the system just to satisfy a target.** Report the real numbers, even when they miss.
7. Follow the priority order in §7. Never trade reliability for features.
8. Commit each meaningful phase or milestone to git.
9. At the end of each phase, update the header, decisions (§10), risks (§11), open questions (§12) and status/test log (§13).

---

## 1. Project

Invisible Canvas is a **vision-based spatial interaction platform**. It turns an ordinary physical projection surface into an intelligent, interactive digital workspace without a dedicated touchscreen.

It must **not** feel like "projector + webcam + drawing app". The central technology is the **Adaptive Spatial Interaction Engine**. Four applications are built on top of it:

1. Interactive Canvas
2. Context-aware AI
3. Interactive 3D Visualization
4. Presentation / Learning Mode

### Device roles

| Device | Role |
|---|---|
| Projector | **Output device**: displays the digital canvas on the surface |
| USB webcam | **Input device**: observes the projected surface and the user's hand/finger |
| Laptop | **Main processing unit**: everything below |
| Physical surface | Where projection and interaction happen |

The laptop performs: computer vision · hand/fingertip tracking · marker fallback tracking · surface calibration · perspective transformation · coordinate mapping · gesture interpretation · interaction state management · canvas rendering · AI processing · (future) 3D visualization · (future) presentation interaction.

**No Raspberry Pi** in the initial implementation. Everything runs on the laptop.

---

## 2. Hardware and environment

### 2.1 Hardware

| Item | Details |
|---|---|
| Laptop | Main processing machine (details in §2.2) |
| Projector | **WZATCO Yuva Go** smart projector: Android-based, native **1280×720**, HDMI input, USB, auto keystone. Used **mainly as an external HDMI display** for this project. |
| Camera | **Logitech Brio 100** USB webcam, the initial external camera (D14). Do not buy another camera yet. Its real resolution, FPS, latency and behavior are **measured experimentally** (§13.2), not taken from the spec sheet. |
| Surface | **Vertical**, flat projection surface: wall, whiteboard or canvas (D13) |

### 2.2 Environment snapshot (inspected 2026-10-08)

| Item | Found |
|---|---|
| OS | Windows 11 Home Single Language, build 10.0.26200 |
| Laptop display | Internal panel TL160ADMP37 (EDID id `TMA2076`), 2560×1600 @ 60 Hz, **Windows scaling 150 %** (logical 1707×1067) |
| GPUs | Intel UHD Graphics (drives the internal panel) + NVIDIA GeForce RTX 5070 Laptop GPU |
| Virtual display driver | "Meta Virtual Monitor" is installed and may appear as an extra display |
| Cameras | Built-in "ACER FHD User Facing" (USB VID 322E, PID 2515). The Brio 100 was not connected at inspection time. |
| Projector | Not connected at inspection time |
| Python | Not installed at first inspection (only Microsoft Store stubs). **Installed 2026-10-08:** Python 3.12.10 per-user via winget (`%LOCALAPPDATA%\Programs\Python\Python312`) with project `.venv`. Locked: numpy 2.5.3, opencv-python 4.14.0.94, pytest 9.1.1 (`requirements.lock`). The OpenCV build has Win32 UI, DirectShow, MSMF, `cv2.aruco` and `pollKey`. |
| DirectShow cameras | Index 0 "ACER FHD User Facing"; **indices 1–4 are virtual "Meta Quest 3/3S/2/Pro" cameras** (Meta software). The Brio's index will depend on enumeration order, so cameras are selected by name. |
| Laptop panel modes | Runs at 60 Hz; the panel offers up to 2560×1600 @ 180 Hz |
| Other tools | git 2.55 (identity VedantR07), winget, no Node.js |

What this means:
- The process must be **per-monitor DPI aware**. Otherwise the 150 % scaling makes window placement and size on the projector wrong.
- The projector must be identified **explicitly** by its EDID name and output type, never by display index. The Meta virtual monitor may also be listed.
- The built-in camera is enough to develop and test the camera pipeline. It cannot see the projection, so calibration needs the Brio 100.
- The camera is also chosen by name ("brio"), never by assumed index.

### 2.3 Physical setup requirements

**Projector**
- Connect over HDMI and set Windows to **Extend** mode (Win+P), not Duplicate.
- Set the projector display to **1280×720** and **100 %** scaling, so one canvas pixel is one projector pixel. If Windows picks 1920×1080, change it. Otherwise the projector rescales the image and thin lines blur.
- Disable overscan/zoom in the projector menu. The 1-px border of the test pattern must be fully visible.
- **Do not rely on keystone for the coordinate mapping** (D13). Physically align the projector square to the surface as much as practical, then turn auto keystone **off**.
  - The homography absorbs any remaining perspective.
  - Any keystone change after calibration silently invalidates the calibration.
  - Digital keystone also costs resolution.
- Turn off image enhancement and motion smoothing. If there is a game/low-latency mode, turn it on (it reduces input lag).

**Camera (Brio 100): what to measure**
- Resolution/FPS modes it really delivers (MJPG vs YUY2; does 60 fps exist?).
- Whether exposure, white balance and focus can be locked to manual. Auto exposure reacts to the changing projected content and makes detection unstable.
- Field of view and lens distortion (visible in the validation error map).
- Display→camera latency.
- Mount rigidly: tripod thread or a solid clip.

**Surface**
- **Vertical**: a flat wall, whiteboard or canvas.
- Matte and non-glossy. Whiteboards are glossy, so watch for hot spots that saturate the camera; a matte canvas or wall is preferred.
- **Flat and rigid.** The homography assumes a plane, so any bending or curling breaks the mapping.
- 16:9 aspect ratio, matching the projector.

**Mounting**
- Camera, projector and surface must not move relative to each other after calibration. Any movement requires recalibration.
- The camera must see the whole projected area with a margin on every side.
- Mount the camera close to the projector, viewing the surface as frontally as possible. This gives more resolution and less fingertip parallax.
- A small offset between camera and projector axes may later help shadow-based touch detection (§6).
- Once the setup is built, record the measured geometry in §13.3: throw distance, image size, camera position.

---

## 3. Architecture

### 3.1 Pipeline

```
Camera
  ↓
Camera Manager
  ↓
Vision Engine
  ↓
Hand / Fingertip / Marker Detection
  ↓
Tracking Engine
  ↓
Surface Calibration
  ↓
Coordinate Mapper
  ↓
Interaction Engine
  ↓
Application Layer
  ↓
Canvas / AI / 3D / Presentation
  ↓
Rendering
  ↓
Projector
  ↓
Physical Surface
```

**The most important engineering problem** is converting physical interaction coordinates seen by the camera into projected-canvas coordinates accurately. The solution is calibration plus a projective (homography) transform (§4).

### 3.2 Pipeline stage → package

| Stage | Package under `src/invisible_canvas/` | Phase |
|---|---|---|
| Camera Manager | `camera/` | P0 |
| Vision Engine; hand/fingertip/marker detection | `vision/` | P1 |
| Tracking Engine (filtering, smoothing, identity) | `tracking/` | P1 |
| Surface Calibration | `calibration/` (math in `geometry/`) | P0 |
| Coordinate Mapper | `mapping/` | P0 |
| Interaction Engine (state machine) | `interaction/` | P1 |
| Application: canvas model | `canvas/` | P1–P2 |
| Application: AI, OCR | `ai/` | P2 |
| Application: 3D, presentation | `viz3d/`, `presentation/` | P3 |
| Rendering, projector output, operator window | `display/` (renderer may move to `render/` later) | P0 (basic) |
| Diagnostics and test commands | `tools/` | P0+ |

Packages for later phases are **not created** until that phase starts.

### 3.3 Runtime model (Phase 1)

- **Camera thread.** A capture thread keeps only the **latest** frame, stamped with a monotonic timestamp (`time.perf_counter()`). Stale frames are dropped, never queued, so latency cannot build up.
  - **Every `VideoCapture` call runs on this thread.** Property changes and the driver settings dialog are queued to it, because `VideoCapture` is not thread-safe.
- **Main thread.** Runs the GUI loop for both the operator window (laptop screen) and the projector window. OpenCV HighGUI must be pumped with `waitKey` on a single thread.
- **Vision worker (P1).** P1 may add a separate vision worker thread. Decide this from measurements.
- **Pure core.** Geometry, target layout, metrics, mapping, config and projector selection have no I/O and no GUI, so they are unit-tested without hardware.
- **Pixel convention.** Pixel centres are at integer coordinates in both camera and projector space (OpenCV convention). Calibration targets sit on integer pixels and are drawn with odd line widths, so they are symmetric about the target pixel.

---

## 4. Coordinate systems and mapping

| Space | Symbol | Meaning | Phase |
|---|---|---|---|
| Camera | **C** | Pixel (u, v) in the camera frame, origin top-left | P0 |
| Projector / display | **P** | Pixel (x, y) in the 1280×720 image sent to the projector, origin top-left | P0 |
| Logical canvas | **L** | Document coordinates of canvas content; can be larger than the display (pan/zoom) | P1–P2 |
| Reach region | **R** | The part of the projected area the user can physically reach | P1–P2 |

Mapping chain:

```
C ──H (homography from calibration)──▶ P ──V (view / reach transform)──▶ L
```

- **H** is a 3×3 matrix from camera pixels to projector pixels. It is estimated with a normalized DLT (Hartley normalization + SVD) in pure numpy.
  - Four point pairs give an exact solution.
  - More than four give a least-squares fit (Phase 1B).
- **Validation needs held-out points.** A four-point fit has no redundancy, so it cannot report its own error. Accuracy **must** be measured on points that were not used for calibration (§9.6).
- **Assumptions:**
  1. The surface is planar.
  2. Lens distortion is small (pinhole camera model).
  3. Camera, projector and surface are fixed.

  Validation tests assumption 2. If the error grows toward the frame edges, add camera intrinsic calibration (`cv2.calibrateCamera`) and undistort points before applying H.
- **H is invertible.** P→C uses H⁻¹, for example to draw the projected-area outline on the camera preview.
- **Teacher Reach (physical canvas ≠ logical canvas).** V maps a smaller reach region R (e.g. the lower part of the board) onto the whole logical canvas. A user who cannot reach the top can then still write anywhere. V is applied after H, so changing it never requires recalibration.
- **Fingertip parallax (P1).** H is exact only for points on the surface plane. A hovering fingertip seen off-axis appears shifted. Keep the camera close to the projector axis and account for this in touch detection.

---

## 5. Applications and features (product scope)

### 5.1 Interactive Canvas
Eventually supports: freehand drawing · writing · pen · eraser · color · brush thickness · lines · rectangles · circles · selection · undo · redo · clear · text where practical.

Content is stored as **structured objects/strokes** (point lists with style and timestamps), not only as a raster image. Selection, undo/redo, AI and re-rendering all depend on this.

### 5.2 Context-aware AI
The user selects written content. The system understands the selection and can:
summarize · explain · simplify · generate examples · generate questions · answer contextual questions · visualize concepts in 3D.

AI must be **contextual**: it works on the selection and the surrounding canvas. It is **not a generic chatbot**. Results appear in a contextual panel.

### 5.3 Interactive 3D Visualization (P3)
### 5.4 Presentation / Learning Mode (P3)

### 5.5 Special features
1. **Teacher Reach / Accessible Writing.** A teacher who cannot physically reach the top of the projection can still write into the full logical canvas. The physical interaction area can be smaller than the logical canvas (physical canvas ≠ logical canvas, §4).
2. **Free / Random Canvas Mode.** Users write freely anywhere, not restricted to lines.
3. **Selection.** Written content and canvas objects can be selected.
4. **AI Summary.** Selected text/content is sent to the AI, and the result appears in a contextual panel.

---

## 6. Interaction model (design intent; implemented in P1)

**Problem.** Do **not** simply detect the movement of every finger and draw. Other fingers move naturally and would cause accidental strokes. The system needs **explicit interaction states**.

Initial approach:

```
IDLE      (no hand)
  ↓
HOVER     (point: one designated fingertip, e.g. index tip, is tracked; cursor shown; no ink)
  ↓
INTENT    (explicit intent gesture)
  ↓
DRAWING   (track only the active fingertip; emit stroke points)
  ↓
RELEASE   (pen up)
  ↓
HOVER     (drawing stopped)
```

Principles:
- **One active fingertip** at a time; all other fingers are ignored.
- **Hysteresis and debounce** on every transition: N consecutive frames, separate enter/exit thresholds. Noise must not be able to start or stop a stroke.
- **Tracking loss** ends a stroke cleanly after a timeout. The cursor never jumps.
- **Smoothing:** filter the fingertip position with low lag (e.g. One Euro filter).
- **Reliability is more important than having many gestures.**

Intent-signal candidates (evaluate with measurements at the start of P1):
- pinch: thumb–index distance, normalized by hand size
- touch detection via the finger's shadow (needs a camera offset from the projector)
- dwell
- physical clicker, foot pedal or keyboard (the most reliable fallback)

**Marker mode** is the reliable fallback: e.g. a stylus with a printed ArUco marker or a distinct colored/LED tip. `cv2.aruco` has been part of the main `opencv-python` package since OpenCV 4.7, so this probably needs no new dependency (verify in P1).

**Hand-tracking candidate:** MediaPipe Hand Landmarker (21 landmarks per hand). Risk R11 applies.

---

## 7. Development principles (priority order; never reverse)

```
RELIABILITY → LOW LATENCY → ACCURACY → NATURAL INTERACTION → INTEGRATION → VISUAL POLISH → FEATURE EXPANSION
```

---

## 8. Roadmap

| Phase | Tier | Scope |
|---|---|---|
| **Phase 1A** | **P0 Foundation** | hardware diagnostics · camera capture · projector output · camera feed · surface setup · **manual** four-point calibration · homography · coordinate mapping · manual validation · unit tests |
| **Phase 1B** | **P0 Foundation** | **automatic** calibration: projected-dot detection, automatic four-point and N-point calibration, automatic validation; lens undistortion if 1A measurements need it. Manual assisted calibration stays as the fallback. |
| Phase 2 | P1 | tracking · interaction · cursor · drawing · erasing · undo/redo |
| Phase 3 | P2 | selection · structured canvas objects · OCR · AI |
| Phase 4 | P3 | 3D · presentation · advanced gestures · environmental robustness · performance optimization |
| Phase 5 | P4 | final integration · testing · benchmarking · demo optimization |

**Naming:** the brief's "Phase 1" success criterion (projector, camera, calibration, mapping) is the **P0 Foundation** tier. So Phase N = tier P(N−1), and Phase 1 is split into 1A and 1B. When in doubt, name the tier.

---

## 9. Phase 1 plan (P0 Foundation)

### 9.1 Success criterion (from the project brief)

> A projected canvas is displayed through the WZATCO projector, the webcam sees the projection area, the system performs four-point calibration, and a camera-space point can be accurately transformed into projected-canvas coordinates.

Phase 1A meets this criterion with **manual** calibration. Phase 1B automates it.

### 9.2 Scope

**Phase 1A (now)**
- hardware diagnostics, done before calibration:
  - all connected cameras with their resolution/FPS modes
  - all displays with their resolutions and refresh rates
  - explicit projector identification
- projector output: fullscreen canvas on the identified projector
- camera capture, live feed, display→camera latency measurement
- physical setup procedure for the vertical surface
- **manual** four-point calibration (operator clicks projected targets in the camera view)
- homography and C↔P coordinate mapping
- calibration persistence
- manual held-out validation and repeatability report
- unit tests

**Phase 1B (next)**
- projected-dot detection
- automatic four-point calibration
- optional N-point calibration
- automatic validation
- lens undistortion, only if the 1A numbers show edge error
- Manual assisted calibration **remains as the fallback**.

**Out of scope for all of Phase 1**
- hand/fingertip tracking, markers, gestures, interaction states
- drawing and the full canvas
- logical canvas / Teacher Reach (documented here only)
- OCR, AI, 3D, presentation
- the long-term renderer choice (D2)
- automatic recalibration and drift detection

### 9.3 Files

Paths are relative to `src/invisible_canvas/` unless stated otherwise.

**Phase 1A**

| File | Responsibility |
|---|---|
| `config/default.toml` (repo root) | Camera (name match, backend, resolution, fps, FOURCC), projector (name match, expected size), calibration (target inset, file location), validation (grid, thresholds), surface width in mm |
| `__main__.py` | CLI: `python -m invisible_canvas <command>` (argparse subcommands); enables DPI awareness before any window opens |
| `config.py` | Loads TOML (stdlib `tomllib`) into frozen dataclasses; rejects unknown keys; applies CLI overrides |
| `display/monitors.py` | Win32 via `ctypes`: per-monitor DPI awareness v2. Lists displays with GDI name, EDID friendly name and ID, output technology (HDMI/internal/virtual), bounds, resolution, refresh, DPI scale and available modes. Pure projector-selection function (§9.7). |
| `display/projector.py` | `ProjectorWindow`: borderless fullscreen window on the identified projector. Verifies that the window rectangle equals the monitor rectangle via Win32. Has a `--windowed` dev fallback. |
| `display/operator.py` | `OperatorWindow`: shows the camera frame on the laptop (scaled to fit, 1:1 when it fits), with overlays, status text, a zoom loupe, and mouse coordinates converted to camera pixels |
| `display/patterns.py` | Test pattern (1-px border, grid, 1-px line pairs, corner labels, resolution text); calibration targets; crosshair; dark canvas |
| `camera/directshow.py` | DirectShow device enumeration via `ctypes` COM: friendly name, device path, USB VID/PID, in the same order as OpenCV `CAP_DSHOW` indices |
| `camera/manager.py` | `CameraManager`: opens the camera by name (or index); requests **and verifies** the resolution/FOURCC/fps from real frames; runs the latest-frame thread; reports measured fps and frame age; queues property changes and the settings dialog to the capture thread |
| `camera/probe.py` | Diagnostics: tries each candidate mode, reads back what was negotiated, measures the fps actually delivered; reads camera properties without changing them |
| `geometry/homography.py` | Pure numpy: normalized DLT, apply (with points at infinity flagged), invert, quad validation (count, finite, distinct, convex/simple, min area), orientation check, reprojection errors |
| `calibration/targets.py` | Pure: positions of the four corner targets (inset) and of the held-out validation grid |
| `calibration/collect.py` | Interactive point collection, shared by calibrate and validate. The projector highlights one target; the operator clicks it in the live camera view with the loupe, nudges with the arrow keys, confirms or undoes. |
| `calibration/store.py` | `Calibration` record as versioned JSON (`data/calibration/current.json` + `history/`). Recomputes and checks H on load. Refuses camera/projector size mismatches. |
| `calibration/metrics.py` | Pure: accuracy statistics (mean, median, p95, max, mm), required/stretch pass levels, repeatability (mean/max corner variation) |
| `mapping/mapper.py` | `CoordinateMapper`: camera→projector and projector→camera for single points and batches, inside-canvas flag |
| `tools/devices.py` | `devices`: full hardware diagnostics. Prints the results and saves JSON to `data/reports/`. |
| `tools/projector_check.py` | `projector`: test pattern, white and black screens on the identified projector; window-rectangle verification |
| `tools/camera_check.py` | `camera`: live feed showing negotiated format, measured fps, frame age, saturation %, property readout; opens the driver settings dialog |
| `tools/latency.py` | `latency`: display→camera latency. Flashes the projector black→white and times when the camera sees it (median, p10, p90 over N trials). |
| `tools/calibrate.py` | `calibrate`: manual four-point calibration. Collect points → compute and validate H → overlay and live hover check → save. |
| `tools/validate.py` | `validate`: manual held-out grid accuracy test with report and error map. `repeatability`: corner variation across the last N calibrations. |
| `tools/map_demo.py` | `mapdemo`: hovering in the camera view projects a crosshair at the mapped point; clicking pins it |
| `tools/common.py` | Shared session: identify and open projector + camera + operator window, always cleaned up; JSON reports |
| `tests/test_*.py` | homography, targets/metrics, mapper/store, config, monitor selection/EDID/struct sizes, camera helpers, display (operator coordinate conversion, loupe sub-pixel clicks, target symmetry, pattern purity) |

All files above exist as of 2026-10-08 (Phase 1A software complete).

**Phase 1B (planned, not started):** `calibration/detect.py` (projected-dot detection) and `--auto` modes for `calibrate` and `validate`.

**Commands at the end of Phase 1A:**

```
python -m invisible_canvas devices
python -m invisible_canvas projector
python -m invisible_canvas camera
python -m invisible_canvas latency
python -m invisible_canvas calibrate
python -m invisible_canvas validate
python -m invisible_canvas repeatability
python -m invisible_canvas mapdemo
```

### 9.4 Dependencies (approved; complete list for Phase 1)

| Dependency | Kind | Why |
|---|---|---|
| Python **3.12.x** (64-bit) | System | Runtime. Installed per-user with `winget install -e --id Python.Python.3.12 --scope user`. Version 3.12 keeps MediaPipe (P1) available. |
| `.venv` | Project | Isolated project environment (`.venv/`, git-ignored) |
| `numpy` `>=2.0,<3` | Runtime | Point arrays and matrix math |
| `opencv-python` `>=4.10,<5` | Runtime | Camera capture (DirectShow/MSMF), HighGUI windows, image processing |
| `pytest` `>=8` | Dev only | Unit tests |

Everything else comes from the standard library: `tomllib`, `json`, `ctypes` (DPI awareness, displays, DirectShow enumeration), `threading`, `argparse`, `dataclasses`, `logging`.

Rules:
- Install **exactly one** OpenCV wheel. Never add `opencv-contrib-python` or `opencv-python-headless` alongside it: they ship conflicting `cv2` modules, and the headless build has no GUI.
- Pin the exact installed versions in `requirements.lock`.

**Deliberately not installed:**
- `mediapipe` (P1)
- PySide6 or pygame (D2)
- `screeninfo`, `pygrabber`, `comtypes` (replaced by `ctypes`)
- `scipy`
- any AI, OCR or 3D package

### 9.5 Implementation steps

| Step | Work | Needs | Check |
|---|---|---|---|
| 1A.0 | Install Python 3.12; create `.venv`; install deps; write `requirements.lock` | — | `import cv2, numpy` works; OpenCV build info lists a GUI backend and DSHOW/MSMF |
| 1A.1 | Hardware diagnostics: `devices` (displays + cameras) | Brio 100 + projector connected | All displays/cameras listed; projector identified by EDID/output type; results recorded in §13.2 |
| 1A.2 | `geometry/` + `calibration/targets.py`, `metrics.py` + tests | — | `pytest` passes |
| 1A.3 | `config.py`; `display/` (projector window, operator window, patterns); `projector` command | Projector | Fullscreen 1280×720 on the identified projector; window rectangle equals monitor rectangle; 1-px border visible; line pairs sharp |
| 1A.4 | `camera/manager.py`; `camera` and `latency` commands | Brio 100 (+ projector for latency) | Negotiated format; fps sustained for 60 s; frame age; exposure-lock behavior; display→camera latency recorded |
| 1A.5 | Physical setup per §2.3; record the geometry in §13.3 | All hardware | Camera sees the whole projected pattern with a margin; saturation checked |
| 1A.6 | `calibration/collect.py`, `store.py`; `calibrate` command + tests | All hardware | Calibration completes, overlay hugs the projection, result reloads after restart |
| 1A.7 | `mapping/mapper.py`; `mapdemo` + tests | All hardware | Crosshair lands on the hovered physical point |
| 1A.8 | `validate` and `repeatability`; acceptance run (§9.6); update brain.md; git commit | All hardware | Acceptance results recorded |

### 9.6 Phase 1A acceptance tests

Run these on the real setup: WZATCO projector + Brio 100 + vertical surface. **Record the actual numbers in §13.2, whether they pass or fail.**

| # | Test | Pass condition |
|---|---|---|
| A1 | Diagnostics | Every display is listed with resolution and refresh rate, and every camera with its measured modes. The projector is identified explicitly (EDID name/output type, not index). The report is saved. |
| A2 | Projector output | Fullscreen 1280×720 canvas on the identified projector; window rectangle equals monitor rectangle; full 1-px border visible; 1-px line pairs sharp; operator UI on the laptop |
| A3 | Camera feed | Brio 100 negotiated mode recorded; ≥ 25 fps sustained for 60 s at the chosen mode; display→camera latency measured (baseline; no threshold yet) |
| A4 | Coverage | The whole projected area is visible with a margin on every side; saturation of projected white recorded |
| A5 | Manual four-point calibration | Completes. Quad validation passes. The outline drawn via H⁻¹ matches the real projection. The calibration reloads after a restart, and a size mismatch is refused. |
| A6 | Repeatability | Three manual calibrations without touching the hardware. **Mean corner variation ≤ 2 camera px.** Max variation is reported too. |
| A7 | Mapping accuracy | Manual held-out grid (default 5×4, none of them calibration points), errors in projector px. **Required: mean ≤ 5 px and max ≤ 12 px. Stretch: mean ≤ 3 px and max ≤ 8 px.** Median, p95, mm and an error-map image are also reported. |
| A8 | Live mapping | In `mapdemo`, hover over the centre, the four corners and three stickers placed at random. Measure the offsets with a ruler and record them. |
| A9 | Unit tests | All `pytest` tests pass |

Metric definitions:
- **Mapping error.** For each held-out target with true projector position p and clicked camera position c, the error is ‖H(c) − p‖ in projector px.
  - In 1A, c is clicked by hand, so the error includes human click error.
  - 1B removes it with automatic detection.
- **Mean corner variation.** For N ≥ 3 calibrations, take each corner k's mean camera position m_k. The variation is the mean of ‖c_{k,r} − m_k‖ over all corners k and runs r.

The 1-camera-pixel repeatability idea from the first plan is **not** an acceptance criterion (D17).

### 9.7 Explicit device identification

**Projector.** Chosen in this order:
1. CLI `--display` (EDID name substring or GDI name such as `\\.\DISPLAY2`)
2. `projector.match` in the config
3. Otherwise automatic: the **single** active display that is not primary, uses a physical external connector (HDMI/DVI/DP/VGA) and is not virtual or indirect

If zero or several displays match, the command stops and lists them; it never guesses. The chosen display and the rule that chose it are always printed. After the first diagnostics run, `projector.match` is set to the projector's EDID name.

**Camera.** `camera.match` (case-insensitive substring of the DirectShow name, default `"brio"`) is resolved to an index at startup. If nothing or several devices match, the command stops and lists them.

### 9.8 Hardware session runbook (Phase 1A acceptance)

Prerequisites:
- Brio 100 on USB.
- Projector on HDMI; Windows display mode **Extend**.
- Projector display set to **1280×720 at 100 %** (Settings → Display).
- Projector auto keystone OFF and aligned physically (§2.3).

Activate the environment with `.venv\Scripts\activate`, then run:

| # | Command | Acceptance | What to do / record |
|---|---|---|---|
| 1 | `python -m invisible_canvas devices` | A1 | Projector identified by EDID name? Put that name into `[projector] match` in `config/default.toml`. Record the Brio's measured modes and fps. |
| 2 | `python -m invisible_canvas projector` | A2 | `window geometry: OK`? Is the 1-px border visible on all 4 sides of the wall? Do the stripe squares look sharp? SPACE shows white/black/dark screens. |
| 3 | `python -m invisible_canvas camera` | A3/A4 | Aim the camera so the whole projection is visible with margin. `s` opens the driver dialog: try locking exposure, white balance and focus, and record what the Brio allows. Project white (step 2) and check that saturation is about 0 %. |
| 4 | `python -m invisible_canvas camera --seconds 60` | A3 | Record mean fps, slowest 1-s window, longest gap. |
| 5 | Measure the projected image width in mm | — | Set `[surface] width_mm`; record the geometry in §13.3. |
| 6 | `python -m invisible_canvas calibrate` | A5 | Click the 4 targets (use the loupe), check that the review outline hugs the projection, save. Record the coverage printout. |
| 7 | `calibrate` two more times, touching nothing; then `python -m invisible_canvas repeatability` | A6 | Record mean/max corner variation. |
| 8 | `python -m invisible_canvas validate` | A7 | 20 held-out clicks. Record mean/median/p95/max, edge vs interior, PASS/FAIL. Keep the error-map PNG. |
| 9 | `python -m invisible_canvas mapdemo` | A8 | Hover at the centre, 4 corners and 3 stickers; measure the offsets with a ruler. |
| 10 | `python -m invisible_canvas latency` | A3 | Record median/p10/p90 display→camera latency. |
| 11 | `python -m pytest` | A9 | All tests pass |

Reports land in `data/reports/` (JSON, plus a PNG for validation). Copy the numbers into §13.2. **Never adjust thresholds to make a run pass.**

Restart check for A5: close everything and run `mapdemo` again. It must load the saved calibration. Changing `[camera] width/height` must make it refuse.

---

## 10. Decisions log

| ID | Date | Decision | Rationale | Revisit |
|---|---|---|---|---|
| D1 | 2026-10-08 | Python 3.12 | OpenCV/MediaPipe/AI ecosystem; MediaPipe wheels lag behind new Python versions | At the start of P1, check MediaPipe wheel support |
| D2 | 2026-10-08 | Phase 1 rendering: OpenCV HighGUI fullscreen window behind a small `ProjectorWindow` interface | No extra dependency; enough for patterns and crosshairs; low latency | Before P1 drawing / P2 UI: compare PySide6 (Qt), pygame (SDL2), web front-end (3D) |
| D3 | 2026-10-08 | Calibration is a camera→projector homography from four point pairs, estimated with a normalized DLT in numpy | Planar surface; brief specifies four-point calibration; pure, testable, double precision | 1B adds N-point; lens undistortion if A7 shows edge error |
| D4 | 2026-10-08 | Accuracy is measured on **held-out** points, separate from calibration points | A four-point fit is exact and cannot show its own error | — |
| D5 | 2026-10-08 | Calibration stored as versioned JSON in `data/calibration/` (git-ignored), with history | Human-readable; specific to this machine; history enables the repeatability test | — |
| D6 | 2026-10-08 | Config in TOML via stdlib `tomllib`; unknown keys rejected | No dependency; typos fail loudly | — |
| D7 | 2026-10-08 | Displays, DPI awareness and DirectShow enumeration via `ctypes` | 150 % scaling breaks placement otherwise; real device names without new dependencies | — |
| D8 | 2026-10-08 | DirectShow is the default camera backend on Windows (MSMF selectable) | Usually more reliable control of resolution, MJPG and exposure | After Brio 100 measurements |
| D9 | 2026-10-08 | Capture thread keeps only the latest frame; all `VideoCapture` calls happen on that thread | Low latency; `VideoCapture` is not thread-safe | — |
| D10 | 2026-10-08 | `src/` layout, `pyproject.toml`, `.venv` | Standard, isolated, editable install | — |
| D11 | 2026-10-08 | Phase N = tier P(N−1) | The brief's Phase 1 criterion matches P0 | — |
| D12 | 2026-10-08 | **Approved:** Python 3.12 installed per-user via winget; project `.venv`; Phase 1 deps = numpy, opencv-python, pytest only | User decision | — |
| D13 | 2026-10-08 | **Approved:** vertical, flat surface (wall/whiteboard/canvas). Keystone is not relied on for mapping; the projector is aligned physically. | User decision; keystone can change and silently invalidate calibration | — |
| D14 | 2026-10-08 | **Approved:** Logitech Brio 100 is the initial camera. No new purchase. Capabilities are measured, not assumed. | User decision | If 1A measurements show it cannot meet targets |
| D15 | 2026-10-08 | **Approved:** git initialized; commit each meaningful milestone; brain.md stays the engineering memory | User decision | — |
| D16 | 2026-10-08 | **Approved:** Phase 1 split. **1A:** manual four-point calibration first. **1B:** automatic calibration. Manual assisted calibration stays as a permanent fallback. | Reliability first; manual mode works without any detection | — |
| D17 | 2026-10-08 | **Approved targets.** Required: mean ≤ 5 px, max ≤ 12 px. Stretch: mean ≤ 3 px, max ≤ 8 px. Repeatability: mean corner variation ≤ 2 camera px. A 1-px repeatability rule is **not** a hard criterion. Never tune just to meet a target. | User decision | After 1A/1B measurements |
| D18 | 2026-10-08 | **Approved:** hardware diagnostics (all displays, resolutions, refresh rates; all cameras, resolutions/FPS; explicit projector identification) come before calibration | User decision; measure before building | — |
| D19 | 2026-10-08 | Phase 1A validation uses manual clicks on held-out targets. Automatic validation comes with 1B. | Keeps 1A free of detection code while still measuring accuracy | — |
| D20 | 2026-10-08 | The process requests 1 ms Windows timer resolution (`timeBeginPeriod(1)`) at startup | `cv2.waitKey(1)` otherwise sleeps a full ~15.6 ms tick; measured: waitKey dropped to ~2 ms | — |
| D21 | 2026-10-08 | Per-frame image work in GUI loops uses OpenCV ops, not numpy axis reductions | Measured: `np.max(img, axis=2)` on 1080p took 30 ms (slower than one frame) vs 5 ms with `cv2.split`/`cv2.max`; GUI frame age fell from 16.8 ms to 0.5 ms | Revisit with the P1 latency budget |
| D22 | 2026-10-08 | Definitions. **Sustained fps** = the slowest full 1-second window over the run. **Display→camera latency** = time from submitting a white frame to the first camera frame whose projected area is brighter than halfway between the black and white levels. | Makes A3 measurable and repeatable | — |
| D23 | 2026-10-08 | Calibration targets are exactly symmetric about their pixel; the ring is mirrored because `cv2.circle` is rasterized 0.065 px off-centre | No systematic bias in clicked or (1B) detected centres | — |

---

## 11. Risks and known issues

| ID | Risk | Mitigation | Status |
|---|---|---|---|
| R1 | Python not installed | Step 1A.0 (winget per-user) | Resolved 2026-10-08 |
| R2 | Camera choice | Brio 100 chosen (D14); measure it | Resolved |
| R3 | Projector auto keystone or auto focus re-triggers and invalidates the calibration | Align physically, keystone off (D13); recalibrate after any change; drift detection (P3) | Open |
| R4 | Input lag and image processing in the Android projector | Game mode on, enhancements off; `latency` measures it | Open |
| R5 | 150 % Windows scaling distorts window coordinates | Per-monitor DPI awareness (D7); projector display at 100 % | Planned |
| R6 | Meta Virtual Monitor is listed as a display | Explicit projector identification (§9.7); virtual displays excluded | Planned |
| R7 | Webcam auto exposure, white balance or focus drift as projected content changes | Lock via config/driver dialog if the Brio 100 allows it; measure | Open |
| R8 | Lens distortion causes error near the edges | A7 error map shows it; 1B adds undistortion if needed | Open |
| R9 | Surface not flat/rigid, or a glossy whiteboard creates hot spots | Rigid, flat, matte surface; check saturation | Open |
| R10 | Camera, projector or surface moves after calibration | Rigid mounts; recalibrate; drift detection (P3) | Open |
| R11 | Projected light on the hand degrades hand detection | Evaluate in P1; darker canvas themes; marker fallback | P1 |
| R12 | Fingertip hover parallax | Camera near the projector axis; touch-detection design in P1 | P1 |
| R13 | Hybrid graphics: the HDMI port may be wired to the NVIDIA GPU | Usually transparent; check first if the projector display misbehaves | Watch |
| R14 | Unknown Brio 100 limits (modes, 60 fps support, focus type, exposure-lock support) | Diagnostics (1A.1) and `camera` (1A.4) measure them | Open |
| R15 | Manual click error inflates the 1A accuracy numbers | Loupe + arrow-key nudging; 1B automatic validation separates mapping error from click error | Open |
| R16 | Four virtual Meta Quest DirectShow cameras shift device indices | Name-based camera selection (§9.7); virtual cameras are not probed by default | Mitigated |
| R17 | DirectShow quirks: each open takes about 2 s; the driver-reported FOURCC is not reliable (the built-in camera reports YUY2 at 1080p30 even when MJPG is requested, whatever the set order) | Trust only measured frame size and fps; open the camera once per session | Open |
| R18 | GUI loop work eats the latency budget (one slow per-frame op, 30 ms, doubled frame age) | D21; profile stage by stage before optimizing; P1 must budget the main loop | Watch |
| R19 | Fullscreen geometry verified only on the laptop panel so far, not on the projector | Step 2 of the §9.8 runbook | Open |

---

## 12. Open questions

1. What is the projector's EDID name? It is filled in after the first diagnostics run with the projector connected and goes into `projector.match`.
2. Which Brio 100 mode to use for Phase 1: 1920×1080 or 1280×720? Decide from the measured fps and latency (default for now: 1920×1080 MJPG @ 30).
3. Physical projected image width in mm, needed to report errors in mm (`surface.width_mm`). Measure during step 1A.5.
4. (P2) Classic OCR, or a multimodal model reading a rendered image of the selected strokes? Which AI provider/model?

Resolved on 2026-10-08: Python install (D12), surface orientation (D13), camera (D14), git (D15), accuracy thresholds (D17).

---

## 13. Status

### 13.1 Changelog
- **2026-10-08**
  - Project initialized: environment inspected (§2.2); created brain.md, README.md, pyproject.toml, .gitignore and the package skeleton; Phase 1 plan written.
  - User approved the decisions recorded as D12–D18.
  - Phase 1 split into 1A/1B.
  - Git initialized.
  - Phase 1A started.

  - Step 1A.0 done: Python 3.12.10, `.venv`, deps installed and locked.
  - Step 1A.1 tooling done: `devices` command (`display/monitors.py`, `camera/directshow.py`, `camera/probe.py`), `config.py`, CLI, unit tests.
  - Steps 1A.2–1A.8 software done:
    - geometry, targets, metrics, mapper and store
    - Camera Manager
    - projector and operator windows, patterns
    - interactive point collection
    - commands `projector`, `camera`, `latency`, `calibrate`, `validate`, `repeatability`, `mapdemo`
  - Tested without the projector and Brio (see the test log). **The hardware acceptance run is pending.**

### 13.2 Test log

**Phase 1A acceptance scoreboard** (update after the hardware session)

| # | Test | Status | Result |
|---|---|---|---|
| A1 | Diagnostics | Partial | Tool verified on the laptop display and built-in camera; **rerun with the Brio + projector** |
| A2 | Projector output | Pending | Fullscreen geometry verification works on the laptop panel (window = display rectangle exactly); not yet on the projector |
| A3 | Camera feed + latency | Pending | Built-in camera: 30.1 fps, slowest second 30 frames. Brio not measured yet. |
| A4 | Coverage | Pending | — |
| A5 | Manual calibration | Pending | Flow verified end to end with synthetic clicks (below) |
| A6 | Repeatability (≤ 2 camera px) | Pending | Computation verified (0.94 px for synthetic ±1 px clicks = 2√2/3, exact) |
| A7 | Accuracy (required 5/12 px, stretch 3/8 px) | Pending | Pipeline verified: perfect clicks give 0.41 px mean (pure pixel rounding) |
| A8 | Live mapping (ruler) | Pending | — |
| A9 | Unit tests | **PASS** | 83 passed |

**2026-10-08: Phase 1A software verification (no projector, no Brio)**
- Unit tests: **83 passed**. They cover homography (incl. OpenCV cross-check and degenerate cases), targets, metrics, mapper, store integrity, config, projector selection, Win32 struct sizes, operator coordinate conversion and loupe sub-pixel clicks, target symmetry and pattern purity.
- CLI error paths: missing projector, missing Brio and missing calibration each give a clear message with exit code 2.
- `projector --display DISPLAY1` (laptop panel used as a stand-in): fullscreen window rect (0,0,2560,1600) = display rect, image area 2560×1600 = canvas, so geometry is **verified**. The 1280×720 expectation warning fired correctly.
- `camera --camera acer --seconds 6`: 30.1 fps, slowest 1-s window 30 frames, 0 failed reads.
  - GUI frame age measured **16.8 ms → 0.48 ms** after D20/D21 (the 30 ms numpy saturation op was the cause).
  - Headless consumer wake-up: 0.3 ms.
- End-to-end GUI run: a scratch harness posted real Win32 mouse and key messages to the operator window (windowed projector, built-in camera, temporary data dir).
  - `calibrate` ×3 saved correctly; review and save worked.
  - `repeatability` reported 0.94 px mean and 1.41 px max for clicks at 0/+1/−1 px, exactly as expected.
  - `validate` with clicks at the positions predicted by the saved calibration: mean 0.41 px, max 0.72 px. That is integer-click rounding only, so **no systematic error in the target → click → H → mapping chain**.
  - `mapdemo`: pins and report OK.
  - Every exit code was 0.
- **Not done (needs hardware):** everything marked Pending above.

**2026-10-08: diagnostics dry run (Brio 100 and projector NOT connected yet)**
- Command: `python -m invisible_canvas devices` (50 s; report `data/reports/devices-20261008-195215.json`)
- Displays: one, `\\.\DISPLAY1` TL160ADMP37 [TMA2076], internal, primary, 2560×1600 @ 60.002 Hz, 32 bpp, 150 %, 156 modes. DPI awareness: per-monitor.
  - Win32 struct sizes match the SDK.
  - The EDID id decodes to TMA2076, which matches WMI.
- Projector: correctly **not identified**; the only display is the internal primary.
- Cameras (DirectShow): [0] ACER FHD User Facing (usb 322e:2515); [1]–[4] Meta Quest virtual cameras. Selection `"brio"` → correctly not found.
- Built-in camera, measured:
  - **Every mode delivers about 30 fps.** 60 fps requests fall back to 30. 1920×1080, 1280×720 and 640×480 are all available. The driver default is 640×480.
  - Each DirectShow open takes 1.7–2.4 s.
  - Readable properties: EXPOSURE=−6 (≈1/64 s), AUTO_WB=1, WB_TEMPERATURE=4500. FOCUS, AUTOFOCUS and AUTO_EXPOSURE are not readable (−1).
- Unit tests: 28 passed.
- **Still needed for A1:** rerun with the Brio 100 and the projector connected.

### 13.3 Measured setup geometry
_Not measured yet (step 1A.5)._
