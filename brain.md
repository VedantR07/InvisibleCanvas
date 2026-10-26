# brain.md — Invisible Canvas / Smart Interactive Surface

> **Persistent engineering memory.** Read this whole file before starting any phase or any substantial change.
> It is the source of truth for scope, architecture, decisions and status.
> Update it at the end of every phase and whenever a decision changes.
> Git records *what* changed; brain.md records *why*, the decisions, the measurements and the current state. Git does not replace it.

| | |
|---|---|
| Last updated | 2026-10-24 |
| Current phase | **Phase 2 (P1, drawing with hand gestures): software complete (504 tests); hardware acceptance as of 2026-10-23 (§9.10, §13.2):** G1″ multi-angle pointing **PASS** (20:43 dark room; 21:30 room light); G2 no accidental ink **PASS** (runs 3 and 4); G3 drawing **PASS** (run 4, and run 5 clean after the R32 fix); G4′ partial erase **PASS**; G5′ presses **measured reliable, not formally passed** (32 presses over 3 runs, 0 wrong, 0 missed; the 20-press protocol was never followed as written); G5′ MOVE drags **not run**; G6 responsiveness **not passed** (processing 41.7–55.9 fps ≥ 30; pipeline p95 32.0–40.5 ms over whole runs, 24.3–34.9 ms over hand frames; the slow frames are the hand search, D40); G7 undo/redo: unit tests pass, UNDO/REDO used live in G5′ runs 2–3, the 5 live round trips not run. Changes during acceptance: D46 one gesture + toolbar, D47 keep-drawing band, D48 multi-angle pointing, D49 pen-lift delay, R32 fix; setup requirement: one room light on. **2026-10-21: Kreo re-validation (§9.9) done except B2 re-run and A8. Foundation on the Kreo: A1, A3 (60 fps; latency 262 ms), A5, A6 (0.04 px), A7 (1.05 / 2.54 px on 10-19; 1.19 / 2.09 px after the 10-21 recalibration) PASS; B1, B3, B4 PASS. Live fingertip cursor works on the Kreo: 97 % of saved frames with a hand tracked, 0 false positives, 54 fps processing, 13.8 ms pipeline; the cursor trails a moving finger by the ~0.28 s end-to-end latency (R4).** Phase 1D accuracy criterion still undecided (open question 12). **Camera changed (D41, 2026-10-17): Kreo Owl 4K Pro replaces the Brio 100. Every hardware result below was measured with the Brio and must be re-measured with the Kreo (§9.9) before it counts again.** **Phase 1D: index-fingertip cursor, in progress, NOT passed.** D39 (2026-10-12, evening): automatic calibration recovery after a moved setup (`recalibrate`; `cursor` recovers on its own when its setup check refuses): a replacement is built from the corners just detected and saved only after the held-out check target, the 20-target held-out validation (A7 required limits) and a confirming setup check; verified offline (410 tests); first hardware use 2026-10-12 20:13: `cursor` recovered a 63.25-px move automatically (check target 0.83 px, validation mean 0.62 / max 1.28 px, confirmation 0.10 px); the other D39 hardware reports not yet reviewed. D38 (2026-10-12): Phase A landmark-glitch diagnostics (observational only: trace `diag`, report `landmark_diagnostics`; the cursor is unchanged). A review found a Phase A regression (`cursor --trace` with targets crashed at the first capture: a variable-name collision); fixed and covered by a regression test, verified offline only (380 tests pass); no hardware run since. D37 (2026-10-11, tracking audit): the dropouts of the day's runs come from `--acquisition full` (reacquisition only by the palm detector on the whole frame: 55 % vs 95 % for tiles on 854 saved hand frames); tiled acquisition now returns a find only when the region tracker confirms it in the same frame (720-px region), an extrapolated fingertip is never drawn, One Euro beta 0.05, full-mode statistics, `--trace` and a motion summary; ~290 ms latency (hardware) and hover parallax remain; hardware verification in progress. D36 (2026-10-10 15:00–15:40): camera moved from ~30 cm to 18 cm beside the projector lens (closest possible: the projector top is not usable); tiled hand acquisition added (faster, 0 false positives); 60-s free-movement test with loss/recovery done (hand found ~97 % while in view). **Accuracy still fails and the shadow-centre test run was INVALID** (shadow centre established at 1/9 targets; where it was, the cursor was 39 px from it): hover parallax at the natural hover distance is not removable with this camera position. Phase 1C complete; 1B B1–B5 PASS; 1A A1, A3, A6, A7 PASS. |
| Next action | **Mission plan §9.12 (user's workflow): Stage 1 audit done; Stage 2: software baseline 547 passed; B-1 done (latency 262 ms, capture 60.16 fps); B-2 (accuracy grid, contact / 2 cm / 5 cm with a ruler), B-3 (bottom-edge writing) and the tape measurements to do. No code change before the baseline.** Earlier: **User mission (2026-10-26): precision writing (bottom edge, contact vs hover), reliable tracking, premium canvas UI, ≥ 50 fps; the pasted text was cut off at its section 5. Offline evidence gathered (§13.2); plan proposed, awaiting approval; nothing changed in code. Never push without asking (user, 2026-10-26).** Earlier: EXPLORE physical run 2 (2026-10-26 14:50, §13.2): X3 done (SUMMARIZE normal); X1 now 4 EXPLORE tries over 2 runs (SQL, Flight, Friendship ×2), the user's judgment pending; X2 (scribbles) still not run on the wall. Run 2 showed an invented claim about a person's name ("Kritagya is a common Indian female name") → EXPLORE prompt now forbids statements about people named in the writing (offline recheck: no claim; no regression). EXPLORE not complete.** Earlier: EXPLORE physical run 1 (2026-10-25 01:09, §13.2), partial: 2 EXPLORE tries (WHAT IS SQL → SQL; FLIGT → Flight), both topics found, judgment by the user pending; X1 needs a third topic, X2 (2 scribbles) and X3 (SUMMARIZE) not run. Display fix after the run: each EXPLORE point on its own line. Open question 17 (correct or refuse a misspelled topic). EXPLORE not complete.** Earlier: D54 EXPLORE built (2026-10-25, user request; §9.11): a sixth AI action (topic, background, key facts, a connected concept) in the same single request; no topic read with confidence → a fixed note, never a guessed topic. Tested offline (unit tests; dry runs on the local model with the user's real writing and scribbles). NOT complete: physical test X1–X3 (proposed, §9.11) pending. S2 PASS (2026-10-25, user's judgment, §13.2).** Earlier: S2 prepared (2026-10-24 23:58, §9.11): laptop on the charger, tracking speed normal again, Ollama + `qwen3-vl:8b-instruct` ready; dry run on the user's finger writing read CAT / DOG / SUN correctly (2 s per answer); panel text fixed (no "Claude" with the local model; transcription as large as the answer). User decision 2026-10-24: S1 selection treated as working on completed loops (22 of 22 exact in runs 2–3), the strict count (run 3: 10 of 12) stays recorded; R34 stays open. Next: live S2 when the user says go.** Earlier: S1 run 3 (2026-10-24, §13.2): count 1 (completed loops) 10 of 10 exact — meets ≥ 9 of 10; count 2 (all loops, broken = failed) 10 of 12 (83 %) — does not. Every miss in runs 2–3 is a broken loop (R34); no completed loop selected a wrong set (22 of 22 exact). The CPU was throttled (battery nearly empty; inference 34 ms vs ~11 ms). Awaiting the user: address R34 first, or continue with S2–S5.** Earlier: S1 run 2 (2026-10-24, §13.2): completed loops 9 of 9 exact (D53 corrected 2 live), all loops 9 of 11 (82 %), 10th word not reached (time limit); not passed. The laptop ran on battery: from 256 s the frame rate fell from ~48 to 10–17 fps. Next: S1 run 3 with the charger connected (§2.1 power row).** Earlier: D53 built (2026-10-24, user-approved): a SELECT loop closes at its tightest point, so the finger's lead-in and run-on no longer change the selection (S1 run 1 recorded loops: 12 of 12 completed loops exact; 3 regression tests). Next: S1 run 2 live, same pass criterion, reported as completed loops and as all attempts (broken loops = failures); then S2–S5. The broken loops (tracking lost over the writing) are kept separately as R34.** Earlier: S1 run 1 FAIL (2026-10-24, §13.2): 10 of 12 completed loops exact, 5 loops broke off. Earlier: R33 resolved (Smart App Control off, user decision; MediaPipe loads). Next: live S1–S5 with `draw --ai` (local `qwen3-vl:8b-instruct`, smoke-tested: answers in 0.9–2.5 s).** Earlier: Phase 3A built and tested offline (530 tests, §9.11). Earlier: D50 built (512 tests); G8 run 1 FAIL (hand found on a busy canvas: light off 30.5 %, on 74.3 %; < 90 %), §13.2. User (2026-10-23): switch the light off for now (code kept, `draw --light` / `gestures --light on` opt-in; G1″/G2/G3 results stand as measured without it) and proceed to Phase 3, AI summarize.** Earlier: User (2026-10-23): D50 first (light on the hand, G8 fixed in §9.10), then Phase 3 (Claude API as an optional function; phone uploads; §9.10 requirements).** Context: options were Phase 3 (P2: selection, structured canvas objects, OCR, context-aware AI; §5.2, §8), D50 (plain white light on the hand: tracking with ink on the hand and the distorted copy of drawings on the hand; user decided on 2026-10-22 to build it after the acceptance tests), and the Phase 2 leftovers (G5′ MOVE drags, G6 decision or search-speed work, G7 live round trips). Still pending from Phase 1: B2 re-run without the projector pointer (R28), `mapdemo` + ruler (A8), visual line-pair check (A2), projector picture settings vs latency (open question 5), Phase 1D accuracy criterion (open question 12). Mount the camera rigidly: it was knocked or drifted before almost every session (R10). |

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
| Camera | **Kreo Owl 4K Pro** USB webcam since 2026-10-17 (D41, user decision), replacing the Brio 100 for now. **Measured 2026-10-19 (D42):** DirectShow "Owl 4K PRO Camera", USB eba4:1303; MJPG 1920×1080 @ 60 delivers 60.1–60.5 fps; exposure −13..−1, focus 0..1023 and gain 0..15 controllable. **Not yet measured:** latency, field of view / distortion, detector and hand-detection behaviour (§9.9). **Previous camera:** Logitech Brio 100 (D14), validated 2026-10-09: DirectShow, MJPG 1920×1080 @ 30, manual exposure −5 → 29.83–29.93 fps sustained over 60 s (D24, D25). All hardware measurements in §13.2 up to 2026-10-12 were made with the Brio. |
| Surface | **Vertical**, flat projection surface: wall, whiteboard or canvas (D13) |
| Room light | **One room light on** while using the hand tools (2026-10-22): in a dark room the projector alone lights the hand, and projected text or ink on the hand lowered hand finding to 44 % (heavy content); with a room light 96 % (§13.2 G1″ run 2). |
| Power | **Laptop on mains power (charger connected)** during sessions (2026-10-24): after S1 run 2 the laptop was found on battery (21 %, Balanced plan, processor performance 56 %). In that run processing fell from ~48 to 10–17 fps from 256 s on and the camera delivered ~33 instead of 60 fps (§13.2); S1 run 3 on the charger but just plugged in (18 %): MediaPipe inference median 34 ms (runs 1–2: ~11 ms), 20 fps; at 33 % and charging, tracking a saved frame took 7.6 ms. On battery at 91 % (2026-10-25 00:0x): tracking 8.8 ms per frame and AI answers 1.1–1.4 s, both normal, so the slowdowns came with a nearly empty battery, not with battery power as such. So: **charger connected or the battery well charged (not near 20 %)**; the laptop holds the CPU back at low charge even on the charger. Before each live run: power state and a tracking-speed check, recorded with the results |

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

**Note (2026-10-09):** the hardware session ran on a different laptop from the snapshot above, which is kept as the original inspection:
- Internal panel `BOE0C29`, 1920×1080 @ 144 Hz, 100 % scaling.
- Projector on HDMI as `\\.\DISPLAY2`, EDID name **`AML TV`** [AML0030], 1280×720 @ 60 Hz, 100 %.
- DirectShow cameras: [0] Brio 100 (046d:094c), [1] Integrated Camera (13d3:54b6), [2] OnePlus Nord 4 (Windows Virtual Camera).
- `.venv` on Python 3.12.10 (Microsoft Store build); numpy 2.5.3, opencv-python 4.14.0.94, pytest 9.1.1, matching `requirements.lock`.

**Note (2026-10-17):** the code from GitHub (commit `99cb22b`) was also synced to the original laptop above (`.venv` matched to `requirements.lock`, hand model downloaded and SHA-256 verified). No Brio, Kreo or projector was connected to it then.

**Note (2026-10-19):** projector and Kreo connected to this laptop. Windows was in **Duplicate** mode (one source `\\.\DISPLAY1` driving the panel at 180 Hz and the projector at 30 Hz); switched to **Extend** with `SetDisplayConfig(SDC_APPLY | SDC_TOPOLOGY_EXTEND)` (user-approved; `DisplaySwitch.exe /extend` had no effect on build 26200). The projector is now `\\.\DISPLAY5` `AML TV` [AML0030], non-primary, at (2560, 0); Windows chose 1920×1080 @ 60 Hz, 150 %; set to **1280×720 @ 60 Hz** with `ChangeDisplaySettingsExW` (user-approved, same as Settings → Display), after which Windows chose **100 %** scaling by itself. In Duplicate mode `devices` lists one display named after the last target (here `AML TV`, "primary"), which is misleading; the automatic projector rule correctly refuses it.

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

**Camera: what to measure** (written for the Brio 100; applies to the Kreo Owl 4K Pro since D41. Also check which of its 4K-class modes really deliver their fps over this USB port and within the CPU decode budget, and whether autofocus can be locked: a hunting focus moves image features)
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
summarize · explain · simplify · generate examples · generate questions · explore the topic (background, key facts, connected concepts; D54) · answer contextual questions · visualize concepts in 3D.

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
| **Phase 2** | **P1** | tracking · interaction · cursor · drawing · erasing · undo/redo. **Plan approved 2026-10-22 (D44, §9.10):** gesture modes (index only = draw, open hand = erase, pinch = select/press, other = hover), partial eraser, bottom toolbar, and pinch-to-move strokes pulled forward from Phase 3 |
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
| `config/default.toml` (repo root) | Camera (name match, backend, resolution, fps, FOURCC, exposure mode/value), projector (name match, expected size), calibration (target inset, file location), validation (grid, thresholds), surface width in mm |
| `__main__.py` | CLI: `python -m invisible_canvas <command>` (argparse subcommands); enables DPI awareness before any window opens |
| `config.py` | Loads TOML (stdlib `tomllib`) into frozen dataclasses; rejects unknown keys; applies CLI overrides |
| `display/monitors.py` | Win32 via `ctypes`: per-monitor DPI awareness v2. Lists displays with GDI name, EDID friendly name and ID, output technology (HDMI/internal/virtual), bounds, resolution, refresh, DPI scale and available modes. Pure projector-selection function (§9.7). |
| `display/projector.py` | `ProjectorWindow`: borderless fullscreen window on the identified projector. Verifies that the window rectangle equals the monitor rectangle via Win32. Has a `--windowed` dev fallback. |
| `display/operator.py` | `OperatorWindow`: shows the camera frame on the laptop (scaled to fit, 1:1 when it fits), with overlays, status text, a zoom loupe, and mouse coordinates converted to camera pixels |
| `display/patterns.py` | Test pattern (1-px border, grid, 1-px line pairs, corner labels, resolution text); calibration targets; crosshair; dark canvas |
| `camera/directshow.py` | DirectShow device enumeration via `ctypes` COM: friendly name, device path, USB VID/PID, in the same order as OpenCV `CAP_DSHOW` indices. `CameraControl`: a device's `IAMCameraControl` (exposure value + auto/manual flag, AE priority): get, set, range. |
| `camera/exposure.py` | (2026-10-09, D24) Applies `[camera] exposure_mode`/`exposure_value`, verifies by read-back, and `ExposureKeeper` keeps it applied while streaming (re-applies after the camera stack resets it). `ExposureState` says what the camera reports, never what was merely requested. |
| `camera/locks.py` | (2026-10-19, D42/D43) Locks `[camera] focus_mode`/`focus_value` (`IAMCameraControl` property 6) and `gain_mode`/`gain_value` (`IAMVideoProcAmp` property 9): applied, verified by read-back, and kept applied while streaming by `LockKeeper` (same mechanism as exposure). `directshow.CameraControl(index, interface)` opens either interface. `CameraManager` opens and keeps both next to exposure; `CameraInfo.focus/gain`, `read_focus()/read_gain()`, `CaptureStats.focus_reapplied/gain_reapplied`; printed by the session tools, `camera` and `devices`. |
| `camera/manager.py` | `CameraManager`: opens the camera by name (or index); requests **and verifies** the resolution/FOURCC/fps from real frames; applies, verifies and keeps the configured exposure (D24); runs the latest-frame thread; reports measured fps, frame age and exposure re-applications; queues property changes and the settings dialog to the capture thread |
| `camera/probe.py` | Diagnostics: tries each candidate mode, reads back what was negotiated, measures the fps actually delivered; reads camera properties without changing them. `configure()` sets the FOURCC **last** (D26). |
| `geometry/homography.py` | Pure numpy: normalized DLT, apply (with points at infinity flagged), invert, quad validation (count, finite, distinct, convex/simple, min area), orientation check, reprojection errors |
| `calibration/targets.py` | Pure: positions of the four corner targets (inset) and of the held-out validation grid |
| `calibration/collect.py` | Interactive point collection, shared by calibrate and validate. The projector highlights one target; the operator clicks it in the live camera view with the loupe, nudges with the arrow keys, confirms or undoes. |
| `calibration/store.py` | `Calibration` record as versioned JSON (`data/calibration/current.json` + `history/`). Recomputes and checks H on load. Refuses camera/projector size mismatches. `archive_calibration` (D39): writes a calibration into the history if it is missing there, never rewrites an entry. |
| `calibration/metrics.py` | Pure: accuracy statistics (mean, median, p95, max, mm), required/stretch pass levels, repeatability (mean/max corner variation) |
| `mapping/mapper.py` | `CoordinateMapper`: camera→projector and projector→camera for single points and batches, inside-canvas flag |
| `tools/devices.py` | `devices`: full hardware diagnostics. Prints the results and saves JSON to `data/reports/`. Reads each camera's exposure but does not set it (its per-mode probes open new streams, which the camera stack resets). Also runnable as `python -m invisible_canvas.tools.devices`. |
| `tools/projector_check.py` | `projector`: test pattern, white and black screens on the identified projector; window-rectangle verification |
| `tools/camera_check.py` | `camera`: live feed showing negotiated format, exposure at open, measured fps, frame age, saturation %, property readout; opens the driver settings dialog. Ends with the exposure read back at the end and the re-application count. Setup aid (display only): `f` / `--preview` shows the whole frame fullscreen on the laptop screen (1:1 for 1920×1080), `b` brightens that preview (gamma 0.4). |
| `tools/latency.py` | `latency`: display→camera latency. Flashes the projector black→white and times when the camera sees it (median, p10, p90 over N trials). Since 2026-10-09 (D27) it re-measures the levels after the trials and marks the run NOT VALID (exit 1) on any missed trial, level drift or lost exposure; per-trial outcomes and peak levels are in the report. |
| `tools/calibrate.py` | `calibrate`: four-point calibration. **Manual** (default, `--manual`): collect points → compute and validate H → overlay and live hover check → save. **Automatic** (`--auto`, D30): detect the 4 corners, check them, fit H the same way, verify with a held-out check target, save with `method: "auto"`; `--dry-run` does not save. Writes `calibration-auto-*.json` with the detection quality. |
| `tools/validate.py` | `validate`: held-out grid accuracy test with report and error map. Since 2026-10-09 (D28) it first checks the 4 calibration corners and stops if the setup no longer matches the calibration (`--no-setup-check` skips it). **Manual** (default, `--manual`): clicks, `validation-*.json` with `"mode": "manual"`. **Automatic** (`--auto`, D30): detections, `validation-auto-*.json` with `"mode": "auto"` and per-point detection quality; `--simulate-shift DX DY` (test only) shifts every projected image. `repeatability`: corner variation across the last N calibrations of the same method. D39: the refusal message names `recalibrate`. |
| `calibration/auto.py` | (Phase 1C, D30) Pure logic of automatic calibration/validation: per-target quality gate, corner association and rejection (missing, ambiguous, unstable, duplicate, wrong order, mirrored), check-target verification, automatic setup check, validation errors. Camera access is a `measure(screen)` callable (real: `tools/common.CameraMeasure`; tests: `tests/synthetic_camera.py`). |
| `calibration/recovery.py` | (D39) Pure logic of automatic calibration recovery after a moved setup: from the refused setup check's own corner detections a candidate is built (`associate_corners`, `Calibration.create`), checked with the held-out check target, validated on the held-out grid (A7 required limits) and confirmed by a setup check against it; `commit_recovery` saves only an accepted candidate, only if `current.json` still holds the refused calibration, after archiving that one in the history; operator hints for every failure reason (`explain`) |
| `vision/hands.py` | (Phase 1D, D33/D36) `HandTracker`: MediaPipe Hand Landmarker; landmarks converted exactly back to camera px; model SHA-256 checked. `acquisition="tiled"` (D36): while no hand is tracked a stateless detector (IMAGE mode) checks the full frame and 2 of 8 overlapping 720-px tiles per frame; after a find ONE VIDEO tracker follows the hand in a square region (≥ 720 px since D37, 3× the hand) re-centred every frame; `square_tiles`, `Region`, `AcquisitionStats`. Default `full` = D33 path. D37: a search hit is returned only after the region tracker has found the hand in the same frame (its landmarks are returned); `HandObservation.view/tip_norm/tip_in_view`; `AcquisitionStats` for both modes; `HandTracker.action` per frame. D40: search budget of `views_per_frame` (2) views per search frame, in turn from full frame, tile 1..N (`next_views`); every new search starts with the full frame. |
| `vision/landmark_diagnostics.py` | (Phase 1D, D38) Observational landmark-glitch diagnostics (relative motion of the index tip against its knuckle, palm-normalised; index extension ratio); `LandmarkDiagnostics.update`, `episodes`, `summary`, `replay` (offline, over `--trace` lines). Never feeds the cursor |
| `vision/cursor.py` | (Phase 1D, D33) Pure cursor logic: tracking / holding / lost / outside states, no glide after recovery, optional One Euro filter, dwell detection for the accuracy test |
| `vision/shadow.py` | (D35/D36) `find_shadow` (whole-image search, experimental, unreliable); `shadow_tip_near` (D36): the fingertip's shadow strip near a known point (the target), its end and centre (half a strip width back), with reasons when not established (hidden, no clear end, width, contrast 0.5–1.3); `steady_shadow_centre` (≥ 3 frames within 6 px). `finger_width` from the knuckle spacing |
| `tools/cursor.py` | (Phase 1D, D33–D39) `cursor`: live fingertip cursor; setup check; brightness pre-check; `--accuracy` with `--aim shadow` (default; D36: each capture measures the cursor against the fingertip's shadow centre, paired per frame; a capture without an established shadow centre makes the run INVALID) or `--aim finger`; per-target detection, first detection after activation, confidence; rows/columns; `--acquisition tiled|full` (default tiled); `--withdraw`; `--targets/--labels/--pause`; `--save-every`; capture frames; D37: a fingertip outside the image MediaPipe saw is not drawn; records carry the drawn position and the state reason; report `transitions`, `reacquired_after_s`, `motion`; `--trace` (per-frame JSONL, off by default); D38: landmark diagnostics recorded in the trace (`diag`) and report (`landmark_diagnostics`), observational only; D39: when the setup check refuses, automatic recovery (validated before it is saved and used; on failure the cursor does not start); `--no-recalibrate` stops at the refusal |
| `tools/setup_check.py` | (D32) `setupcheck`: repeated automatic setup checks with optional simulated shifts, judged against several limits (read-only diagnostic) |
| `tools/recalibrate.py` | (D39) `recalibrate [--dry-run]`: setup check; if moved, automatic recovery (calibration/recovery.py), report `calibration-recovery-*.json`; also used by `cursor` (`recover_in_session`) |
| `tools/hand_check.py` | (D34) `handcheck`: read-only hand-detection diagnostic. Per projected grey level: detection rate, canvas-region brightness, hand size, verdict (too dark / no hand / small hand); saves camera frames, the exact MediaPipe input image and per-frame metadata to `data/diagnostics/handcheck-<stamp>/`. `--image FILE` runs the same pipeline on a photo (positive control) |
| `tools/map_demo.py` | `mapdemo`: hovering in the camera view projects a crosshair at the mapped point; clicking pins it |
| `tools/common.py` | Shared session: identify and open projector + camera + operator window, always cleaned up; JSON reports |
| `tests/test_*.py` | homography, targets/metrics, mapper/store, config, monitor selection/EDID/struct sizes, camera helpers (incl. FOURCC-last order), exposure control (apply, read-back, reset/re-apply, failure paths), display (operator coordinate conversion, loupe sub-pixel clicks, target symmetry, pattern purity), mapping chain and setup check, cross detector (`test_detect.py`, synthetic) and the `detect` diagnostic's pure parts |
| `calibration/detect.py` | (Phase 1B, D29) `detect_cross()`: centre of the projected cross in camera px from its geometry (arm-line intersection), with quality fields and a reason for every rejection |
| `tools/detect_check.py` | (Phase 1B, D29) `detect`: read-only diagnostic of the detector on real frames (24 targets, single frames, negative controls, click-free consistency, comparison with manual centres); JSON report + PNG contact sheet |

All files above exist as of 2026-10-08 (Phase 1A software complete); `camera/exposure.py` and `tests/test_exposure.py` were added 2026-10-09.

**Phase 1B:** first increment done 2026-10-10: `calibration/detect.py` (detection of the existing calibration crosses, not separate dots) and the `detect` diagnostic (D29).
**Phase 1C** (2026-10-10, D30): `calibration/auto.py`, `calibrate --auto [--dry-run]`, `validate --auto [--simulate-shift DX DY]`. Manual modes unchanged and still the default. Possible next: optional N-point calibration / lens undistortion (R8).

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

**Phase 1B–1D commands** (since D31 `calibrate`/`validate` are automatic by default; `--manual` clicks):

```
python -m invisible_canvas detect                      # detector diagnostic (read-only)
python -m invisible_canvas calibrate --auto [--dry-run]
python -m invisible_canvas validate --auto             # setup check + 20 detected targets
python -m invisible_canvas validate --auto --simulate-shift DX DY   # test only: perturbed projection
python -m invisible_canvas repeatability               # compares calibrations of the current calibration's method
python -m invisible_canvas setupcheck --repeat 12 --interval 45   # D32: no-movement drift series (read-only)
python -m invisible_canvas recalibrate [--dry-run]     # D39: setup check; if moved: detect, validate, confirm, then save
python -m invisible_canvas setupcheck "--shifts=0,0 1,0 2,0 -2,0 0,2 3,0 0,0"   # D32: sensitivity sweep
python -m invisible_canvas cursor [--seconds N] [--accuracy] [--aim shadow|finger] [--acquisition tiled|full] [--withdraw] [--smoothing] [--trace] [--background 0-255] [--save-every S] [--no-recalibrate]   # Phase 1D
python -m invisible_canvas cursor --targets "640,690 640,690" --labels "2cm 8cm" --pause 5   # D35: hover sweep
python -m invisible_canvas handcheck [--backgrounds "40 128 255"] [--image FILE]   # D34: why is a hand (not) detected
```

Since D31, `calibrate` and `validate` without a flag are automatic; add `--manual` to click.

### 9.4 Dependencies (approved; complete list for Phase 1)

| Dependency | Kind | Why |
|---|---|---|
| Python **3.12.x** (64-bit) | System | Runtime. Installed per-user with `winget install -e --id Python.Python.3.12 --scope user`. Version 3.12 keeps MediaPipe (P1) available. |
| `.venv` | Project | Isolated project environment (`.venv/`, git-ignored) |
| `numpy` `>=2.0,<3` | Runtime | Point arrays and matrix math |
| `opencv-contrib-python` `>=4.10,<5` (4.14.0.94) | Runtime | Camera capture (DirectShow/MSMF), HighGUI windows, image processing. Replaced `opencv-python` (same version) on 2026-10-10 because MediaPipe requires contrib (D33); `<5` because MediaPipe does not pin OpenCV and OpenCV 5 is out |
| `mediapipe` `>=1.1,<2` (1.1.0) | Runtime | Phase 1D hand landmarks (D33, user-approved). Pulls absl-py, flatbuffers, matplotlib, sounddevice, certifi and their dependencies (`requirements.lock`). Model `models/hand_landmarker.task` downloaded separately (SHA-256 pinned) |
| `pytest` `>=8` | Dev only | Unit tests |

Everything else comes from the standard library: `tomllib`, `json`, `ctypes` (DPI awareness, displays, DirectShow enumeration), `threading`, `argparse`, `dataclasses`, `logging`.

Rules:
- Install **exactly one** OpenCV wheel. Since D33 it is `opencv-contrib-python`; never add `opencv-python` or `opencv-python-headless` alongside it: they ship conflicting `cv2` modules, and the headless build has no GUI.
- Pin the exact installed versions in `requirements.lock`.

**Deliberately not installed:**
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
| 3 | `python -m invisible_canvas camera` | A3/A4 | Aim the camera so the whole projection is visible with margin. Exposure comes from `[camera] exposure_mode`/`exposure_value` (D24) and is printed at open; check it says `confirmed by read-back`. `s` opens the driver dialog: check white balance and focus and record what the Brio allows (an exposure change there is overridden by D24). Project white (step 2) and check that saturation is about 0 %. |
| 4 | `python -m invisible_canvas camera --seconds 60` | A3 | Record mean fps, slowest 1-s window, longest gap, failed reads, exposure at end and the re-applied count. **Close every other camera window first** (R20). |
| 5 | Measure the projected image width in mm | — | Set `[surface] width_mm`; record the geometry in §13.3. |
| 6 | `python -m invisible_canvas calibrate` | A5 | Click the 4 targets (use the loupe), check that the review outline hugs the projection, save. Record the coverage printout. |
| 7 | `calibrate` two more times, touching nothing; then `python -m invisible_canvas repeatability` | A6 | Record mean/max corner variation. |
| 8 | `python -m invisible_canvas validate` | A7 | 20 held-out clicks. Record mean/median/p95/max, edge vs interior, PASS/FAIL. Keep the error-map PNG. |
| 9 | `python -m invisible_canvas mapdemo` | A8 | Hover at the centre, 4 corners and 3 stickers; measure the offsets with a ruler. |
| 10 | `python -m invisible_canvas latency` | A3 | Record median/p10/p90 display→camera latency. |
| 11 | `python -m pytest` | A9 | All tests pass |

Reports land in `data/reports/` (JSON, plus a PNG for validation). Copy the numbers into §13.2. **Never adjust thresholds to make a run pass.**

Restart check for A5: close everything and run `mapdemo` again. It must load the saved calibration. Changing `[camera] width/height` must make it refuse.

### 9.9 Camera change re-validation (D41: Kreo Owl 4K Pro)

The Brio results do not transfer to another camera. Run in this order and stop at the first failure; record every number in §13.2, pass or fail. Close every other camera program first (R20).

| # | Command / action | Replaces (Brio result) | Check / decide |
|---|---|---|---|
| 1 | `python -m invisible_canvas devices` (add `--camera <part of the Kreo's name>` while `"brio"` is still configured) | A1 camera part, D25 modes | DirectShow name and USB id; the modes that really deliver their fps; exposure read-out. Set `[camera] match` to the Kreo's name. The probe list stops at 1920×1080, so 4K-class modes are not measured yet (open question 14). |
| 2 | `python -m invisible_canvas camera` | D24 | Does `manual -5` apply and read back? If the Kreo has no exposure control or another range, the session tools stop with "exposure NOT APPLIED" (by design); then choose `exposure_mode`/`exposure_value` from what `camera` shows. Check that autofocus is off or stable, and check white balance. |
| 3 | `python -m invisible_canvas camera --seconds 60` | A3 fps, D25 | ≥ 25 fps sustained at the chosen mode; whether the exposure is reset after stream start (R21 was Brio behaviour). |
| 4 | `python -m invisible_canvas latency` | A3 latency (275 ms) | Median vs the Brio. `tools/common.SETTLE_SECONDS` (0.8 s) must stay > 2× the median, otherwise automatic calibration captures too early. |
| 5 | Re-aim; record the new camera position in §13.3 | §13.3, D36 | Whole projection in the frame with margin (A4); camera–projector baseline (parallax, R12) |
| 6 | `python -m invisible_canvas detect` | B1–B5 | Detector margins (line residual, arm width) on the new optics |
| 7 | `calibrate` ×3, `repeatability`, `validate`, `validate --manual` | A5–A7, Phase 1C | Same thresholds (D17); never tuned to pass |
| 8 | `handcheck`, `cursor --seconds 30` | Phase 1D baseline | Detection rate, fps, pipeline time with the new frames |
| 9 | `python -m pytest` | A9 | `tests/test_config.py` pins the Brio config values; update it together with the config |

**Progress (2026-10-19, §13.2):** steps 1–2 done: exposure −6, focus 410 and gain 15 locked and confirmed (D42, D43); `camera --headless --seconds 10`: 60.24 fps. Step 5 must come before step 6: the projection is cut off at the top of the camera frame.

### 9.10 Phase 2 plan (P1): drawing with hand gestures (approved 2026-10-22, D44; **revised by D46**)

**Revision D46 (2026-10-22, user decision after G1 run 1): one gesture + toolbar tools.** This replaces the gesture table, G1, G4 and G5 below; everything else in this section stays.

| Hand | Effect |
|---|---|
| Index finger only (POINT, confirmed after 7 frames ≈ 130 ms) — **posture: point sideways across the wall, finger flat, side of the hand towards the camera** (pointing into the wall hides the hand from the camera: G1′ run 1 vs run 2) | use the current tool at the fingertip: **PEN** draws, **ERASER** erases only the ink it touches (radius by width: 12 / 24 / 42 px), **MOVE** drags the drawing under the fingertip |
| Anything else — **recommended: open hand or fist** (G1 run 1: read as POINT in 1/335 and 3/402 frames) | cursor only |
| Cursor held on a toolbar button for **1 s** (CLEAR **2 s**) | presses it once (move off and back to press again) |

Toolbar (bottom edge): PEN, ERASER, MOVE · 4 colours (choosing a colour selects PEN) · 3 widths · UNDO, REDO, CLEAR.

**Revised acceptance tests (fixed 2026-10-22, before any run):**

| # | Test | Pass condition |
|---|---|---|
| G1′ | Pointing recognition (`gestures`, guided: POINT, OPEN, FIST, each held twice; a prompt starts only once a hand is seen) | POINT prompt: ≥ 95 % of hand-present hold frames POINT; OPEN and FIST prompts: ≥ 95 % not POINT; the engine never in DRAW during an OPEN/FIST hold |
| G4′ | Partial erase (ERASER tool) | erasing across 3 strokes removes ink only along the eraser path; the rest stays |
| G5′ | Dwell presses and MOVE | 20 toolbar presses → ≥ 19 correct, 0 wrong buttons; 0 presses during G2's 60 s; 5 MOVE drags → 5/5 moved by the fingertip's displacement |

G2, G3, G6 and G7 are unchanged.

**D50 (2026-10-23, user decision: build after the Phase 2 tests, before Phase 3): light on the hand.** Every frame the projected image is painted plain white over the tracked hand (convex outline of the 21 landmarks in projector px + 25 px margin), stretched ahead along the hand's motion by the ~0.26 s display loop (look-ahead capped), and held ~1 s at the last position after a loss. Projected ink, text and the cursor no longer fall on the hand (§13.2 2026-10-22: hand found 100 % over plain white vs 62 % over ≥ 8 % dark content in a dark room; the distorted copy of drawings on the hand). The cursor becomes a ring around the fingertip, outside the light (it stays on the wall); a toolbar dwell fills it as a progress arc. `draw --no-light` disables it. Files: `display/handlight.py` (pure), `canvas/render.py`, `tools/tracking_session.py`, `tools/draw.py`, `tools/gestures.py` (`--busy`, `--light on|off|ab`).

**G8 (fixed 2026-10-23 before any D50 code):** one `gestures --angles --busy --light ab` recording: the 5 pointing angles over a busy background (dense text and lines over the whole projection), 4 rounds with the light off, on, off, on. Pass: with the light on, the hand found in ≥ 90 % of the pointing hold frames and in at least the fraction found with the light off; processing ≥ 30 fps and pipeline p95 ≤ 33 ms over the light-on rounds. Afterwards G1″, G2 and G3 are re-run with the light on (the projected image changes what the camera sees).

**Phase 3 requirements recorded from the user (2026-10-23, not designed yet):** (1) the context-aware AI uses the **Claude API** (Anthropic) reading an image of the selected strokes (no separate OCR library), as an **optional function the user switches on when needed** (needs internet and an API key on the laptop); (2) **bring content from the user's phone**: upload files, data or images from the phone and use them on the canvas.

**D49 (2026-10-22, after G3 run 2): pen-lift delay.** The pen lifts only after 0.6 s without a pointing hand; shorter interruptions are bridged. To start a new stroke right after a lift, wait about half a second.

**D48 (2026-10-22, user decision after G1′ runs 3–4): multi-angle pointing.** The user's natural pointing is upward with the back of the hand to the camera; the system must recognise the index finger from different angles without losing accuracy or latency. Plan (approved):
1. Record once: `gestures --angles --video`: guided prompts POINT UP, POINT UP-LEFT, POINT UP-RIGHT, POINT SIDEWAYS, POINT DOWN-DIAGONAL, OPEN HAND, FIST, 2 rounds; the camera video (MJPG AVI, written in a background thread) and the per-frame landmarks are saved.
2. Replay offline: `replay <recording>` runs the video through the real tracker, classifier and engine (recorded timestamps) and reports per prompt: hand found %, POINT %, keep-band %, DRAW in OPEN/FIST holds, processing ms per frame.
3. Improve, judged on the recording (round 1 to design, round 2 held out): (a) tracking: keep / re-acquire a pointing hand near its last position before the full search (`vision/hands.py`); (b) view-robust pointing (`vision/gestures.py`), e.g. the duplicate-finger rule (§13.2 G1′ run 4).
4. Fresh live test G1″. A finger pointing into the wall is hidden behind the hand at this camera position and is not covered.

**G1″ (fixed 2026-10-22 before any D48 code):** fresh `gestures --angles` recording; for **each** pointing angle: hand found in ≥ 90 % of hold frames and ≥ 95 % of the hand-present hold frames POINT; OPEN and FIST: ≥ 95 % not POINT; the engine (with D47) never in DRAW during an OPEN/FIST hold; processing ≥ 30 fps and pipeline p95 ≤ 33 ms over the recording (as G6). G1″ replaces G1′ for D48.

**D47 (2026-10-22, after G3 run 1): keep-drawing band.** A stroke starts only on a strict POINT (7 frames, unchanged); once drawing, the stroke continues while the hand stays within a looser band (index ≤ 60°, middle/ring ≥ 45°, little ≥ 30°, thumb ignored). **To lift the pen: open the hand fully or make a fist** (a half-open hand keeps drawing). G1′ and G3 must be re-run on fresh recordings.

**D46 implementation (2026-10-22):** `interaction/engine.py`: `mode_of` mapping, default `TOOL_MODES` (POINT → DRAW, all else HOVER), `GESTURE_MODES` kept for the D44 mapping; enter frames 7. `canvas/toolbar.py`: 13 buttons of 80 × 56 px (tools, colours, widths, actions), `DWELL_S` 1 s, `CLEAR_DWELL_S` 2 s. `interaction/drawing.py`: tools PEN / ERASER (radius 12 / 24 / 42 px by width) / MOVE on the pointing stroke; `update_pointer` presses a button after the dwell (once; re-armed by leaving it). `canvas/render.py`: tool buttons, dwell progress bar, tool cursors. `tools/gestures.py`: prompts point / open / fist, POINT-vs-not scoring, a hand gate before each prompt and a "hand seen" indicator. Tests 488 passed (D46: engine defaults and the observed misread runs, dwell, tools, a fake-session draw → ERASER dwell → erase → UNDO dwell run, open hand / fist never draw).


**Gestures (user design).** The cursor always follows the hand; its look shows the mode.

| Hand shape | Mode | Cursor point | Effect |
|---|---|---|---|
| Index finger only (middle, ring, little finger curled) | DRAW | index fingertip | ink while the shape is held |
| All five fingers open | ERASE | palm centre, circle scaled to the hand | removes only the ink under the circle (strokes are split) |
| Pinch (thumb tip on index tip) | SELECT | between the thumb and index tips | on a toolbar button: press it; on a stroke: pick it up, move, release to drop |
| Any other shape (fist, relaxed hand, two fingers) | HOVER | index fingertip | cursor only |
| No hand | IDLE | hidden | — |

**Reliability rules (§6).**
- A mode is entered only after its shape is seen in `enter_frames` consecutive frames (default 4, ≈ 70 ms at 54 fps).
- A mode is left only after `exit_frames` frames of another shape (default 3).
- Pinch uses separate enter/exit distances.
- Points recorded while the shape is changing are dropped, so strokes have no hooks.
- Hand lost: the stroke pauses for ≤ 150 ms, then ends cleanly. The cursor never jumps.
- Clear needs the pinch held on its button for 1 s.
- The laptop keyboard can also undo (z), redo (y) and save (s).

**Shape recognition.** From the 21 landmarks: per-finger straightness (fingertip-to-knuckle distance ÷ joint-chain length) and the thumb–index tip distance ÷ palm size. It uses MediaPipe's 3-D world landmarks (metres, hand-centred) when present, because the camera sees the back of the hand and 2-D bends depend on the view; otherwise it uses the 2-D camera landmarks. No new dependency.

**Canvas.** White background (the Kreo needs it to see the hand: grey 128 → canvas region 52, 255 → 129–157). Content is structured strokes (projector px = logical canvas for now). Undo/redo covers draw, erase (one step per erase gesture), move and clear. Bottom-edge toolbar: 4 ink colours, 3 widths, undo, redo, clear. Saved as JSON + PNG to `data/canvas/` on exit.

**Files** (paths under `src/invisible_canvas/`; pure modules unit-tested without hardware):

| File | Responsibility |
|---|---|
| `vision/hands.py` | `HandObservation.world`: MediaPipe world landmarks (21 × 3 m), optional |
| `vision/gestures.py` | `classify()`: POINT / OPEN / PINCH / OTHER with measurements, pinch hysteresis |
| `interaction/engine.py` | Mode state machine (debounce, hysteresis, trimming, loss) → canvas events |
| `canvas/model.py` | `Stroke`, `Canvas`: add, partial erase (split), hit-test, move, JSON |
| `canvas/history.py` | Undo/redo commands |
| `canvas/toolbar.py` | Bottom toolbar layout, hit-testing, hold-to-clear |
| `canvas/render.py` | Canvas, active stroke, selection, toolbar, mode cursor |
| `interaction/drawing.py` | `DrawingController`: applies engine events to canvas, history and toolbar |
| `tools/gestures.py` | `gestures`: guided recording of each shape (G1), landmarks saved for offline analysis |
| `tools/draw.py` | `draw`: the drawing app (setup check + recovery, tracking, gestures, canvas, report) |
| `tools/tracking_session.py` | Shared by `draw`/`gestures`: setup check with validated recovery, brightness check, `HandPoints` (shape + smoothed projector points, eraser radius = 0.6 × palm length, 25–140 px) |

**Status 2026-10-22:** all files above implemented (D45); unit and fake-session tests pass (64 new: gestures 26, engine 16, canvas/history/toolbar/controller/render 18, tools 4); `draw` started on the hardware. Hardware acceptance G1–G7 not run yet.

**Acceptance tests (fixed 2026-10-22 before any hardware run; never loosened to pass).** Phase 2 passes when all of these pass on the Kreo setup:

| # | Test | Pass condition |
|---|---|---|
| G1 | Shape recognition (`gestures`, guided: each of POINT, OPEN, PINCH and two OTHER shapes held twice) | per shape ≥ 95 % of hand-present scored frames classified as prompted, and DRAW never entered (after debounce) during a non-POINT prompt |
| G2 | No accidental ink | 60 s of free movement in HOVER shapes and between shapes without the index-only shape → 0 strokes |
| G3 | Drawing | 10 deliberate strokes (lines, a circle, letters) → 10 strokes, no extra stroke, no gap inside a stroke |
| G4 | Partial erase | erasing across 3 strokes removes ink only within the eraser path; the rest stays (checked on the saved canvas) |
| G5 | Pinch | 20 toolbar presses → ≥ 19 correct, 0 wrong buttons; 5 stroke moves → 5/5 moved by the hand's displacement |
| G6 | Responsiveness | ≥ 30 fps processing while drawing (60-s run), pipeline p95 ≤ 33 ms |
| G7 | Undo/redo | every action type undone and redone exactly (unit tests + 5 live round trips) |

**Steps.** (1) world landmarks + `gestures.py` + guided recording tool; (2) canvas, history, toolbar, renderer, engine, controller, `draw`; (3) hardware: G1 recording, offline check, then G2–G7. Gesture thresholds may be set from the G1 recording (the evidence) before G2–G7 run; the criteria above stay fixed.

### 9.11 Phase 3A plan (P2): AI summarize on selected writing (approved 2026-10-23, D51)

**Use.** (1) **SELECT** tool: pointing draws a loop; on pen-up the strokes inside it are selected (highlighted); nothing selected = the whole canvas. (2) **AI** button, present only when AI is switched on: opens a projected panel with SUMMARIZE, EXPLAIN, SIMPLIFY, EXAMPLES, QUESTIONS and CLOSE (dwell to press, as the toolbar). (3) The panel shows "thinking…", then what Claude read (transcription) and the answer, in large text; drawing continues meanwhile.

**Design.**
- Off by default: `draw --ai` or `[ai] enabled = true`. With AI off nothing is sent and no AI button is shown.
- Request: the selected strokes rendered black on white (cropped, margin) as a PNG + the action → Claude via the official `anthropic` Python SDK; model `claude-opus-5-5` (config `[ai] model`); adaptive thinking; structured output {transcription, result}; server-side refusal fallbacks enabled. Credentials from the environment (`ANTHROPIC_API_KEY`), never stored in the repository.
- Runs in a background worker thread; the tracking/drawing loop never waits. No key, no internet, a timeout or a refusal → a message in the panel; the app continues.
- Each request's image and answer saved to `data/ai/` (git-ignored).
- Files: `ai/` (`client.py`: request building, answer parsing, error mapping; `worker.py`: background jobs), `canvas/selection.py` (loop hit-test, selection → image), toolbar (SELECT, AI), `interaction/drawing.py` (select tool, AI actions, panel state), `canvas/render.py` (loop, panel), `config.py` (`[ai]`), `tools/draw.py` (`--ai`); tests with a fake client (no network).
- New dependency: `anthropic` (official SDK, exact version pinned in `requirements.lock`): needed for the Claude API (user decision 2026-10-23, §9.10 Phase 3 requirements).

**Acceptance (fixed 2026-10-23 before any Phase 3 code):**

| # | Test | Pass condition |
|---|---|---|
| S1 | Selection | a loop around one of three handwritten words selects exactly that word's strokes in ≥ 9 of 10 tries (live) |
| S2 | AI answer | a short handwritten sentence → SUMMARIZE → the panel shows a transcription the user judges correct and a summary in ≥ 4 of 5 tries; time to answer measured and reported |
| S3 | No freezing | while an AI request runs: processing ≥ 30 fps and drawing still works |
| S4 | Off means off | with AI off: no AI button, no network call, `anthropic` not needed (tests) |
| S5 | Failures | no key / no internet: a clear message in the panel, the app keeps running (tests + one live check) |

**D52 (2026-10-23, user decision): free of cost — local AI by default.** The user wants no charges at all; the Claude API is billed per request. The AI now runs on the laptop: **Ollama** (free local model server, installed as a separate application) with the vision-language model **`qwen3-vl:8b`** (6.2 GB download; its model page claims OCR robust to blur, tilt and poor lighting; no page mentions handwriting, so S2 decides; alternative `qwen2.5vl:7b`, 6.0 GB). Hardware: RTX 5070 Laptop GPU 12 GB, 16 GB RAM, i7-14650HX; hand tracking runs on the CPU, so the GPU is free for the model. The request goes to Ollama's local HTTP API (`http://127.0.0.1:11434`, stdlib `urllib`, no new Python package): system prompt + task + image, JSON schema output {transcription, result}; same panel, same S1–S5. No account, no key, no internet, nothing leaves the laptop. The Claude backend stays in the code as an option (`[ai] backend = "claude"`), off. Failure messages for S5: Ollama not running, model not downloaded, timeout.
**Later (Phase 3B):** content from the user's phone (files, images) onto the canvas, planned separately.

**Implementation (2026-10-23):** `ai/client.py` (`build_request`: image block + task, system prompt, `output_config` {effort, json_schema {transcription, result}}, `betas: [server-side-fallback-2026-07-01]` + `fallbacks: "default"`; `parse_response`: refusal / max_tokens / missing text / invalid JSON → panel messages; `ClaudeAssistant.ask` never raises, `error_message` maps the SDK errors and the no-key TypeError), `ai/worker.py` (`AIWorker`: one request at a time in a daemon thread, `submit` / `poll`, saves PNG + JSON to `data/ai/`), `canvas/selection.py` (`select_in_loop`: ≥ 60 % of a stroke's points inside, loops < 400 px² ignored; `selection_image` cropped, margin 24, longer side ≤ 1024 px; `png_bytes`), `canvas/panel.py` (`AIPanel` layout at the right above the toolbar, `wrap`, `ascii_text`), `canvas/toolbar.py` (SELECT tool, optional AI button, button width fitted: 77 px without AI, 70 px with), `interaction/drawing.py` (select loop, panel states menu/thinking/answer/error, `ai_jobs`, `take_ai_jobs`, `ai_answer`, strokes refused under the panel), `canvas/render.py` (loop, selection halo, panel), `config.py` (`[ai]`: enabled false, model `claude-opus-5-5`, effort medium, max_tokens 16000, timeout 60 s, fallbacks true), `tools/draw.py` (`--ai`, worker wiring, report `ai` with answers and the frame rate while a request runs). Dependency: `anthropic` 2.2.0 as the optional extra `ai` (`pip install -e .[ai]`; lock file regenerated; the SDK's API checked on the installed package: `beta.messages.create` takes `fallbacks` (`"default"` or a list), `betas`, `output_config`, `timeout`; no key → TypeError at request time; no network → `APIConnectionError`). Tests: 18 new (`tests/test_ai.py` 16, `tests/test_draw_tool.py` 2, fake Claude, no network); full suite 530 passed, 22 skipped. **Live S1–S5 not run yet** (no API key on this laptop).

**D53 (2026-10-24, user-approved after S1 run 1): the SELECT loop closes at its tightest point.** A stroke starts where pointing starts (after the 7-frame entry, with the buffered points), so a loop also contains the finger's way to where the user begins circling, and possibly a run-on past the start. `select_in_loop` joined the drawn path end-to-start, so in S1 run 1 the lead-in took a neighbouring word's stroke into the polygon (loop 8) or cut one of the word's own strokes out (loop 9). Now `canvas/selection.py` `close_loop` finds the closest pair between a point of the loop's first third and a point of its last third (`CLOSE_PART` 1/3) and keeps only the path between them; unchanged when the drawn ends are already the closest pair or the loop has < 8 points (`MIN_CLOSE_POINTS`). `select_in_loop` uses the closed part (area check and hit test). The controller's selection log adds `points` and `closed_points` per loop. The S1 pass criterion and the pen-lift delay (D49, 0.6 s) are unchanged. Offline on the 17 loops of S1 run 1: 12 of 12 completed loops exact (before: 10), the same for windows of 25 %, 33 % and 40 % (50 %: 2 wrong, the windows meet mid-loop); the 5 broken loops still select nothing. Tests: synthetic lead-in over a neighbouring word, synthetic lead-in through the word with a run-on, the 17 recorded loops (`tests/fixtures/s1_run1_loops.json`); all three fail with `close_loop` disabled.

**S2 preparation (2026-10-24 23:20–23:58; no live test; the S2 criterion above is unchanged).**
- Ready: laptop on the charger (78 %, charging), processor performance 111 % under load; tracking on saved frames of S1 run 3 8.8 ms per frame with a hand, 19.6 ms searching (references: 7.6–8.3 ms offline, D40 ~21 ms; S1 run 3 live 34 ms while throttled). Ollama 0.40.10 running (it updated itself from 0.40.9), `qwen3-vl:8b-instruct` installed.
- Dry run on the user's finger writing (the S1 run 2 canvas, `LocalAssistant`, SUMMARIZE, no projector): warm-up 7.6 s; whole canvas read as "CAT DOG Sun" (4.5 s, the first question), the single words "CAT", "DOG", "Sun" (2.0 s each). Only the letter case of SUN differs.
- Panel (`canvas/render.py`): the text said "Claude" while the local model answers → "Choose what the AI should do with it." / "The AI is reading... N s"; the transcription was drawn small and grey (0.5) → "READ:" and the transcription as large and dark as the answer (0.62), as §9.11 specifies ("in large text"). README: `ollama pull qwen3-vl:8b-instruct`.
- Protocol for the live run: one `draw --ai --seconds 1200 --trace --save-every 2` session on a fresh canvas; 5 tries, each a new short sentence written with PEN (block capitals, two lines, in the left two-thirds: the open panel covers the right third), nothing selected (the whole canvas is read), AI → SUMMARIZE; the user judges whether the READ line is what they wrote; CLOSE, CLEAR (hold 2 s), next sentence. Pressing SUMMARIZE again on the same writing is not a new try (temperature 0: the same image gives the same answer). Time to answer = each answer's `latency_s` in the report (request start → answer; the panel counts the seconds live).

**D54 (2026-10-25, user request): EXPLORE.** A sixth AI action: the topic of the selected writing (or the whole canvas) and what lies beyond the written words — background, key facts and one connected concept to explore next — in 3 or 4 short lines; not a repeat or a summary. Same single request, worker and panel as the other actions: the model reads the handwriting and explores in one pass (a separate transcribe-then-explore call would add ~1–2 s for nothing). Its answer format (`EXPLORE_SCHEMA`) adds `readable` (boolean) and `topic`; the other five actions keep `SCHEMA`, so their requests are unchanged (tested). When the model reports no confident topic, names none, transcribes nothing but `[?]` marks, or the answer is cut off at the token limit, the code replaces the model's text with a fixed note (`UNREADABLE`: "Could not read a clear topic. Write it larger, or select just the topic word, and try again."): no guessed topic or facts reach the wall. Local backend: EXPLORE's token cap 400 (the others 1024). Panel: 7 buttons in 3 columns (130 × 52 px; longest label 99 px), CLOSE alone at the bottom right as before, the answer area unchanged (374 px); the answer heading reads "EXPLORE: <TOPIC>"; each "- " point on its own line (`point_lines`, added after physical run 1, where the model ran the points together in one line). Files: `ai/client.py` (`ACTIONS["explore"]`, `EXPLORE_SCHEMA`, `schema_for`, `legible`, `answer_from_json`, `no_topic`, `UNREADABLE`, `AIAnswer.topic` / `readable`), `ai/local.py` (schema per action, `EXPLORE_MAX_TOKENS`), `canvas/panel.py` (`PANEL_ACTIONS` + explore, `COLUMNS` 3), `canvas/render.py` (topic heading), `tools/draw.py` (topic in the console summary), README. Tracking, gestures, the pen-lift delay and selection unchanged.
- Dry runs (local model, no projector, 00:35–00:55): first prompt on the design set (4 S2 images, 3 scribbles): topics 4 of 4; scribbles: 2 of 3 gave the note, 1 repeated "[?]" until the 1024-token limit (26.5 s, a "cut off" error); "I Love Pengyien" explored as "a Chinese surname" (invented). Changed (EXPLORE only): one [?] per unreadable part, refuse words not known as a subject, token cap 400, a cut-off EXPLORE answer → the note. After: design set topics 4 of 4, scribbles 3 of 3 the note (one at the cap, 10.6 s); held-out set (S2 try 3, S1 CAT / DOG / SUN, 3 new scribbles): topics 4 of 4 (Cat ×2, Dog, Sun), scribbles 3 of 3 the note (one at the cap, 12.6 s). "Pengyien" is still "a Chinese surname", and dog breed counts differ between answers (340, 700+, 1,000): R35. Times: topics 1.8–3.4 s; scribbles 0.8–3.4 s, 10.6–12.6 s when the cap ends a loop.
- **Physical acceptance (proposed 2026-10-25 before any physical EXPLORE run; the user may change it):** X1: 3 fresh handwritten topics (one word, two words, a short question; one of them chosen with a SELECT loop) → EXPLORE shows the right topic and 3–4 lines that go beyond the writing, judged correct and useful by the user, in 3 of 3. X2: 2 deliberate scribbles → the note and no topic, 2 of 2. X3: SUMMARIZE on one X1 writing unchanged (READ and a summary). Times to answer reported. **Status: built and tested offline; not complete until the physical test.**

### 9.12 Precision and UX mission (user, 2026-10-26): bottom-edge tracking, contact vs hover writing, premium canvas

**Goal (user):** write smoothly across the whole usable canvas (the bottom included), contact writing within the existing accuracy requirements, hover writing measured, improved and validated within a stated operating range, a polished canvas without losing writing space or speed, the AI unchanged, ~50 fps kept. Reliable interaction over demonstrations. Workflow fixed by the user: (1) repository audit, (2) baseline with the **existing** diagnostics, no code change before it, (3) engineering proposal → **stop for approval**, (4) bottom-region tracking, (5) writing accuracy (contact point, hover geometry; independent validation points; operating range), (6) writing ergonomics, (7) UI polish (no major UI rewrite before 4–6), (8) final regression and hardware validation, then a report (what was wrong / changed / improved / passed / open / how to test / next). Mandatory rules as §0 plus: no paid services, AI local and unchanged, no keys in the repo, no bypassing Windows security, **no push without explicit approval**, no new hardware without first showing why the existing setup cannot do it, keep the concepts separate (projector–wall geometry, camera–wall calibration, fingertip landmark, contact point, hover parallax, gestures, stroke filtering, rendering).

**Stage 1 audit (2026-10-26):** camera `camera/manager.py`, `exposure.py`, `locks.py` (MJPG 1080p60, −6 / focus 400 / gain 15, newest-frame thread); hand detection and tracking `vision/hands.py` (tiled search, 2 views per search frame D40, region tracking ≥ 720 px, same-frame confirmation D37, `tip_in_view`) with `tools/tracking_session.py` (`TRACKER_OPTIONS` presence/tracking 0.3, `HandPoints` drops a fingertip outside MediaPipe's view, smoothing); fingertip = landmark 8 in camera px; mapping `mapping/mapper.py` + `calibration/store.py` (H), setup check and recovery `calibration/recovery.py`; gestures `vision/gestures.py` (fold angles, keep band D47, D48 rules); strokes `interaction/engine.py` (7 / 3 frames, lift 0.6 s), `interaction/drawing.py` (tools, toolbar-band and panel filters, selection D53), `canvas/model.py`, `history.py`; rendering `canvas/render.py` (cached strokes, per-frame overlays), `display/projector.py`; UI `canvas/toolbar.py`, `canvas/panel.py`; AI `ai/` (worker thread, off the frame loop). Diagnostics: `devices`, `camera`, `latency`, `calibrate`, `validate`, `recalibrate`, `setupcheck`, `cursor --accuracy`, `handcheck`, `gestures`, `replay`, `draw --trace`. Reliable by evidence: calibration and mapping (recoveries 1.01–1.19 px mean), recovery after moves, 60-fps capture, AI path (S2), selection logic (22 of 22 completed loops). To investigate: bottom-band hand losses (§13.2 2026-10-26), stroke points dropped silently in the toolbar band, hover parallax (never measured with the Kreo), frame rate (38–49 fps overall in recent runs, search frames ~20 ms, 24–32 fps while the AI answers).

**Stage 2 baseline protocol (fixed 2026-10-26 before any run; existing tools only):**
- Software: full test suite. **Result 2026-10-26: 547 passed, 22 skipped, 0 failed** (the 22 need recordings from the other laptop).
- B-1 (nobody in the projection): `latency` (display → camera, 20 flashes), `camera --headless --seconds 60` (capture rate). Power state and a tracking-speed check recorded before every session.
- B-2 accuracy grid, `cursor --accuracy --aim finger --trace --save-every 1 --targets "160,120 640,120 1120,120 160,360 640,360 1120,360 160,600 640,600 1120,600" --labels "TL TC TR ML MC MR BL BC BR"` (bottom row in the real bottom writing band), three times: (a) fingertip touching the wall on the target; (b) fingertip 2 cm in front of the target, (c) 5 cm, set with a ruler held perpendicular to the wall, its end on the target centre. Per target: error (px, and mm once the image size is measured), the 1-s spread, hand found, first detection; a target not reached within 60 px in 30 s counts as a miss. The capture tool is `cursor` (raw cursor, its own tracker defaults: presence/tracking 0.5), so the numbers describe fingertip + mapping, not the drawing app's smoothing.
- B-3 bottom-edge writing, `draw --seconds 240 --trace --save-every 1`: PEN, five horizontal lines left → right at about y 100, 250, 400, 520 and 610 (the last just above the toolbar), slowly, then the same five quickly; then the word BOTTOM written just above the toolbar. Per height band: hand losses, time to re-find, stroke breaks, points dropped in the toolbar band, frame rate.
- **Amendment 2026-10-26 16:12 (before B-3 ran):** B-3 traces guides instead of free lines, and B-4 is added: `draw --seconds 300 --trace --save-every 1 --load data/canvas/guides-b3.json` (5 light-grey guide lines, x 150–1130 at y 100, 250, 400, 520, 610; the last just above the toolbar). B-3: PEN (black), trace each guide left → right slowly, top to bottom, then the same five quickly; fingertip touching the wall. B-4: the same with the fingertip about 3 cm from the wall. Per guide: ink distance from the guide (median, p95, max; projector px), strokes per line (breaks), hand losses, time to re-find, points dropped in the toolbar band, frame rate; touch vs hover compared on the same guides. The rounds b/c showed the fingertip 4× less steady when hovering (still jitter 1.2 → 4.4–4.8 px).
- Geometry (tape measure, by the user): projected image width and height on the wall; camera lens position relative to the projector lens (right, up/down, towards the wall); projector lens and camera lens to the wall.
- Reported separately: capture fps, processing fps, pipeline median / p95, inference median / p95, dropped frames, tracking losses, display → camera latency.

**Proposed criteria for Stage 4 (bottom tracking), awaiting the user:** on a fresh B-3 recording, hand losses in the bottom writing band (y 560–648) per 1000 hand frames no higher than in the top and middle bands; no stroke point dropped without a record; median time to re-find the hand ≤ 0.6 s; processing fps not lower than the baseline; no detection threshold loosened. Criteria for Stage 5 (hover) after the baseline, before any fix.

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
| D8 | 2026-10-08 | DirectShow is the default camera backend on Windows (MSMF selectable) | Usually more reliable control of resolution, MJPG and exposure | **Validated 2026-10-09** on the Brio 100 (D25, §13.2). MSMF measured worse: ignores the FOURCC request, opens in 38–44 s, ~half of its reads are duplicate frames (R22). |
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
| D24 | 2026-10-09 | **Exposure is config-driven.** `[camera] exposure_mode = "manual" \| "auto" \| "unchanged"` + `exposure_value` (DirectShow units, 2^value s). **Phase 1 default: manual −5 (31.25 ms).** Set through DirectShow `IAMCameraControl` (ctypes), verified by read-back, and kept applied by the capture thread: checked every 0.25 s, re-applied when the camera stack resets it (R21). If the camera does not confirm, `CameraManager` raises `CameraError` (the diagnostic `camera` tool warns instead). Manual/auto require `backend = "dshow"`. | Measured: auto exposure with AE priority 1 caps the Brio at ~15 fps in dim light; manual ≤ −5 holds 30 fps. A locked exposure also addresses R7. OpenCV `CAP_PROP_EXPOSURE` cannot read back auto/manual under DirectShow (`AUTO_EXPOSURE` reads −1), so it could not verify the setting. No dependence on the driver dialog. | If the room lighting changes (−5 too dark or saturating); in P1 if fingertip motion blur at 31 ms matters (−6 = 15.6 ms also holds 30 fps, darker) |
| D25 | 2026-10-09 | **Validated Brio 100 mode: DirectShow, MJPG 1920×1080 @ 30, manual exposure −5.** Measured 29.93 fps (60 s, slowest second 29) and 29.83 fps (60 s, slowest second 27, config-driven). | Meets A3 (≥ 25 fps sustained). 1280×720 MJPG measured the same fps; it is the fallback if the latency step shows 1080p costs too much. No 60 fps mode exists. | After the latency measurement (runbook step 10) and the P1 latency budget |
| D26 | 2026-10-09 | `probe.configure()` sets width, height and fps first and the **FOURCC last**; a regression test pins the order | With `CAP_DSHOW`, every later size or fps change renegotiates the format without the FOURCC and the driver silently falls back to YUY2 (Brio: 1080p and 720p at 4.97 fps). Measured: FOURCC first → YUY2; FOURCC after size but before fps → YUY2; FOURCC last → MJPG. | — |
| D27 | 2026-10-09 | **A latency run counts only if it is valid:** every trial detected, and the black/white levels re-measured after the trials still straddle the threshold (and exposure still confirmed). Otherwise `latency` prints NOT VALID and exits 1; such runs are not recorded as results. | The 18:32 run printed a median from 4 of 20 trials (16 missed) without any warning. With a ~275 ms step and a 1.5 s window, a valid setup misses nothing (0 of 120 trials missed in 6 runs). A miss means the threshold no longer described the scene. Stricter, not looser: no threshold was changed. | — |
| D28 | 2026-10-09 | **Setup check before validation:** `validate` first has the 4 calibration corners clicked again; if they differ from the saved calibration clicks by more than the repeatability limit (A6 metric, `repeatability_mean_px` = 2 camera px), it stops and asks for a recalibration; nothing is recorded as a validation. The result is stored in the validation report. | The 19:59 A7 FAIL (mean 5.87 px, every error down-right) came from a setup that moved ~5 camera px after the 19:53 calibration, not from the mapping (test log). Nothing detected it, so it looked like a mapping error. The check does not touch H, the error computation or any threshold. | When 1B detection exists: detect the corners automatically instead of clicking |
| D29 | 2026-10-10 | **Phase 1B, first increment: automatic cross detection, diagnostic only.** `calibration/detect.py` finds the projected cross from its geometry (two fitted arm lines, centre = their intersection; the ring is never used), and rejects with a reason instead of guessing. `python -m invisible_canvas detect` evaluates it on real frames; `calibrate`/`validate` stay manual until it passes. **Acceptance criteria, fixed before the first hardware run:** 24 targets (4 calibration corners at 6 % inset, 20 validation points at 4 % inset), rendered as in `calibrate`/`validate` but without label text, each with a black background frame and 10 single frames. **B1** all 24 detected on the averaged frame and ≥ 95 % of single frames accepted, every rejection with a reason. **B2** no false detection: blank screens and two crosses in one search window are all rejected. **B3** stability per target: single-frame sd ≤ 0.3 camera px and max distance from their mean ≤ 1.0 px. **B4** click-free consistency: H from the 4 detected corners maps the 20 detected grid centres within the unchanged A7 thresholds (required mean ≤ 5 / max ≤ 12, stretch ≤ 3 / ≤ 8 projector px). **B5** agreement with the manual centres (only if the setup still matches the calibration, D28 metric ≤ 2 px): mean ≤ 2.0, max ≤ 4.0 camera px vs the clicked centres (clicks are quantised to 1.25 camera px and carried ~1–2 px human error, so this bounds agreement, not accuracy); otherwise B5 is not evaluable. Edge and interior targets reported separately. | Automating calibration needs a detector proven on real frames first; manual calibration stays the fallback (D16). | After the hardware evaluation |
| D30 | 2026-10-10 | **Phase 1C: automatic calibration and validation, explicit and opt-in.** `calibrate --auto` / `validate --auto` (manual stays the default, `--manual` explicit). **Calibration:** each corner is projected alone, detected (whole frame, black background frame, 10 single frames), and must pass a per-target gate (averaged detection ok; ≥ 80 % of single frames accepted; single-frame sd ≤ 0.3 px and ≤ 1.0 px from their mean, from B3). The 4 points must be ≥ 5 % of the frame apart (no duplicate), a convex quad in TL-TR-BR-BL order (`validate_quad`) with the projector corners' orientation (no swap or mirror). H is fitted by the existing `Calibration.create()` from the 4 corners only; a **held-out check target** at (320, 216), off every symmetry axis, must map back within `required_max_px` (catches a cyclically relabelled assignment, which convexity cannot). Saved with `method: "auto"`, same file format. **Validation:** the D28 setup check with detected corners (same metric and 2-px limit, not weakened), then the 20 held-out targets detected; same statistics and thresholds; report `validation-auto-*.json`, `"mode": "auto"`, per-point detection quality. **Never** a fallback to clicks, old points or guesses: any failure stops with a reason per target; nothing is saved or recorded. `detect` only uses manual reports as its manual reference; `repeatability` only compares calibrations of one method. | B1–B5 passed on real frames; automation removes the 1–2 px human click error. Manual stays as the fallback and the independent cross-check (D16). | After `validate --manual` on an automatic calibration; open question 7 |
| D31 | 2026-10-10 | **Automatic mode is the default** for `calibrate` and `validate` (user decision 7). `--manual` stays explicit; `--auto` is still accepted (compatibility). `calibrate --dry-run` and `validate --simulate-shift` now work without a flag and are refused with `--manual`. An automatic failure still stops with its reasons and names `--manual` as the alternative; it never falls back to clicks. Regression tests: default mode selection, `--auto` compatibility, explicit `--manual`, option conflicts, default commands never request clicks. | Phase 1C passed on hardware, including the manual cross-check (00:44: mean 1.32 / max 2.92). Automation removes the 1–2 px click error. | — |
| D32 | 2026-10-10 | **Automatic-mode setup-check limit: 1.0 camera px evaluated, NOT adopted; 2.0 kept** (user decision 8 asked for evidence first). New config key `[validation] auto_setup_limit_px` (= 2.0), used when the calibration is automatic; manual calibrations keep `repeatability_mean_px` (2.0); config refuses an automatic limit looser than the manual one. New read-only diagnostic `setupcheck`. **Decision rule fixed before measuring:** adopt 1.0 only if (a) a ~10-min no-movement series stays ≤ 0.5 px, (b) simulated moves ≥ 2 projector px are refused at 1.0 in every direction, (c) a real small movement is detected. **Measured:** (a) FAIL: untouched for 8.3 min the scene drifted steadily, variation 0.06 → 1.52 px (mean shift +1.30, +2.40; largest corner 4.46 px); 1.0 refused from 4.6 min (5/11), 2.0 never. (b) PASS: 1-px moves 0.49–0.84 px (pass), 2-px moves 1.08–1.49 px (refused at 1.0), 2,2 and 3-px moves 1.62–1.83 px (refused at 1.0, **passed at 2.0**). (c) PASS: the real drift was caught at 1.0. One of 44 corner measurements was rejected by the stability gate (sd 0.31 > 0.3 px). | 1.0 is a good detector, but on the current mounts the scene really moves ~2 camera px within ~5 min, so it would refuse almost every calibration older than that; 2.0 lets moves of up to ~3 projector px through. The root cause is the drift (R10). Not weakened: 2.0 is the existing limit. | When the mounts are stable: rerun the 10-min series; if ≤ 0.5 px, set `auto_setup_limit_px = 1.0` |
| D33 | 2026-10-10 | **Phase 1D: index-fingertip cursor with MediaPipe Hand Landmarker** (user-approved dependency change). `opencv-python` is replaced by `opencv-contrib-python` at the same version 4.14.0.94 (MediaPipe requires contrib; still exactly one OpenCV wheel, §9.4), pinned `<5` because OpenCV 5.0 is on PyPI and MediaPipe's requirement is unpinned; `mediapipe` 1.1.0 (Apache-2.0) and its dependencies added; `pyproject.toml` and `requirements.lock` updated. Model `hand_landmarker.task` (float16, version 1) downloaded from Google's MediaPipe model storage into `models/` (git-ignored), SHA-256 pinned in `vision/hands.py` and checked at load. VIDEO running mode, one hand, inference on a 960-px-wide copy. Landmark coordinates: normalized (0 = image edge) → camera px = n · size − 0.5 (pixel centres at integers), then the validated calibration H. Cursor states: tracking / holding (≤ 150 ms after a dropout, frozen) / lost (hidden) / outside (hidden); recovery jumps to the new position, never glides. Smoothing (One Euro) is optional and off by default. The automatic setup check runs before tracking. No drawing or erasing. | MediaPipe was the planned P1 hand tracker (D1). Swapping the wheel keeps one OpenCV and the same version. | After the hardware measurements (FPS, latency, accuracy, stability) |
| D34 | 2026-10-10 | **0 % hand detection diagnosed: the canvas was too dark; default canvas grey 40 → 128, brightness pre-check, `handcheck` diagnostic.** The pipeline was checked step by step and cleared: camera frame BGR uint8 1920×1080 → INTER_AREA 960×540 → letterbox 960×960 → RGB, C-contiguous, `mp.Image` SRGB; VIDEO mode with strictly increasing ms timestamps; thresholds 0.5/0.5/0.5 (MediaPipe defaults, unchanged); model SHA-256 verified at load. Positive control (official MediaPipe sample photo through the same `HandTracker`): found, score 0.96. Real hand: grey 40 → 0 %, 80/128/200 → 100 %. In a dark room the projection is the only light on the hand; at grey 40 the canvas region reads 23 against a camera black level of ~16. The MediaPipe NORM_RECT warning is unrelated (it also appears when hands are found). Accuracy test capture radius 4 → 8 px (measured fingertip scatter 1.7–2.4 px rms made 4 px mostly unreachable; the error is still the mean position; no acceptance threshold changed). | Evidence before change: brightness was the only variable that changed the result with the same hand, model and code. | When the room lighting or the projector changes |
| D35 | 2026-10-10 | **Accuracy test without wall contact: "on the target" = the fingertip's shadow on the target centre** (the target's projector ray passes through the fingertip; the shadow and the target are both on the wall, so the alignment does not depend on where the operator stands). Cursor and target ring stay visible. Per-target diagnostics (detection rate, first-detection delay, handedness confidence, hand size, capture frame). **Provisional criteria (user), not validated:** mean ≤ 5 and max ≤ 12 projector px over the 9 targets; no persistent edge-target detection failure; reliable loss/recovery; 60-s free-movement test passes. **Finding:** with a single camera the calibration is exact only on the wall; a hovering fingertip maps to where the camera's line of sight through it meets the wall, not where the projector's ray through it does. The gap grows with the hover distance and the camera–projector baseline and cannot be inferred from the fingertip image: no threshold or calibration change removes it. Homography, thresholds and targets unchanged. | Viewpoint-independent and measurable without contact; the only definition the current hardware can check. | When the parallax approach (hardware/algorithm/hover band) is chosen |
| D36 | 2026-10-10 | **Approved direction (user): camera closer to the projector lens; tiled acquisition; grey 128 + room light as the acceptance conditions; fingertip measured against the projected shadow centre with the cursor visible.** Implemented: tiled acquisition (`--acquisition tiled`, default) with one region track; the shadow-centre reference measured at each capture (`shadow_tip_near`), a run is INVALID unless every target's shadow centre is established; `--withdraw`; rows/columns. Measured: the camera could only move to 18 cm (from ~30); thresholds, homography and targets unchanged. Outcome: acquisition better, 60-s test complete; accuracy run invalid (1/9 shadow centres), parallax 39 px where measured. | User decision after D35 | When the parallax approach is decided (depth measurement or hover band) |
| D37 | 2026-10-11 | **Tracking audit (user request: cursor does not follow the fingertip).** Diagnosis (read-only, saved frames + reports): (1) the 2026-10-11 runs used `--acquisition full`, whose only reacquisition is MediaPipe's palm detector on the whole frame (192 px): on 854 saved frames with a detectable hand it found 55 % vs 95 % for the 720-px tiles, and 0 of 473 live-`lost` frames vs 52; its report showed 0 search frames because full mode never updated the statistics; (2) end-to-end latency ~290 ms is hardware (R4), processing ~13 ms; (3) One Euro beta 0.01 lagged 5.6–8.7 px while moving; (4) a fresh detection on a 640-px region around a search hit found the hand in 81.5 % (720 px: 89.5 %), and an unconfirmed hit was drawn for one frame; (5) the search hit and the region put landmark 8 on different fingers in 6.3 % of frames (R25). Changes: `HandTracker` returns a search hit only after the region tracker finds the hand in the same frame (its landmarks), `Region.around` min_side 720, `HandObservation.view/tip_norm/tip_in_view`, `AcquisitionStats` for both modes (frames, track_losses, tip_outside_view; full: frames after a frame without a hand are search frames), `HandTracker.action`; `CursorUpdate.reason/since_seen_s`, `CursorTracker.transitions/reacquired_after_s`; OneEuroFilter default beta 0.05; `cursor`: an extrapolated fingertip is not drawn, records carry the drawn position and reason, report `transitions`, `reacquired_after_s`, `motion` (lag, still jitter, transient jumps), `--trace` (per-frame JSONL, off by default). Calibration, thresholds, hold time, hardware and display settings unchanged. | Measured on saved frames and replayed trajectories (§13.2, 2026-10-11) | After the D37 hardware verification; R25 once traces show the cause of the live transient jumps |
| D38 | 2026-10-12 | **Landmark-glitch diagnostics, Phase A: observational only.** New pure module `vision/landmark_diagnostics.py`: per frame, in camera px, (1) relative motion = |Δ(landmark 8 − landmark 5)| between consecutive camera frames ÷ palm length |landmark 5 − landmark 0|, flagged > 0.25; (2) extension = |landmark 8 − landmark 5| ÷ |landmark 5 − landmark 0|, flagged < 0.43; combined flag = OR (no decision when neither is True and one is undecided). No decision (and a reset of the temporal baseline) on no hand, missing/NaN/None landmarks, palm < 2 px, a skipped camera frame, a frame after an unusable one, or a fresh search acquisition. Handedness is not an input. `cursor` runs it after the cursor update and only records it: trace `diag` per frame, report `landmark_diagnostics` (counts, no-decision reasons, episodes of consecutive flagged frames with start/end, duration, frames, peak motion, minimum extension, reasons). The cursor, smoothing, states, tip validity, mapping and the jump counter are unchanged (verified bit-identical on the four 2026-10-11 traces). | Offline analysis of the four traces (2026-10-12): thresholds from glitch-free frames (relative motion max 0.168, extension min 0.48 on 13,998 clean frames; leave-one-run-out 0.24-0.25 / 0.43-0.44); 9/9 labelled glitch events flagged within 2 frames, plus the sustained misfit at 21:24 74.1-77.1 s (25/52 frames); the old jump counter caught 2/9. | Phase B (treating a flagged frame like an invalid fingertip) only after recordings with deliberate finger bends, fast flicks and pointing towards the camera; user approval |
| D39 | 2026-10-12 | **Automatic calibration recovery after a moved setup (portability), validated before it is saved.** New pure module `calibration/recovery.py` and command `recalibrate [--dry-run]`; `cursor` runs the same recovery when its setup check refuses (`--no-recalibrate`: the D28 stop). Steps: (1) candidate from the four corners the refused setup check has just detected (whole-frame detection, D29; their old camera positions are never used), through the existing `associate_corners` (missing, ambiguous, unstable, duplicate, not convex, wrong order, mirrored) and `Calibration.create` (`method: auto`, same projector points); (2) held-out check target within `required_max_px` (D30); (3) the 20 held-out grid targets detected and mapped through the candidate must meet the A7 required limits (mean ≤ 5, max ≤ 12 projector px), as `validate` judges; (4) a setup check against the candidate after the validation must pass (automatic limit, 2.0 camera px), so nothing moved during recovery. Only then `commit_recovery`: refuses unless accepted and unless `current.json` still holds the refused calibration; archives that one in the history (never rewrites an entry); atomic write of the candidate. Any failure: the calibration directory is untouched, the step and reason are printed with operator hints, `cursor` does not start. Report `calibration-recovery-*.json` every time. No threshold, detector parameter or file format changed; no offsets; nothing simulated in the production path. | Root cause of the 2026-10-12 19:19 refusal (`setupcheck-20261012-191953`): a real move, not a checker fault. All four corners were detected (whole frame, worst single-frame sd 0.06 px) at +72…+77 camera px in x with ±8 px vertical change at the bottom corners (perspective), variation 37.26 px vs limit 2.0: the refusal is correct (the old H would be ~66 projector px wrong on the grid). What was missing was a recovery path: `cursor`/`validate` stopped and asked for `calibrate`, which saves after one check target without the held-out validation. Offline from the report: the detected corners form a valid quad and the moved canvas lies inside the camera image (x 231–1658, y 147–962). | Default-on recovery in `cursor` after the hardware validation (open question 13); whether to recover after a failed corner detection (not done: the same corners would be needed) |
| D40 | 2026-10-12 | **Hand-search budget: at most 2 search views per search frame, in turn** (full frame, tile 1..8, full frame, ...; every new search, at start or after a dropped region, begins with the full frame; first hit wins). Replaces full frame + 2 tiles on every search frame. Unchanged: detection/presence/tracking confidences, region tracking and patience, D37 same-frame confirmation, the tiles, the report keys (`search_views` now ≤ 2 per search frame). | `cursor-20261012-201357` (30 s, tiled): no-hand frames pipeline median 53.0 ms (p95 69.3) = queue age 15.5 ms + inference 36.0 ms; hand frames 11.6 ms. 382 views = 128 search frames × 3 − 2 (the full-frame hit stopped after its first view); 131 no-hand frames = 126 search misses + 1 tile hit not yet confirmed by the region tracker + 4 region-tracker misses (derived from the counters; no trace). Offline on saved no-hand frames, one view costs ~10.5 ms whether full frame or tile (palm detector, 192×192 input; preparing the image < 1 ms), so 3 views exceed the 33-ms frame interval: the loop fell behind (117 frames in 4.88 s, ~24 fps, while searching). The full frame cannot be dropped: on 1,347 saved frames it found a hand no tile found in 42 (mostly near the image edges or large hands); repeated every frame it mostly repeats its miss (the 27.6 s loss: 10 search frames, full frame missed every time, a tile found it). Estimate, not measured on hardware: ~21 ms of search per frame; each view recurs every 4.5 search frames (~150 ms at 30 fps, vs every 4 frames ≈ 167 ms for the tiles before), the full frame every ~150 ms instead of every frame. | Hardware comparison with the same 30-s run; if reacquisition gets slower, a search that starts near the last region (not done) |
| D41 | 2026-10-17 | **Camera changed to the Kreo Owl 4K Pro (user decision), replacing the Brio 100 for now.** D14's rule stays: capabilities are measured, not assumed. Until §9.9 is done, every camera-dependent setting is only a starting value from the Brio: `[camera] match = "brio"` (will not find the Kreo, so the tools stop and list the cameras, by design), MJPG 1920×1080 @ 30 (D25), manual exposure −5 (D24), the exposure re-application behaviour (R21), the 0.8 s settle time (based on the Brio's 275 ms latency), the detector's arm-width margins (D29) and the parallax geometry (§13.3). The phase status is unchanged, but A1, A3–A7, B1–B5, the Phase 1C results and the Phase 1D measurements are Brio results and are re-run per §9.9. No config change before the Kreo is measured. | User decision | After the §9.9 measurements |
| D42 | 2026-10-19 | **Kreo Owl 4K Pro settings (user decisions: 1080p @ 60 fps; lock focus).** `[camera]`: match `"owl 4k"` (DirectShow "Owl 4K PRO Camera"), MJPG 1920×1080 @ **60**, manual exposure **−6** (15.6 ms, the longest that fits a 16.7-ms frame), and new keys `focus_mode`/`focus_value` = manual **410** (`camera/focus.py`). Measured: 1080p @ 60 delivers 60.1–60.5 fps (720p @ 60 only 30, 1440p/4K 30); through `CameraManager` −6 and −7 give 60.1–60.2 fps (slowest second 60), −5 only 31.6; exposure confirmed by read-back and never reset by the camera stack (re-applied 0×, unlike the Brio, R21). Autofocus hunted 719 → 399 → 64 → 499 and settled at 499; checkerboard sharpness (Laplacian variance) peaks at 400–420 (531 at 410) and is 122 at 499, so focus is locked at 410 (**changed to 400 at 12:27**: a second sweep after the setup was rebuilt peaked at 400 = 966, 410 = 95 %; the night sweep had 400 = 99 % of its best); the keeper visibly re-applied the configured focus when it was changed during streaming. **Gain is not locked yet:** at −6 and gain 0 the image is dark (grey-128 canvas 5.7, white 69.8, dark room); gain (`IAMVideoProcAmp`, 0..15, manual only) 8 / 12 / 15 → grey-128 26.5 / 43.3 / 54.4, white 105.7 / 129.8 / 145.6, temporal noise sd 0.46 → 0.86, 60 fps kept, no saturation. Auto exposure reaches grey-128 137 at 60 fps but follows the projected content (white read darker than grey 200), so it stays unusable (D24). No threshold changed. | Measured on hardware (§13.2, 2026-10-19) | Gain lock (open question 16); canvas grey level for hand detection (`handcheck`); re-sweep focus if the camera–wall distance changes |
| D43 | 2026-10-19 | **Gain lock (user decision): `[camera] gain_mode = "manual"`, `gain_value = 15`.** The focus lock is generalised into `camera/locks.py` (one `Setting` per locked property: focus on `IAMCameraControl`, gain on `IAMVideoProcAmp`; exposure keeps its own module). 15 is the Kreo's maximum: at exposure −6 it gives white 145.6 (the Brio's white was 114–143) and grey-128 54.4, 60 fps kept, temporal noise sd 0.86, no saturation (D42 sweep). Hardware check: `camera --headless --seconds 10` → exposure manual −6, focus manual 410, gain manual 15, all confirmed at open and end, re-applied 0×; 60.24 fps, slowest second 59, 0 failed reads. The grey-128 canvas (54) is still darker than with the Brio (142): the hand-tracking canvas level is to be chosen with `handcheck` (D34). | User decision; D42 measurements | If the room light changes, or `handcheck` shows the canvas too dark for hand detection |
| D44 | 2026-10-22 | **Phase 2 design approved (user): gesture-driven drawing.** Index finger only = draw, all five fingers open = erase (only the ink touched, strokes split), pinch = select (toolbar press; pick up / move / drop strokes, pulled forward from Phase 3; lasso/AI selection stays in Phase 3), any other shape = hover; the cursor always follows the hand. Bottom-edge toolbar. Debounced modes (§9.10), shape recognition from MediaPipe 3-D world landmarks, white canvas. Acceptance G1–G7 fixed before any run. | User decision; §6 interaction model; Kreo brightness (D43) | After the G1 recording (thresholds) and G2–G7 |
| D45 | 2026-10-22 | **Phase 2 implementation choices, from evidence.** (1) Finger state = **fold angle** (palm direction wrist→knuckle vs finger direction knuckle→tip), not straightness: on the user's 66 saved frames of 2026-10-21 (mostly pointing) straightness gave POINT in 10/66 (world) because the curled fingers fold at the knuckle (straightness 0.7–0.85), while fold angles separated them (index median 17°, middle/ring/little 101/118/89°) and gave POINT in 53/66; the other 13 frames were checked by eye: genuinely open hands while entering, two fingers, transitions, and one MediaPipe misfit. Thresholds: extended ≤ 45°, middle/ring curled ≥ 60°, little finger ≥ 45° (it stays looser when this user points). (2) 3-D world landmarks (view-independent; 2-D fallback). (3) Pinch needs the index fold ≤ 110°: in a fist the thumb lies next to the curled index tip (found by a synthetic test). (4) The engine buffers the confirming frames, so a stroke starts where the shape began. G1–G7 unchanged. | Offline evidence (§13.2, 2026-10-22) | After the G1 recording |
| D46 | 2026-10-22 | **Gesture plan revised (user decision): one gesture + toolbar tools** (§9.10 revision). Index finger = use the tool (PEN / ERASER / MOVE); anything else = cursor; toolbar buttons pressed by holding the cursor on them (1 s, CLEAR 2 s). Enter frames 4 → 7. Revised criteria G1′, G4′, G5′ fixed before any run. | G1 run 1 (§13.2): pinch not observable from behind the user (pinch ratio inverted vs a fist), other shapes 72–92 %; open hand and fist almost never read as POINT (1/335, 3/402, longest run 3 frames); pinch-like misreads lasted up to 6 frames, two-finger up to 14, so 7 confirmation frames block the observed pinch-like runs; a stroke still starts where the shape began (buffered start). | After G1′ |
| D47 | 2026-10-22 | **Keep-drawing band (user decision after G3 run 1):** starting a stroke stays strict (POINT: index ≤ 45°, middle/ring ≥ 60°, little ≥ 45°, 7 frames); once in DRAW, a frame continues the stroke if index ≤ 60°, middle/ring ≥ 45°, little ≥ 30° (thumb ignored); 3 frames outside the band (or no hand for 0.15 s) end it. `GestureParams.keep_*`, `HandShape.keeps_point`, `HandInput.keeps_draw`. | G3 run 1 (§13.2): strokes broke while the user was still pointing (index fold up to ~53°, middle down to ~54° while drawing); real lifts and the open hand are far outside the band (fist index ~89°, open middle ~38°). Replay of the recorded measures: G3 run 34 → 21 strokes, breaks < 1 s 16 → 6; the G2 PASS run unchanged (0 strokes). Trade-off: a half-open hand keeps drawing; lifting the pen needs an open hand or a fist. | After fresh G1′ and G3 runs |
| D48 | 2026-10-22 | **Multi-angle pointing (user decision after G1′ runs 3–4):** record the pointing angles on video once, replay offline to improve tracking (keep / re-acquire a pointing hand) and view-robust classification, then a fresh live test G1″ (criteria fixed before any code, §9.10). | The user's natural pointing (upward, back of the hand to the camera) gave 54–75 % POINT and long stretches without a hand (G1′ runs 3–4); single-frame offline tests do not represent the live tracker (the run-2 frames that were 99.3 % POINT live are mostly not found or read as pinch one frame at a time), so improvement needs recorded video. | After G1″ |
| D49 | 2026-10-22 | **Pen-lift delay (user decision after G3 run 2):** in DRAW the pen lifts only after 0.6 s (`EngineParams.lift_s`) without a frame that continues the stroke (other shapes and no hand alike; at least the 0.15-s dropout hold); a shorter interruption is bridged with a straight join and its frames are never drawn. Starting a stroke unchanged (7 strict POINT frames). | G3 runs 1–2: strokes broke on 0.2–1.1 s interruptions while the user kept pointing (finger turned towards the wall, misreads, lost hand); deliberate lifts took ≥ 1.1 s. Engine replay of the traces: G3 run 2 20 → 16 strokes, run 1 34 → 17, G2 runs 0; G1″ run 1 re-evaluated: still PASS, 0 DRAW frames in OPEN/FIST holds. Cost: re-pointing within 0.6 s of a deliberate lift joins the two strokes; the cursor stays in DRAW 0.6 s after a lift. | After a fresh G3 |
| D50 | 2026-10-23 | **Light on the hand (user decision: after the Phase 2 tests, before Phase 3):** plain white projected over the tracked hand (landmark outline + 25 px, motion look-ahead ~0.26 s, held ~1 s after a loss); ring cursor around the fingertip outside the light, dwell shown as an arc; `--no-light`. Acceptance G8 (§9.10) fixed before code. | Projected content on the hand lowered hand finding (dark room: 62 % over ≥ 8 % dark vs 100 % over white; with a room light 96 %) and showed a distorted copy of drawings on the hand (§13.2). | **Off by default since 2026-10-23 (user decision after G8 run 1)**: kept as an opt-in (`draw --light`, `gestures --light on/ab`); revisit with a light that also helps a hand that is not yet tracked |
| D51 | 2026-10-23 | **Phase 3A approved (user): AI summarize on selected writing** (§9.11): SELECT loop, AI panel (summarize, explain, simplify, examples, questions), Claude Opus 5.5 via the official `anthropic` SDK on an image of the selected strokes, structured output, background worker, off by default (`--ai`), acceptance S1–S5 fixed before code; new dependency `anthropic`. | User decisions 2026-10-23 (Claude API as an optional function; Phase 3 requirements in §9.10); a multimodal model reads handwriting directly, so no OCR library (open question 4) | After S1–S5 |
| D52 | 2026-10-23 | **Free of cost (user decision): the AI runs locally** — Ollama + `qwen3-vl:8b` on the laptop GPU via Ollama's local HTTP API (stdlib, no Python dependency); `[ai] backend = "local"` by default, the Claude backend (D51) kept as an option, off. S1–S5 unchanged. | The user wants no charges; the Claude API is paid per request. The RTX 5070 (12 GB) runs an 8B vision model; the model choice from the Ollama library pages (§9.11) | After S2 (handwriting reading quality) |
| D53 | 2026-10-24 | **SELECT loop closed at its tightest point** (user-approved): `close_loop` keeps the path between the closest pair of points from the loop's first and last third; the lead-in and run-on are dropped before the hit test (§9.11). S1 criterion and pen-lift delay unchanged. | S1 run 1: both wrong selections (2 of 12 completed loops) came from the lead-in; offline on the recorded loops 12 of 12 exact, stable for windows of 25–40 % | After S1 run 2 |
| D54 | 2026-10-25 | **EXPLORE action (user request):** topic + background, key facts and a connected concept in the same single request; its own answer format with `readable` / `topic`; no topic read with confidence (or a cut-off answer) → a fixed note, never the model's text; panel buttons in 3 columns, answer area unchanged; the other actions unchanged (§9.11). | User request 2026-10-25; one call reuses the handwriting reading; the code-level note keeps guessed topics off the wall (the model's own judgment was not enough in the dry runs) | After the physical test X1–X3 |

---

## 11. Risks and known issues

| ID | Risk | Mitigation | Status |
|---|---|---|---|
| R1 | Python not installed | Step 1A.0 (winget per-user) | Resolved 2026-10-08 |
| R2 | Camera choice | Brio 100 chosen (D14); measure it | Resolved |
| R3 | Projector auto keystone or auto focus re-triggers and invalidates the calibration | Align physically, keystone off (D13); recalibrate after any change; drift detection (P3) | Open |
| R4 | Input lag and image processing in the Android projector | Game mode on, enhancements off; `latency` measures it. **Measured 2026-10-09:** display→camera 275 ms median in total. The camera path is bounded at ≤ ~194 ms median (exposure-step test), so the display path (Windows compositor + HDMI + projector) is ≥ ~80 ms, plausibly ~80–150 ms. Projector picture settings not yet checked (§2.3); A/B with `latency` is the next step. | Open |
| R5 | 150 % Windows scaling distorts window coordinates | Per-monitor DPI awareness (D7); projector display at 100 % | Planned |
| R6 | Meta Virtual Monitor is listed as a display | Explicit projector identification (§9.7); virtual displays excluded | Planned |
| R7 | Webcam auto exposure, white balance or focus drift as projected content changes | Lock via config/driver dialog if the Brio 100 allows it; measure. **2026-10-09:** exposure is locked by config and kept applied (D24); the Brio offers manual exposure −11..−2. White balance and focus are not addressed yet. **Gain is not locked by manual exposure (measured 2026-10-09):** it stays wherever auto exposure last left it, so projected white at exposure −5 read 143 in one session and 114 in later ones (after an auto-exposure session). Levels are stable within a session. Gain lock through config is a candidate follow-up. **Kreo (2026-10-19, D42):** gain is manual-only 0..15 and sits at 0 under manual exposure, which leaves the 60-fps image too dark (grey-128 canvas 5.7); white balance is auto (1800..10000 settable). A gain lock is now needed (open question 16). **Locked since D43** (manual 15, kept applied). White balance and focus: focus locked (D42); white balance still auto. | Exposure mitigated; gain, WB and focus open |
| R8 | Lens distortion causes error near the edges | A7 error map shows it; 1B adds undistortion if needed. **2026-10-10 (automatic, click-free):** residuals ~1.0–1.3 projector px mid-span (x = 345 and 934, pointing towards the centre) and 0.1–0.6 px near the calibration corners, a pattern consistent with mild lens distortion that a 4-point H cannot model. Well within stretch; N-point fit or undistortion would reduce it if a later phase needs it. | Watch |
| R9 | Surface not flat/rigid, or a glossy whiteboard creates hot spots | Rigid, flat, matte surface; check saturation | Open |
| R10 | Camera, projector or surface moves after calibration | Rigid mounts; recalibrate; drift detection (P3). **Happened 2026-10-09:** ~5 camera px between the 19:53 calibration and the 19:59 validation (cause not identified), failing A7. Mitigation added: setup check before validation (D28). Measured afterwards: corners stable within ~1.3 px over 3 min. **Happened again** after the 23:24 A7 PASS: by 23:46 every target sat ~(+65, −11) camera px from the 23:20 calibration (setup-check variation 53 px). Over the next ~3 min the detected centres moved ≤ 1.0 px. **A third time** between 00:07 and 00:29 on 2026-10-10: all corners +22.8…+25.4 camera px in x (automatic setup check refused the 00:02 calibration, variation 12.39 px). Afterwards a slow creep of ~0.8–1.7 px (mostly +y) between 00:31 and 00:35. **Measured untouched drift (D32):** 01:02–01:10 on 2026-10-10 the corners drifted steadily, setup variation 0.06 → 1.52 px (largest corner 4.46 camera px in 8.3 min); between calibrations 00:36→01:02 and 01:11→01:20: 0.94 and 0.98 px. Mapping error grows with calibration age; the stricter automatic limit is blocked by this. **A fourth time** between 01:51 and 01:59 on 2026-10-10, during the hand session: corners +76…+84 camera px in x with a slight rotation (variation 39.9 px); the setup check refused `cursor` (as designed), `setupcheck` reproduced it, recalibrated automatically at 02:00:32. **Fifth/sixth time:** between 02:00 and 14:05 the setup changed substantially (variation 71.35 px; the projection now fills 48 % of the camera frame instead of 67 %); between 14:08 and 14:32 a uniform drift of (−7, +3) camera px (setup check 0.14 → 3.71 px across the session). **D36:** camera moved deliberately (15:00); after the 15:19 calibration a steady creep: 0.04 → 0.30 px in 100 s (stability check), 0.72 px by 15:36. Still on a bottle. **Seventh time:** before 19:19 on 2026-10-12 the corners moved +72…+77 camera px in x with ±8 px vertical change at the bottom corners (setup variation 37.26 px, `setupcheck-20261012-191953`). **D39:** recovery is now automatic and validated (`recalibrate`, `cursor`); it does not fix the mount, and a setup still moving during recovery is refused (confirmation step). **Kreo setup:** moved ~(+185, −138) camera px between 2026-10-19 and 10-21; on 2026-10-22 00:23 variation 12.78 px and at 00:28 24.37 px (still changing; corners moved outward, i.e. the projection grew in the camera image: camera or projector moved, or projector zoom). | Open |
| R11 | Projected light on the hand degrades hand detection | **Inverted on this setup (D34):** the projection is the hand's only light; too little light, not too much, stopped detection (grey 40 → 0 %; 80–200 → 100 %). Default canvas grey 128; `cursor` warns when the canvas region reads < 25. **Remaining:** a hand reaching in from the unlit surround (left edge, top-left corner) has its palm in the dark and is acquired late or not at all (24 % of frames at the top-left target). **D35:** the main cause is the palm detector's input (the whole frame scaled to 192×192, ~10 camera px per detector px; a hand is ~20 px there, an unlit palm leaves only the fingers): on saved frames cold detection found the hand in 26/74 full frames vs 55/74 with 2×2 tiles, and 8/12 vs 0/12 top-left frames with tight crops. A ceiling light raised detection to 93.4 % (left column 77/100/100 %) with 2 tracking losses, vs 74.9 % and 25 losses in daylight alone. **D36: tiled acquisition** (offline: found 13/23 visible-but-lost hands vs 0/23, 0/202 false positives; hardware: first detection after activation median 1.84 s vs 2.24 s full frame incl. reach, 0 false positives in 30 s). Cost while searching: ~25 fps, capture→projector ~51 ms | Mitigated (1D) |
| R12 | Fingertip hover parallax | **Confirmed as the dominant accuracy error (D35).** Single camera: the hover distance is not observable from the fingertip, so the cursor (camera line of sight → wall) and the projector ray through the fingertip (where its shadow falls) disagree by ≈ hover distance × baseline / distance to the wall. Measured: shadow 25–50 camera px from the fingertip at the bottom row (night frames; 21–41 projector px); with the shadow on the target, cursor errors 25–55 projector px at the bottom row (runs 2 and 4); pointing from arm's length puts the shadow > 200 camera px away. Options: camera at the projector lens, hover-distance measurement (shadow, stereo, depth), or a hover band. **D36:** camera moved to 18 cm (closest possible, projector top unusable); with the shadow centre on the target the cursor was still 39 px away (T4), implying a ~25–35 cm hover. Baseline ≤ ~3 cm would be needed: not reachable with a separate webcam | Open (1D) |
| R13 | Hybrid graphics: the HDMI port may be wired to the NVIDIA GPU | Usually transparent; check first if the projector display misbehaves | Watch |
| R14 | Unknown Brio 100 limits (modes, 60 fps support, focus type, exposure-lock support) | Diagnostics (1A.1) and `camera` (1A.4) measure them. **Brio only; since D41 the Kreo's limits are R26.** **Measured 2026-10-09:** MJPG 1920×1080 and 1280×720 reach 30 fps with exposure −5/−6/−7 (smaller MJPG sizes, 960×544 and 640×480, measured only under auto exposure: 15 fps); YUY2 1080p/720p 5 fps, 640×480 15 fps under auto exposure; no 60 fps mode (60 requests report 60, deliver ≤ 30); exposure −11..−2, auto and manual, lockable (D24). Focus/autofocus not readable via OpenCV (−1). | Mostly resolved; focus type open |
| R15 | Manual click error inflates the 1A accuracy numbers | Loupe + arrow-key nudging; 1B automatic validation separates mapping error from click error. 2026-10-09: the validation clicks were within ~1–2 camera px of the detected target centres (rms 1.86 px), all made in the 0.80× view without the loupe. **1B note:** at the 4 % validation inset the top/bottom targets' rings are clipped by the canvas edge, which biases a ring-inclusive centroid by ~6–9 px; 1B detection must use the cross only (or the ring must fit). **Addressed by D29:** the detector never uses the ring; clipped-ring targets are detected on real frames. Also found: `validate` draws the label of right-column targets across the cross's upper arm (harmless for clicking; detection screens omit labels, and the line fit drops stray pixels). | Open (manual path); detector side addressed |
| R16 | Four virtual Meta Quest DirectShow cameras shift device indices | Name-based camera selection (§9.7); virtual cameras are not probed by default | Mitigated |
| R17 | DirectShow quirks: each open takes about 2 s; the driver-reported FOURCC is not reliable (the built-in camera reports YUY2 at 1080p30 even when MJPG is requested, whatever the set order). **Corrected 2026-10-09:** on the Brio 100 the reported FOURCC matched the measured behaviour in every run (YUY2 ↔ 5 fps at 1080p, the USB 2.0 limit; MJPG ↔ 15/30 fps). The MJPG→YUY2 reports were the set-order bug (D26), not unreliable reporting. "Whatever the set order" did not include FOURCC strictly last; the built-in ACER camera is not on the current machine to re-test. Driver-reported **fps** is still unreliable (reports 60 for a 15 fps stream). Brio opens take 4–7 s (up to 9.9 s on 2026-10-10). **2026-10-10:** 2 of 5 opens started within a few seconds of the previous session's release failed (exit 2; the one whose message was captured: "opened but delivered no frames"); a retry a few seconds later worked. | Trust measured frame size and fps; open the camera once per session; wait a few seconds between sessions | FOURCC part resolved; open time and reopen failures open |
| R18 | GUI loop work eats the latency budget (one slow per-frame op, 30 ms, doubled frame age) | D21; profile stage by stage before optimizing; P1 must budget the main loop | Watch |
| R19 | Fullscreen geometry verified only on the laptop panel so far, not on the projector | Step 2 of the §9.8 runbook. 2026-10-09: user visual check on the projector passed (§13.2, A2) | Partly resolved |
| R20 | A second process holding the camera (a forgotten `camera` window) made the Brio deliver exactly 1 frame/s (~1000 ms gaps, 0 failed reads); MSMF then fails to start (0xC00D3704) | Run one camera tool at a time; before measuring, check for leftover `python -m invisible_canvas` processes. **Again 2026-10-10 14:00:** a `camera` preview held the Brio and `cursor` crashed on a missing frame; tools now stop with a clear message (`current_seq`) | Watch |
| R21 | The Windows camera stack resets the Brio's exposure to its stored value (−4, auto) about 1 s and again about 3 s after **every** stream start, so a single set at open is lost (measured: read-back said manual −5, the run delivered 15 fps). Source not identified (possibly Windows' per-camera default settings); not verified. | `ExposureKeeper` (D24) re-applies within 0.25 s, 1–2× per session, and the count is reported. The first ~2 s of a session can run on auto exposure (measured first seconds: 27 and 28 frames). | Mitigated |
| R22 | With MSMF, about half of `read()` calls return the previous frame again, so a read count overstates fps (29.8 "fps" = 15 real) | DirectShow is the validated backend (D8/D25); its reads were all new frames (0 duplicates measured) | Watch (only if MSMF is used) |
| R23 | The automatic fingertip-shadow finder is not reliable on real frames (D35): the index shadow is often hidden behind the other fingers (open hand) and a lit room gives wrong matches | Kept experimental (`--shadow-check`, off); capture frames saved for visual checks | Open |
| R24 | The shadow-centre reference cannot be established at most targets (D36): at the bottom row the fingertip's shadow falls behind the hand (hidden from the camera and the operator), in room light it is pale (shadow 143–148 vs canvas 190–194), and the operator often aims the fingertip instead | Run marked INVALID rather than guessed; needs another reference or a dark room **2026-10-12 20:44 (camera 18 cm right of the projector lens, dark room):** 0/9 established; in the 8 saved captures no near-black strip lies beyond or beside any index fingertip (the hand's shadow shows only at the upper/right edges of the hand, which are farther from the wall), and every target centre is lit, so the shadow was not on the target either. Geometry: the camera sees the shadow shifted towards its own side (right, plus any unmeasured vertical offset) by ~18·h/(160−h) cm; for a finger pointing left that is back along the finger, i.e. hidden at any hover. No detector defect found (the hidden case is covered by `test_a_shadow_hidden_under_the_finger_is_not_established`). | Open (1D): the reference is not executable at this geometry |
| R25 | MediaPipe sometimes labels another finger as the index (landmark 8): on saved frames a search hit and the region around it disagreed by > 30 px in 6.3 % of frames, with the wrist within ~8 px (finger identity, not position); open hand 14 %, fist 18 %, pointing 4 %; the handedness label differed in 54 % of those vs 12 % otherwise. Live: transient 25–70 px jumps during region tracking (85 in `cursor-20261011-172832`, 32 in -171849, 0–5 per full-mode run) | D37: the first point after acquisition comes from the tracker that follows the hand; point with the index finger, other fingers curled; `--trace` records wrist, index MCP/PIP/tip, middle and ring tips to attribute the live jumps before any filter is added. **D38 (diagnostic only):** offline the glitches show as the index tip moving against its own knuckle (> 0.25 palm per frame) or an implausibly low extension (< 0.43); also found: a sustained skeleton misfit (21:24 74.1–77.1 s, finger pointing up, cursor ~55 projector px off for ~3 s) that no jump counter can see. Both are now recorded per frame and as episodes; the cursor is unchanged | Open (1D): detection in place, no mitigation |
| R26 | Kreo Owl 4K Pro capabilities unknown (D41): DirectShow name, MJPG modes and real fps, exposure control through `IAMCameraControl`, exposure resets, autofocus behaviour, latency, field of view and lens distortion. A 4K-class mode may exceed the USB bandwidth or the CPU MJPG decode budget; a hunting autofocus moves image features between frames | §9.9 measures each item before any setting is changed. **2026-10-19:** modes, exposure, focus and gain ranges measured (D42); latency, field of view / distortion, detector margins and hand detection still open | Open |
| R27 | The laptop sleeping during a running session: the HDMI link drops (the projector disappears from Windows), and on wake the camera device is re-created, so the session's DirectShow control handles fail ("the camera has no exposure control"): exposure, focus and gain are no longer kept, while frames continue (seen 2026-10-19: one `camera --preview` session, 37,442 s with a 22,546-s gap; the manager logged the loss as designed) | Disable sleep for sessions; restart the tools after any sleep (a new open applies and confirms all three again) | Open |
| R28 | The WZATCO's Android system can overlay its own blue mouse pointer on the HDMI image (it showed in black projections too): it hides whatever is projected under it. On 2026-10-19 it sat at about projector (605, 360) and broke one cross of the B2 two-cross control, which then counted as a single cross | Switch off the remote's mouse mode or move the pointer off the canvas before sessions; check a black projection for it | Open |
| R29 | Keep-drawing band (D47): once drawing, a half-open or loosely pointing hand keeps the stroke going, so a lazy pen lift adds a tail, and a late shape change at a G1′ prompt can leave DRAW on for a frame (the G1′ run 2 recording replayed with D47: 1 DRAW frame at the start of an OPEN hold, the user still pointed until 30 ms before it). Hand dropouts > 0.15 s and index misreads of 80–90° still break strokes. | Lift the pen with a clearly open hand or a fist; fresh G1′ and G3 runs decide; no further loosening without new evidence | Open (2026-10-22) |
| R30 | Pointing recognition depends on the pointing posture at this camera position (beside the projector, seeing the back of the hand): finger flat and sideways along the wall, side of the hand to the camera: 99.3 % POINT (G1′ run 2); pointing into the wall: the finger is hidden behind the hand (no hand found, or read as a pinch/fist: G1′ runs 1 and 3); pointing upward with the back of the hand to the camera: often no hand found (G1′ run 3) and strokes break (G3 run 1). Lowering MediaPipe confidences does not help (no hand at 0.2 on the run-1 frames). | User guidance (§9.10 posture); the on-screen "hand: seen" indicator; long term: a camera position that sees the hand from the side (open question) | Open (2026-10-22) |
| R31 | D48 trade-offs: (a) the two-view index rule makes a deliberate pinch seen from behind read as POINT more often (G1 run 1 pinch prompt 11.9 → 19.8 % of frames, longest run 6 → 15 frames: a pinch can now draw); (b) presence/tracking confidence 0.3 may keep a hand tracked longer after it leaves or on a hand-like shape (not measured: no recording without a hand); (c) some up-left poses seen from behind are not detected at all (replay: 14–26 % in one round whatever the setting). (d) the phantom rule also fires on an open hand with the fingers together (G2 run 4: 490 frames; harmless, ring/little extended), so index + middle held together with ring and little curled read as POINT. | Open hand or fist to stop drawing (unchanged, §9.10); G1″ PASS and G2 run 4 PASS with D48; (c) is a model limit at this camera position (R30) | Open (2026-10-22) |
| R32 | D49 resumed a stroke on a continuing frame that arrived just as the 0.6-s window closed, because the window was only checked on non-continuing frames: after a real lift, a hand passing through a pointing-like pose drew a straight join from the lift point (G3 run 4: ~175-px tail on the S). (L and V joined in G3 run 3 is a different case: a 0.58-s pause inside the window.) | **Fixed 2026-10-22:** the window is checked on every frame (`interaction/engine.py`); a regression test reproduces the case (fails on the old engine). Replay of all G2/G3 traces: G3 run 4 still 10 strokes with the S ending at its real end; other runs unchanged (G3 runs 1–3: 17, 16, 16; G2: 0). The approved variant (resume only after 3 continuing frames) was rejected on the data: G3 run 1 17 → 21, run 3 16 → 18 (2 frames: 19, 16). Pause ≥ 1 s between shapes still advised (lift_s). | Fixed (2026-10-22); fresh G3 to confirm |
| R33 | **Windows Smart App Control blocks MediaPipe** (2026-10-24 21:19): `draw --ai` failed at start with `OSError: [WinError 4551] An Application Control policy has blocked this file` loading `.venv\Lib\site-packages\mediapipe\tasks\c\libmediapipe.dll` (61 MB); Code Integrity events 3077/3033 name it; `HKLM\SYSTEM\CurrentControlSet\Control\CI\Policy\VerifiedAndReputablePolicyState` = 1 (enforced). The same file loaded on 2026-10-23: the policy changed (Smart App Control can leave evaluation mode by itself), not the project. OpenCV loads; all hand tools (`draw`, `cursor`, `gestures`, `replay`) need the DLL. | User decision (a Windows security setting; never bypassed by the project): (1) turn Smart App Control off (Windows Security → App & browser control; on many Windows 11 versions it cannot be turned on again without a reset), or (2) keep it on and replace MediaPipe with a tracker on signed components (e.g. ONNX Runtime): large rework, all D33–D48 tuning to redo | **Resolved 2026-10-24 (user decision):** the user turned Smart App Control off (registry state 1 → 0, verified); `libmediapipe.dll` loads and `HandTracker` runs again. Other protection unchanged: McAfee antivirus on and up to date (Defender passive), Windows Firewall on for all profiles |
| R34 | **SELECT loops break off when tracking is lost over the writing** (S1 run 1, 2026-10-24): 5 of 17 loops ended early and selected nothing: hand NOT SEEN for > 0.6 s (3: loop 13 at the top edge of the projection above SUN, loops 15 and 16 at the top of CAT) or the index read as curled, fold 98–151° (2: loops 2 and 10). The user redid each loop at once and the redo was right. S1 run 2 (2026-10-24 22:52): 2 of 11 loops broke (loops 8 and 9 on DOG: partial arcs ended with the index read as curled or pinching, fold 60–123°), both while the frame rate was down to 12–15 fps (on battery); the redo was right. S1 run 3 (23:09): 2 of 15 loops broke: loop 8 on DOG (index read as curled, fold 74–97° for ~0.6 s) and loop 11 on CAT (index fold 61–73°, just above the D47 keep band's 60°, for ~0.6 s); both at ~25 fps with the CPU throttled; the redo was right. The interruptions (1.1–2.7 s) are as long as the user's pauses between deliberate loops (1.6–2.0 s), so a longer pen-lift delay cannot tell them apart; it is not raised to hide the losses (user, 2026-10-24). Same cause as G8 (hand found far less often over a busy canvas without the light, D50). | Not addressed yet (user: keep documented separately, address later). Options: the D50 light (off by user decision), tracking work on hands over projected content; S1 reports broken loops as failed attempts | Open |
| R35 | **EXPLORE's facts come from the local 8B model's memory** (offline, no sources) and can be wrong: in the dry runs (2026-10-25) it explored the unknown word "Pengyien" as "a Chinese surname" and gave dog breed counts of 340, 700+ and 1,000 in different answers; physical run 1: "aviation history began in 1903" (a simplification: 1903 is the first powered aeroplane flight); physical run 2: "Kritagya is a common Indian female name" about a person named in the writing (a claim the model cannot know; the prompt now forbids statements about named people, 2026-10-26). The prompt asks for well-established facts only and to refuse words it does not know as a subject; the model does not reliably comply. | The READ line shows what was read; X1 judges correctness and usefulness; options: a short caution line under EXPLORE answers, a larger local model, the Claude backend (paid; not chosen, D52) | Open (2026-10-25) |

---

## 12. Open questions

1. What is the projector's EDID name? It is filled in after the first diagnostics run with the projector connected and goes into `projector.match`. **Answered 2026-10-09:** `AML TV` [AML0030] on HDMI; the automatic rule identifies it. Not yet written into `projector.match`.
2. Which Brio 100 mode to use for Phase 1: 1920×1080 or 1280×720? Decide from the measured fps and latency (default for now: 1920×1080 MJPG @ 30). **Answered by D25 (2026-10-09):** 1920×1080 MJPG @ 30 validated; both sizes measured the same fps; latency still to be measured.
3. Physical projected image width in mm, needed to report errors in mm (`surface.width_mm`). Measure during step 1A.5.
4. (P2) Classic OCR, or a multimodal model reading a rendered image of the selected strokes? Which AI provider/model? **Answered 2026-10-23 (D51): Claude (Anthropic API, `claude-opus-5-5`) reading an image of the selected strokes; no OCR library.**
5. Does the WZATCO Yuva Go have a game/low-latency picture mode, and which of its settings (MEMC, noise reduction, dynamic contrast, keystone) change the measured latency? (R4)
6. (1B) What moved the setup three times (≈5 px after 19:53, ≈53 px after 23:24, ≈24 px between 00:07 and 00:29)? Until the mounts are fixed, every calibration has a short life (R10).
7. ~~(1B/1C) Should `--auto` become the default?~~ **Answered 2026-10-10: yes (D31).**
8. ~~(1C) Stricter setup limit for `--auto`?~~ **Answered 2026-10-10 (D32): 1.0 px evaluated, not adopted while the scene drifts; 2.0 kept.** Re-evaluate after the mounts are fixed.
9. (1D) How well does the fingertip cursor work with a real hand on this setup? **Answered for detection (D34, D35); accuracy limited by hover parallax (D35).**
10. (1D, D35/D36) How should hover parallax be handled? **D36:** moving the camera is exhausted (18 cm, measured limit). Remaining: a hover-distance measurement (dedicated shadow detection, a second camera, a depth sensor) or an accuracy criterion for a hover band. Geometry recorded in §13.3 (vertical offset after the move not re-measured).
11. (1D, D35) Operational definitions for the provisional criteria: "no persistent edge-target detection failure" (proposal: every target captured within 30 s and ≥ 80 % hand-found per target) and "60-s free test passes" (proposal: ≥ 90 % hand-found excluding deliberate exits, every exit recovered within 1 s).
12. (1D, D36) Which accuracy reference, if the shadow centre cannot be established in room light / at the bottom row: a dark room for the test, a physical pointer of known length touching the wall, or fingertip contact for the measurement only?
13. (D39) After the hardware validation of `recalibrate`: keep automatic recovery on by default in `cursor` (current; `--no-recalibrate` stops instead)? Should repeated recoveries within a short time (a mount that keeps moving) stop with a warning instead of recovering again?
14. ~~(D41) Kreo Owl 4K Pro mode~~ **Answered 2026-10-19: 1920×1080 @ 60 (user), D42.** Original question: 1920×1080 @ 30 as with the Brio, 1920×1080 @ 60 if it really delivers 60 fps (halves the camera's frame interval; latency matters for the cursor), or a higher resolution for calibration accuracy (more decode time per frame)? Measuring 4K-class modes needs them added to the `devices` probe list (`camera/probe.py`), which is not done yet.
15. (D41) Is the Kreo permanent or temporary ("for now")? Camera selection is by name, so going back to the Brio means restoring its `[camera]` settings (D24, D25) and recalibrating.
16. ~~(D42) Lock the Kreo's gain through config~~ **Answered 2026-10-19: yes, gain 15 (D43).** Original question: Lock the Kreo's gain through config (`IAMVideoProcAmp` gain 0..15, same read-back/keeper mechanism as exposure and focus)? At −6 the image is too dark without it; gain 15 gives white 145.6 (like the Brio's 114–143) and grey-128 54.4 (the Brio: 142). Hand detection will also need a brighter canvas or room light; measure with `handcheck` (D34) after the gain lock.

17. (D54, EXPLORE physical run 1) Should EXPLORE correct an obvious misspelling (the model read "FLIGT" and explored "Flight") or refuse it with the note (what the prompt asks for misspelled words)? The READ line shows the original letters either way. After the 2026-10-26 prompt change the model also took "Pengyien" as "Penguin" (before: "a Chinese surname").

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
- **2026-10-09** (hardware session, Brio 100 + WZATCO; on a different laptop, see the §2.2 note)
  - `python -m invisible_canvas.tools.devices` now runs the diagnostic (it had no `__main__` guard and exited silently).
  - Brio camera investigation (test log below). Fixed the FOURCC set-order bug (D26).
  - Added config-driven exposure control: `[camera] exposure_mode`/`exposure_value`, default manual −5 (D24). New `camera/exposure.py`; `CameraControl` in `camera/directshow.py`; `CameraManager` applies, verifies and keeps it; `camera` and the session tools print it.
  - Validated camera mode recorded (D25). D8 validated. R7, R14, R17 updated; R20–R22 added.
  - A1 PASS; A2 visual check passed (user); A3 camera feed PASS, latency pending. Unit tests 104.
  - Evening: latency investigation (test log). The 18:32 run (16 of 20 missed) was not valid; valid runs give a 275 ms baseline, so **A3 PASS**. `latency` now reports validity (D27). Found: manual exposure does not lock gain (R7); the projection's bottom edge is outside the camera frame (A4). Unit tests 108.
  - Setup preview added to `camera` (`f`/`--preview`, `b`), display only; with it open: 29.90 fps, slowest 1-s window 30, 0 failed reads. The camera had been re-aimed by then: the whole alignment pattern is inside the frame (A4). Unit tests 113.
  - Night: user ran 3 calibrations (19:46–19:53), `repeatability` PASS (0.75/1.50 px) and `validate` FAIL (19:59, mean 5.87 px). Investigated (test log): mapping chain correct; the setup moved after calibrating. Added the setup check (D28) and 9 regression tests. Calibration and reports archived unchanged in `data/archive/20261009-before-mapping-investigation/`. Unit tests 122.
  - 23:20–23:24 (user): recalibrated; setup check 1.41 px; **A7 PASS** (mean 1.99, max 4.03 px). Archived by the user in `data/archive/a7-pass-20261009-233128/`.
- **2026-10-10** (Phase 1B, first increment)
  - `calibration/detect.py`, `tools/detect_check.py` (`detect` command), 86 new tests (83 detector, 3 diagnostic). Manual `calibrate`/`validate` unchanged. Detector acceptance criteria fixed before the hardware runs (D29).
  - Real hardware: B1–B4 PASS in two runs; B5 not evaluable (the setup moved ~53 px after the A7 run). Unit tests 208.
  - 00:02–00:07 (user): manual `calibrate` (00:02:24), manual `validate` PASS (setup 1.01 px, mean 1.87 / max 4.32), `detect` with **B1–B5 PASS** (`detection-20261010-000700.json`).
  - 00:10–00:40, **Phase 1C** (D30): `calibration/auto.py`, `calibrate --auto [--dry-run]`, `validate --auto [--simulate-shift]`, capture shared in `tools/common.py`, `detect`/`repeatability` keep manual and automatic apart; detector speed-up (exactly equivalent, verified). 32 new tests (31 in `test_auto.py` with the synthetic camera `tests/synthetic_camera.py`, 1 in `test_detect_check.py`), 1 test fixture made realistic. Pre-1C state archived in `data/archive/pre-phase1c-20261010-002928/`. Hardware: automatic calibration and validation PASS; setup check refused a real and simulated moves. Unit tests 240.
  - 00:44 (user): `validate --manual` on the automatic 00:36 calibration PASS (mean 1.32 / max 2.92); closes the manual cross-check. **Phase 1C acceptance complete.**
  - 00:53–01:25: **D31** automatic mode default (3 new tests); **D32** `setupcheck` diagnostic, `auto_setup_limit_px` (2.0), hardware drift series and sensitivity sweep, 1.0 not adopted; **D33** dependency swap (`opencv-contrib-python` 4.14.0.94, `mediapipe` 1.1.0; `pyproject.toml`, `requirements.lock`, `.gitignore`), hand model downloaded and pinned, `vision/` package, `cursor` command; hardware re-verified after the swap; first no-hand cursor runs. Unit tests 271.
  - 01:28–02:10, **D34** (0 % hand detection): `tools/hand_check.py` (`handcheck`), `HandTracker.prepare()` (exact MediaPipe input, refuses non-BGR-uint8 frames), `cursor` default canvas grey 128 + brightness pre-check, accuracy capture radius 8 px with on-target feedback, `--save-every`, target index per frame. Hand session on hardware: detection, loss/recovery and 9-target accuracy measured; setup moved and was recalibrated (02:00:32). 11 new tests. Unit tests 282.
  - 13:30–14:35, **D35** (accuracy investigation): `vision/shadow.py`; `cursor` `--aim`, per-target diagnostics, capture frames, `--targets/--labels/--pause`, `--shadow-check` (experimental), provisional criteria; fixed: a repeated target was captured from the previous hold (samples collected during the pause); fixed: a camera without frames crashed `cursor`/`handcheck` (`current_seq`). Lit-room hardware session (daylight, then ceiling light), two recalibrations. 18 new tests. Unit tests 300.
  - 15:00–15:40, **D36**: geometry measured and recorded (§13.3); camera moved to 18 cm; `vision/hands.py` tiled acquisition + region tracking; `vision/shadow.py` `shadow_tip_near`, `steady_shadow_centre`, knuckle-based finger width; `cursor` shadow-centre reference + run validity, `--acquisition`, `--withdraw`, rows/columns, acquisition statistics. Hardware: calibration 15:18:58, stability check, false-positive run, Experiment A (invalid), Experiment B (tiled vs full), 60-s test. 18 new tests. Unit tests 318.
- **2026-10-11** (tracking audit)
  - **D37**: Stage 1 read-only diagnosis (reports of the day, 854 saved frames, replayed trajectories); `vision/hands.py` same-frame confirmation, region ≥ 720 px, observation view/fingertip-in-view, statistics for both modes; `vision/cursor.py` reasons, transitions, reacquisition times, beta 0.05; `tools/cursor.py` extrapolated fingertips not drawn, records/report additions, `--trace`. 20 new tests. Unit tests 338.
- **2026-10-12** (landmark-glitch diagnostics)
  - Offline forensic analysis of the four 2026-10-11 traces (read-only); **D38** Phase A: `vision/landmark_diagnostics.py`, `cursor` records trace `diag` and report `landmark_diagnostics`; cursor behaviour unchanged (bit-identical replay). 41 new tests (`tests/test_landmark_diagnostics.py`; trace tests skip without the local data). Unit tests 379.
  - Review of Phase A: regression found: in `tools/cursor.py` the per-frame landmark diagnostic and the target-capture status text shared the name `diag`, so with `--trace` and targets the trace line on a capture frame called `to_json()` on a string and the run aborted (AttributeError, before the report was written). Fixed by distinct names (`landmark_diag`, `target_status`); regression test `test_trace_with_targets_records_diagnostics_on_capture_frames` (failed before the fix, passes after). Unit tests 380.
  - **D39** (automatic calibration recovery): root cause of the 19:19 setup-check refusal investigated (real move, ~74 camera px); new `calibration/recovery.py`, `tools/recalibrate.py` (`recalibrate [--dry-run]`), `store.archive_calibration`; `cursor` recovers a moved setup automatically (`--no-recalibrate`) and prints hints when the setup check cannot detect the corners; the `validate` refusal names `recalibrate`; the `tests/test_cursor_tool.py` helper can run the setup check on a synthetic scene. 30 new tests (`tests/test_recovery.py`). Unit tests 410. Offline only; no hardware run.
  - **D40** (hand-search budget): read-only analysis of `cursor-20261012-201357` and an offline per-view timing on saved frames; `vision/hands.py` `views_per_frame` (replaces `tiles_per_frame`), `next_views`, full frame first in every new search. 5 new tests in `tests/test_acquisition.py` (they fail on the previous schedule); the fake landmarker keeps the last image and the fixture passes options. Unit tests 415. Offline only.

- **2026-10-17**
  - Code synced from GitHub (commit `99cb22b`, Kritagya Kumar) to the original laptop (§2.2): fast-forward, nothing local lost.
  - `.venv` synced to `requirements.lock`: `opencv-python` removed first, then `opencv-contrib-python` 4.14.0.94 and `mediapipe` 1.1.0 installed; `pip check` clean; the environment matches the lock file exactly.
  - Hand model downloaded from the D33 URL: 7,819,105 bytes, SHA-256 matches the pinned value.
  - Unit tests on this laptop: 393 passed, 0 failed, 22 skipped. All skips need the other laptop's local recordings in `data/` (git-ignored).
  - **D41:** camera changed to the Kreo Owl 4K Pro (user). Re-validation plan §9.9, risk R26, open questions 14–15. The Kreo was not connected to this laptop, so nothing was measured; no code or config change.

- **2026-10-22** (Phase 2)
  - 00:34 G1 run 1 FAIL (D44 gestures; analysis in §13.2); user decision D46 (one gesture + toolbar tools); implemented, tests 488 passed.
  - 18:14–19:11 hardware (§13.2): G1′ run 1 FAIL (pose), run 2 PASS; G2 runs 1–2 invalid, run 3 PASS; G3 run 1 FAIL (strokes break while still pointing).
  - **D47** (user decision): keep-drawing band: `vision/gestures.py` (`GestureParams.keep_*`, `HandShape.keeps_point`, in `as_dict`), `interaction/engine.py` (`HandInput.keeps_draw`; DRAW continues within the band), `tools/tracking_session.py` (`HandPoints` passes it), `tools/gestures.py` (records `keeps`, `evaluate` runs the engine with it). 4 new tests. Full suite: 491 passed, 22 skipped, 1 failed: `test_landmark_diagnostics.py::test_trace_with_targets_records_diagnostics_on_capture_frames` (time-based fake `cursor` run with a 0.2-s pause; the `cursor` tool does not use any D47 code; it passed 5 of 5 times run alone): flaky under full-suite load, not a D47 regression.
  - **D48 steps 1–2** (user-approved plan, §9.10): `tools/video.py` (`VideoRecorder`: MJPG AVI written by a background thread; a full queue drops and counts a frame instead of slowing the loop), `tools/gestures.py` (`--angles` prompt set with a direction arrow, `--video`, per-frame `process_ms` / `pipeline_ms` / `video_index`, `evaluate(expected, min_found)` for G1″, `timing` with the G6 limits), `tools/replay.py` (`replay DIR`: the recorded video through the tracker, `ShapeReader` and the engine at the recorded timestamps; per prompt, per round, shape agreement with the live run, tracker ms), `tools/tracking_session.py` (`ShapeReader` split out of `HandPoints`, shared with `replay`), CLI and README. 8 new tests; full suite 499 passed, 22 skipped.
  - **D48 step 3:** `vision/gestures.py`: two-view index rule (`alt_extended_max_deg` 65°, `alt_reach_min` 1.6), phantom-middle rule (`phantom_gap_max` 0.35, middle fold < 45°), `HandShape.index_reach` / `tip_gap` / `phantom_middle` (in `as_dict`), `keeps_point` true for every POINT; `tools/tracking_session.py`: `TRACKER_OPTIONS` (tiled, presence and tracking confidence 0.3) used by `draw`, `gestures`, `replay` (`cursor` unchanged). 2 new tests; full suite 501 passed, 22 skipped.
  - **D49** (user decision): `interaction/engine.py` `EngineParams.lift_s` 0.6 s, DRAW kept until no continuing frame for `lift_s` (dropout: the longer of `hold_s` and `lift_s`); mechanics tests run with `lift_s=0`, G1′/G1″ evaluation tests use a 0.74-s prepare phase (real: 3 s); 2 new tests. Full suite 503 passed, 22 skipped.
  - **R32 fix** (user-approved): `interaction/engine.py` checks the D49 window on continuing frames too (`_gap_frames`); the approved 'resume after 3 frames' variant was built, measured on the traces (more breaks) and removed. 1 new regression test. Full suite 504 passed, 22 skipped.
- **2026-10-23**
  - Phase 2 status recorded (G6 and G7 from the recorded runs; header cleaned). User: D50 first, then Phase 3 (requirements in §9.10).
  - **D50** (user decision): `display/handlight.py` (`HandLight`: convex landmark outline in projector px + 25 px, look-ahead 0.26 s along the centroid velocity capped at 150 px, held 1 s with a 45-px margin after a loss; `grown_hull`, `paint`), `canvas/render.py` (`light=` paints the polygon last; ring cursor `RING_RADIUS` 38 px with the dwell as an arc), `tools/tracking_session.py` (`projector_landmarks`), `tools/draw.py` (light on by default, `--no-light`, trace `lit`, report `light`), `tools/gestures.py` (`--light on|off|ab`, `--busy` background with the prompt in a top banner, `evaluate_light` for G8, segment-aware `timing`). Measured cost: 0.06 ms per frame (update + paint). 8 new tests; full suite 512 passed, 22 skipped.
  - G8 run 1 FAIL (§13.2). **User decision: light off by default** (`draw --light`, `gestures --light` default off; code and tests kept); README updated. Tests 512 passed.
  - **Phase 3A** (D51, §9.11): plan and S1–S5 recorded before code; `anthropic` 2.2.0 (optional extra `ai`); `ai/` package, selection, panel, SELECT tool, AI button, controller flow, renderer, `[ai]` config, `draw --ai`; 18 new tests; full suite 530 passed, 22 skipped. Live tests pending the user's API key.
  - **D52** (user decision: free of cost): Ollama 0.40.9 installed (winget `Ollama.Ollama`, installer hash verified), its app started (server `http://127.0.0.1:11434`); model `qwen3-vl:8b` pulled. `ai/local.py` (`LocalAssistant`: `/api/chat` with system prompt, task, image, JSON schema format, temperature 0, keep_alive 30m; `warm_up` loads the model; errors: not running, model not downloaded, timeout), `[ai] backend` (default `local`), `local_model`, `local_url`, timeout 120 s; `AIWorker(warm_up=True)`; `draw` picks the backend; report `ai.backend`, `ai.warmed_up`. 5 new tests (stub Ollama over real HTTP); full suite 535 passed, 22 skipped. Windows refuses a closed local port only after ~2 s of retries, so "Ollama not running" appears after ~2 s.
  - D52 smoke test (no projector): `qwen3-vl:8b` turned out to be the **thinking** variant (same ID 9cf69da2b16d as `qwen3-vl:8b-thinking` on the Ollama tags page): on the user's real finger-drawn G3 canvas it deliberated for 2,895 tokens / 88 s and never answered; `think: false` had no effect. Pulled **`qwen3-vl:8b-instruct`** (ID 70e58e37beb1, 6.2 GB) and made it the default; `num_predict` capped at 1024; '°' → ' deg' on the panel. Instruct results: model load 7.7 s (warm-up); finger-drawn G3 canvas (2 lines, 2 verticals, circle, diagonal, L, V, S, Z) read as 'ILYOSZT', answers in 0.9–2.5 s; a script-font sentence read perfectly, summarize / explain / questions in 0.9–2.5 s (GPU, warm). The thinking model stays on disk unused (`ollama rm qwen3-vl:8b` frees 6.2 GB). Report: `selections` (each loop's bounds and selected ids, for S1).
  - D44 design approved and recorded with acceptance criteria G1–G7 (§9.10).
  - Implemented (D45): `vision/gestures.py`, `HandObservation.world`, `interaction/engine.py`, `interaction/drawing.py`, `canvas/` (model, history, toolbar, render), `tools/tracking_session.py`, `tools/gestures.py` (`gestures`), `tools/draw.py` (`draw`); tests 479 passed. Hardware: recalibrated after a move; `draw` smoke run.
- **2026-10-24**
  - R33: Smart App Control turned off by the user; MediaPipe loads again.
  - S1 run 1 FAIL (§13.2): 10 of 12 completed loops exact, 5 broken loops (R34).
  - **D53** (user-approved): `canvas/selection.py` `close_loop` (`CLOSE_PART` 1/3, `MIN_CLOSE_POINTS` 8) used by `select_in_loop`; `interaction/drawing.py` logs `points` / `closed_points` per loop; `tests/test_ai.py` 4 new tests (closed and short loops unchanged, two synthetic lead-in regressions, the 17 recorded S1 run 1 loops from `tests/fixtures/s1_run1_loops.json`); the regressions fail with `close_loop` disabled.
  - S1 runs 2–3 (§13.2); user decision: S1 selection working on completed loops (22 of 22), strict count recorded, R34 open. Power requirement added (§2.1).
  - S2 preparation (§9.11): `canvas/render.py` panel text without "Claude" and the transcription as large as the answer; `canvas/panel.py` docstring; README model tag `qwen3-vl:8b-instruct`.
- **2026-10-25**
  - S2 run 1 (§13.2): 5 SUMMARIZE tries, 15 answers, 0 errors, on battery without a slowdown; **S2 PASS** on the user's judgment. Power rule refined (§2.1).
  - 2026-10-26: EXPLORE physical run 2 (§13.2), partial; EXPLORE prompt: never state anything about a person named in the writing (offline recheck on 11 images; AI + draw tool tests 48 passed).
  - EXPLORE physical run 1 (§13.2), partial; `ai/client.py` `point_lines` (EXPLORE points on separate lines; 1 new test; full suite 547 passed, 22 skipped).
  - **D54 EXPLORE** (user request, §9.11): `ai/client.py`, `ai/local.py`, `canvas/panel.py`, `canvas/render.py`, `interaction/drawing.py` (docstring), `tools/draw.py`, README; `tests/test_ai.py` 7 new tests (AI tests 32; full suite 546 passed, 22 skipped); dry runs on the local model. Physical test pending.
- **2026-10-19** (Kreo re-validation, original laptop)
  - Windows switched from Duplicate to Extend (user-approved); projector resolution/scaling still to be set by the user.
  - Kreo measured (`devices`, scratch read-only probes, `CameraManager` runs): modes, exposure, focus, gain, brightness, projection footprint, focus sweep (§13.2).
  - **D42:** `camera/focus.py` (focus lock, keeper), `CameraManager`/`CameraInfo`/`CaptureStats` focus fields, focus printouts (`common.focus_text`, `camera`, `devices`), `directshow.FOCUS`; `[camera]` → owl 4k, 60 fps, exposure −6, focus manual 410; `tests/test_focus.py` (13) and `tests/test_config.py` (Kreo defaults, 2 focus-config tests). Unit tests: 408 passed, 0 failed, 22 skipped (the same local-data skips).
  - **D43:** gain lock; `camera/focus.py` generalised into `camera/locks.py` (focus + gain), `CameraControl(index, interface)` opens `IAMCameraControl` or `IAMVideoProcAmp`, `directshow.GAIN`; `CameraManager` keeps both locks; `common.lock_text`, `camera` and `devices` print gain; `[camera] gain_mode`/`gain_value` = manual 15; `tests/test_focus.py` → `tests/test_locks.py` (focus and gain), `tests/test_config.py` (gain default, focus/gain mode checks). Unit tests: 415 passed, 0 failed, 22 skipped.

### 13.2 Test log

**2026-10-26 (16:11–16:16): mission baseline B-3 (trace guides, contact) — no ink at all: every stroke started on the toolbar and stayed dead (a confirmed usability failure); not a writing measurement**

- First attempt 16:11: the setup check stopped (1 of 4 corners not seen steadily: the user was in front of the projection); nothing ran.
- 16:13 `draw --seconds 300 --trace --save-every 1 --load data/canvas/guides-b3.json` (`draw-20261026-161641.json`, trace and frames `data/diagnostics/draw-20261026-161331/`, sheet `b3_frames_sheet.jpg`): setup 0.35 px, on battery 37 %, 173.5 s, 39.7 fps (pipeline median 27.7 / p95 41.4 ms). **0 strokes drawn**; DRAW entered 3 times (12.1, 29.8 and 13.4 s), each **started in the toolbar band** (cursor y 747, 686, 712) and was refused (`strokes_refused_on_toolbar` 3); 7 dwell presses (thin, pen ×2, black, green, blue, select, move). The cursor was in the toolbar band or below in 1492 of 3289 frames (45 %), down to y 956 and x −190.
- Saved frames: the user **pressed toolbar buttons with the index finger pointing** (16.2, 39.5, 49.5 s) — natural, and D46 allows any shape for a dwell press — so DRAW began on the toolbar; then, still pointing, the user moved up and traced the guides (21.3, 30.4, 85.0, 90.1 s: fingertip on the bottom and middle guides, cursor next to it) while the refused stroke stayed open: nothing was drawn and nothing on the wall said why. SELECT and MOVE were pressed in passing.
- Root cause (code, `interaction/drawing.py`): a stroke whose start lies in the toolbar band (or under the panel) is refused as a whole and stays refused until the pen lifts (open hand / fist, then the 0.6-s delay); points inside the band are dropped silently. With the toolbar at the bottom and pointing used to press, writing right after a press fails. (Together with the 408 dropped points of the earlier sessions.)
- Not a writing-accuracy measurement: B-3 to be repeated with the instruction "move to the start of the line with an open hand, then point" (the D46 usage).

**2026-10-26 (16:09–16:10): mission baseline B-2 round c ("5 cm hover", the user's estimate) — 9 of 9: mean 7.22, max 9.70 px; hovering mainly costs steadiness**

- Power: on battery 40 %. Setup unchanged (0.24 px).
- `cursor --accuracy --aim finger …` (`cursor-20261026-161009.json`, frames `data/diagnostics/cursor-20261026-160909/`): TL 9.24 (+5.2, +7.6), TC 9.70 (+9.3, +2.7), TR 9.41 (+5.1, +7.9); ML 9.27 (+5.1, +7.7), MC 8.14 (+8.0, +1.3), MR 3.64 (+3.6, +0.6); BL 3.88 (+3.4, +1.8), BC 5.02 (−5.0, −0.1), BR 6.64 (+5.1, +4.2). **Mean 7.22, max 9.70 px**; mean signed (+4.42, +3.74); 43.2 s, 53.0 fps, inference median 9.3 ms, hand found 85.1 %.
- **Rounds a / b / c compared** (contact / ~2 cm / ~5 cm, distances by the user's eye): mean 9.62 / 6.44 / 7.22 px, max 26.93 / 10.89 / 9.70 px; mean signed (−3.9, +4.3) [placement at TL/TC] / (+2.8, +3.2) / (+4.4, +3.7); **still jitter 1.21 / 4.35 / 4.75 px rms; transient jumps 8 / 16 / 32**; spread sd median 3.06 / 3.60 / 3.20 px. In this static test hovering at ≤ ~5 cm does not produce a large systematic error (the shift grows ~+1.6 px in x from 2 to 5 cm, inside the placement scatter of ±5 px); it makes the fingertip ~4× less steady. Whether that is what makes hover writing feel inaccurate is tested in B-3 / B-4 (writing on guides).

**2026-10-26 (16:04–16:07): mission baseline B-2 round b ("2 cm hover") — 9 of 9 measured: mean 6.44, max 10.89 px; hover distance not verified (no ruler visible in the frames)**

- Power: on battery 43 %. Setup unchanged (0.16 px).
- `cursor --accuracy --aim finger …` (`cursor-20261026-160700.json`, frames `data/diagnostics/cursor-20261026-160457/`, sheet `b2b_captures_annotated.jpg`): TL 5.27 (+5.2, +0.9), TC 6.81 (+0.9, +6.8), TR 9.79 (+9.3, +3.1); ML 2.99 (+2.2, +2.0), MC 0.82 (−0.1, −0.8), MR 9.64 (+6.8, +6.8); BL 6.75 (+5.9, +3.2), BC 10.89 (−9.9, +4.6), BR 4.97 (+4.5, +2.2). **Mean 6.44, max 10.89 px**; mean signed (+2.75, +3.20) px, sd (5.27, 2.39); spread sd median 3.60 px; 39.2 s, 52.8 fps, inference median 9.3 ms, hand found 83.4 %, TL first detection 7.1 s (hand found 28 % there).
- Capture frames: the cursor mean again on the visible fingertip end, the fingertip near the target centre; **no ruler visible in any of the 9 frames**: the user confirmed afterwards that the fingertip was "about 2 cm" from the wall by eye (an estimate, not a ruler measurement). The mean shift (+2.8, +3.2) is of the size the geometry predicts for ~2 cm (≈ 1.1 px/cm horizontally, D35), but placement scatter (sd 5.3 px in x) is larger than that shift: not a parallax measurement until the distance is verified.

**2026-10-26 (16:01–16:02): mission baseline B-2 round a (contact) — 9 of 9 measured: mean 9.62, max 26.93 projector px; the cursor sits on the visible fingertip end, the errors are fingertip placement**

- Power: on battery 46 %. Setup unchanged (0.19 px; calibration 2026-10-26 15:54:09). Canvas region 103 at grey 128, unlit surround 54.
- `cursor --accuracy --aim finger --trace --save-every 1 --targets (9; bottom row y 600)` (`cursor-20261026-160212.json`, trace and capture frames `data/diagnostics/cursor-20261026-160113/`, annotated sheet `b2a_captures_annotated.jpg`): 42.5 s; errors TL 13.92 (−13.9, +0.0), TC 26.93 (−26.1, +6.7), TR 6.76 (−4.7, +4.8); ML 11.16 (+0.8, +11.1), MC 10.64 (−0.9, +10.6), MR 5.15 (+3.8, +3.5); BL 1.73 (+1.6, +0.7), BC 4.10 (+0.8, −4.0), BR 6.20 (+3.3, +5.3). **Mean 9.62, max 26.93 px**, 1-s spread sd median 3.06 px. Against the provisional D35 criterion (mean ≤ 5, max ≤ 12): not met. Bottom row best (1.7–6.2 px).
- Capture frames (each cropped around its target with the cursor mean, through H⁻¹): **in all 9 the cursor mean lies on the visible end of the fingertip.** At TL and TC the finger came in horizontally from the left and its end stopped 14–27 px short of the target centre; at ML and MC the fingertip ended just below the centre; on the bottom row it was on the target. So this round measures where the fingertip was placed relative to the target (the user confirmed afterwards: the fingertip touched the wall at every target, the top ones included, so at TL / TC the contact really was 14–27 px left of the centre), not a camera / landmark / mapping error; the fingertip end vs the cursor is within a few px by eye (not yet measured numerically). The hypothesis that landmark 8 lies behind the touching point (cursor past the target) is not supported: the cursor was short of it.
- Timing with the hand present: 53.7 fps (camera 60.2), inference median 9.2 / p95 20.5 ms, queue 6.8 ms, pipeline median 19.5 / p95 33.5 ms; hand found 88.3 %, 5 tracking losses, reacquired median 0.18 s.

**2026-10-26 (15:53–15:59): mission baseline B-2 round a (contact) — INVALID: nobody in the projection**

- Power: on battery 53 %. Setup moved 33.1 px (mean shift −65.9, +0.7 camera px); automatic recovery accepted (check target 2.11 px, validation mean 1.11 / max 2.00 px; calibration 2026-10-26 15:54:09). Canvas region 103 at grey 128, unlit surround 55.
- `cursor --accuracy --aim finger --trace --save-every 1 --targets (9, bottom row y 600)` (`cursor-20261026-155944.json`, frames `data/diagnostics/cursor-20261026-155355/`): all 9 targets skipped after 30 s each; hand found in 0 % of 8816 frames. All 267 saved frames show the empty grey test screen: no hand, body or shadow ever entered the projection (dark fraction inside the projection 0.0000 in every frame). Not an accuracy result; to be repeated.
- Usable measurement: with no hand in view the frame loop ran at **32.6 fps** (camera 60.2): every frame a search, search 23 ms median, inference median 22.7 / p95 25.7 ms, queue 8.5 ms, pipeline median 34.1 / p95 42.9 ms (D40: 2 views per search frame).

**2026-10-26 (15:50–15:52): mission baseline B-1 (§9.12) — display → camera latency 262 ms; capture 60.16 fps**

- Power: on battery 55 %; tracking a saved frame 8.1 ms (normal). Nobody in the projection; room light on.
- `latency --trials 20` (`latency-20261026-155054.json`): valid (20 of 20, levels held: black 72.9 → 71.5, white 164.9 → 164.7, measured over the inner 80 % of the calibrated projection): **median 262 ms**, p10 253, p90 281, min 249, max 286 (the same median as 2026-10-19).
- `camera --headless --seconds 60` (`camera-20261026-155204.json`): MJPG 1920×1080 delivered, **60.16 fps**, slowest 1-s window 57 frames, longest gap 47 ms, 0 failed reads, frame age median 0.26 ms; exposure −6, focus 400, gain 15 confirmed at open and end, re-applied 0×.
- So: capture is not the limit (60 fps delivered); a processing rate below 60 fps comes from the frame loop; the ~262 ms is camera + display hardware (R4).

**2026-10-26 (evening): bottom-edge tracking — offline evidence from the recorded `draw` sessions (no code change)**

- 19 `draw` traces 2026-10-22 … 10-26 (Kreo, room light). Hand losses (hand seen → no hand next frame) per 1000 frames with the hand, by the fingertip's projector y: top/middle (y < 432) 6.3–6.4; lower canvas 432–560: 9.7; **just above the toolbar 560–648 (the bottom writing band): 20.6**; over the toolbar 648–720: 12.6; below the canvas: 46.0. Time to see the hand again after a loss: top/middle 0.59–0.62 s, bottom row 1.11 s, toolbar row 1.16 s. Search source is the region tracker in > 99 % of hand frames everywhere (losses, not slow searches, dominate).
- **408 stroke points were dropped without a record**: `DrawingController._stroke_point` ignores points in the toolbar band (y ≥ 648) while the stroke stays open (a counter exists only for refused stroke starts).
- Camera geometry (calibration 2026-10-26 14:50): projection at camera y ≈ 199–818 of 1080, 254 camera px of frame below it: the hand writing at the bottom stays inside the camera image.
- Saved frames from losses between two bottom-region sightings (5): in 3 the hand is not near the canvas (behind the body, moving across: real exits); in 2 the hand is near the bottom with the palm below the lit projection, only the fingertip lit (R11: the palm detector needs a lit palm).
- Hover (Objective B), from earlier records: parallax ≈ hover × camera–projector baseline ÷ distance (D35, R12); with the 18-cm horizontal baseline and ~156 cm to the wall, ≈ 1.1 projector px per cm of hover horizontally, plus an unmeasured vertical part; contact runs (D37) 4.5–5.7 px mean. The camera–projector vertical offset was never measured after the 2026-10-10 move.

**2026-10-26 (14:50–15:02): EXPLORE physical run 2 (on battery 95 → 82 %) — X3 done; X1 tries 3–4; X2 still not run; a name claim fixed in the prompt afterwards**

- Setup moved 77.8 px overnight (mean shift +154.9, +4.9 camera px); automatic recovery accepted (check target 2.00 px, validation mean 1.01 / max 2.09 px; calibration 2026-10-26 14:50:29). Canvas brightness 144. Tracking a saved frame 7.9 ms before the run.
- `draw --ai --seconds 900 --trace --save-every 2` (`draw-20261026-150230.json`, trace `data/diagnostics/draw-20261026-145014/`, requests `data/ai/20261026-14*`): ended by the user at 659 s; 26,398 frames, 40.1 fps, pipeline median 26.5 / p95 45.9 ms, inference median 10.5 ms. The user also used ERASER, UNDO (13), MOVE, colours, widths and SELECT (2 loops).
- The user's own writing: "My FRIEND": SUMMARIZE (X3) normal, READ correct, 6.84 s (the run's first request); EXPLORE → "Friendship" (universal bond; trust and support; how it evolves; cultural norms), 2.16 s. "KRITAGYA IS MY FRIEND": EXPLORE → "Friendship", 4.12 s, but its first point was "Kritagya is a common Indian female name" — a claim about a person named in the writing that the model cannot know (R35); QUESTIONS normal, 1.46 s.
- While requests ran: 345 frames at 23.6 fps, pipeline p95 68.0 ms (battery 82–95 %, so not the battery): the minute with the requests ran at 24.3 fps. S3 data (≥ 30 fps while a request runs): not met in either EXPLORE run.
- After the run: EXPLORE prompt line "Never state anything about a person named in the writing (for example where the name comes from or whether it is male or female): explore the general topic instead." Offline recheck on 11 images: the KRITAGYA writing → "Friendship" with no statement about the name; SQL, Flight, AI, Catfish, Sun unchanged; 3 scribbles the note; "Pengyien" now "Penguin" (open question 17). AI + draw tool tests 48 passed.
- **EXPLORE not complete:** X1 4 tries over the two runs (all topics found; the user's judgment pending), X2 (scribbles) not run on the wall, X3 done.

**2026-10-25 (01:09–01:15): EXPLORE physical run 1 (D54; on battery 49 → 42 %) — partial: 2 EXPLORE tries, both topics found; X2 and X3 not run; a display fix after the run**

- Setup unchanged (1.15 px); canvas brightness 157; tracking a saved frame 8.1 ms before the run.
- `draw --ai --seconds 900 --trace --save-every 2` (`draw-20261025-011509.json`, trace `data/diagnostics/draw-20261025-010921/`, requests `data/ai/20261025-011*`): ended by the user at 332 s. 12,792 frames, 38.6 fps (camera 60.2), pipeline median 27.4 / p95 47.9 ms, inference median 10.7 ms; per minute 48 → 30.5 fps (the last two minutes 30.5 fps with the hand present 77 %).
- The user tried their own topics: (1) "WHAT IS SQL" (whole canvas), read correctly; EXPLORE topic "SQL", 4 points (manages relational databases; standardized by ANSI and ISO; querying, updating and managing structures; explore ACID properties next), 4.70 s; then QUESTIONS 1.20 s and EXAMPLES 2.31 s on the same writing, normal. (2) "FLIGT" (written without the H; chosen with a SELECT loop: 5 strokes, D53 closed the loop 177 → 152 points), read correctly as "FLIGT"; EXPLORE explored "Flight" (it corrected the spelling instead of refusing it as the prompt asks; open question 17), 4 points (air travel; aerodynamics and lift; "aviation history began in 1903"; spaceflight), 5.40 s.
- Not done: a third topic (X1 needs 3), the scribbles (X2), SUMMARIZE (X3; QUESTIONS and EXAMPLES answered normally).
- Display issue: the SQL answer came as one line ("databases. - Standardized by ..."), so the panel wrapped the four points into one paragraph with dashes at the line ends. Fixed after the run (`point_lines`, EXPLORE only, unit test); the re-rendered panel shows the four points on separate lines. Not yet seen on the wall.
- While requests ran: 353 frames at 26.0 fps, pipeline p95 63.1 ms (S2 run 1 at 91 % battery: 32.5 fps): S3 data, below its 30 fps.
- **EXPLORE not complete:** X1 2 of 3 tries (the user's judgment pending), X2 and X3 not run.

**2026-10-25 (00:35–01:05): D54 EXPLORE — built and tested offline; the physical test (X1–X3) not run yet**

- Unit tests (`tests/test_ai.py`, 7 new): EXPLORE has its own answer format and the five other actions' requests are unchanged (both backends; token cap 400 for EXPLORE only, 1024 for the others); a readable answer gives the topic; no confident topic, no topic, only `[?]` marks, a non-boolean `readable` or a cut-off answer give the fixed note and never the model's text (both backends); a summarize answer keeps its old shape; the panel has 7 non-overlapping buttons inside it, labels fit, buttons at least toolbar-sized, CLOSE bottom right, answer area 374 px; EXPLORE pressed by dwell, its answer drawn with "EXPLORE: <TOPIC>" and the note drawn without the model's guessed topic (checked on the drawn text); the local HTTP path sends `EXPLORE_SCHEMA`. AI tests 32 passed; **full suite 546 passed, 22 skipped, 0 failed**. A first version passed `action` twice to the new parser, so every answer of every action became "could not be read": the existing tests caught it before any run.
- Dry runs on the local model and the rendered panel: §9.11 (D54). Not a physical test.

**2026-10-25 (00:13–00:33): S2 AI answer, run 1 (local `qwen3-vl:8b-instruct`, on battery) — 5 SUMMARIZE tries, 5 summaries shown; PASS on the user's judgment**

- Power: on battery (the user's choice), 91 % at the start, 71 % at the end; tracking 8.8 ms on a saved frame and AI answers 1.1–1.4 s on the dry-run words just before (normal). Setup moved 34.2 px (mean shift −68.2, −3.2 camera px); automatic recovery accepted (check target 1.77 px, validation mean 1.04 / max 2.19 px; calibration 2026-10-25 00:14:55). Canvas brightness 157.
- `draw --ai --seconds 1200 --trace --save-every 2` (`draw-20261025-003329.json`, trace `data/diagnostics/draw-20261025-001439/`, requests in `data/ai/20261025-00*`): ended by the user (ESC) at 1040 s. 43,120 frames, 41.5 fps (camera 60.2), pipeline median 25.7 / p95 43.4 ms; inference median 10.6 ms; 43–49 fps per minute with the hand in view, 29–36 fps in minutes mostly without a hand (search frames, D40): no slowdown on battery. 81 strokes, 20 undo, ERASER used, CLEAR 4×.
- 15 AI requests, all answered (0 errors): 5 SUMMARIZE on 5 writings, plus EXPLAIN 3, EXAMPLES 3, SIMPLIFY 2, QUESTIONS 2 on the same writings. What the model read (SUMMARIZE, time to answer): (1) "I Love Pengyien" 3.47 s; (2) "WHAT Is AI" 2.27 s; (3) "Tell me about CaT" 4.00 s; (4) "Tell me about DOG" 3.78 s; (5) "CAT FISH" 1.52 s (after EXPLAIN 3.51 s and EXAMPLES on the same writing). Every request on new writing took 2.3–4.0 s; repeated requests on the same writing 0.8–1.5 s (median of all 15: 1.23 s).
- Checked against the images sent (`data/ai/*.png`): each transcription matches the letters visible in the image, including the case ("Is", "CaT"); in (1) the image shows "Pengyien" as written. Try (4) reused the strokes of "Tell me about" from try (3) (CaT erased and DOG written; no CLEAR in between), so only "DOG" was new writing there.
- S3 data (not an S3 pass: drawing during a request was not exercised): while requests ran, 918 frames at 32.5 fps, pipeline p95 54.4 ms.
- **S2 PASS on the user's judgment** (2026-10-25: "The physical testing went well."; criterion ≥ 4 of 5 judged correct, with a summary). The user did not single out any try; every READ line matched the letters in the image sent (checked here). Time to answer for new writing 2.3–4.0 s, follow-up actions on the same writing 0.8–1.5 s.

**2026-10-24 (23:09–23:15): S1 selection, run 3 (D53, run 2 canvas loaded) — count 1: 10 of 10 completed loops exact (meets ≥ 9 of 10); count 2: 10 of 12 loops (83 %, does not); CPU throttled at low battery**

- On the charger (charging, 18 % at the start). Setup unchanged (variation 0.21 px; calibration 2026-10-24 22:51:16). Canvas brightness 163.
- `draw --ai --seconds 360 --trace --save-every 2 --load data/canvas/canvas-20261024-225822.json` (`draw-20261024-231512.json`, trace `data/diagnostics/draw-20261024-230856/`): the user's CAT DOG SUN from run 2 loaded (strokes 908–919: CAT 908–912, DOG 913–916, SUN 917–919), SELECT pressed, 15 loops at 13–121 s, then no hand until the 360-s limit.
- Frame rate: 20.3 fps overall (camera 59.7), pipeline median 51.8 / p95 68.3 ms; 23–31 fps during the loops; **MediaPipe inference median 34.2 ms** (runs 1 and 2: 10.6 and 10.9 ms). After the run (33 %, charging at 107 W) tracking a saved frame of this run took 7.6 ms per frame (standalone `HandTracker.process`, median of 100).
- Loops (order CAT, DOG, SUN, CAT, DOG, SUN, CAT, DOG, SUN, CAT; a broken loop redone on the same word): 1 CAT, 2 DOG, 3 SUN, 4 CAT, 5 DOG, 6 SUN, 7 CAT exact; 8 DOG broken (2.3 s, an arc over D and O); 9 DOG exact; 10 SUN exact; 11 CAT broken (2.9 s, around C and A only); 12 CAT exact (the 10th word); then 13 DOG, 14 SUN, 15 CAT exact (the user continued the order).
- **Count 1, completed loops: 10 of 10 exact (all 15 loops: 13 of 13). Count 2, all loops (broken = failed): 10 of 12, 83 % (all 15: 13 of 15, 87 %).** Against S1 (≥ 9 of 10 tries): count 1 meets it, count 2 does not. Runs 2 and 3 together: 22 of 22 completed loops exact; every miss is a broken loop (R34).
- D53: as drawn, all 13 completed loops would also have been exact in this run; the two broken arcs as drawn would have selected part of a word (loop 8: D's stem and O; loop 11: C), with D53 nothing. Loop 6 had one cursor point far off the canvas (bounds from x = −200) and still selected exactly SUN.
- Broken loops (R34): loop 8 ended with the index read as curled (fold 74–97°, ~0.6 s); loop 11 with the index fold at 61–73° (just above the keep band's 60°, D47) for ~0.6 s.

**2026-10-24 (22:52–22:58): S1 selection, run 2 (D53) — not passed: completed loops 9 of 9 exact, all loops 9 of 11 (82 %); the 10th word was not reached; frame rate collapsed (laptop on battery)**

- Setup moved 7.7 px (mean shift +8.2, +12.9 camera px); automatic recovery accepted (check target 2.12 px, validation mean 1.12 / max 2.23 px; calibration 2026-10-24 22:51:16). Canvas brightness 165. Local AI warmed up; no AI request (S1 only).
- `draw --ai --seconds 360 --trace --save-every 2` (`draw-20261024-225822.json`, trace `data/diagnostics/draw-20261024-225101/`, canvas `canvas-20261024-225822`): 13,241 frames, 36.8 fps overall (camera 52.6), pipeline median 24.7 / p95 73.8 ms. Writing took 0–265 s (31 strokes drawn, ERASER and CLEAR used); 12 strokes on the canvas: CAT 908–912 (T bar 911), DOG 913–916, SUN 917–919.
- Protocol: loops in the order CAT, DOG, SUN, CAT, DOG, SUN, CAT, DOG, SUN, CAT; a broken loop is redone on the same word. 11 loops (265–358 s): 1 CAT, 2 DOG, 3 SUN, 4 CAT, 5 DOG, 6 SUN, 7 CAT exact; 8 DOG broken (2.5 s, an arc over the top of D and O), 9 DOG broken (3.1 s, around D and O but not the bottom or G), 10 DOG exact, 11 SUN exact. The run ended (360-s limit) 2.3 s after loop 11, before the 10th word (CAT).
- **Count 1, completed loops: 9 of 9 exact. Count 2, all loops (broken = failed): 9 of 11 (82 %).** S1 (≥ 9 of 10 tries): **not passed** (9 of the 10 words done; count 2 below 90 % whatever the 10th loop had done).
- D53 live: the closed loop dropped 0–36 points of 55–140 (logged `points` / `closed_points`). Rebuilt from the trace: as drawn, loop 1 would have missed CAT's T bar (911) and loop 10 DOG's O (915); with D53 both were exact. No loop was made worse (loop 9 as drawn: D's stem only; with D53 nothing).
- Broken loops (R34): loop 8 ended with the index fold rising to 60–123° (read as curled, then pinch, then lost); loop 9 with pinch readings (fold 74–89°). Both partial and redone at once.
- **Frame rate:** 46–51 fps until 256 s, then **10–17 fps** to the end, with the camera delivering ~33–35 instead of 60 fps; the whole selection phase ran at that rate (~16 loop points per second vs ~44 in run 1). Not the selection halo: it started before the first selection (270.7 s), and rendering this canvas takes 0.9 ms without and 4–6 ms with a selection (offline). After the run the laptop was on battery (21 %, Balanced plan, processor performance 56 %); the Windows log has an AC/DC event at 20:35, no event at the drop. Likely cause: battery power saving; a run on mains power will confirm or refute it. Run 1 (same evening) also slowed from ~50 to 33–40 fps after 100 s. Two stalls at the start (1.59 s at 5.9 s, 1.34 s at 14.3 s; cause not checked).

**2026-10-24 (21:28–21:34): S1 selection, run 1 — FAIL (10 of 12 completed loops exact; 5 loops broke off and selected nothing)**

- Setup moved ~287 camera px since 2026-10-23 (camera moved again, R10); automatic recovery accepted (check target 2.12 px, validation mean 1.15 / max 2.52 px; calibration 2026-10-24 21:28:41). Canvas brightness 181; room light on. Local AI warmed up (`qwen3-vl:8b-instruct`), no AI request in this run (S1 only).
- `draw --ai --trace` (`draw-20261024-213346.json`, trace `data/diagnostics/draw-20261024-212826/`, canvas `canvas-20261024-213346`): 239 s, 41.0 fps, pipeline median 25.6 / p95 46.1 ms. The user wrote CAT DOG SUN with PEN (14 strokes: CAT 1–6, the T's top bar is stroke 5; DOG 7–10; SUN 11–14), pressed SELECT and drew 17 loops.
- Every loop rebuilt from the trace (the 5 buffered start points included) reproduces the logged selection exactly (17 of 17).
- Completed loops (12): **10 exact** (CAT ×4, DOG ×3, SUN ×3); **2 wrong**, both on CAT's T bar, which ends ~40 px from DOG's D: loop 8 around DOG also took the T bar (`[5, 7, 8, 9, 10]`), loop 9 around CAT missed it (`[1, 2, 3, 4, 6]`). Cause (overlay `s1_loops_8_9.png` in the trace folder): the stroke starts where pointing starts, so the path of the finger moving to the loop's start becomes part of the loop. Loop 8 began between CAT's A and T and ran over the T to the top of DOG; the closed polygon (end joined to start) then contains the T bar. Loop 9 began at the T's stem and ran up through the T bar; with the end-to-start chord this cut ~45 % of the bar out of the polygon (selected below 60 %).
- Broken loops (5, all selected nothing): 0.8–1.8 s long. Loops 13, 15 and 16: hand lost (NOT SEEN) for > 0.6 s (13 at the top edge of the projection above SUN, 15 and 16 at the top of CAT); loops 2 and 10: index read as curled (fold 98–151°) for ~0.6 s. Each time the user redid the loop at once and the next loop was right (2→3 DOG, 10→11 CAT, 13→14 SUN, 15/16→17 CAT). The interruptions lasted 1.1–2.7 s, as long as the user's pauses between deliberate loops (1.6–2.0 s), so a longer pen-lift delay cannot tell them apart.
- **S1 criterion (≥ 9 of 10 tries exact): FAIL** — completed loops 10 of 12 (83 %); all loops 10 of 17; first try per intended selection 6 of 12.
- Fix D53 (proposed after this run; approved by the user and built the same evening, §10): close the loop at its tightest point — the closest pair between the loop's first and last third — and select with that closed part (drops the lead-in and any overshoot). Offline on these 17 loops: 12 of 12 completed loops exact, the same for head/tail windows of 25 %, 33 % and 40 % (50 % breaks 2: the windows meet). The broken loops are tracking losses over the writing (same cause as G8: the hand found far less often over a busy canvas without the light); no change proposed for them.

**2026-10-23 (21:05–21:22): G8 run 1 (D50 light on the hand, busy background) — FAIL; the light more than doubles hand finding**

- First attempt: the setup check found none of the 4 corners; a camera frame showed only a plain wall and projecting white vs black changed 0.0 % of the frame (the projector was not showing the picture or the camera pointed away). After the user fixed it: projection in 37.4 % of the frame (margins left 656, right 52, top 138, bottom 281 camera px). The setup had moved ~165–205 camera px; automatic recovery accepted (check target 1.00 px, validation mean 1.00 / max 3.23 px; calibration 2026-10-23 21:16:55). Canvas brightness 177; room light on.
- `gestures --angles --busy --light ab --rounds 4 --prepare 2 --hold 5` (`gestures-20261023-212223.json`, frames `data/diagnostics/gestures-20261023-211640/`): hand found over the pointing hold frames **light off 30.5 %** (1500 frames; rounds 1 and 3: 28.5 / 32.5 %), **light on 74.3 %** (1790; rounds 2 and 4: 84.4 / 63.2 %); light-on timing 35.9 fps, pipeline p95 42.4 ms. **G8 FAIL** (74.3 % < 90 %; p95 > 33 ms).
- Shape numbers not usable: the saved frames show an open hand during POINT UP-LEFT and POINT UP-RIGHT (round 2), pointing during OPEN HAND (round 1) and a second person's hand in the projection in round 2 (frames 10, 13); the reported "open read as POINT" (100 frames) and DRAW in OPEN holds (177 frames: round 1 off 99, round 2 on 40, round 4 on 38) follow the hand actually shown. Most other frames follow the prompts.
- Frames confirm the light: in light-on rounds the ink and text are cut away around the hand (e.g. 22_up_0, 10_up_right_0).
- Limit seen: the light only covers a tracked hand; a hand entering or lost is still covered in lines while it is searched for, which on this busy canvas is the weak point (search frames also cause the slow p95).

**2026-10-23: G6 responsiveness and G7 undo/redo — status from the recorded runs (no new session)**

- G6 criterion: "≥ 30 fps processing while drawing (60-s run), pipeline p95 ≤ 33 ms" (frames not specified). Recorded `draw` runs with drawing: G3 run 4 42.8 fps, p95 40.5 ms all frames / 28.3 ms hand frames; G3 run 5 46.0 / 37.3 / 25.4; G4′ 55.9 / 32.0 / 24.3; G5′ run 2 41.7 / 40.4 / 34.9; G5′ run 3 48.3 / 37.6 / 33.3. Processing passes everywhere; p95 passes on hand frames in 3 of 5 runs and over whole runs in 1 of 5. The slow frames are the hand search while no hand is tracked (two views of ~10.5 ms each, D40). **G6 not passed** (not re-interpreted to pass).
- G7: undo/redo of every action type is covered by unit tests (`tests/test_canvas.py`); live, UNDO and REDO were pressed in G5′ runs 2 and 3 (one each). The 5 live round trips were not run: **G7 not formally passed**.

**2026-10-23 (19:38–19:43): G5′ presses, run 3 — protocol not completed; 14 presses, 0 wrong (runs 1–3: 32 presses, 0 wrong, 0 missed)**

- First attempt 19:38: setup moved 46 px; automatic recovery refused at validation (top target sd 0.32 px > 0.3); `recalibrate` 19:39 refused too (bottom-right target: 7 of 10 frames); the corners shifted ~3 camera px between the two attempts a minute apart: the camera was still settling after being knocked. `recalibrate` 19:40 accepted (check target 1.86 px, validation mean 0.95 / max 2.06 px).
- `draw --seconds 120 --trace --save-every 2` (`draw-20261023-194337.json`, trace `data/diagnostics/draw-20261023-194122/`): presses (replay): ERASER 16.4 s, MOVE 19.1, black 21.0, red 23.6, blue 25.2, green 27.1, thin 29.2, medium 31.7, thick 34.0, UNDO 36.4, REDO 38.0, CLEAR 40.6 (in toolbar order, each after a hold of 1.5–2.7 s on that button), then drawing and CLEAR at 60.4 and 74.4 s (deliberate holds of 2.3–2.6 s). Rests of 0.51–0.93 s pressed nothing. PEN never pressed, no second round, 6 strokes drawn: the 20-press protocol was not followed. Processing 48.3 fps, pipeline p95 37.6 ms.
- Runs 1–3 together: **32 presses, each on the button the hand rested on; 0 wrong, 0 missed, 0 accidental** (every rest shorter than the dwell pressed nothing; no neighbouring button was ever pressed). **G5′ presses: not formally passed** (protocol never completed); measured reliable. G5′ MOVE drags not done.

**2026-10-23 (19:16–19:22): G5′ presses, run 2 — INCOMPLETE (12 presses, order not followed; 0 wrong)**

- Setup recovered automatically before the run; canvas brightness 175. `draw --seconds 240 --trace --save-every 2` (`draw-20261023-192201.json`, trace `data/diagnostics/draw-20261023-191634/`); processing 41.7 fps, pipeline median 25.5 / p95 40.4 ms.
- Presses (trace replayed through the engine and controller): ERASER 33.0 s, MOVE 40.9, black 48.6, red 61.5, blue 73.9, green 81.5, thick 97.2, UNDO 107.4, REDO 110.1, CLEAR 113.3, CLEAR 121.5, black 124.5; then drawing to the end (19 strokes). PEN, thin and medium not pressed, CLEAR pressed twice (holds of 2.54 and 2.64 s: deliberate), the second round not done.
- Every press followed a rest of 1.1–2.6 s on that same button; rests of 0.78 and 0.82 s pressed nothing; no press of a neighbouring button. Runs 1–2 together: **18 presses, each on the button the hand rested on; 0 accidental, 0 missed**. The 20-press protocol was not completed: G5′ presses still open.

**2026-10-22 (~22:26): "the drawing changes when I hover over it" (user observation)**

- The user saw existing drawings take a different direction or a slight distortion when hovering over them. Check (G5′ run 1 trace replayed through the engine and controller, stored canvas compared frame by frame): 2023 hover frames; the stored canvas changed only by the eraser (195 frames in DRAW with ERASER) and by committing the 7 pen strokes at their pen-up (6 frames counted as IDLE, 1 as HOVER: the frame that ends a stroke). Hovering never changed it.
- Cause: optical. The part of a drawing that falls on the hand is projected onto the hand, which is nearer the projector than the wall, so it appears shifted and bent next to the hand's shadow on the wall. D50 (plain white on the hand) would remove it. **User decision: build D50 after the Phase 2 acceptance tests** (then its own test and quick re-runs of G1″, G2, G3).

**2026-10-22 (22:21–22:24): G5′ presses, run 1 — INCOMPLETE (6 of 20 presses before the 120 s ended; 0 wrong)**

- Protocol: 20 dwell presses in a stated order (PEN … REDO, then PEN … thin), open hand, lift above the toolbar between buttons; the user asked to draw between presses (allowed: only presses are scored).
- `draw --seconds 120 --trace --save-every 1` (`draw-20261022-222402.json`, trace `data/diagnostics/draw-20261022-222145/`): presses reconstructed by replaying the trace through the engine and controller (identical action log after the final pen-up): ERASER 34.4 s, MOVE 45.1, black 59.6, red 71.2, blue 93.2, ERASER 106.2 (PEN at the start skipped: already selected). Every rest on a button of 1.55–2.14 s pressed that button; two passes of 0.53 and 0.58 s pressed nothing. **0 wrong presses, 0 missed presses**, but 6 of 20: not evaluable. Processing 48.4 fps, pipeline p95 36.8 ms.

**2026-10-22 (22:15–22:17): G4′ run 1 (partial erase; room light) — PASS**

- Protocol (fixed before the run): 3 horizontal lines with the pen, ERASER by dwell, one straight swipe down through the 3 lines, open hand. Setup recovered automatically before the run; canvas brightness 166.
- `draw --seconds 60 --trace --save-every 1` (`draw-20261022-221719.json`, canvas `data/canvas/canvas-20261022-221719.json/.png`): strokes 3, press:eraser 1, erase actions 1; **6 strokes on the canvas**; processing 55.9 fps, pipeline median 16.0 / p95 32.0 ms.
- Check: the trace replayed through the engine and controller reproduces the saved canvas exactly; eraser radius 24 px (medium), 80 erase positions along x 565–652, y 27–494, at most 18.4 px apart (< 48 px: no holes). Each of the 3 lines is now **2 pieces**; removed ink 31–35 points per line, all within 27.4 px of an eraser position; kept ink at least 28.2 px away — the erase reach is radius + half the stroke width (24 + 4 = 28 px): ink removed only where the eraser circle touched it. **G4′ PASS.**

**2026-10-22 (22:00–22:03): G3 run 5 (confirmation after the R32 fix; room light) — PASS, clean**

- Setup moved 53.35 px (camera knocked); automatic recovery accepted (validation mean 1.15 / max 2.65 px). Canvas brightness 174.
- `draw --seconds 120 --trace --save-every 1` (`draw-20261022-220256.json`, canvas `data/canvas/canvas-20261022-220256.json/.png`, trace `data/diagnostics/draw-20261022-*`): **exactly 10 strokes**, one per shape; no extra stroke, no gap, **no stray line**; pauses between shapes 1.18–3.89 s; processing 46.0 fps, pipeline median 23.3 / p95 37.3 ms. **G3 PASS.**
- Bridged interruptions (D49) inside V (0.11, 0.10 s), S (0.35, 0.18 s) and Z (0.10–0.50 s): drawn as straight joins (the S looks angular).
- Note for G6: the `draw` pipeline p95 was 36.8–41.1 ms in every G3 run (G6 limit 33 ms); processing 41.7–48.7 fps.

**2026-10-22 (21:35–21:38): G3 run 4 (room light, D47–D49) — PASS by the criterion, with one stray straight tail**

- Setup 0.21 px (unchanged); canvas brightness 177. `draw --seconds 120 --trace --save-every 1` (`draw-20261022-213756.json`, canvas `data/canvas/canvas-20261022-213756.json/.png`, frames and trace `data/diagnostics/draw-20261022-213540/`): **exactly 10 strokes**, one per shape (2 horizontal lines, 2 vertical lines, circle, diagonal, L, V, S, Z); no extra stroke, no gap inside a stroke; pauses between shapes 1.02–7.03 s; processing 42.8 fps, pipeline median 25.6 / p95 40.5 ms. **G3 PASS** (criterion of §9.10).
- Defect not covered by the criterion: the S stroke carries a straight tail of ~175 px to the V. The user lifted at the end of the S (64.57 s, finger curled, index 73°); 0.6 s later, while the hand moved on, a single frame read as POINT (65.17 s, near the V), inside the D49 window, so the stroke resumed with a straight join and then ended (hand lost). Strokes 1–8 and 10 had no bridged interruption; the S had only this one (R32).

**2026-10-22 (21:31–21:34): G3 run 3 (room light, D47–D49) — INVALID (the user erased and redrew during the run)**

- Setup 0.18 px (unchanged); canvas brightness 177. `draw --seconds 120 --trace --save-every 1` (`draw-20261022-213400.json`, frames and trace `data/diagnostics/draw-20261022-213144/`): 13 strokes, ERASER pressed twice and PEN twice (cursor held 1.6–1.8 s on each: deliberate; saved frame t 75.9 shows the user holding ERASER), 3 erase actions; 6 strokes left on the canvas. Processing 48.7 fps, pipeline median 22.5 / p95 36.8 ms. Not counted (the protocol forbids corrections); the user asked to redraw.
- Up to the first correction (t 68.8 s, saved frame): all 10 shapes drawn as **9 strokes with no break** (every stroke started after a pause ≥ 1.8 s). L and V came out as one stroke: an interruption of 0.58 s (28 'other' frames) between them was bridged by D49 (< 0.6 s) — the D49 cost (a quick re-point joins strokes). D49 also bridged a 0.24-s break inside the circle and a 0.38-s one inside the Z.

**2026-10-22 (21:26–21:30): G1″ run 2 — PASS, with one room light on (first run not in a dark room)**

- Setup moved 31.43 px; automatic recovery: check target 1.87 px, validation mean 1.01 / max 2.29 px (calibration 2026-10-22 21:26:50). Canvas region brightness **177** (dark room: 153–158).
- `gestures --angles` (`gestures-20261022-213007.json`, frames `data/diagnostics/gestures-20261022-212636/`): POINT / hand found: up 99.4 % / 100 %, up-left 96.1 % / 100 %, up-right 100 % / 100 %, sideways 99.8 % / 92 %, down 97.0 % / 97 %; OPEN 100 % not POINT, FIST 99.8 % (1 POINT frame); DRAW in OPEN/FIST holds 0; processing 42.3 fps, pipeline p95 29.7 ms. **G1″ PASS.**
- Projected content on the hand (same analysis as above): over text 2173/2227 found (98 %), over plain white 307/307 (100 %). With ≥ 8 % of the area under the hand dark: **96 %** (1238/1292) with the room light vs **44 %** (21/48, a small sample) in the dark-room G1″ run 1; earlier dark-room runs over text 40–78 %. The room light largely removes the effect of projected content on the hand; most of the gain over G1′ runs 3–4 came from D48 and the hand poses (G1″ run 1, dark, already 96 % over text overall).
- Setup requirement from now on: one room light on (the hand lit by more than the projector); see §2.

**2026-10-22 (~21:00): projected content on the hand (user observation) — analysis; room light**

- The user observed that when projected text or lines fall on the pointing finger ("like a shadow on the finger"), the indicator often shows "hand: NOT SEEN". All sessions so far ran in a dark room (every light off).
- Offline check on the four recordings with prompt text (G1′ runs 3–4, angle baseline, G1″ run 1; pointing holds; the screen under the last known hand box, projector px, from the calibration valid at the time): hand found **100 %** (2559/2559 frames) when < 2 % of that area was dark, 96 % (1795/1873) at 2–8 %, **62 %** (1061/1717) at ≥ 8 %. Per run, over text vs plain white: G1′ run 3 40 % vs 100 %; angle baseline 78 % vs 100 %; G1″ run 1 96 % vs 100 %. (Not-found frames are placed at the last known hand position, which favours the association somewhat; the hand was never lost over plain white.)
- Proposed D50 (even light on the hand: plain white projected on and around the tracked hand, with movement look-ahead, held ~1 s after a loss; A/B test G8). **User decision: not now** — the user turned one room light on so the hand is lit by more than the projector, and asked to test the current system under that light first.

**2026-10-22 (20:50–20:54): G3 run 2 (with D47 + D48) — FAIL (20 strokes; about 15 shapes drawn, 5 breaks)**

- Setup moved again (~19 camera px); automatic recovery: check target 2.10 px, validation mean 1.12 / max 2.47 px (calibration 2026-10-22 20:51:13).
- `draw --seconds 120 --trace --save-every 1` (`draw-20261022-205413.json`, frames and trace `data/diagnostics/draw-20261022-205059/`): **20 strokes** (protocol: 10); processing 41.7 fps, pipeline median 26.6 / p95 41.1 ms. **G3 FAIL.**
- 15 strokes started after a pause of ≥ 1.86 s (deliberate): the user drew about 15 shapes instead of the 10 (extra loops and arcs), so the count is not a clean measure. 5 strokes came from breaks of 0.24–1.10 s (G3 run 1: 16): 2 with the index turned towards the wall (read as bent 65–107°, 2-D reach 0.8–1.3; saved frames t 31.4 and 78.1: back of the hand to the camera, finger pointing into the wall, R30), 2 with the hand lost (> 0.15 s; one ~1 s), 1 with the little finger read as straight (23–29° < the 30° keep limit).
- Design evidence for D49 (the traces replayed through the engine with a pen-lift delay): G3 run 2 20 → 16 strokes (0 breaks < 1 s), G3 run 1 34 → 17, G2 runs 3 and 4: 0 strokes; the shortest deliberate lift observed 1.12 s (run 2).

**2026-10-22 (20:46–20:48): G2 run 4 (fresh, with D47 + D48) — PASS**

- Setup moved again (~9 camera px); automatic recovery: check target 2.13 px, validation mean 1.13 / max 2.51 px (calibration 2026-10-22 20:46:41).
- `draw --seconds 60 --trace --save-every 1` (`draw-20261022-204841.json`, frames and trace `data/diagnostics/draw-20261022-204627/`): **0 strokes, 0 presses, DRAW never entered**; hover 3044 / idle 202 frames (hand present ~94 %); shapes open 2478, other 540, pinch 11, **point 8** (longest run 3 frames < 7); processing 54.1 fps, pipeline median 20.3 / p95 29.7 ms. **G2 PASS** with the changed classifier and tracker.
- Coverage: cursor x −13 to 1285, y up to 690; the toolbar band only 27 frames (1 button visit, PEN 0.24 s): the "0 presses during G2" part of G5′ was only lightly exercised in this run (run 3 had 7 visits).
- Unexpected: the phantom-middle flag was set on 490 open-hand frames (fingers held together: index and middle tips close, both straight). Harmless here (POINT also needs ring and little finger curled) but it means two fingers held together with ring and little curled now read as POINT (added to R31).

**2026-10-22 (20:39–20:43): G1″ run 1 (fresh live, D48) — PASS**

- Setup moved 3.76 px; automatic recovery: check target 2.09 px, validation mean 1.10 / max 2.42 px (calibration 2026-10-22 20:40:05). No video (timing as in use).
- `gestures --angles` (`gestures-20261022-204317.json`, frames `data/diagnostics/gestures-20261022-203951/`): POINT and hand found per angle: up 100 % / 93 %, up-left 100 % / 100 %, up-right 100 % / 100 %, sideways 100 % / 100 %, down 100 % / 95 %; OPEN 100 % not POINT (505 of 505), FIST 100 % (508 of 508); DRAW in OPEN/FIST holds 0; processing 42.7 fps, pipeline p95 29.7 ms. **G1″ PASS** (criteria of §9.10, over the whole recording).
- Per round: round 1 every prompt 100 % / 100 %; round 2 up hand found 86 % and down 88 % (below 90 % if a round were judged alone; the criterion is over the recording).
- Saved frames: natural pointing with the back of the hand to the camera (up, up-left) is now tracked ("hand: seen").
- Attribution: the D48 classifier rules decided only 25 of 2504 pointing hold frames (two-view index rule; phantom rule 0 frames), so this live pass is not mainly due to them; the hand poses of this run were easier to read and the tracker setting (presence/tracking 0.3) cannot be separated from that without video. The replay of the baseline recording (§13.2, 20:08) remains the evidence for the rules (3 → 5 of 7 prompts).

**2026-10-22 (20:08–20:12): D48 angle recording (baseline, before the D48 rules) and offline analysis**

- Setup moved 35.23 px; automatic recovery: check target 2.09 px, validation mean 1.11 / max 2.46 px (calibration 2026-10-22 20:08:53).
- `gestures --angles --video` (`gestures-20261022-201209.json`, `data/diagnostics/gestures-20261022-200840/`: frames.jsonl + video.avi, 5927 frames, 0 dropped). Live G1″ (baseline): up 99.6 % POINT / hand 96 % PASS; up-left 95.9 % / hand **61 %** FAIL; up-right 93.8 % / 84 % FAIL; sideways **61.8 %** / 100 % FAIL; down 100 % / 100 % PASS; open 100 %, fist 100 % not POINT; DRAW in OPEN/FIST holds 0; timing 43.4 fps, pipeline p95 **34.1 ms** (FAIL by 1.1 ms; the video thread was encoding during this run). **G1″ (baseline) FAIL.**
- Replay fidelity: the same per-prompt figures within a few points; shape equal to the live run in 93.6 % of frames; tracker 7.9 ms median per frame offline. The rounds failed differently (sideways 100 % in round 1, 23 % in round 2; up-left hand 18 % in round 1, 83 % in round 2), so both rounds were used for diagnosis — a deviation from the plan's "round 2 held out"; the judgement is the fresh live G1″ (the true held-out test).
- Causes: (1) sideways round 2: index 3-D fold median 54° (p90 62°) for a straight finger (hand cocked); 2-D reach 1.80 (pointing p10 ≥ 1.66 at every angle; fist p90 ≤ 1.06); (2) up-right round 1 and upward pointing: the phantom middle finger (tip gap median 0.16, middle fold 14–38°); (3) up-left round 1: the hand not found (tracker log: 118 search misses, 8 unconfirmed hits, 8 region drops in 189 hold frames); the hand is visible in the video (back of the hand, ~120 px, the prompt text projected across it).
- Classifier candidates on every recorded prompt (hold frames; longest consecutive POINT run in non-pointing prompts; 7 frames start a stroke): 2-D reach alone (≥ 1.5) turns 13.2 % of G1 run 1 fist frames into POINT: rejected. Two views (fold ≤ 65° and reach ≥ 1.6): sideways 61.8 → 98.9 %, fist/open +0 to +0.5 % (longest run 1), G1 run 1 pinch prompt 11.9 → 19.8 % (longest run 6 → 15). Phantom (gap < 0.35) alone: pinch prompt longest run 65 — refined to "middle reads straight (< 45°)": pinch prompt unchanged (11.9 %, run 6), G1′ run 4 75.3 → 87.8 %, up-right 93.8 → 97.6 %.
- Tracker variants (replay, hand found per hold): presence + tracking confidence 0.3: up-left r2 82.7 → 99.6 %, up-right r1 92.3 → 95.6 %, all frames 90.0 → 92.2 %; detection confidence 0.3 and region patience 5/10: no consistent gain. Up-left round 1 stays 14–26 % with every setting; IMAGE-mode detection on crops of 720/560/440/360 px around the last hand found 0–3 % of its missing frames (up-right 0–19 %): a detection limit of the model for that hand pose, not of the settings.
- With the D48 rules and the tracker setting (replay of the same recording): up 100 % / hand 99 %; up-left 97.0 % / **68 %** (r1 26 %, r2 100 %); up-right 97.6 % / 92 %; sideways 98.2 % / 100 %; down 100 % / 100 %; open, fist 100 % not POINT; DRAW in OPEN/FIST holds 0; tracker 8.3 ms median, 17.9 ms p95 offline; shape equal to the live (old) run in 90.1 % of frames. 5 of 7 prompts pass (baseline 3).

**2026-10-22 (19:43–19:45): G1′ run 4 — FAIL (pointing upward again; analysis of the middle-finger misreads)**

- Setup 0.09 px (unchanged). The user was asked for the sideways posture with a concrete description; the saved frames (01_point_0, 01_point_1, 04_point_1) again show the index pointing straight up with the back of the hand to the camera.
- `gestures` (`gestures-20261022-194451.json`, frames `data/diagnostics/gestures-20261022-194337/`): **POINT 75.3 %** of 392 hand frames (of 544 hold frames; other 91, pinch 6) FAIL; OPEN 100 % (620 of 620) PASS; FIST 99.8 % not POINT (572 of 609; 1 POINT frame) PASS; DRAW during OPEN/FIST holds 0 PASS. **G1′ FAIL.**
- Per round: round 1: hand in 268 of 297 hold frames, POINT 178 (66 %), keep-band 200; round 2: hand in 124 of 247, POINT 117 (94 %), then no hand for the last 123 frames of the hold.
- Non-POINT reasons in the POINT holds: middle fold < 60° 66 frames (alone), index > 45° 9, little < 45° 7, combinations 14. In the 83 POINT-prompt frames (runs 2–4) misread through the middle finger, the tracker put the middle fingertip on the index fingertip (2-D tip gap / palm size: median 0.25, p5 0.06; correctly read POINT frames 1.10; open hand 0.52; fist 0.28): from behind, the one visible finger is assigned to both index and middle. A 2-D reach measure does not help (the misplaced middle tip reaches as far as an open hand's, median 1.81).
- Candidate rule (design evidence only, not implemented): middle tip within 0.35 palm of the index tip and the index extended → the middle counts as curled. Replay: run 4 POINT 295 → 346 of 392 (88 %), run 3 120 → 121, run 2 unchanged (418); G1 run 1 two-finger prompt 31 → 35 of 328 POINT, pinch prompt 42 → 56; open/fist ≤ +1 frame. Helps, does not reach 95 % alone; frames without a hand (pointing up loses the hand for long stretches) are not addressed by any classifier rule.

**2026-10-22 (19:35–19:38): G1′ run 3 (first run with D47) — FAIL (pointing upward / into the wall)**

- Setup drifted 6.08 px; the `gestures` automatic recovery refused at the validation step (point 16 at (51, 690), bottom-left near where the user stands: single-frame sd 0.33 px > 0.3); `recalibrate` with the user away: check target 1.67 px, validation mean 1.02 / max 2.19 px, confirmation 0.09 px (calibration 2026-10-22 19:35:41).
- `gestures` (`gestures-20261022-193801.json`, frames `data/diagnostics/gestures-20261022-193643/`; setup 0.06 px): **POINT 54.3 % POINT** of 221 hand frames (of 466 hold frames; pinch 65, other 36) FAIL; OPEN 100 % not POINT (614 of 614) PASS; FIST 100 % not POINT (366 of 517) PASS; **DRAW during OPEN/FIST holds 0** (the engine ran with the D47 keep flag) PASS. **G1′ FAIL.**
- Per round: POINT round 1: hand in 51 of 209 hold frames, 44 POINT; round 2: hand in 170 of 257, 76 POINT, 65 pinch (index fold median 86°, pinch ratio 0.13: the finger hidden behind the hand), 29 other.
- Saved frames: the user pointed upward or diagonally upward with the back of the hand to the camera (01_point_1, 04_point_1: "hand: NOT SEEN"), or into the wall (04_point_0: the finger hidden behind the fist). In run 2 (PASS, 99.3 %) the finger lay sideways along the wall with the side of the hand towards the camera. D47 does not change the classification (only the engine), so it is not implicated.
- Conclusion: pointing recognition depends strongly on the pointing posture at this camera position (R30). Next: a fresh G1′ with the documented posture (§9.10), and the posture stated to the user with a concrete picture.

**2026-10-22 (19:09–19:11): G3 run 1 — FAIL (strokes break while the user is still pointing)**

- Protocol fixed before the run (told to the user): 10 strokes (2 horizontal lines, 2 vertical lines, a circle, a diagonal, the letters L, V, S, Z, one stroke each), open hand between strokes, pen, 120 s; pass = exactly 10 strokes on the saved canvas, no extra stroke, no gap inside a stroke.
- `draw --seconds 120 --trace --save-every 1` (`draw-20261022-191123.json`, frames and trace `data/diagnostics/draw-20261022-190908/`; setup 0.66 px): **34 strokes** (DRAW entered 34 times; idle 1662 / hover 1995 / draw 1796 frames). **G3 FAIL.** The canvas also does not follow the 10-shape plan exactly (e.g. a line through the circle, a "7"), so not every extra stroke is a system error.
- 16 breaks shorter than 1 s between strokes. The saved camera frames inside such breaks (t 24.3, 59.7, 71.8 s) show the index finger still clearly pointing (mostly pointing upward) while the shape was read as not POINT. Frames around the exits: index fold > 45° (35 frames), middle fold < 60° (22), a pinch reading with index > 45° (~20). Inside the short breaks: index fold median 29° (p90 53°), middle median 63° (p10 54°), ring 71°, little 63°; after real pen lifts (mostly a fist): index median 89°, middle 93°; G1′ open hand: index 41°, middle 38°, ring 39°, little 30°. While drawing, the middle finger's fold sits close to the 60° limit (p5 63°).
- Replay of the recorded measures through the real engine with a "keep drawing" band (design evidence only, `sim_hysteresis.py` in the session scratchpad): while in DRAW a frame continues the stroke if index ≤ 45+b, middle/ring ≥ 60−b, little ≥ 45−b (thumb ignored); entry unchanged. b = 15°: G3 run 34 → 21 strokes, breaks < 1 s 16 → 6; G2 PASS run unchanged (0 strokes, DRAW never entered, for b = 10/15/20); G1′ run 2: 1 DRAW frame at the start of an OPEN hold (the user still pointed until 30 ms before that hold began). The 6 remaining breaks: index read as bent 80–90° for several frames, or the hand lost for up to 0.5 s (> the 0.15 s dropout hold); some may be real lifts.
- Timing (not the G6 run): processing 45.4 fps; pipeline median 23.5 / p95 40.6 ms.

**2026-10-22 (19:01–19:06): G2 run 3 — PASS (no accidental ink)**

- First attempt 19:01: the setup check stopped (1 of 4 corners not seen steadily). Second attempt: setup moved 11.96 px; the automatic recovery built a good replacement (check target 1.59 px, validation mean 1.03 / max 2.28 px) but refused it at the confirmation step (top-right corner single-frame sd 0.31 px > 0.3): **not loosened**. `recalibrate` with everyone clear, 19:03: check target 1.53 px, validation mean 1.01 / max 2.18 px, confirmation 0.06 px (calibration 2026-10-22 19:03:06).
- `draw --seconds 60 --trace --save-every 1` (`draw-20261022-190526.json`, frames and trace `data/diagnostics/draw-20261022-190411/`; setup 0.05 px): **0 strokes, 0 presses, DRAW never entered** (hover 2974, idle 183 frames; hand present ~94 %). Shapes: open 1229, pinch 934, other 693, **point 1** (a single frame; the 7-frame debounce held), no hand 299. **G2 PASS.**
- Coverage: cursor x 43–1235, y down to 713 (the toolbar band: 91 frames); 7 button visits (eraser, blue, thin, thick, clear), longest 0.27 s, so **0 presses during G2** (that part of G5′ passes).
- Timing: processing 52.6 fps (camera 60.1); pipeline median 20.4 / p95 32.3 ms (G2 is not the G6 run: G6 is measured while drawing).

**2026-10-22 (18:50–18:53): G2 run 2 — INVALID (the user pointed on purpose; drawing behaved correctly)**

- Setup moved again (variation 90.66 px, mean shift (−179.1, −19.5) camera px: the camera had been moved); `draw` recovered automatically (check target 1.26 px, validation mean 0.97 / max 2.36 px, confirmation 0.08 px; calibration 2026-10-22 18:51:02).
- `draw --seconds 60 --trace --save-every 1` (`draw-20261022-185302.json`, frames and trace `data/diagnostics/draw-20261022-185048/`): 11 strokes, 1 press (GREEN); modes idle 458 / hover 1632 / draw 802 frames; shapes point 818, other 655, pinch 437, open 369, no hand 612.
- Saved camera frames: every frame taken in DRAW (t 5.1, 9.1, 28.3, 51.6 s, ...) shows the index finger deliberately pointed at the wall; the open hand (t 17.2) and a loose hand sliding along the toolbar (t 24.3) gave HOVER, no ink. GREEN was pressed after the cursor rested on it 1.02 s (46.80–47.82 s); the other toolbar visits lasted 0.30–0.56 s and pressed nothing. The system did what D46 specifies; the run was not the G2 protocol (no index-only shape), so **not counted as a G2 result**. Not a G3 result either (the intended strokes were not stated in advance).
- Timing (not a G6 run): processing 48.2 fps (camera 60.2); pipeline median 21.7 / p95 41.0 ms.
- Lesson for the procedure: state the purpose of G2 plainly ("checks that nothing is drawn when you do not point"); the user's natural reaction to the canvas is to draw.

**2026-10-22 (18:39–18:42): G2 run 1 — INVALID (user not in position when the run started)**

- Setup moved again before the run (variation 24.29 px, mean shift (+41.4, +25.0) camera px); `draw` recovered automatically (check target 1.96 px, validation mean 1.03 / max 2.22 px, confirmation 0.09 px; calibration 2026-10-22 18:40:09). The first attempt a minute earlier failed to open the camera (DirectShow open error, once; a direct open right after worked).
- `draw --seconds 60 --trace` (`draw-20261022-184209.json`, trace `data/diagnostics/draw-20261022-183955/`): no hand for the first 27 s; 27–48 s the hand was read as POINT in long runs (215 and 91 frames) and 9 strokes were drawn; 48–60 s mostly no hand. Shapes: point 699, other 121, pinch 27, open 2, no hand 1540 frames.
- The user reports not being in position yet when the drawing screen appeared, so the 60 s were not the G2 protocol (free movement without the index-only shape): **not counted as a G2 result**.
- Observation kept for the next run: the POINT frames had the index straight (fold median 20°) and middle/ring/little fingers at a median 74–79° (10th percentile 63–70°), just past the 60° curled limit; the deliberate G1′ POINT had them at 94–103°. A loose hand with the index out may read as POINT; the fresh G2 run (with camera frames saved) will show whether that happens during normal movement. No threshold changed.
- Timing (not a G6 run): processing 39.8 fps (camera 60.2); pipeline median 28.0 / p95 42.8 ms over all frames, 20.9 / 29.1 ms on hand frames (no-hand searching is the slower part).

**2026-10-22 (18:25–18:26): G1′ run 2 — PASS (fresh recording, pointing sideways)**

- Posture changed only (no code or parameter change since run 1): the user stood to the side and pointed sideways across the projection, finger flat on/near the wall, side of the hand towards the camera. Open hand and fist held as in run 1.
- Setup check 0.73 px (unchanged, no recalibration); canvas region 153.
- `gestures` (`gestures-20261022-182627.json`, frames `data/diagnostics/gestures-20261022-182505/`): **POINT 99.3 % POINT** (421 hand frames of 496 hold frames; misreads: 2 other, 1 pinch) PASS; **OPEN 100 % not POINT** (536 of 536; read as open 368, other 168) PASS; **FIST 100 % not POINT** (218 of 429; read as pinch 164, other 54) PASS; **DRAW during OPEN/FIST holds 0** PASS. **G1′ PASS.**
- Per round: POINT 98.7 % (152 hand frames of 227) and 99.6 % (269 of 269); OPEN 269/269 and 267/267 hand frames, 0 POINT; FIST 124/219 and 94/210 hand frames, 0 POINT. Both rounds pass on their own.
- Notes: the fist is found in only ~51 % of hold frames (a fist seen from behind is a weak palm-detector target); harmless for drawing (no hand = no ink) but the cursor disappears while a fist is held, so the open hand is the better "not drawing" shape. The fist read as PINCH is harmless under D46 (PINCH → cursor only). The first POINT wait took 123 frames (the user finding the posture); the second 258.

**2026-10-22 (18:14–18:18): G1′ run 1 — FAIL (pointing hand rarely detected)**

- Before: the setup had moved again (variation 32.70 px, mean shift (−65.0, −5.1) camera px). The `gestures` automatic recovery refused at the validation step (point (345, 470) single-frame sd 0.74 px: the user was near it); after the user stepped away, `recalibrate` accepted (check target 2.05 px, validation mean 1.11 / max 2.35 px, confirmation 0.11 px; calibration 2026-10-22 18:15:19).
- `gestures` (`gestures-20261022-181755.json`, frames `data/diagnostics/gestures-20261022-181626/`; setup 0.29 px, canvas region 153): **OPEN 99.8 % not POINT** (486 hand frames of 509) PASS; **FIST 100 % not POINT** (101 of 382) PASS; **DRAW during OPEN/FIST holds 0** PASS; **POINT 82.2 % POINT of only 45 hand frames (of 357 hold frames)** FAIL. **G1′ FAIL.**
- Cause (saved frames): while pointing, the user's finger pointed into the wall and away from the camera; the camera saw a compact dark fist with a short finger stub and the on-wall indicator read "hand: NOT SEEN". MediaPipe finds no hand in any of the 4 saved pointing frames even at detection/presence/tracking confidence 0.3 and 0.2 (offline, design evidence): a pose/view limitation, not a threshold. The open hand (fingers spread) was found in 95 % of hold frames. On 2026-10-21 the user pointed sideways with the finger flat across the wall: 97 % tracked.
- Next: a fresh recording with the finger held flat and sideways across the projection (side of the hand towards the camera), or a camera position that sees the hand from the side.

**2026-10-22 (00:34): G1 run 1 — FAIL** (`gestures-20261022-003634.json`, frames `data/diagnostics/gestures-20261022-003449/`)

- Results (hold phases, hand-present frames): point 8.6 % of 35 (of 367 hold frames); open 79.7 % of 335; pinch 2.8 % of 353 (301 read as other); fist 26.6 % of 402 (258 read as **pinch**); two 78.7 % of 328; DRAW during non-POINT holds 61 frames. **G1 FAIL.** Recorded as is; no threshold changed for this result.
- Analysis (saved frames + world landmarks):
  - Round 1 POINT: no hand in the picture (the prompt started before the user was in place: a protocol flaw of the tool). Round 2 POINT: the arm entered from the left and the hand pointed up and away; MediaPipe found it in 15/175 frames. Round 2 had low hand presence for every prompt (66–132 of ~195).
  - **Pinch vs fist is not observable from this camera position:** the camera sees the back of the hand, the touching fingertips are hidden, and MediaPipe guesses them. Measured thumb–index ratio: the user's pinch median 0.66 [p10 0.40], the user's fist 0.25 [0.17]: inverted. Index fold: pinch 81°, fist 82° (the 110° fist guard never applies).
  - Open hand: finger folds median 22–32°, p90 up to 49° (limit 45°).
  - Design evidence only (same recording, NOT a G1 result): a classifier without pinch and with two fingers as a shape gives open 80–92 %, two 71–72 %, fist→other 87–91 %, for extended limits 45–55°. No variant reaches 95 % per frame.
- Conclusion: from behind the user, per-frame landmark shapes are reliable only for a clearly visible index-only point seen side-on (2026-10-21: 97 % tracked; ~80 % POINT including other shapes). Pinch cannot be used on this setup. A re-test must be a fresh recording (the adjusted classifier must not be judged on the recording it was adjusted on).

**2026-10-22: Phase 2 implementation (D44, D45)**

- Offline evidence (66 saved frames of the 2026-10-21 cursor run, real MediaPipe pass, world landmarks present: wrist→middle knuckle 0.099 m): straightness classifier POINT 10/66 (world) / 8/66 (image); fold-angle classifier POINT 53/66 (world) / 52/66 (image). Skeleton overlays: in the pointing frames MediaPipe fits the hand (index along the finger, others folded into the palm); the non-POINT frames are open hands (9.8, 10.8, 20.8 s), two fingers (18.8 s), transitions (72–74, 83–84 s) and one misfit with all fingers drawn on the index (12.8 s). Pinch ratio on pointing frames ≥ 0.43 (enter 0.25).
- Tests: 479 passed, 22 skipped (64 new). Fake-session runs: `draw` draws one 300-px stroke from a scheduled POINT sequence; draw → open-hand erase → pinch on UNDO restores the stroke; `gestures` writes frames.jsonl (21 × 2-D + world landmarks) and the G1 report.
- Hardware (00:23–00:30): the setup had moved; `draw`'s automatic recovery was **refused** at the validation step (target (640, 29) single-frame sd 0.33 > 0.3 px), nothing saved; `recalibrate` at 00:28 **accepted**: check target 1.95 px, held-out validation mean 1.04 / max 2.25 px, confirmation 0.16 px (`calibration-recovery-20261022-002905`). `draw --seconds 10` without a hand (`draw-20261022-002943.json`): setup 0.13 px, canvas region 153, 358 frames, **processing 35.7 fps** while searching (camera 60.1), pipeline median 31.9 / p95 39.1 ms, IDLE throughout, **0 strokes**, canvas saved.

**2026-10-21 (23:38–23:44): setup moved, recalibrated, first valid Kreo cursor run**

- `cursor --background 255 --save-every 1 --seconds 90`: the setup check refused the 2026-10-19 calibration (variation 115.59 px, mean shift (+185.1, −138.0) camera px: the setup had been moved). The automatic recovery (D39) **failed safely** at the check-target step (6/10 single frames, 4 × "no cross found": the operator's hand was in the projection) and saved nothing (`calibration-recovery-20261021-233904.json`); the cursor did not start. Correct behaviour.
- Operator out of the projection → `calibrate` (auto, 23:39:49): 4/4 corners 10/10, sd ≤ 0.037 px; check target 1.86 px; projection 29.8 % of the frame, margins left 447, top 164, right 357, bottom 309; corner shifts vs 10-19 +175…+211, −116…−148 camera px. `validate` (auto, `validation-auto-20261021-234054.json`): setup 0.10 px; 20/20, worst sd 0.028 px; **mean 1.19, median 1.28, p95 2.03, max 2.09, rms 1.34** projector px (edge 1.06, interior 1.51); required + stretch PASS.
- **Cursor, 90 s, white canvas (canvas region 157), hand moved freely with deliberate exits** (`cursor-20261021-234247.json`, frames `data/diagnostics/cursor-20261021-234102/`): setup check 0.19 px; 4877 frames, **processing 54.2 fps** (camera 60.2, 0 failed reads); inference median 8.5 ms (p95 19.4), queue 2.4 ms, **pipeline median 13.8 ms**, p95 33.2, one 926-ms stall; hand found 82.5 % of all frames (tracking 82.5, holding 0.5, lost 17.0), 3 tracking losses; acquisitions 1 full-frame + 4 tile, 838 search frames (search 19 ms median), 1 unconfirmed; still jitter 1.08 px rms; 0 transient jumps; reacquired after 4.26 and 8.13 s (the operator's deliberate exits at 37–44 s and 85–90 s); landmark diagnostics 24 flagged frames in 9 episodes (22 low extension).
- Saved frames (1 per second): 68 with a hand in the projection → **66 tracking (97 %)**, 2 lost (9 s: hand entering; 71 s: brief dropout); all 21 empty frames lost (**0 false positives**).
- Projected crosshair vs fingertip in the camera's own view (35 frames with both visible; fingertip = end of the hand silhouette): offsets in every direction (crosshair above in 18/35), median (−17, −2.5) camera px, sd 31 / 56 px, up to ~130 px. Hover parallax cancels in the camera's own view, so this is the **end-to-end latency during motion** (~262 ms display→camera + ~14 ms processing): the crosshair shows where the finger was ~0.28 s earlier. A still-finger accuracy run (`--accuracy`) is still needed for the Phase 1D number.

**2026-10-19 (12:25–12:36): Kreo hardware test of the whole pipeline (§9.9 steps 1–7; projector 1280×720 @ 60 Hz, 100 %; room light)**

- Before: the laptop had slept for ~6.3 h inside a `camera --preview` session (R27): the projector disconnected and the session lost its camera locks; reconnected by the user; Windows restored Extend + 1280×720 by itself. Projector resolution had been set to 1280×720 @ 60 Hz via `ChangeDisplaySettingsExW` (user-approved); Windows then chose 100 % scaling.
- Scene check: whole projection inside the frame (user re-aimed); all 4 corner targets visible, nearest 170 px from a frame edge; focus sweep peak 400 (config changed 410 → 400).
- **A1 PASS** (`devices-20261019-122819.json`): 2 displays with resolution/refresh; projector `AML TV` [AML0030] identified on HDMI by the automatic rule, current mode 1280×720 / 100 % / mode offered all OK; Kreo identified by name; MJPG 1920×1080 @ 60 → 59.9 fps; the camera keeps exposure −6 / focus 400 / gain 15 on the device.
- **A2 (automatic part) PASS:** fullscreen window rect (2560, 0, 3840, 720) = display rect, image area 1280×720 = canvas, in every session. Visual line-pair check by the user still open.
- **A3 fps PASS** (`camera-20261019-122934.json`): 3611 frames in 60.0 s, **60.15 fps**, slowest 1-s window 59, longest gap 45 ms, 0 failed reads; exposure, focus, gain confirmed at open and end, re-applied 0×.
- **A3 latency (valid)** (`latency-20261019-123627.json`): 20/20 trials, levels held (black 1.9 → 2.3, white 135.7 → 136.0), ROI = projected area; **median 262 ms**, p10 257, p90 277, min 235, max 282 (Brio: 275). 60 fps saved ~13 ms; the display path dominates (R4).
- **Detector** (`detection-20261019-123054.json`): **B1 PASS** 24/24, 240/240 single frames; **B3 PASS** max sd 0.034 px, max from mean 0.065 px (Brio 0.16 / 0.37); **B4 PASS** click-free mean 1.07, max 2.59 (edge 0.79, interior 1.73); **B2 FAIL**: blank screens rejected 4/4; two crosses at (345, 470) rejected, at (640, 360) accepted with 1 candidate. Investigated (read-only, `two_cross` recapture): the left cross of the pair falls on the projector's own blue pointer overlay (R28) and is broken into fragments (shortest half-arms 3–4 px, a hollow piece), so only one cross remained; at gap 110 around (640, 360) and at (900, 250) both crosses were intact and rejected correctly. No detector parameter changed; re-run B2 after removing the overlay. B5 not evaluable (no manual reference).
- **A5 PASS (automatic):** 3 calibrations 12:33:36, 12:33:57, 12:34:18 (~20 s each): 4/4 corners, 10/10 single frames, sd ≤ 0.024 px; check target 1.84–1.85 projector px (limit 12); projection 31.6 % of the frame.
- **A6 PASS** (`repeatability-20261019-123428.json`): mean corner variation **0.04 camera px**, max 0.07 (Brio auto: 0.66 / 1.43).
- **A7 PASS, stretch PASS** (`validation-auto-20261019-123534.json` + .png): setup check 0.03 px; 20/20 detected, worst sd 0.024 px; **mean 1.05, median 0.83, p95 2.43, max 2.54, rms 1.31** projector px; edge 0.78, interior 1.69. Error map: smooth field, largest (2.0–2.5 px) in the upper-left/upper-middle, ~0.1–0.5 at the corners: mild lens distortion a 4-point H cannot model (R8). Brio auto: 0.61 / 1.31 with the projection at ~54–67 % of the frame (here 31.6 %).
- **Hand tests 12:45–12:49 (no valid tracking result yet):**
  - `handcheck` (`handcheck-20261019-124536.json`, frames `data/diagnostics/handcheck-20261019-124521/`): grey 40 → canvas region 1 (too dark), 128 → 51, 255 → 128; "no hand" at every level. The frames show no hand until the last level (45 frames per level = 0.75 s at 60 fps; the tool was sized for 30 fps). The blue projector pointer (R28) was gone by then.
  - Offline on the two white-canvas frames with the hand (pointing, from the left, well lit): `handcheck --image` (whole-frame detector) found nothing; the cursor's **tiled** acquisition found the hand at the first try in both (scores 0.70, 0.88). With the projection at 31.6 % of the frame a hand is too small for the whole-frame palm detector; `handcheck` uses that path, so on this setup it under-reports what `cursor` can find.
  - `cursor --seconds 30` (grey 128, `cursor-20261019-124729.json`) and `cursor --seconds 30 --background 255 --save-every 1` (`cursor-20261019-124842.json`, frames `data/diagnostics/cursor-20261019-124756/`): hand found 0 %. **Invalid as tracking tests: no hand entered the projection** (all 30 saved frames: 0–1 dark pixels inside the projection). Measured anyway: setup checks 0.17 / 0.22 px; canvas region 52 at grey 128, 129 at grey 255; camera 60.1–60.2 fps; processing **34.1–34.8 fps while searching** (search ~21 ms per frame, pipeline median 32.5–33.3 ms, p95 ~41 ms): at 60 fps the two-view search (D40) no longer fits one frame interval (16.7 ms); latest-frame capture drops the rest instead of queueing.
- Not run yet: `mapdemo` (A8), B2 re-run. (A cursor run with a hand followed on 2026-10-21, see above.)

**2026-10-19: Kreo Owl 4K Pro measurements (§9.9 steps 1–2; original laptop, dark room, projector at 1920×1080 input)**

- Display topology: Duplicate → Extend (see §2.2 note). Projector `\\.\DISPLAY5` `AML TV`, identified by the automatic rule; fullscreen window rect = display rect (2560, 0, 4480, 1080).
- `devices --camera "owl 4k"` (`devices-20261019-013048.json`): "Owl 4K PRO Camera" usb eba4:1303 at DirectShow index 0 (then ACER, then the 4 Meta virtual cameras). Default 640×480 YUY2 30 fps. MJPG 1920×1080 @ 30 → 30.0, **@ 60 → 60.5**; MJPG 1280×720 @ 30/60 → 29.9/30.0; MJPG 640×480 → 30.0; YUY2 1080p 5.0, 720p 12.0, 480p 30.2 fps. Opens 0.8–3.6 s. Properties: AUTOFOCUS 1, FOCUS 395, EXPOSURE −7 (auto), AUTO_WB 1, GAIN 0.
- Read-only probes: MJPG 3840×2160 @ 30 → 30.1 (@ 60 → 29.9), 2560×1440 → 29.9 (both), 1920×1080 @ 60 → 60.1 fps. `IAMCameraControl`: exposure −13..−1 (default −7, auto+manual), focus 0..1023 (default 192, auto+manual), pan/tilt ±160, zoom 0..100, roll 0..3 (all 0, manual), AE priority not supported. `IAMVideoProcAmp`: brightness, contrast, hue, saturation, sharpness 1..64 (32), gamma 0..64 (32), white balance 1800..10000 (auto, 5000), backlight 0..6 (1), **gain 0..15 (0, manual only)**, powerline 1..2.
- `CameraManager`, 1080p @ 60, 6 s each: exposure −5 → 31.58 fps; **−6 → 60.17 fps, slowest second 60, longest gap 35 ms**; −7 → 60.14 fps; 0 failed reads; exposure confirmed at open and end, re-applied 0×.
- Projection footprint (white − black > 25 camera levels): x 507..1712, **y 0..628 (cut off at the top)**, 34.9 % of the frame; margins left 507, top 0, right 207, bottom 451 camera px. **A4 currently FAILS: re-aim (tilt up).**
- Brightness in the projection (focus 499, gain 0): −6 → black 0, grey-128 5, grey-200 48, white 69; −5 → 0 / 31 / 87 / 112; auto → 0 / 137 / 208 / 203 (60 fps; follows the content). Gain at −6: 0 → grey-128 5.7, white 69.8 (sd 0.46); 4 → same; 8 → 26.5 / 105.7 (0.89); 12 → 43.3 / 129.8 (0.85); **15 → 54.4 / 145.6 (0.86)**; 58.5–60.4 fps; no saturation. Gain restored to 0 afterwards.
- Focus: autofocus on the alignment pattern 719, 399, 64, 499, 499, 499 (0.5-s samples); on the dark desktop 391–413. Sweep on a projected 24-px checkerboard (exposure −5, keeper off): 250:59, 300:113, 350:270, 400:523, 450:332, 500:118, 550:35, ≥600: ≤10; fine 380:433, 390:487, 400:525, **410:531**, 420:509, 430:463; rechecks 410: 530, 532; 499: 122. A first sweep with the focus keeper active measured nothing: the keeper put the configured value back within 0.25 s (working as designed).
- **D43 hardware check:** `camera --headless --seconds 10` (`camera-20261019-015618.json`): requested MJPG 1920×1080 @ 60, delivered 1920×1080, driver reports MJPG; exposure manual −6, focus manual 410, gain manual 15, all confirmed by read-back at open and end, re-applied 0×; 604 frames in 10.0 s, **60.24 fps**, slowest 1-s window 59, longest gap 35 ms, 0 failed reads, frame age median 0.24 ms.

**Phase 1A acceptance scoreboard** (update after the hardware session)

| # | Test | Status | Result |
|---|---|---|---|
| A1 | Diagnostics | **PASS** (2026-10-09) | `devices-20261009-023110.json`: 2 displays with resolution/refresh; projector `AML TV` [AML0030] identified on HDMI by the automatic rule (1280×720 @ 60 Hz, 100 %, all checks OK); Brio 100 and Integrated Camera with measured modes |
| A2 | Projector output | Partial (2026-10-09) | **User visual check passed:** the WZATCO receives the 1280×720 output, the full alignment rectangle is visible, corner labels (0,0), (1279,0), (0,719), (1279,719) correct. Not yet recorded here: the `window geometry` printout and 1-px line-pair sharpness |
| A3 | Camera feed + latency | **PASS** (2026-10-09) | Brio 100, DirectShow, MJPG 1920×1080 @ 30 delivered, exposure manual −5 from config: **29.83 fps mean over 60 s, slowest 1-s window 27 (≥ 25), 0 failed reads** (`camera-20261009-022733.json`). **Display→camera latency baseline: median 275 ms** (p10 253, p90 295, min 242, max 311; 80 trials in 4 valid runs, 0 missed; dark room; ROI = central half, no calibration). A3 sets no latency threshold, so it passes on a valid measurement; the 18:32 run (16 of 20 missed) is **not valid** and not used. 275 ms is high for interaction (R4). |
| A4 | Coverage | Pending (2026-10-09) | 18:4x snapshot: the projection's bottom edge was outside the camera frame. **19:37, after re-aiming:** the whole alignment pattern (all four corner labels and the 1-px border) is inside the frame; the bottom margin is the smallest, roughly 25 camera px at the bottom-left (estimated from a downscaled frame). User to confirm with the setup preview (`camera --preview`, `b`). Saturation not yet checked. |
| A5 | Manual calibration | Partial (2026-10-09) | Three calibrations completed and saved (19:46, 19:52, 19:53). Restart reload and size-mismatch refusal not yet recorded on the hardware. |
| A6 | Repeatability (≤ 2 camera px) | **PASS** (2026-10-09) | Mean corner variation **0.75 camera px**, max 1.50 (3 calibrations 19:46–19:53; `repeatability-20261009-195330.json`) |
| A7 | Accuracy (required 5/12 px, stretch 3/8 px) | **PASS** (2026-10-09 23:24) | Calibration 23:20:30, setup check 1.41 px (≤ 2). 20 held-out manual clicks: **mean 1.99, median 1.91, p95 3.11, max 4.03 projector px**, rms 2.16; required and stretch PASS (`validation-20261009-232455.json` + .png; archived with calibration and history in `data/archive/a7-pass-20261009-233128/`). Earlier: 19:59 FAIL (5.87 / 10.03, setup moved after calibrating, test log); 20:53 run mean 3.06, max 4.86 (required PASS, stretch FAIL). Thresholds unchanged. |
| A8 | Live mapping (ruler) | Pending | — |
| A9 | Unit tests | **PASS** | 415 passed, 0 failed, 22 skipped on the original laptop (2026-10-19, D43); 408 passed + 22 skipped (D42); 415 passed (2026-10-12 D40; 410 D39; 380 D38 fix; 379 D38; 338 D37; 318 D36; 300 D35; 282 D34; 271 Phase 1D; 240 Phase 1C; 208 Phase 1B; 122 on 2026-10-09, 83 on 2026-10-08) |

**Phase 1B detector scoreboard (D29; criteria fixed before the runs)**

| # | Criterion | Status | Result (runs 23:49 and 23:52, 2026-10-09) |
|---|---|---|---|
| B1 | All 24 targets detected; ≥ 95 % of single frames | **PASS** | 24/24 averaged and 240/240 single frames, both runs |
| B2 | No false detection (blank, two crosses) | **PASS** | 4/4 blank screens rejected ("no projected target", peak 1.6 grey levels); 2/2 two-cross screens rejected ("2 crosses in the search area"), both runs |
| B3 | Stability: sd ≤ 0.3, max from mean ≤ 1.0 camera px | **PASS** | max sd 0.163 / 0.164 px (median 0.04), max from mean 0.336 / 0.373 px |
| B4 | Click-free consistency within A7 thresholds | **PASS** | mean 0.82 / 0.81, max 2.46 / 2.22 projector px (edge mean 0.92 / 0.91, interior 0.58 / 0.58); within stretch as well |
| B5 | Agreement with manual centres (mean ≤ 2, max ≤ 4 camera px) | **PASS** (2026-10-10 00:07) | Not evaluable at 23:49/23:52 (setup moved). After the user's manual `calibrate` (00:02) and `validate` (00:05): setup 1.05 px; detected − manual: all 24 mean **1.65**, max **2.99**; corners mean 2.10, max 2.99; grid mean 1.56, max 2.67; mean vectors (−0.04, +0.59) grid, (+0.66, +1.02) corners. Same run: B1–B4 PASS, click-free mean 0.56 / max 1.22 projector px (`detection-20261010-000700.json`) |

**Phase 1C scoreboard (D30)**

| Item | Status | Result (2026-10-10) |
|---|---|---|
| Automatic calibration on hardware | **PASS** | 00:31, 00:35, 00:36: 4/4 corners, 10/10 single frames each, sd ≤ 0.07 px; check target maps back within 1.06–1.15 projector px (limit 12) |
| Automatic validation on hardware | **PASS** (twice) | 00:32: mean **0.61**, median 0.47, p95 1.24, max **1.31**, rms 0.72; 00:37: mean **0.61**, median 0.58, p95 1.22, max **1.27**, rms 0.72 (edge 0.49, interior 0.87–0.90); setup check 0.07 / 0.05 px; required and stretch PASS |
| Automatic repeatability (A6 metric) | **PASS** | 3 automatic calibrations: mean corner variation 0.66, max 1.43 camera px (scene creep included); back-to-back 0.04 px |
| Setup check refuses a stale calibration | **PASS** | Real move (00:07→00:29, ~24 camera px): refused (variation 12.39 px). Simulated 4,0 and 5,5 projector px: refused (2.72, 4.88 px). Simulated 2,0: not refused (1.42 px), validation measured mean 2.35 / max 3.36, marked SIMULATED |
| Auto vs manual corner centres, same setup | **PASS** (00:44) | The user's `validate --manual` setup check clicked the 4 corners against the automatic 00:36 calibration: clicked − detected 2.07, 0.43, 0.71, 1.42 camera px, **mean 1.16, max 2.07**, mean vector (+0.21, −0.66); variation 0.58 px (unchanged). Within the B5 agreement bounds (mean ≤ 2, max ≤ 4). (The 00:29 comparison against the 00:02 clicks was not valid: the setup had moved.) |
| Manual validation of the automatic calibration | **PASS** (00:44) | 20 manual clicks: **mean 1.32**, median 1.01, p95 2.61, **max 2.92**, rms 1.54 projector px; edge 1.45, interior 1.00; required + stretch PASS; mean error vector (−0.13, −0.47) projector px (`validation-20261010-004455.json`, `"mode": "manual"`). Grid clicks vs the 00:37 detections: mean 1.43, max 3.29 camera px, mean vector (−0.14, −0.74) |
| Manual workflow | **Unchanged** | Default mode; tested with a fake session (calibrate, validate, report keys, repeatability) |

**Phase 1D scoreboard (D33)**

| Item | Status | Result (2026-10-10, real hardware unless stated) |
|---|---|---|
| Dependencies swapped and verified | **Done** | One OpenCV wheel (contrib 4.14.0.94): Win32 UI, DirectShow, MSMF, aruco, pollKey present; `pip check` clean; camera 29.98 fps, slowest 1-s window 29, 0 failed reads, exposure −5 confirmed |
| Live hand detection + fingertip → H → projector cursor | **Works on hardware** | Real hand, canvas grey 128 (D34): cursor follows the fingertip; it reached all four edges (x 61–1231, y 47–693 projector px) |
| Processing rate | **Measured** | 29.9 fps = camera rate (899 and 898 frames in 30 s) |
| Latency | **Measured (processing part)** | Inference median 11.2 / 11.6 ms (p95 11.8 / 13.0); capture → projector image median 12.9 / 13.3 ms (p95 13.7 / 14.8). End-to-end fingertip → cursor on the wall ≈ A3 display→camera loop (275 ms) + processing ≈ **290 ms** (estimate: the loop contains the same camera and display paths) |
| False hand detections (no hand, grey canvas) | **Measured** | 0 of 1797 frames |
| Tracking loss / recovery | **Measured** | Hand hidden 10.47–15.45 s: holding 4 frames (≤ 150 ms), then lost; tracking again from 15.48 s on the hand's return (`cursor-20261010-015114.json`). Free run: dropouts 0.87 and 0.56 s, both recovered |
| Detection rate with a hand | **Measured** | `handcheck` (hand in view, 45 frames per level): grey 40 → 0 %; 80, 128, 200 → **100 %** (hand length 211–217 camera px). `cursor --seconds 40` free movement: **94.8 %** of 1197 frames, first acquisition 0.29 s. Accuracy run (reaching to targets): 70.2 %; per target 100 % except top-left 24 %, mid-left 79 %, bottom-left 74 %, bottom-right 70 % |
| Fingertip accuracy (9 targets) | **Measured, no gate defined: NOT passed** | `cursor-20261010-020249.json`, calibration 02:00:32, setup 0.05 px: errors 3.83, 2.23, 8.62 (top row), 3.80, 4.66 (centre), 2.10 (middle row), 10.92, 15.99, 22.92 (bottom row) projector px; **mean 8.34, median 4.66, max 22.92**, rms 10.72; edge mean 8.80. For comparison only, the A7 click limits (5/12) would not be met |
| Fingertip stability | **Measured** | sd (rms about the mean, 1 s hold) 3.36–4.38 px, median 4.01, with the 8 px capture rule; 1.67–2.37 px on the 4 targets captured under the 4 px rule |
| Fingertip accuracy, shadow on target (D35) | **Measured, provisional criteria NOT met** | Lit room. Grey 128 (run 1, `cursor-20261010-141710`): 8/9, mean 7.69, max 17.50 (frames: mostly the fingertip itself on the target; shadow faint). Grey 80 (run 2, `-142108`, shadow visible): 7/9, mean 21.09, max 36.16; at T8/T9 the target centre is in the fingertip's shadow and the cursor 25–30 px above it. Ceiling light (run 4, `-142824`, shadow aim confirmed): 9/9, mean 23.44, max 54.94 (bottom row 8.5, 40.5, 54.9) |
| Hover sweep (D35) | **Inconclusive** | `cursor-20261010-142543`: bottom 2/8/15 cm → 20.8/12.0/2.6, top → 4.6/14.1/19.8 px; the frames show the fingertip itself on the target in some captures, so adherence to the shadow instruction could not be verified |
| 60-s free movement (D35) | **FAIL (38.0 %)** | `cursor-20261010-143343`, ceiling light: 29.9 fps, hand found 38.0 %, 7 losses; the user pointed from arm's length (shadow > 200 camera px from the hand) and the hand was in view but not detected in most lost frames |
| Shadow-centre accuracy, camera at 18 cm (D36) | **INVALID run** | `cursor-20261010-152458`, room light, grey 128, tiled: shadow centre established at 1/9 targets (T4: cursor 39.04 px from it, shadow 3.8 px from the target). Errors vs the targets (not the criterion reference): 11.6, 25.0, 20.6 / 36.5, 11.0, 18.0 / 42.1, 5.3, 19.8; mean 21.1, max 42.1; rows top 19.1/25.0, middle 21.8/36.5, bottom 22.4/42.1; columns left 30.1/42.1, centre 13.8/25.0, right 19.5/20.6 (mean/max) |
| Edge acquisition, tiled vs full (D36) | **Measured** | `--withdraw`, fingertip aim. First detection after activation (includes the reach): tiled 1.84, 1.10, 2.27, 2.03, 1.70, 2.38, 1.94, 1.47, 1.46 s (median 1.84, max 2.38; `cursor-20261010-153158`); full 2.21, 2.70, 3.57, 2.03, 3.84, 1.68, 2.37, 1.82, 2.24 s (median 2.24, max 3.84; `-153406`). Every target acquired in both. Hand found over the run 71.3 % vs 58.1 % |
| False positives, tiled (D36) | **0** | 30 s, nobody in view, room light: 0 of 760 search frames (`cursor-20261010-152204`); offline 0 of 202 empty-wall frames |
| 60-s free movement, tiled (D36) | **Complete, loss and recovery shown** | `cursor-20261010-153559`: 29.1 fps, hand found 83.5 % of 60 s, 8 losses; frames: 3 deliberate exits (11.5–13.6, 19.8–21.9, 53.1–55.0 s) each recovered as soon as the hand was back; misses in view ~1.4 s (body crossing, 28 s) and at the camera's right edge; ~97 % found while in view (±1 s, frames every 1 s). Meets the D35 proposed definition, pending the user's confirmation |

**2026-10-11: D37, tracking audit (Stage 1 measurements; read-only)**

- Reports of the day: 13 `cursor` runs; from 17:41 all with `--acquisition full --smoothing --no-setup-check`. `cursor-20261011-191833` (131.9 s, 29.9 fps): hand in 25.4 % of frames, 12 losses; gaps of 0.6–7.6 s while tracking mid-canvas at ordinary speed (median 467 px/s in the last 4 frames, = the run's p90); the last 55.8 s had no hand (no frames saved: presence unknown). Inference median 10.9 ms, capture → projector image 12.7 ms.
- Acquisition offline (1347 raw frames of the 2026-10-10 runs, stateless detection): the full frame (960 px, what full mode runs while it has no hand) found the hand in 470, the eight 720-px tiles in 812; of the 854 frames with a hand found by either, full frame 55.0 %, tiles 95.1 % (by hand length 0–70 px: 38.9 / 98.9 %; > 140 px: 61.4 / 94.0 %). Frames the live tracker had marked `lost`: full frame 0/473, tiles 52/473. Frames with neither: mostly an empty wall (checked on a contact sheet).
- Crop size for a fresh detection (hand-centred, 854 frames): 320 px 19.2 %, 400 36.3 %, 480 49.1 %, 560 69.4 %, 640 80.3 %, 720 89.2 %, 900 87.8 %, 1080 87.4 % (tighter crops are worse). Region around a live-order search hit: 640 px 81.5 %, 720 px 89.5 %, 800 px 89.2 %.
- Finger identity: search hit vs region tip > 30 px in 54/764 frames; the search's index tip lay on the region's middle (14), ring (3), little (21) or thumb (7) tip and on the index in 9; wrist within ~8 px.
- Smoothing, replay of 28 recorded tracking segments (6 runs): still jitter (rms about a centred 9-frame mean) raw 0.96 px; beta 0.01: 0.48 px, lag 5.6 px (30–300 px/s) / 8.7 px (> 300 px/s); beta 0.05: 0.55 px, 2.1 / 2.8 px. Raw landmark noise of a still fingertip sd 1.17 px per axis.
- Hover parallax: the centre target of `cursor-20261011-185822` gave 35.1, 18.6 and 6.8 px with the same direction (down-right) under the same calibration (validation mean 1.33 px): depth-dependent, consistent with R12; ~6 px of it is landmark 8 lying inside the fingertip end.
- Checked and correct: crop/letterbox → camera px restoration, cursor drawn in projector-local px (canvas = projector window), monotonic timestamps, no repeated frames, filter reset on reacquisition, hold ≤ 150 ms drawn orange.
- **Recalibration (Stage 4).** 20:02 `validate --auto` (user) refused the 16:00 calibration: the Brio had been knocked; all 4 corners detected 10/10, shifts (+4.8, +83.2), (−6.4, +91.4), (−1.7, +89.1), (−9.4, +82.7), mean (−3.2, +86.6), variation 43.40 px (limit 2) (`setup-check-20261011-200219`). The user secured the camera in its final position. The `projector` window (PID 20404) was stopped with the user's approval. **20:09:22 automatic calibration** (`calibration-auto-20261011-200925`): 4/4 corners 10/10 frames, sd ≤ 0.042 px; check target 1.19 px (limit 12); projection 53.7 % of the frame, margins left 140, top 146, right 353, bottom 106 px; vs 16:00 variation 43.43 px (corners agree with the 20:02 check within 0.1 px: no movement in between). **20:10 `validate --auto` PASS** (`validation-auto-20261011-201044`): setup check variation 0.04 px (limit 2), mean shift (+0.05, −0.02); 20/20 held-out points, mean 0.63, median 0.54, p95 1.21, max 1.39, rms 0.73 projector px (edge 0.51, interior 0.93); required and stretch PASS. The 16:00 calibration stays in `history/20261011-160021-649.json` (unchanged).
- **20:21 accuracy run (user), full acquisition** (`cursor-20261011-202121`: `--accuracy --aim finger --acquisition full --smoothing`, D37 code, calibration 20:09:22, setup check 0.77 px): 9/9 measured; errors T1–T9 15.7, 9.5, 14.0 / 4.5, 10.6, 6.7 / 4.8, 26.4, 22.3 px (mean 12.72, max 26.35; provisional criteria not met). Capture frames: landmark 8 lies on the visible fingertip end at every target; the error is the fingertip's camera position vs the target with the operator's eye aim while hovering (T8/T9 fingertip ~20 camera px above the target; top row +y, bottom row −y, i.e. towards the operator's eye height), viewpoint/hover parallax (R12), not tracking. Acquisition statistics now filled in full mode: 118 search frames, 5 acquisitions, 4 track losses (previously reported 0). T1 (top-left) first detection 3.8 s, hand found 53 % (R11); others 98–100 %. Motion: lag median 2.3 px (replay predicted 2.1–2.8); still jitter 2.59 px rms overall but **0.64 px drawn / 1.16 px raw without the jump windows** (replay predicted 0.55); **23 transient jumps** (13.7 per 1000 tracked frames) during holds at T4, T5 (13 in 2.3 s), T6, T7, T8: 30–54 px, back in 1–3 frames; at T5 along the index finger towards the knuckles (~45 px); replay: the drawn cursor moves median 17.4 px on a jump frame with beta 0.05 vs 8.6 px with 0.01 (the lag fix lets jumps through more; R25 needs a landmark-level fix, not more smoothing).
- **20:29 accuracy run (user), tiled + trace** (`cursor-20261011-203023`, trace `data/diagnostics/cursor-20261011-202914/trace.jsonl`; `--accuracy --aim finger --smoothing --trace --save-every 0.5`; setup check 0.48 px): errors T1–T9 11.4, 10.5, 8.4 / 4.1, 2.4, 9.0 / 2.5, 28.8, 3.8 px (mean 9.00, max 28.82); hand 96.2 %; one acquisition (search-tile, confirmed in the same frame), then tracking without a loss from 2.49 s to the end; T1 first detection 2.30 s (full run 3.78 s). **Chain verified on all 1465 hand frames:** H(tip_cam) = mapped (≤ 0.012 px), mapped = cursor input, landmark 8 = tip_cam, cursor state replay 0 mismatches, drawn = One Euro replay (≤ 0.011 px), all 9 dwell means and sample counts recomputed exactly; crop restoration consistent only within the trace's rounding (tip_norm stored to 0.01 = ±3.6 px on a 720-px region: an instrumentation limit). **T8 (+24.5, −15.2):** dwell 45.08–46.06 s, 30 tracked frames, raw sd 2.2/2.7 px, drawn mean = raw mean within 0.2 px; the error was reached by a smooth whole-hand move (44.62–45.29 s, tip and wrist both 2–7 px per frame), no landmark anomaly in the T8 or T9 dwell; same pointing pose at T7/T8/T9 (tip–PIP 38–42 px, middle tip ~100 px away, label Right 0.90); in the saved frames landmark 8 is at the visible fingertip end and the H-mapped target sits on the projected target cross (validation at (640, 690): 0.53 px), so the camera really sees the fingertip ~27 camera px right and ~24 up from the target. The operator stood well right of T8 (eye right of and above it), close to T9: the direction matches eye-aim/hover parallax (R12); hover depth itself could not be measured (shadow gaps not separable by eye, R23). Same target in the 20:21 run: (+0.4, −26.3) under the same calibration. Diagnosis: no coordinate or state bug; posture/hover. **Jump counter:** 0 is correct by its definition (independent recount 0; also 0 at >15 and >10 px) with full coverage, but it misses transients during motion: at 2.55 s (2 frames after acquisition, ~710 px/s) one frame had label Left, index tip–PIP 11 px (median 36.8) and the mapped tip 43.8 px off the midpoint of its neighbours; the drawn cursor moved 33 px that frame. A midpoint test finds exactly that one event in the run (all others ≤ 7.8 px). Other landmark signs without effect on the tip: label Left in 54 frames (78 changes; tip steady, median midpoint deviation 1.06 px), noisy middle-tip landmark (tip–middle 11–91 px at T1).
- **Three finger-aim runs compared (read-only):** A `cursor-20261011-203023` (20:29), B `-204153` (20:40), C `-204426` (20:43); all tiled, `--aim finger --smoothing --trace --save-every 0.5`, calibration 20:09:22, setup checks 0.48 / 0.11 / 0.43 px. Mean / max error 9.00 / 28.82, 8.67 / 16.85, 7.35 / 10.75 px; stability sd median 3.97 / 3.13 / 2.67 px. Chain verified on all three traces (H ≤ 0.012 px, state replay 0 mismatches, drawn = One Euro replay ≤ 0.012 px, all 27 dwell means recomputed exactly). Mapping at the target positions (validation 20:10): 0.22–1.21 px. **Repeatable:** top-row y error positive in 9/9 holds (row means +9.1 / +8.0 / +5.3), middle row positive 9/9 (+3.6 / +3.4 / +4.1), bottom row mixed; T6 x −6.6 / −8.1 / −8.3; across-finger component negative in 18/18 top and middle holds. **Variable:** x at T2, T3, T4, T7, T9 changes sign between runs (run-to-run sd up to 8.4 px), T8 28.8 / 6.4 / 7.9. Within a 1-s capture window the fingertip drifted up to 10.7 px (sd 0.9–3.9 px per axis). Hand always from the right, finger pointing left (top row up-left). Visible fingertip end vs landmark 8 (one raw frame per hold, R−B edge): median 2.3 camera px beyond the landmark (−2.2 to 6.3), off the centre line median 2.4 px; correcting for it leaves the top-row +y and T6 −x patterns. Contact: in all 27 holds a grey shadow band remains above the fingertip (narrower in B and C than in A); no frame shows the shadow meeting the tip; not convertible to cm (vertical camera–projector offset not re-measured after the 20:00 knock). Diagnosis: not mapping (≤ 1.2 px measured) and not the coordinate chain; landmark placement ~2–3 px; the remaining 5–10 px is operator aim/viewpoint (hover with eye aim, reference-point convention) plus within-hold drift, with a repeatable row-dependent component. Next: a controlled contact experiment before any change.
- **Two contact-protocol runs compared (read-only):** P `cursor-20261011-205722` (20:56) and L `-210014` (20:59), tiled, `--aim finger --smoothing --trace --save-every 0.2`, calibration 20:09:22, setup checks 0.09 / 0.42 px; mean / max 4.48 / 8.68 and 5.66 / 9.39 px; chains verified (H ≤ 0.013 px, 0 state mismatches). **L T5 (+8.6, +3.9), sd 5.44:** the hand came in from the left, overshot to ~+15 px (24.1–24.4 s) and settled to (+0.8, +1.9) by the end of the capture window; tip and wrist drifted together (−11.6 / −14.1 px; tip–wrist sd 1.4 / 2.0 px): settling inside the 1-s window, accepted by the 8-px rule; last 0.2 s of the window (+1.5, +2.1). Hand length 68 vs 113 px in P (different hand shape), stable within the window. Over the last 0.2 s of every window the mean |error| is 4.38 (P) and 4.65 (L) px. **Repeatability P vs L:** run-to-run rms difference 6.06 px per target; signed x not repeatable (r = +0.06), y partly (r = +0.54); mean signed (−0.24, +1.78) vs (−0.20, +2.89). Over all five finger-aim runs (A, B, C, P, L) y is positive at T1–T5 in 5/5 runs and negative at T8 in 5/5; top-row y +2.5…+4.4 in P/L vs up to +14 in A–C. Mapping at those positions 0.22–1.21 px (validation): not a mapping bias. **Contact:** no separate shadow visible at any P/L fingertip (hover run A: a 10–15 px band at every tip); shadow-strip index middle/bottom rows A 0.24–0.47, P/L 0.04–0.18, but C 0.09–0.22 overlaps and the index fails on the top row; contact is consistent with the frames but not verifiable (mm-level hover indistinguishable; vertical camera–projector offset not re-measured). Detection dropouts while at the target: P T7 25 frames, L T4 10, P T1 7. Assessment: residual 4.5–5.7 px is the size of the run-to-run variation; a row-dependent y component (~2–4 px under contact) repeats in sign; no code or calibration change justified yet; next: interleaved repeated targets (T2/T5/T8 × 5, contact) to put confidence intervals on the per-target means.

**2026-10-12 (20:44): interactive accuracy run INVALID, investigated read-only (no code change)**

- Run `cursor-20261012-204701` (`--accuracy`, `--aim shadow`, tiled, D40 two-view search, calibration 20:12:23, setup check 0.40 px; validation of the same calibration at 20:53: 20/20, mean 0.73 / max 1.17 px). Errors 6.6–30.5 px on 8 targets (T3 timed out), shadow centre 0/9 ("no shadow strip near the target" at all 8): INVALID, correctly.
- Coordinates checked on the saved captures: the projected target ring and cross sit on the magenta H⁻¹(target) mark, and H⁻¹ of the reported cursor mean sits on the drawn fingertip, at every target. The errors are the visible fingertip-to-target offsets (fingertip beside or above the cross by ~10–30 px), not a mapping or arithmetic error.
- Shadow: see R24 (hidden behind the finger at this camera position; target centres lit, so not aimed by shadow either). Re-detecting landmarks on the annotated single captures worked for 2/8 only (T1, T5: no shadow near the target or near the fingertip).
- Hand detection: edge targets 73 % hand-found (T1 56 %, T3 31 %, T6 48 %, T9 67 %) vs centre 98 %; earlier runs 95–97 % at the edges. Confound: this run was in a DARK room (unlit surround luma 20; earlier runs 119–122, room light) and the first with D40. The failures are on the tracking side, which D40 does not touch: 53 region losses, 13 of 67 search hits unconfirmed by the region tracker (earlier runs 0–6), T1 46 dropouts of median 2 frames while held on the target; T3's longest no-hand stretch was 132 frames (every view tried ~29 times). Captures: at the right-edge targets the operator stands outside the beam and the hand enters from darkness; lit skin 51–71 luma against canvas ~140. Not proven: lighting as the cause (needs the same run with room light, which also clears or convicts D40).

**2026-10-12 (evening): D39, automatic calibration recovery (offline only, no hardware run)**

- Trigger: `setupcheck-20261012-191953` refused the 00:52:42 calibration: variation 37.26 px (limit 2.0), corner shifts TL (+76.6, +0.3), TR (+76.2, +1.2), BR (+72.3, +9.2), BL (+72.0, −7.2) camera px; all corners detected (worst single-frame sd 0.06 px). A real move; the checker is right. Offline from the report: the old calibration would err 65.6 mean / 73.1 max projector px on the 20-point grid; the four detected corners give a valid candidate with the whole canvas inside the image.
- Tests (synthetic camera, `tests/test_recovery.py`, 30): unchanged setup → no recovery (4 projections only); moves (40, −12), (−120, −40), (−200, −30) camera px and the real 19:19 geometry → recovered (corners within 0.15–0.2 px of truth, validation max < 0.4 px, confirmation < 0.2 px); refused with the reason and hints: missing corner, corner cut off by the image border, ambiguous corner, unstable markers (setup-check step), swapped and mirrored assignments (corners step, nothing further projected), missing check target, missing grid target, an inaccurate candidate (setup moved 10 px after the corners: validation mean 8.2 px > 5), movement after the validation (confirmation step); commit only when accepted, never over a changed `current.json`, previous kept in the history, history entries never rewritten; the plan uses the existing targets and limits; `recalibrate` unchanged / moved / `--dry-run` / failure; `cursor` recovers and runs on the new calibration, does not start after a failed recovery, `--no-recalibrate` keeps the old stop. Full suite: 410 passed.
- **First hardware use (20:13, read from `calibration-recovery-20261012-201326.json` only):** `cursor` refused the 20:02:19 calibration (variation 63.25 px, mean shift (−79.5, −98.3) camera px) and recovered: check target 0.83 px, held-out validation mean 0.62 / median 0.51 / max 1.28 projector px (A7 required PASS), confirmation 0.10 px, canvas fully visible (54 % of the frame); saved and used by `cursor-20261012-201357`. Not yet measured: recovery duration, a person in front of the projection. Reports of 20:03–20:16 otherwise not reviewed.
- Hardware validation (approved steps, in order; stop at the first failure): `python -m invisible_canvas setupcheck` (expect REFUSED, ~37 px); `python -m invisible_canvas recalibrate --dry-run` (expect accepted, nothing saved; check the report's validation and confirmation); `python -m invisible_canvas recalibrate` (saves; the 00:52:42 calibration stays in the history); `python -m invisible_canvas validate --auto` (setup check unchanged, A7 PASS); `python -m invisible_canvas setupcheck --repeat 3 --interval 20` (stable); `python -m invisible_canvas cursor --seconds 30` (no recovery expected now). Optional, deliberate: move the camera or projector slightly, then `cursor --seconds 30` (expect automatic recovery, then tracking).

**2026-10-12: D38, landmark-glitch analysis (offline) and Phase A diagnostics**

- Traces `cursor-20261011-202914`, `-212416`, `-213733`, `-224039` (15,616 frames). Labels: hindsight excursion of the tip against its knuckle (frames 2 before/after), trajectories, and every saved camera frame that fell on an event (33 + 8 inspected). Glitch events: K1 20:29 2.55; K2 21:24 133.71; K3 21:24 151.24–151.64; K4a/b 21:37 121.85 / 122.14–122.25; K5 21:37 163.98–164.25 (visual); K6/K7 22:40 24.47 / 146.60; N1 21:24 132.17–133.24 (visual); N2 21:24 74.12–77.13 sustained misfit (8/8 frames: landmark 8 ~59 camera px below the upward-pointing fingertip). Quoted 22:40 wrist figures 10.0 / 7.1 were projector px (camera 10.9 / 7.9).
- Signals on 13,998 clean frames: label flips 10.8 % of frames (unusable alone); tip-PIP vs rolling median adapts to sustained misfits and missed K2; relative motion of the tip against its knuckle max 0.168 palm; extension min 0.48. Relative motion > 0.25 palm OR extension < 0.43: all glitch events, 0 clean frames; ambiguous events flagged: 5 at the implemented 0.25 / 0.43 (fast entry, reacquisition, label flicker, hand leaving; 3/7 with the stricter 0.3 / 0.45 analysis variant). Flagged is not verified: none of these 5 is a confirmed glitch. Two small probable glitches are not flagged (21:37 119.07 s, relative motion 0.238; 21:24 31.13 s, 0.184). The old counter: 2/9 (misses glitches during motion: the return test needs the hand to stay within 8.3 px).
- Not in the data: genuine finger bends, flicks faster than ~46 camera px/frame, pointing towards the camera. False-positive rate on those is unmeasured.
- Phase A replay (live code path, trace landmarks): 20:29 2 suspicious frames / 1 episode; 21:24 77 / 35; 21:37 36 / 11; 22:40 4 / 3; every flag inside a labelled window (incl. an unverified reacquisition frame at 21:24 131.32). Cursor replay before/after: identical outputs, states, losses, transitions, jump counter.
- Phase A regression (review, 2026-10-12): `cursor --targets … --trace` aborted at the first capture (AttributeError at `_trace_line`, name collision). Reproduced without hardware (fake session); the new regression test failed on the old code with that error and passes after the fix; the scratch reproduction (targets with and without `--trace`) passes; full suite 380 passed. Offline verification only; no hardware run.

**2026-10-10 (15:00–15:40): D36, camera move, tiled acquisition, shadow-centre protocol**

- Geometry from the user (§13.3). Camera moved to 18 cm right / 4 cm in front of the projector lens (on the bottle, fixed); placing it on the projector was not possible (top not usable).
- Offline (saved frames): one sweep (full frame + 8 tiles) found the hand in 13/23 frames where the live tracker had lost a visible hand (full frame 0/23) and in 77/82 tracked frames (full 34/82); 0/202 empty-wall frames; ~11 ms per view. Region tracking needed crops ≥ 600 px (384–500 px crops never confirmed the hand; 5 frames).
- 15:18:58 automatic calibration (check target 1.18 px; projection 63.2 % of the frame, bottom margin 29 px). Stability check (`setupcheck-20261010-152106`): 0.04 → 0.30 px over 100 s, never refused at 1 or 2 px.
- Experiment A (`cursor-20261010-152458`): INVALID; see the scoreboard. Capture frames: shadow on the target at T2 (moved 9.9 px during the hold) and T4; fingertip on the target at T5, T6, T8, T9; at the bottom row the shadow is hidden behind the hand.
- Experiment B and 60-s test: see the scoreboard. Search frames run at ~33 ms (full + 2 tiles).
- The shadow-centre measurement was also tried on the D35 run-2/run-4 frames: mostly not established, as the shadow was not at the targets there (checked by eye).

**2026-10-10 (13:30–14:35): D35, accuracy investigation**

- Model bundle: `hand_detector.tflite` input 1×192×192×3, `hand_landmarks_detector.tflite` 1×224×224×3. The palm detector sees the whole letterboxed frame: 1920 camera px → 192, ~10 camera px per detector px.
- Night frames (`data/diagnostics/cursor-20261010-020046/`), cold detection (fresh tracker, one call): found in 26/74 frames the live tracker had (full frame), 26/74 with gamma 0.5, 33/74 cropped to the canvas, **55/74 with 2×2 tiles**. Top-left frames with the hand present but lost live: 0/12 full frame, **8/12 with 600–900 px crops**. The unlit surround reads ~21 (black level): at the left edge only the fingers are lit.
- Shadow geometry, night frames: shadow tip 25–50 camera px up-right of the fingertip at the bottom row, parallax 21–41 projector px (4 automatic finds, 3 checked by eye). Open hand: the index shadow is often hidden behind the other fingers. Shadow ~21, lit skin 63–120, lit canvas 135–175 (dark room).
- 14:00 the user's `camera` preview and `projector` were running; `cursor` crashed (no frame); both stopped with the user's approval. 14:05: room lit (canvas region 68 with the projector black; 18 at night); the projection had moved (variation 71.35 px) → automatic calibration 14:08:26 (check target 0.77 px).
- Invalid runs, not counted: `cursor-20261010-141300` (no hand shown for targets 1–7: empty wall in the frames); `-142331` (sweep captured back-to-back: bug, fixed). Two setup-check refusals while the operator stood in front of a corner (the operator must stay clear during the corner crosses).
- Runs 1–4: see the Phase 1D scoreboard. Hand found 74.9 % (run 1, 25 losses), 81.9 % (run 2, 32 losses), 93.4 % (run 4, ceiling light, 2 losses); first detection at the first target 1.8–2.6 s (18 s at night).
- 14:30–14:33: setup check 3.06 / 3.71 px (drift), automatic calibration refused once (top-left single-frame sd 0.49 > 0.3), then saved 14:32:19 (check target 0.86 px; all corners (−7, +3) since 14:08). Run 5 (60 s): 38.0 %.
- Not done: dark-room runs (daylight could not be blocked); camera/projector distances not measured.

**2026-10-10 (01:28–02:10): D34, 0 % hand detection diagnosed; hand session**

- Starting point: `cursor-20261010-013128.json`, 60 s, 1796 frames, canvas grey 40, hand in view: 0 % detection.
- Pipeline (inspected, unchanged): camera frame BGR uint8 1920×1080 → `INTER_AREA` 960×540 → letterbox 960×960 (pad_y 210) → BGR→RGB, C-contiguous → `mp.Image(SRGB)`; VIDEO mode, ms timestamps strictly increasing; min detection/presence/tracking 0.5; one hand; model SHA-256 checked at load. Tests now assert RGB order, the square shape and refusal of non-BGR-uint8 frames.
- Positive control (`handcheck --image`, official MediaPipe sample photo, scratch copy): found, score 0.96, hand length 243 px. Degraded copies: found down to 140 px hand length and a hand mean luma of 16; missed at 120 px / 10.
- No-hand control (`handcheck-20261010-013712.json`): grey 0/40/80/128/200/255 → canvas region 18/23/67/144/229/235, 0 detections.
- Real hand (`handcheck-20261010-014127.json`, 45 frames per level): grey 40 → region 23, **0 %**; 80 → 66, **100 %**; 128 → 142, **100 %**; 200 → 226, **100 %**. Frames in `data/diagnostics/handcheck-20261010-014108/`.
- Fix: default canvas grey 128, brightness pre-check in `cursor` (`scene_check` in the report).
- Free run (`cursor-20261010-014214.json`, 40 s, grey 128): hand 94.8 %, 2 losses, recovered.
- Accuracy run 1 (`cursor-20261010-015040.json`, 4 px capture): 4/9 measured (3.95, 4.15, 9.53, 4.11; sd 1.67–2.37), 5 skipped; the fingertip passed within 0.1–1 px of skipped targets but never stayed within 4 px for 1 s. Capture radius → 8 px (regression test: at 2.37 px rms, 4 px accepts ≤ 40 % of 1-s holds, 8 px ≥ 97 %).
- 01:59: the setup check refused `cursor` (variation 39.9 px; `setupcheck-20261010-015953.json`, reproduced 11 s apart); automatic calibration 02:00:32 (corner sd 0.03–0.13 px, check target 0.79 px; right margin now 45 camera px).
- Accuracy run 2 (`cursor-20261010-020249.json`, frames every 1 s in `data/diagnostics/cursor-20261010-020046/`): 9/9 measured, see the scoreboard; 29.9 fps, inference median 9.9 ms, capture → projector 11.8 ms; 7 losses.
- Saved frames: (a) top-left / left targets: the arm comes from the unlit surround, palm and wrist are dark, only the fingers are lit; the hand is acquired late (re-running single saved frames cold often finds no hand where the live VIDEO-mode run tracked one: acquisition depends on the palm detector, tracking does not). (b) bottom targets: the hand's shadow is 40–50 camera px from the fingers, so the finger hovered in front of the wall (R12); the tip landmark sits on the fingertip as the camera sees it. The mapping itself is ~1–2 px (A7, Phase 1C), so the 11–23 px bottom-row errors are fingertip/pose/parallax, not calibration.
- Not judged: no fingertip-accuracy gate is defined. **Phase 1D is not passed.**

**2026-10-10 (00:53–01:25): D31, D32, D33**

- **D31** (automatic default): `calibrate` with no flag ran the automatic path on hardware (01:02, 01:11, 01:20; check target 1.03–1.13 px).
- **D32** (`setupcheck`, `setupcheck-20261010-011045.json` and `-011440.json`):
  - Untouched series, 11 checks over 8.3 min: variation 0.06, 0.15, 0.37, 0.60, 0.80, 0.95, 1.12, 1.29, 1.39, 1.46, 1.52 px; mean shift reached (+1.30, +2.40), largest corner 4.46 camera px. Refused at 1.0 from 4.6 min (5/11), never at 2.0.
  - One check: top-right rejected by the stability gate (single-frame sd 0.31 > 0.3 px).
  - Sweep (drift during it 0.08 → 0.12 px): 1-px moves 0.49–0.84 px; 2-px 1.08–1.49; (2,2) 1.62; 3-px 1.70–1.83.
  - Rule (a) failed → 1.0 not adopted; 2.0 kept (does not catch moves of up to ~3 projector px).
- **D33**:
  - Model `hand_landmarker.task` float16 v1, 7,819,105 bytes, SHA-256 `fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1` (bundle: hand_detector.tflite, hand_landmarks_detector.tflite), from `https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task`.
  - First cursor run (01:20, 30 s, no hand, canvas grey 40): see the scoreboard.
  - MediaPipe logged once per run "Using NORM_RECT without IMAGE_DIMENSIONS is only supported for the square ROI". The inference image was then letterboxed to a square (round trip exact to 1e-6 in tests), but the warning persists with square input (01:23 run), so it is not caused by the frame shape. Its effect on landmark accuracy, if any, will show in `cursor --accuracy`.
  - Tests: 31 new across `test_cursor.py`, `test_hands.py` (incl. a real MediaPipe pass over empty frames with the pinned model), `test_setup_check.py`, `test_config.py` and `test_auto.py`. Full suite **271 passed**.

**2026-10-10 (00:10–00:40): Phase 1C: automatic calibration and validation (D30)**

Implementation:
- `calibration/auto.py` (pure): `TargetMeasurement` + quality gate, `associate_corners`, `verify_check_target`, `auto_setup_check`, `validation_result`; `targets.check_target()`.
- `tools/common.py`: `capture_frames` (moved from `detect`), `CameraMeasure`, `shifted`.
- `calibrate --auto [--dry-run]`, `validate --auto [--simulate-shift DX DY]`, explicit `--manual`.
- `detect` uses only manual validations as the manual reference; `repeatability` compares one method at a time.
- Detector: per-component pixel scans limited to the bounding box (36 ms instead of 51 ms per full frame). Outputs verified byte-identical on 50 fixed synthetic detections before and after.
- Calibration file format unchanged (`method: "auto"` was already allowed by the schema).

Tests (synthetic camera: the real target rendering through a known homography, noise from a precomputed pool; these check logic, not hardware):
- measurement gate: clean, unstable, blank, too few frames;
- correspondence: missing, ambiguous (2 crosses), duplicate, swapped, mirrored, cyclic relabelling caught by the check target;
- fit: H maps the true grid within 0.1 px; file format and integrity check unchanged;
- validation: metrics via `accuracy_stats`, the same edge mask, a missing target stops it;
- setup check: moves of 6 and (−3, 5) camera px refused, 0.4 px accepted, a 5,5 projector shift refused, a missing corner stops it;
- tools with a fake session:
  - `calibrate --auto` saves `method: "auto"`; `--dry-run` saves nothing; a failure exits 1 and saves nothing, and **manual clicks are never requested** (tripwire);
  - `validate --auto` passes and writes only `validation-auto-*` (all manual report keys + `mode`), refuses a moved and a simulated-shifted setup, stops on a detection failure;
  - option conflicts are rejected;
  - manual `calibrate`/`validate` unchanged (legacy report keys + `mode`), `repeatability` per method.
- 32 new tests (31 here, 1 in `test_detect_check.py`: automatic validations are never a manual reference), 1 test fixture made realistic (manual reports carry their `method`). Full suite: **240 passed**.

Real hardware (Brio 100 MJPG 1920×1080, manual exposure −5; reports in `data/reports/`):
1. 00:29 `calibrate --auto --dry-run`: 4/4 corners, 10/10 single frames, sd ≤ 0.08 px, check target 1.15 px. Versus the 00:02 manual clicks: every corner +23.6…+26.5 camera px in x (variation 12.35 px). The 00:07 detection had matched those clicks within ≤ 3 px, so **the setup moved between 00:07 and 00:29**; not a code offset (same detector; check target consistent).
2. 00:30 `validate --auto` on the stale 00:02 manual calibration: **refused** (mean shift +24.77, +0.07; variation 12.39 px > 2), nothing recorded (`setup-check-20261010-003041.json`).
3. 00:31 `calibrate --auto` (saved; `calibration-auto-20261010-003111.json`): corners within 0.30 px of the dry run; check target 1.15 px; projection fills 66.9 % of the frame, margins 162/64/132/95 px.
4. 00:32 `validate --auto`: setup 0.07 px; **mean 0.61, median 0.47, p95 1.24, max 1.31, rms 0.72** projector px; edge 0.49, interior 0.87; 20/20, worst single-frame sd 0.18 px; required + stretch PASS (`validation-auto-20261010-003231.json`).
5. Simulated perturbation (`--simulate-shift`):
   - 2,0 → setup variation 1.42 px (passes), validation mean 2.35 / max 3.36, marked SIMULATED;
   - 4,0 → refused (2.72 px);
   - 5,5 → refused (4.88 px).
   All four corners also showed ~+0.7 px in y: scene creep.
6. 00:35 and 00:36 `calibrate --auto`: back-to-back variation 0.04 px. `repeatability` (3 automatic): mean 0.66, max 1.43 camera px, PASS.
7. 00:37 `validate --auto` on the 00:36 calibration: setup 0.05 px; **mean 0.61, median 0.58, p95 1.22, max 1.27, rms 0.72**; required + stretch PASS (`validation-auto-20261010-003731.json`). Error map: largest residuals (1.0–1.3 px) mid-span, smallest near the corners (R8).
8. Systematic offset between detector and clicks (from B5, 00:07): mean vectors (−0.04, +0.59) grid and (+0.66, +1.02) corners, camera px; nothing beyond click precision.

Comparison with manual: manual A7 (00:05) mean 1.87 / max 4.32; automatic (00:32 / 00:37) mean 0.61 / max 1.31 and 1.27. Different calibrations (the setup moved in between), so this compares the methods, not one calibration. The automatic numbers have no click error; a shared detector bias would cancel in auto-on-auto validation, hence the manual cross-check:

9. **00:44 manual cross-check** (user, `validate --manual` on the automatic 00:36 calibration, setup unchanged: variation 0.58 px):
   - clicked − detected corners mean **1.16**, max 2.07 camera px;
   - manual validation **mean 1.32 / max 2.92** projector px, PASS. That is better than the manual-on-manual A7 runs (1.99 / 4.03 and 1.87 / 4.32), as expected when only the validation carries click error.
   - In both sessions with an unchanged setup (00:07 and 00:44), the clicks sit ~0.6–1.0 camera px **above** the detected centres (mean y: detected − clicked +0.59 / +1.02 at 00:07; clicked − detected −0.66 / −0.74 at 00:44); x agrees within ~0.2–0.7 px.
   - Which side is biased is unknown (human click habit or detector). The size, ≈ 0.6 projector px, is far below every threshold and now bounds a shared detector bias.

Limitations:
- An automatic calibration uses the same detector as the automatic validation, so a uniform detector bias would not show there. Bounded by the manual cross-checks: detector and clicks differ systematically by ~0.7 camera px in y (≈ 0.6 projector px), consistent in two sessions; ground truth unknown.
- The setup check's 2-px limit admits moves of ~2 projector px (open question 8).
- The camera must be upright and not mirrored (a mirrored image is rejected; use `--manual`).
- Rendering and detection assume one active cross per screen.
- Each automatic run takes ~1.5 min for calibration plus validation (0.8 s settling per projected image).

Current calibration: automatic, 00:36:05. The manual 00:02 calibration stays in `history/` and the pre-1C archive; to go back, run `calibrate --manual`.

**2026-10-10 (00:00): Phase 1B first increment: automatic cross detection**

Objective: find the centre of the projected calibration cross automatically on real frames, reliably enough to automate calibration and validation later. Diagnostic only; the manual path stays the reference and the fallback (D16, D29).

Detector (`calibration/detect.py`):
- **Signal:** target frame − black-projection frame, then a white top-hat (25 px). Removes ambient light and brightness gradients and keeps the 3-px arms.
- **Threshold:** 40 % of the peak, never below 6 noise sigmas (MAD); peak ≥ 10 grey levels and peak/noise ≥ 8, else "no projected target".
- **Candidates:** connected components, solid at their centroid (a ring, clipped arc or glyph is hollow there or not cross-shaped).
- **Centre:** pixels split into two arms by angle, one weighted total-least-squares line per arm (one robust pass drops pixels > 2.5 rms off the line), centre = the lines' intersection. This is perspective-exact for ideal lines; the ring is never used.
- **Rejected, with a reason:** cut off by the image border or search window; half-arm < 12 px; line residual > 3.5 px; elongation < 5; half-arm balance < 0.6; arms < 60° apart; the lines not crossing on the bright pattern; 0 or ≥ 2 crosses.
- Quality fields: contrast, residual, balance, arm angle, fit sigma, candidate count. Invalid input raises `DetectionError`. Parameters come from the target geometry and were not tuned on hardware.

Synthetic tests (`tests/test_detect.py`, 83; the real target rendering warped by known homographies with blur, gain, ambient light and noise; these check the algorithm, not hardware performance):
- clean crosses ≤ 0.05 px;
- near the border (complete at 40 px detected; cut off rejected with the reason);
- clipped rings at all 6 top/bottom positions ≤ 0.05 px (a ring-inclusive centroid is > 2 px off there);
- perspective: realistic keystones up to 1.6× all 24 detected ≤ 0.11 px, 1.85× rejected ("half-arms unequal"), never wrong;
- gain 0.25–3 (3 saturates the arms) ≤ 0.1 px; ambient light + gradient + noise ≤ 0.25 px; too faint rejected;
- blank / two crosses / ring / bar / blob / text rejected;
- label text across an arm ≤ 0.05 px;
- pixel-centre convention exact, search window coordinates identical to full frame, camera centre → H → projector ≤ 0.05 px;
- 10 noisy frames sd < 0.05 px; sub-pixel shifts followed within 0.03 px;
- invalid inputs raise.

Development findings: label glyphs ("t") first passed the cross test (fixed by the 12-px half-arm floor); `validate`'s right-column labels run across the upper arm (fixed by the robust refit; detection screens omit labels).

Real hardware (`python -m invisible_canvas detect`; Brio 100 MJPG 1920×1080, manual exposure −5; 24 targets, 6 background + 10 single frames each):
1. **23:46, search windows from the 23:20 calibration:** 0/24 detected. Every cross was cut by its window and **rejected** (no wrong centre returned). Cause: every target sat (+65, −11) camera px (sd ~4–6) from where the calibration predicted, i.e. the setup had moved since the A7 run. Consequences: the diagnostic now searches the whole frame by default (`--calibration-windows` is opt-in), and the saved calibration does not match the current hardware.
2. **23:49 and 23:52, whole frame** (`detection-20261009-234957.json`, `detection-20261009-235217.json`, + .png): results in the scoreboard above.
   - Margins on real frames: line residual 2.13–2.87 px (limit 3.5, the smallest margin), balance ≥ 0.89, arm angle 83.6–89.7°, contrast ≥ 275, fit sigma ≤ 0.15 px.
   - Run-to-run (2.5 min apart): centres moved mean 0.60, max 1.02 camera px, common shift (+0.28, +0.46). Corners mean 0.72, grid edge 0.62, grid interior 0.50. Larger than the single-frame sd, so this is the scene, not detector noise.
   - Contact sheet of the 23:49 run inspected at 4×: every marker on the arm intersection, including the top-row targets with clipped rings.
   - Click-free per-point errors (run 2): 0.17–2.22 projector px; the largest at the bottom row (grid 19: 2.22).
3. Camera: 27.7–28.2 fps during the runs, 0 failed reads, exposure manual −5 confirmed at the end. Two camera opens directly after a previous run failed (exit 2; one shown as "delivered no frames"); a retry worked (R17).

Limitations: one active cross per searched area; the search must contain the whole cross; perspective up to ~1.6× keystone; residual limit assumes arms ≤ 12 camera px wide (closer cameras would need a larger `max_arm_width_px`); validated on this Brio/WZATCO setup in a dark room only; B5 (agreement with manual clicks) is still open.

Next decision: after a fresh `calibrate` + `validate` + `detect` evaluates B5, decide on `--auto` modes (open question 7).

**2026-10-09 (night): A7 validation FAIL investigation**

Data (archived unchanged in `data/archive/20261009-before-mapping-investigation/`): calibration 19:53 (corners at projector (77,43), (1202,43), (1202,676), (77,676)), repeatability 19:53 (0.75/1.50 px), validation 19:59 (5×4 grid at 4 % inset). All clicks, calibration and validation, were made in the 0.80× operator view (values on the 96/77 camera-px lattice): no loupe, no arrow nudges.

1. **Per-point errors** (mapped − target, projector px): dx +1.32…+6.55 (mean **+3.58**, sd 1.55), dy +1.61…+8.08 (mean **+4.55**, sd 1.77); **dx > 0 and dy > 0 at all 20 points**. Largest: (51,690) +5.93,+8.08 = 10.03; (51,29) +6.13,+6.47; (934,690) +6.55,+6.30. Smallest: (934,29) +1.32,+1.61.
2. **By region:** down-right everywhere, larger on the left. Column means (dx, dy) from left to right: (+5.5,+6.9), (+3.5,+4.9), (+2.3,+4.8), (+3.3,+3.3), (+3.3,+2.9). Row means are similar (dx +3.4…+4.0, dy +4.2…+5.2).
3. **Coordinate systems checked:** camera→projector H estimated from (camera clicks, projector targets) and applied the same way in validation; pixel centres at integers everywhere; operator click → camera px `(v + 0.5)/s − 0.5` matches `cv2.resize`; targets on integer pixels, drawn symmetrically. Regression test: a target rendered, warped into a synthetic camera and centroided maps back to its pixel within 0.03 px (affine) and 0.13 px (perspective, the centroid's own second-order bias). No convention error.
4. **Offset vs perspective/scale** (fits in projector space): no correction rms 6.23 px; **one translation (−3.58, −4.55): rms 2.29, mean 2.02, max 4.24**; affine (scale 1.0016/0.9992, rotation 0.19°): rms 1.70; homography refitted to the 20 validation clicks (floor: click noise + lens + planarity): rms 1.49. **It is an offset, not a perspective or scale error.**
5. **Detected target centres** (diagnostic, read-only; projector shows each target and black, centroid of the cross only in the difference image), 20:09–20:12:
   - Corners stable over 3 min (≤ 1.3 px, no trend).
   - Calibration clicks (19:53) − detected corners: TL (−6.6,−6.3), TR (−4.0,−3.5), BR (−5.0,−3.6), BL (−6.4,−6.2); **mean (−5.5, −4.9) camera px**.
   - Validation clicks (19:59) − detected grid: mean (−0.5, +0.7), sd ~1, rms 1.86 px: **the validation clicks were accurate**.
   - **Click-free validation** (H from the 4 detected corners → 20 detected grid centres): **mean 1.03, max 2.10 projector px**.
   - Saved H applied to the detected grid: mean 5.74, max 8.20 (the stored H is off).
   - Detected-corner H applied to the user's 19:59 clicks: mean 1.71, max 3.92 (diagnostic only, not an A7 result).
6. **Conclusion:** the three calibrations (19:46–19:53) agree with each other (0.75 px), and the validation clicks (19:59) agree with the scene at 20:09–20:12. The calibration clicks are ~5 camera px up-left of the current target centres. A clicking habit shared by both phases would cancel exactly (regression test), so the scene moved ~5 camera px down-right relative to the camera **between 19:53 and 19:59** (a bump or a projector auto adjustment; ~0.2° of camera rotation is enough). The cause is not identified. The 4-point method itself reaches ~1 px on this setup.
7. **First detector attempt (lesson for 1B):** a ring-inclusive centroid was biased 6–9 px on the top and bottom grid rows, whose rings are clipped by the canvas edge at the 4 % inset. The cross-only centroid fixed it (R15).
8. **Change:** setup check before validation (D28); 9 regression tests (`tests/test_mapping_chain.py`). No change to H, thresholds, targets or error computation. Unit tests **122 passed**.

**2026-10-09 (evening): display→camera latency investigation**

Setup as in the entry below; room dark during these measurements. "Level" = mean pixel value over latency.py's ROI (the central half of the camera frame, since there is no calibration).

1. **The user's run** (`latency-20261009-183256.json`): black 137.9, white 199.7, threshold 168.8; 4 of 20 trials detected (255, 289, 285, 274 ms), **16 missed**, median 280 ms. The report kept no per-trial order or levels. A `python -m invisible_canvas projector` window (started 18:26) was still open on the projector during the run.
2. **What the number measures.**
   - **Start:** `t0` = `perf_counter()` right after `projector.show(white)` (`cv2.imshow`) and one `cv2.pollKey()`. That dispatches the window's repaint, so the white frame has been handed to Windows.
   - **Stop:** the capture-thread timestamp (when `cap.read()` returned) of the first camera frame whose ROI level exceeds the midpoint of the black/white levels measured at the start. Only frames newer than the latest frame before the flip are considered.
   - **Included:** Windows composition (DWM, next 60 Hz vblank) and scanout, HDMI, projector processing and light output (its refresh/response), the camera's sampling phase (0–1 frame), the 31 ms exposure, readout, the Brio's processing and MJPG encoding, USB, DirectShow MJPEG decode, `read()`.
   - **Excluded:** the main thread's polling and level computation (the timestamp is taken at capture), and all of our later processing.
   - **Resolution** is one frame (33.4 ms). The threshold sits at 50 %, so a partly exposed frame counts when it is more than half white. A random 0.25–0.6 s wait before each flip randomises the phase.
3. **Brightness trace** (every frame, slow and fast flips, 20 white + 20 black transitions): every transition is one clean step. The frame at ~236–270 ms after `show()` is partial; the frame at ~270–302 ms is complete; white→black is symmetric; no slow ramps (no dynamic-contrast effect); nothing missed. Black 16, white 143. This was with the user's `projector` window still open, so that window was not the cause.
4. **The real tool, unmodified, same conditions** (`latency-20261009-184118.json`): 20 of 20, median 270 ms (p10 256, p90 287), black 16.2, white 142.9.
5. **Why the 16 misses.** Not expected sampling behaviour: valid setups missed 0 of 120 trials. In missed trials the white never crossed the threshold (168.8) within 1.5 s, so the reference levels measured at the start no longer described the scene. The user's levels (138/200) are far above today's at the same exposure (16/114–143). Auto exposure does not reproduce them in this scene (black 2, white 118–132). Most consistent explanation: more light in the scene when the reference was measured (e.g. room lights on), then a change during the run. A gain change is the other candidate. The old report cannot tell which. Hence D27.
6. **Camera-only path** (no projector involved; white projection held constant, exposure stepped −5 ↔ −7 at random phase, keeper disabled): first changed frame after `Set()` at **median 194 ms, min 125, max 215** (30 of 30). Upper bound for the camera's share, because the sensor may apply a new exposure 0–2 frames later. So the camera path is ≤ ~125–195 ms, and the display path (Windows + HDMI + projector) is the remainder, **≥ ~80 ms, plausibly ~80–150 ms**. No single dominant source is proven. The camera path is the largest bounded block, but no configuration change shortened it.
7. **Resolution A/B** (paired runs, same session conditions): 1920×1080 pooled 80 trials, median **275 ms** (p10 253, p90 295); 1280×720 pooled 40 trials, median 259 ms (p10 248, p90 276). Per-run medians 1080p: 270, 267, 275, 287; 720p: 267, 257. The difference is smaller than the run-to-run spread, so it is **not a demonstrated improvement**; D25 is unchanged.
8. **Gain is not locked:** white at exposure −5 was 143 in early sessions and 114 after an auto-exposure session, stable within each session (R7).
9. **Updated tool** (D27), real run: valid, 20 of 20, median 287 ms (p10 268, p90 302); levels after the trials 16.0/114.6 vs 16.0/114.4 at the start; exposure still manual −5; re-applied 0× (`latency-20261009-185057.json`).
10. **Coverage observation:** in the white snapshot the projection's bottom edge lies outside the camera frame (A4).
11. Unit tests: **108 passed** (104 + 4 latency-validity tests).

**2026-10-09: Brio 100 camera investigation and exposure control (hardware session)**

Setup: Brio 100 on USB, WZATCO on HDMI (`AML TV`, 1280×720), `projector` window showing the pattern (it lights the scene the camera sees). DirectShow unless stated. Scratch measurement scripts (not in the repo) opened the real camera and counted real frames; "luma" is the mean pixel value.

1. **Starting symptoms.** `camera` showed 1920×1080 "requested MJPG, driver reports YUY2 30 fps", measured **5.0 fps**. A `camera --seconds 60` run gave **1.00 fps** (60 frames in 59 s, every 1-s window 1 frame, longest gap 1002 ms, 0 failed reads).
2. **The 1 fps was a second process.** A forgotten interactive `camera` window was still holding the Brio. While it ran, every test gave exactly 1.00 fps with ~1000 ms gaps, and MSMF failed with `0xC00D3704` (failed to start streaming). After closing it, the symptom disappeared (R20).
3. **FOURCC set order** (MJPG 1920×1080 @ 30 requested, camera free):

   | Order | Negotiated | Measured |
   |---|---|---|
   | FOURCC, width, height, fps (old `configure()`) | YUY2 | 4.97 fps |
   | FOURCC, width, height, FOURCC, fps | YUY2 | 4.97 fps |
   | width, height, fps, **FOURCC last** | MJPG | 14.93 fps |
   | params passed to the `VideoCapture` constructor | MJPG | 14.93 fps (opens in 1.4 s) |

   Root cause 1: every size/fps change renegotiates without the FOURCC, so MJPG silently fell back to **YUY2, which USB 2.0 carries at only ~5 fps at 1080p/720p**. Fixed by D26.
4. **Mode sweep, DirectShow, FOURCC last, exposure as found (auto, AE priority 1).** 0 failed reads and 0 duplicate frames everywhere:

   | Request | Delivered | Measured |
   |---|---|---|
   | MJPG 1920×1080 @ 30 | 1920×1080 MJPG | 14.92 fps |
   | MJPG 1280×720 @ 30 | 1280×720 MJPG | 14.97 fps |
   | MJPG 1280×720 @ 60 | 1280×720 MJPG (reports 60) | 14.97 fps |
   | MJPG 960×540 @ 30 | 960×544 MJPG | 14.97 fps |
   | MJPG 640×480 @ 30 | 640×480 MJPG | 14.97 fps |
   | YUY2 1920×1080 @ 30 | 1920×1080 YUY2 | 4.97 fps |
   | YUY2 1280×720 @ 30 | 1280×720 YUY2 | 4.97 fps |
   | YUY2 640×480 @ 30 | 640×480 YUY2 | 14.97 fps |

   Every MJPG size stops at the same ~15 fps, so the cap is not bandwidth.
5. **MSMF, same modes:** reported 29.7–30.0 "fps", but about **half of the reads were duplicate frames** (74 of ~149): ~15 real fps. It ignored the FOURCC request (YUY2 1080p "at 30 fps" is impossible over USB 2.0) and took 38–44 s to open (R22). Not used.
6. **Exposure test** (DirectShow, MJPG; controls set through `IAMCameraControl`, then restored to the original exposure (−4, auto) and AE priority 1, verified):

   | Setting | 1280×720 | 1920×1080 | Luma (1080p) |
   |---|---|---|---|
   | As found: auto exposure, AE priority 1 | 14.97 fps | 14.97 fps | 91 |
   | Auto exposure, AE priority 0 | 29.95 fps | 29.94 fps | 55 |
   | **Manual −5 (31.2 ms)** | **29.85 fps** | **29.85 fps** | 65 |
   | Manual −6 (15.6 ms) | 29.95 fps | 29.94 fps | 41 |
   | Manual −7 (7.8 ms) | 29.94 fps | 29.95 fps | 28 |

   Root cause 2: **auto exposure with AE priority 1 ("Low Light Compensation") stretches the exposure in this dim scene and halves the frame rate to ~14.97 fps.** The Brio's exposure range is −11..−2 (auto and manual).
7. **First 60-s confirmation** (AE priority 0 set from a separate process, project `camera` tool, MJPG 1080p): **1796 frames, 29.93 fps, slowest 1-s window 29, longest gap 50 ms, 0 failed reads** (`camera-20261009-020717.json`). The setting carried over between processes.
8. **Exposure resets at stream start** (R21). The first config-driven version set manual −5 once at open: read-back said confirmed, but the 60-s run measured **15.21 fps**, and the camera reported auto again afterwards. Timing test (set at first frame, polled every 50 ms): exposure jumped back to (−4, auto) at 0.69 s and 2.88 s in one run, and at 1.49 s and 3.68 s in another, then held. Kept alive past that window, manual −5 stays and the stream runs at 30.0 fps. Hence `ExposureKeeper` (D24).
9. **Final, config-driven** (`exposure_mode = "manual"`, `exposure_value = -5`, started from auto):
   - `camera --headless --seconds 60`: exposure at open `manual -5 (31.2 ms), confirmed by read-back`. **1791 frames over 60.0 s, mean 29.83 fps, slowest 1-s window 27, longest gap 80 ms, 0 failed reads.** Exposure at end: manual −5 confirmed; re-applied 1× (`camera-20261009-022733.json`).
   - Per-second frames: 27 and 28 in the first two seconds (auto exposure until the reset was undone), then 29–31 for the remaining 58 s.
   - `exposure_mode = "auto"` (10 s): auto confirmed at open and end, 15.00 fps, re-applied 0×.
   - Fail-safe, `exposure_value = -20`: `CameraManager` raises `CameraError: exposure NOT APPLIED (requested manual -20): exposure_value -20 is outside the camera's range -11..-2; camera reports auto ...`. The `camera` tool warns, shows NOT APPLIED and measures 14.99 fps.
   - `devices` rerun (`devices-20261009-023110.json`): Brio MJPG requests now deliver MJPG (15 fps under the stored auto exposure, which the output states); YUY2 1080p/720p 5 fps. Integrated Camera: at most 1280×720, YUY2 only, 16.6 fps.
10. Unit tests: **104 passed** (83 + 1 FOURCC-order test + 15 exposure tests + 5 config tests).

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
**2026-10-19 (original laptop, Kreo):** setup rebuilt by the user; not measured with a tape yet. From the camera: projection 31.6 % of the 1920×1080 frame, corners at camera TL (391, 312), TR (1282, 355), BR (1317, 873), BL (307, 855) (visibly keystoned), margins left 226, top 277, right 534, bottom 165 px; about 0.79 camera px per projector px at the top edge. The tables below are the 2026-10-10 Brio setup.

Measured by the user with a tape measure on 2026-10-10 (D36); nothing here is estimated.

| Item | Before (until 15:00) | After the move (from 15:19) |
|---|---|---|
| Brio lens → projector lens | ~30 cm sideways, camera 10–15 cm higher | 18 cm to the right, 4 cm in front (towards the wall); vertical offset not re-measured |
| Projector lens → wall | 160 cm | 160 cm |
| Brio lens → wall | 157 cm | not re-measured (~156 cm from the 4 cm forward move) |
| Projected image | 129 cm wide × 75 cm high (≈ 9.9 projector px per cm) | same |
| Mounting | projector on the table; Brio on top of a bottle on the table | same bottle, fixed; the projector top cannot hold the camera (user) |

Parallax per cm of hover (D35 model, projector px): ≈ hover × baseline parallel to the wall / distance × 9.9 px/cm. Before: baseline 31.6–33.5 cm → 2.0–2.1 px per cm. After: 18 cm horizontal plus the unmeasured vertical offset → 1.1 px/cm (no vertical) to 1.5 px/cm (15 cm vertical). A 5-px error at a 25–30 cm hover would need a baseline of ≤ ~3 cm.
