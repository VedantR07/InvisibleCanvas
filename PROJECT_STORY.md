# Invisible Canvas: the whole story, from the first day to today

*Written 2026-10-26. It covers everything from 2026-10-08 (the first day) to 2026-10-26 (the second EXPLORE test).*

This file explains the project in plain language, from start to end: what it is, what hardware it uses, what was
built, in which order, why each decision was made, every test that was run (passed or failed), the problems found
along the way and how they were solved, and what is still open. It is a story for reading. The engineering record
with every number and every decision stays in `brain.md`, and the exact code history is in git. Wherever this file
and `brain.md` differ, `brain.md` is the source of truth.

---

## Contents

1. [What Invisible Canvas is](#1-what-invisible-canvas-is)
2. [The hardware and the room](#2-the-hardware-and-the-room)
3. [The rules the project follows](#3-the-rules-the-project-follows)
4. [The central problem: from camera pixels to projector pixels](#4-the-central-problem-from-camera-pixels-to-projector-pixels)
5. [The timeline, day by day](#5-the-timeline-day-by-day)
6. [How the system works today, end to end](#6-how-the-system-works-today-end-to-end)
7. [Where the code lives](#7-where-the-code-lives)
8. [The commands you can run](#8-the-commands-you-can-run)
9. [Every acceptance test and its status](#9-every-acceptance-test-and-its-status)
10. [All decisions (D1–D54) in one line each](#10-all-decisions-d1d54-in-one-line-each)
11. [Known problems and risks that are still open](#11-known-problems-and-risks-that-are-still-open)
12. [Open questions](#12-open-questions)
13. [What is left to do](#13-what-is-left-to-do)
14. [Glossary](#14-glossary)

---

## 1. What Invisible Canvas is

Invisible Canvas turns an ordinary wall into an interactive digital workspace. A **projector** shows a canvas on
the wall, a **webcam** watches the wall and your hand, and the **laptop** does all the thinking. You draw, erase,
press buttons, select writing and ask an AI about it, all by pointing at the wall with your index finger. There is
no touchscreen, no pen and no special hardware.

The project brief says it must **not** feel like "projector + webcam + drawing app". The core idea is an
**Adaptive Spatial Interaction Engine**: the part that understands where your finger is on the wall and what you
mean by your hand's shape. Four applications are planned on top of it:

1. **Interactive Canvas**: drawing, writing, erasing, colours, widths, selection, undo/redo.
2. **Context-aware AI**: select written content; the AI reads it and can summarize, explain, simplify, give
   examples, ask questions and (since D54) explore the topic. It is not a general chatbot: it works on what is on
   the wall.
3. **Interactive 3D visualization** (later phase).
4. **Presentation / learning mode** (later phase).

Special features from the brief:
- **Teacher Reach**: someone who cannot reach the top of the projection can still write everywhere (a smaller
  physical area mapped onto the whole canvas). Planned, not built yet.
- **Free canvas**: write anywhere, not on lines.
- **Selection**: written content can be selected.
- **AI summary**: the selection goes to the AI and the answer appears in a panel.

The roles of the devices:

| Device | Role |
|---|---|
| Projector | Output: shows the canvas on the wall |
| Webcam | Input: watches the wall and your hand |
| Laptop | Does everything: vision, hand tracking, calibration, coordinate mapping, gestures, canvas, rendering, AI |
| Wall | Where you interact |

Everything runs on the laptop. There is no Raspberry Pi or other computer.

The project is planned in phases (tiers):

| Phase | Tier | Scope |
|---|---|---|
| Phase 1A | P0 Foundation | hardware diagnostics, camera, projector, manual four-point calibration, coordinate mapping, validation |
| Phase 1B/1C/1D | P0 Foundation | automatic calibration and validation; fingertip cursor (1D) |
| Phase 2 | P1 | hand tracking, gestures, drawing, erasing, undo/redo, toolbar |
| Phase 3 | P2 | selection, AI (3A); content from your phone (3B, later) |
| Phase 4 | P3 | 3D, presentation mode, advanced gestures, robustness |
| Phase 5 | P4 | final integration, benchmarking, demo |

---

## 2. The hardware and the room

### The laptop
- Windows 11 Home Single Language (build 26200).
- Intel Core i7-14650HX, 16 GB RAM.
- Two graphics chips: Intel UHD (drives the laptop screen) and an **NVIDIA GeForce RTX 5070 Laptop GPU with 12 GB**
  (used by the local AI since D52).
- Laptop screen 2560×1600 at 150 % Windows scaling. Because of the scaling, the program declares itself
  "per-monitor DPI aware", otherwise windows would land in the wrong place on the projector.
- Some extra software shows up as fake devices: a "Meta Virtual Monitor" (a fake display) and four Meta Quest
  virtual cameras. The project therefore never picks a display or camera by its number; it picks them by name.

### The projector
- **WZATCO Yuva Go**: an Android smart projector, native resolution **1280×720**, connected by HDMI. Windows sees it
  as "AML TV" [AML0030].
- Used as a plain second screen: Windows in **Extend** mode (not Duplicate), the projector display at **1280×720,
  60 Hz, 100 % scaling**, so one canvas pixel is exactly one projector pixel.
- Auto keystone must be off, because any keystone change after calibration would silently break the mapping.
- Its Android system can draw a blue mouse pointer over the picture; that pointer once broke a detector test (R28).
- Measured once (2026-10-10, with the first camera setup): the image on the wall was 129 cm wide × 75 cm high, the
  projector lens 160 cm from the wall, about 9.9 projector pixels per centimetre.

### The camera (two cameras over time)
1. **Logitech Brio 100** (from day 1 until 2026-10-17): 1920×1080 at 30 frames per second, manual exposure.
2. **Kreo Owl 4K Pro** (since 2026-10-17, your decision, D41): 1920×1080 at **60 frames per second** (MJPG),
   exposure locked at −6 (15.6 ms), focus locked at 400, gain locked at 15. Every Brio result had to be measured
   again with the Kreo.

The camera sits beside the projector (closest possible: 18 cm to the right of the lens; the projector's top cannot
hold it). It sees the back of your hand, which turned out to matter a lot for gestures (Phase 2).

### The room
- A **vertical** flat wall (decision D13).
- **One room light on** (since 2026-10-22). In a dark room the projector is the only light on your hand, and
  writing or lines projected onto your hand made the hand much harder to find.
- **Power** (since 2026-10-24/25): the charger connected, or the battery well charged. When the battery was nearly
  empty (~20 %), the laptop slowed its processor down heavily, even on the charger, and tracking fell from ~48 to
  10–20 frames per second. At 91–95 % on battery everything ran at normal speed.

---

## 3. The rules the project follows

These come from you and are written at the top of `brain.md`:

1. Read `brain.md` completely before starting any phase.
2. Build phase by phase; never build a later phase's features early.
3. Before any substantial change, explain the plan and files, then get your approval.
4. Install only what the current phase needs; every dependency needs a reason.
5. Never claim success without testing on the real hardware; record the real numbers.
6. **Never tune the system just to pass a test.** Report the real numbers even when they fail.
7. Priority order, never reversed: **reliability → low latency → accuracy → natural interaction → integration →
   visual polish → features.**
8. Commit each milestone to git (git records what changed; `brain.md` records why).
9. Do not push to GitHub without asking you. (GitHub has the code up to 2026-10-17; the 61 newer commits are on the
   laptop only.)
10. Since 2026-10-23: **no cost**. Nothing may charge money; the AI runs locally for free.
11. Never store API keys in the project; never bypass Windows security (you decide security settings yourself).

Acceptance criteria are always written down **before** the test runs, and are never loosened afterwards to make a
result pass. Many entries in this story say "FAIL" or "not passed" for exactly that reason.

---

## 4. The central problem: from camera pixels to projector pixels

The camera sees the wall at an angle. A point the camera sees at pixel (u, v) is somewhere on the projected
canvas at projector pixel (x, y). The program must convert one into the other accurately, otherwise the ink would
not appear under your finger.

Because the wall is flat, this conversion is a **homography**: a 3×3 matrix that maps any point of one flat view
onto another. It is found by **calibration**: the projector shows four crosses near the corners of the canvas, the
camera finds them, and from the four pairs (where the cross is in the projector image, where the camera sees it)
the matrix is computed.

Four points always fit exactly, so they cannot tell you how accurate the result is. Accuracy is therefore checked on
**held-out points**: 20 other crosses (a 5×4 grid) that were not used for calibration. The error is how far each
mapped point lands from where it should be, in projector pixels.

The targets fixed on day one (D17): **required mean ≤ 5 px and max ≤ 12 px; stretch goal mean ≤ 3 px and max
≤ 8 px**; and three calibrations in a row must agree within 2 camera pixels on average (repeatability).

Coordinate spaces used in the project:
- **Camera space (C)**: pixels in the camera image (1920×1080).
- **Projector space (P)**: pixels in the image sent to the projector (1280×720).
- **Logical canvas (L)**: the drawing's own coordinates (for now the same as P; Teacher Reach will use a different
  mapping later).

One physical limit discovered in Phase 1D: the homography is exact only for points **on the wall**. A fingertip
hovering in front of the wall is seen by the camera from a different angle than the projector's light, so its
mapped position shifts with the hover distance ("hover parallax"). A single camera cannot measure that distance.
More on this in section 5.

---

## 5. The timeline, day by day

### 2026-10-08: Day 1, the foundation

- The laptop was inspected: Windows build, displays, graphics chips, cameras (only the built-in ACER camera and the
  Meta virtual cameras), no projector yet. **Python was not installed**; Python 3.12.10 was installed for your user
  only (via winget), with a project environment `.venv`.
- `brain.md`, the README, `pyproject.toml` and the package skeleton were created; the Phase 1 plan was written; git
  was started. You approved decisions D12–D18 (Python 3.12, a vertical wall, the Brio 100 camera, git, Phase 1 split
  into 1A manual and 1B automatic, the accuracy targets, diagnostics before calibration).
- Phase 1A software was written the same evening:
  - `devices`: lists every display (with its EDID name, connection type, resolution, refresh rate and scaling) and
    every camera (with the modes it really delivers). Uses Windows functions directly (ctypes), no extra packages.
  - `projector`: a full-screen test pattern on the projector, with a check that the window really covers the whole
    projector display.
  - `camera`: a live camera view with frame rate and brightness readings.
  - `calibrate` (manual): you click the four projected crosses in the camera view, with a zoom loupe.
  - `validate` (manual): you click 20 held-out crosses; the program reports the mapping error.
  - `repeatability`, `mapdemo` (hover in the camera view, a crosshair appears on the wall), `latency`.
- Two speed fixes found while testing: Windows' timer was made precise to 1 ms (D20), and a slow per-frame image
  operation was replaced (D21: the camera image's age dropped from 16.8 ms to 0.5 ms).
- 83 unit tests passed. Nothing could be tested with the real projector and camera yet.

### 2026-10-09: the first hardware session (Brio 100 + projector, on a different laptop)

The camera gave strange frame rates, and each one had a different cause:

1. **1 frame per second**: a forgotten camera window was still holding the camera (R20). Closing it fixed it.
2. **5 frames per second**: the order in which the camera settings were sent made Windows fall back from the
   compressed MJPG format to an uncompressed one that USB 2.0 can only carry at 5 fps. Fixed by sending the format
   last (D26).
3. **15 frames per second**: the camera's automatic exposure ("low light compensation") stretched every frame in
   the dim room. Fixed with a **manual exposure** set from the config file and checked by reading it back (D24):
   29.9 fps.
4. Windows reset the exposure to automatic about 1 s and 3 s after every stream start (R21). A small helper now
   re-applies it within 0.25 s.

Then the measurements:
- **Latency** (from showing white on the projector to the camera seeing it): **275 ms** median. One earlier
  measurement had missed 16 of 20 flashes; the tool now refuses to report a result unless every flash was seen
  (D27).
- A1 (diagnostics) **PASS**, A3 (camera 29.83 fps for 60 s, latency measured) **PASS**.
- Night: three manual calibrations agreed within 0.75 px (A6 **PASS**), but the first accuracy test **failed** (mean
  5.87 px). The investigation showed the camera setup had moved about 5 pixels between calibrating and validating.
  Nothing had detected that, so a **setup check** was added: before validating, the four corners are checked again,
  and if they moved more than 2 px the program stops and asks for recalibration (D28).
- 23:24: recalibrated, **A7 PASS: mean 1.99 px, max 4.03 px** (both the required and the stretch targets).

### 2026-10-10: automatic calibration, then the first hand tracking

*(The work from 10-09 to 10-12 is not in this laptop's git history day by day: it reached GitHub as one commit,
`99cb22b` by Kritagya Kumar, and was copied to this laptop on 2026-10-17. The 10-09 hardware session ran on a
different laptop.)*

- **Phase 1B, automatic cross detection (D29)**: the program finds each projected cross in the camera image by
  itself (fitting the two arms as lines and taking their crossing point). Criteria B1–B5 were fixed first. Result:
  all 24 targets found in every frame, no false finds, stable to 0.16 px, consistent with the clicks: **B1–B5 PASS**.
- **Phase 1C, automatic calibration and validation (D30)**: `calibrate` and `validate` now work without clicks.
  Automatic validation: **mean 0.61 px, max 1.31 px**. A manual cross-check of the automatic calibration: mean 1.32
  px. Automatic became the default (D31); manual stays available with `--manual`.
- **D32**: could the setup check be stricter (1 px instead of 2)? A 10-minute test showed the untouched setup slowly
  drifting by 1.5 px, so 1 px would refuse almost every calibration older than 5 minutes. 2 px was kept.
- **Phase 1D, the fingertip cursor (D33)**: Google's **MediaPipe Hand Landmarker** finds 21 points on the hand
  (wrist, knuckles, fingertips). This needed a dependency change (approved): `opencv-contrib-python` instead of
  `opencv-python`, plus `mediapipe` 1.1.0. The hand model file is downloaded separately and its checksum is checked.
  New command `cursor`: a dot on the wall follows your index fingertip.
- **D34, the hand was never found (0 %)**: the canvas was projected dark grey, and in a dark room the projector is the
  only light on your hand. At grey 40 the hand was invisible; at grey 80–200 it was found 100 % of the time. The
  default canvas became mid-grey (later white), and a brightness check was added.
- **D35, accuracy**: the cursor was 8–23 px from the targets, worst at the bottom row. The cause is **hover
  parallax**: your fingertip floats in front of the wall, and the camera (beside the projector) sees it from another
  angle. The error grows with the hover distance and cannot be removed by any setting.
- **D36**: the camera was moved as close to the projector lens as possible (18 cm), and **tiled hand search** was
  added: when no hand is tracked, the program searches the whole frame and 720-pixel tiles (a hand is tiny in the
  whole frame, so the detector missed it). Hand found ~97 % of the time while in view; 0 false finds. The accuracy
  test with the shadow reference was invalid (the finger's shadow was hidden behind the hand at this camera
  position, R24).

### 2026-10-11: tracking audit (D37)

You reported that the cursor did not follow the fingertip well. The audit found:
- Those runs used the "full frame" search, which found hands in only 55 % of frames (tiles: 95 %).
- The ~290 ms delay between finger and cursor is the camera and projector hardware (R4), not the program (~13 ms).
- The smoothing filter lagged; it was made faster.
- MediaPipe sometimes labels another finger as the index for a frame (R25).
Fixes: a search hit is only used after the region tracker confirms it in the same frame; better statistics; a
per-frame trace for diagnosis. Accuracy runs with the finger touching the wall: mean 4.5–5.7 px.

### 2026-10-12: diagnostics and automatic recovery

- **D38**: an observer that flags implausible finger movements (glitches) and records them, without changing the
  cursor. A bug in it (two things with the same name) was found in review and fixed with a test.
- **D39, automatic calibration recovery**: the camera kept getting moved or knocked (R10: seven times by then). Now,
  when the setup check fails, the program builds a new calibration from the corners it just saw, checks it on a
  held-out target and on the 20-point grid (must meet the A7 limits), checks that nothing moved during the check,
  and only then saves it (the old one stays in the history). First real use: it recovered from a 63 px move with
  0.62 px accuracy.
- **D40**: the hand search was limited to 2 views per frame, because 3 views took longer than one camera frame.

### 2026-10-17: the camera changes

- The code was copied from GitHub to this laptop (commit `99cb22b`), with the hand model downloaded and checked.
- **D41**: you chose the **Kreo Owl 4K Pro** camera instead of the Brio. All camera-dependent results became
  "Brio results" that had to be measured again.

### 2026-10-19: the Kreo measured and the whole pipeline re-tested

- Windows was switched from Duplicate to **Extend** mode and the projector to 1280×720 at 100 % (both approved).
- **D42**: MJPG 1920×1080 at **60 fps** works (other sizes only 30); exposure −6 keeps 60 fps; the autofocus kept
  hunting, so focus is locked (best sharpness at 400).
- **D43**: with exposure −6 the image was far too dark; gain is locked at 15 (the maximum).
- The laptop went to sleep for 6 hours during a camera preview; the projector disconnected and the camera locks were
  lost (R27). Lesson: disable sleep during sessions.
- Full re-test: A1 **PASS**; A3 **PASS** (60.15 fps, latency **262 ms**); detector B1, B3, B4 **PASS**; B2 **FAIL**
  because the projector's own blue mouse pointer broke one of the test crosses (R28; to be re-run); automatic
  calibration A5 **PASS**; repeatability A6 **PASS** (0.04 px); accuracy A7 **PASS** (mean 1.05, max 2.54 px).

### 2026-10-21: the first good fingertip run on the Kreo

The setup had moved again and was recalibrated (validation mean 1.19 px). A 90-second cursor run: **54 fps**,
13.8 ms processing per frame, the hand tracked in 97 % of saved frames with a hand, 0 false finds. The cursor trails
a moving finger by about 0.28 s (the hardware latency).

### 2026-10-22: Phase 2, drawing with gestures

**The plan (D44, approved):** index finger only = draw, open hand = erase, pinch = select/press, anything else =
hover; a toolbar at the bottom; a white canvas. Acceptance tests G1–G7 were fixed first. Shapes are recognised from
the **fold angle** of each finger (how much it bends at the knuckle), using MediaPipe's 3-D hand points (D45).

**G1 run 1 FAIL (00:34)**: the camera sees the **back** of your hand, so a pinch (thumb touching index) is hidden and
looks like a fist. Pinch cannot work from this camera position.

**D46, your decision: one gesture + toolbar.** Index finger pointing = use the current tool (PEN draws, ERASER
erases only what it touches, MOVE drags a drawing); anything else = just the cursor; holding the cursor on a toolbar
button for 1 s presses it (CLEAR needs 2 s). A stroke starts only after 7 frames of pointing (to ignore short
misreads).

Then a long day of live tests:
- **G1′ run 1 FAIL**: you pointed into the wall; the camera saw a fist with the finger hidden behind it.
- **G1′ run 2 PASS** (99.3 % pointing recognised): pointing sideways along the wall, side of the hand to the camera.
- **G2 (no accidental ink)**: runs 1 and 2 invalid (not in position; pointed on purpose), **run 3 PASS** (60 s of free
  movement, 0 strokes).
- **G3 run 1 FAIL**: strokes broke apart while you were still pointing (the finger bent a bit while moving).
  **D47, keep-drawing band**: starting a stroke stays strict, but once drawing, a slightly bent finger keeps the
  stroke going.
- **G1′ runs 3 and 4 FAIL**: your natural pointing is upward with the back of the hand to the camera (R30). You asked
  for the finger to be recognised from different angles. **D48, multi-angle pointing**: a guided recording of five
  pointing angles was saved as video, replayed offline through the real tracker, and two new rules were added (the
  finger seen in two views; a "phantom middle finger" that MediaPipe draws on top of the index), plus slightly
  lower tracker confidence. **G1″ PASS**: all five angles 100 % pointing, hand found 93–100 %.
- **G2 run 4 PASS** with the new rules (0 strokes).
- **G3 run 2 FAIL** (20 strokes): short interruptions (0.2–1.1 s) still split strokes. **D49, pen-lift delay**: the pen
  lifts only after 0.6 s without pointing; shorter gaps are joined.
- You noticed that writing projected onto your finger makes the hand "NOT SEEN". The analysis confirmed it: hand found
  100 % over plain white, 62 % over dark content. You turned **one room light on**: hand found 96 % even over writing
  (**G1″ run 2 PASS**). The room light became a setup requirement.
- **G3 run 3** invalid (you corrected with the eraser); **G3 run 4 PASS** (exactly 10 strokes) but with one stray
  straight tail; cause found and fixed (**R32**: the 0.6 s window was not checked on every frame); **G3 run 5 PASS**,
  clean.
- **G4′ PASS** (partial erase): only the ink touched by the eraser disappeared, checked point by point.
- **G5′ presses run 1**: 6 of 20 presses, 0 wrong.
- You saw drawings "change shape" when hovering: the drawing itself never changed; the part of the picture that falls
  on your hand looks shifted (an optical effect).

### 2026-10-23: finishing Phase 2, the light on the hand, and the AI plan

- **G5′ presses runs 2 and 3**: in total 32 presses over 3 runs, every one on the button you rested on, 0 wrong, 0
  missed, 0 accidental. The 20-press protocol was never followed exactly, so G5′ is "measured reliable, not formally
  passed". MOVE drags were not tested.
- **G6 (speed)** not passed: processing 42–56 fps (≥ 30, fine), but the slowest 5 % of frames took 32–41 ms (limit
  33 ms) when searching for a lost hand. **G7 (undo/redo)**: unit tests pass, UNDO/REDO used live, but the 5 live round
  trips were not run.
- **D50, light on the hand**: the projector paints plain white over your hand (with look-ahead for movement), so no
  writing falls on it. **G8 FAIL**: on a busy canvas the hand was found 30.5 % without the light and 74.3 % with it
  (target 90 %). You decided: **light off by default** (kept as the `--light` option).
- Your Phase 3 wishes: the AI as an optional function you switch on; and later, bringing files and images from your
  phone onto the canvas (Phase 3B).
- **D51, Phase 3A plan**: a SELECT tool (draw a loop around writing), an AI button, a panel with SUMMARIZE, EXPLAIN,
  SIMPLIFY, EXAMPLES, QUESTIONS and CLOSE; the AI reads an image of the selected strokes. Acceptance tests S1–S5 were
  fixed first. It was first built with the paid Claude API.
- **D52, your decision: free of cost.** The AI now runs on the laptop: **Ollama** (a free local model server) with the
  vision model **qwen3-vl:8b-instruct**, using the RTX 5070. No account, no key, no internet, nothing leaves the
  laptop. (The first model downloaded was the "thinking" variant, which deliberated for 88 s and never answered; the
  "instruct" variant answers in 1–3 s.) The Claude option stays in the code, switched off.

### 2026-10-24: Windows security, then the selection test S1

- **R33**: `draw --ai` would not start: Windows **Smart App Control** blocked MediaPipe's library file. The project
  never bypasses security; you turned Smart App Control off yourself, and MediaPipe loaded again.
- **S1 run 1 FAIL** (target: a loop around one of three words selects exactly that word in ≥ 9 of 10 tries). You
  wrote CAT DOG SUN and drew 17 loops:
  - 12 loops were completed; 10 selected exactly their word, 2 were wrong. Both wrong ones came from the
    **lead-in**: the stroke starts where pointing starts, so the path of your finger moving to the loop's start
    became part of the loop (one took CAT's T into DOG, one cut the T out of CAT).
  - 5 loops broke off half way and selected nothing: the hand was lost or the finger read as bent over the writing.
    You redid each one at once.
- **D53, the loop closes at its tightest point**: the program finds where the loop's start and end come closest and
  uses only the closed part, dropping the lead-in and any overshoot. On the 17 recorded loops: 12 of 12 completed
  loops exact. Regression tests use your real recorded loops.
- **S1 run 2**: 9 of 9 completed loops exact (D53 corrected two of them live), 9 of 11 counting broken loops; the run
  ended before the 10th word. During the run the frame rate collapsed from ~48 to 10–17 fps: the laptop was **on
  battery at ~20 %** and slowed its processor down.
- **S1 run 3** (on the charger, battery 18 %): **10 of 10 completed loops exact; 10 of 12 counting broken loops** (83
  %). The processor was still held back (hand model 34 ms per frame instead of ~11 ms).
- **Your decision**: S1 selection counts as working on completed loops (22 of 22 exact over runs 2 and 3); the strict
  result stays recorded; the broken loops stay open as **R34**, to be fixed later; no tracking threshold or pen-lift
  delay changed to hide them.
- **S2 preparation**: a dry run of the local AI on your finger-written CAT DOG SUN read every word correctly (2 s each).
  The panel's text was fixed: it said "Claude" although the local model answers, and the "READ:" line (what the AI
  read) was small and grey; it is now as large as the answer.

### 2026-10-25: the AI test S2, and EXPLORE

- **S2** (target: a short handwritten sentence → SUMMARIZE → a transcription you judge correct and a summary, ≥ 4 of 5
  tries; answer time reported). On battery (91 → 71 %), no slowdown. Your 5 sentences: "I Love Pengyien", "WHAT Is
  AI", "Tell me about CaT", "Tell me about DOG", "CAT FISH". All read exactly as written, 15 AI answers, 0 errors,
  new writing answered in 2.3–4.0 s. You said "the physical testing went well": **S2 PASS** on your judgment.
- Your request: a new action **EXPLORE** (D54). It finds the topic of the writing and gives background, key facts and
  one connected concept to explore next, in 3–4 short lines, without repeating the writing.
  - It uses the same single AI request as the other actions (one model call reads and explores).
  - Its answer also says whether a topic was read with confidence. If not, the program throws the model's text away
    and shows a fixed note: *"Could not read a clear topic. Write it larger, or select just the topic word, and try
    again."* So a guessed topic never reaches the wall.
  - The panel buttons moved to 3 columns (the answer area kept its size); CLOSE stays bottom right.
  - Offline tests on your real writing: topics found correctly; on random scribbles the model once repeated "[?]"
    for 26 s, so EXPLORE's answer length was capped (now ≤ ~12 s) and a cut-off answer shows the note.
  - A known weakness was found at once: the model's facts come from its own memory (no internet) and can be wrong.
    It called "Pengyien" "a Chinese surname" and gave different dog breed counts in different answers (R35).
- **EXPLORE physical run 1**: "WHAT IS SQL" → topic SQL (4 good points, 4.7 s); "FLIGT" (written without the H, chosen
  with a SELECT loop) → the model explored "Flight" (it corrected the spelling; open question 17). The SQL points came
  back as one line and ran together on the wall; fixed so each point gets its own line.

### 2026-10-26: EXPLORE run 2 and the person rule

- The camera had moved 155 camera pixels overnight; the automatic recovery recalibrated (mean 1.01 px) and the run
  started normally.
- "My FRIEND": SUMMARIZE worked as before (test X3 done); EXPLORE → "Friendship".
- "KRITAGYA IS MY FRIEND": EXPLORE → "Friendship", but one point said "Kritagya is a common Indian female name", a
  claim about a real person that the model cannot know. The EXPLORE instructions now forbid any statement about a
  person named in the writing; re-checked offline on 11 images: no such claim, nothing else broken.
- While the AI answers, tracking slows to about 24–26 fps (test S3 wants ≥ 30); recorded for the S3 test.

---

## 6. How the system works today, end to end

This is what happens when you run `python -m invisible_canvas draw --ai`:

1. **Find the devices.** The projector is found by its name and connection (the only external HDMI display); the
   camera by its name ("owl 4k"). A full-screen window opens on the projector and its size is verified.
2. **Open the camera.** 1920×1080 MJPG at 60 fps; exposure, focus and gain are set, read back and kept applied
   while running. A capture thread always keeps only the newest frame, so delay cannot build up.
3. **Setup check.** The four corner crosses are projected and found. If they moved more than 2 camera pixels since the
   last calibration, **automatic recovery** builds, checks and saves a new calibration (or stops with a reason).
4. **Brightness check.** The canvas region must be bright enough for the camera to see your hand.
5. **Every frame (~40–50 per second):**
   - **Hand tracking.** If no hand is tracked, the hand detector searches 2 views per frame (the whole frame, then
     720-pixel tiles in turn). Once found, a tracker follows the hand in a square region around it.
   - **Hand shape.** From the 21 hand points: the fold angle of each finger. POINT = index straight, middle and ring
     curled, little finger curled. While drawing, a looser band keeps the stroke going.
   - **Coordinate mapping.** The index fingertip (camera pixels) goes through the calibration matrix to projector
     pixels, with light smoothing.
   - **Interaction engine.** A stroke starts after 7 frames of POINT (the first points are kept, so it starts where
     you began); it ends after 3 frames of another shape, but only once 0.6 s have passed without pointing (short
     gaps are joined); losing the hand briefly is bridged the same way.
   - **Drawing controller.** Applies the stroke to the current tool: PEN adds ink; ERASER removes only the ink it
     touches (strokes are split); MOVE drags a drawing; SELECT draws a loop (closed at its tightest point, D53) and
     selects the strokes with at least 60 % of their points inside. Resting the cursor on a toolbar or panel button
     for 1 s presses it (CLEAR 2 s). Every action can be undone and redone.
   - **Rendering.** The canvas (cached), the selection halo, the loop being drawn, the toolbar, the AI panel and the
     cursor are drawn into one 1280×720 image and shown on the projector.
6. **The AI (with `--ai`).** Pressing AI opens the panel. An action button renders the selected strokes (or the whole
   canvas when nothing is selected) black on white as a PNG and hands it to a **background worker**, so tracking never
   waits. The worker sends it to Ollama on the laptop (`http://127.0.0.1:11434`) with the task. The model returns
   structured JSON: what it read (transcription) and the result. The panel shows "The AI is reading... N s", then
   READ and the answer. Every request's image and answer are saved in `data/ai/`. Only one request runs at a time.
7. **At the end** the canvas is saved (JSON + PNG in `data/canvas/`) and a report with every measurement is written to
   `data/reports/` (frame rate, timing, modes, actions, selections, AI answers and their times). With `--trace`, a
   per-frame trace is saved for analysis.

The toolbar (bottom of the canvas): PEN · ERASER · MOVE · SELECT · black · red · blue · green · thin · medium · thick ·
UNDO · REDO · CLEAR · AI (only with `--ai`).

The AI panel (right side): SUMMARIZE · EXPLAIN · SIMPLIFY · EXAMPLES · QUESTIONS · EXPLORE · CLOSE.

---

## 7. Where the code lives

All code is in `src/invisible_canvas/` (Python 3.12, numpy, OpenCV contrib, MediaPipe; standard library for
everything else, including the connection to Ollama).

| Folder | What it does |
|---|---|
| `camera/` | opens the camera by name, sets and keeps exposure / focus / gain, newest-frame thread, mode probing, DirectShow device names |
| `display/` | finds displays and the projector (Windows functions), the projector and operator windows, test patterns, the light on the hand (D50) |
| `geometry/` | the homography maths (pure numpy) |
| `calibration/` | target positions, cross detector, manual collection, automatic calibration, recovery, accuracy metrics, saving and loading calibrations |
| `mapping/` | camera ↔ projector coordinate conversion |
| `vision/` | MediaPipe hand tracker (tiled search, region tracking), hand-shape classifier, cursor logic, glitch diagnostics, shadow tools |
| `interaction/` | the interaction engine (states, debounce, pen-lift delay) and the drawing controller (tools, buttons, selection, AI panel) |
| `canvas/` | strokes and the canvas, undo/redo history, toolbar layout, selection and loop closing, the AI panel layout, rendering |
| `ai/` | the AI request and answer formats (`client.py`), the local Ollama backend (`local.py`), the background worker (`worker.py`) |
| `tools/` | every command (`devices`, `calibrate`, `validate`, `cursor`, `gestures`, `draw`, `replay`, ...) and shared session code |
| `config.py` + `config/default.toml` | all settings (camera, projector, calibration limits, AI backend and model) |

Other files: `tests/` (31 test files; 547 tests passed and 22 skipped in the last full run, 2026-10-25; the skipped ones
need recordings that exist only on the other laptop), `tests/fixtures/` (your real S1 loops as test data),
`brain.md` (the engineering memory), `README.md` (setup and commands), `requirements.lock` (exact package versions).
`data/` (calibrations, reports, recordings, canvases, AI requests) and `models/` (the hand model) are on the laptop
only, not in git.

---

## 8. The commands you can run

```
python -m invisible_canvas devices        # hardware diagnostics: displays, projector, cameras
python -m invisible_canvas projector      # alignment pattern on the projector
python -m invisible_canvas camera         # live camera view (--preview: large view; --seconds 60: report)
python -m invisible_canvas latency        # display -> camera latency
python -m invisible_canvas calibrate      # automatic four-point calibration (--manual: click the corners)
python -m invisible_canvas validate       # held-out accuracy test (--manual: click the targets)
python -m invisible_canvas recalibrate    # setup check; if moved: build, check and save a new calibration
python -m invisible_canvas repeatability  # how much recent calibrations differ
python -m invisible_canvas setupcheck     # repeated setup checks (read-only)
python -m invisible_canvas mapdemo        # hover in the camera view -> crosshair on the wall
python -m invisible_canvas cursor         # index-fingertip cursor on the wall
python -m invisible_canvas handcheck      # why a hand is or is not detected
python -m invisible_canvas detect         # cross-detector diagnostic
python -m invisible_canvas gestures       # guided gesture recording (--angles, --video, --busy, --light)
python -m invisible_canvas replay DIR     # replay a gesture recording offline
python -m invisible_canvas draw           # the drawing app (--light: light on the hand)
python -m invisible_canvas draw --ai      # the drawing app with the AI panel (local, free)
python -m pytest                          # all unit tests
```

Useful `draw` options: `--seconds N` (stop after N seconds; ESC also quits), `--trace` (per-frame trace),
`--save-every S` (save a camera picture every S seconds), `--load FILE` (continue a saved canvas).

---

## 9. Every acceptance test and its status

### Phase 1A (foundation) — measured with the Brio, then again with the Kreo

| Test | What | Status |
|---|---|---|
| A1 | diagnostics, projector identified by name | **PASS** (Brio 10-09, Kreo 10-19) |
| A2 | projector output, full-screen, sharp lines | partly: geometry verified, you checked the picture; the 1-px line-pair check not recorded |
| A3 | camera ≥ 25 fps for 60 s, latency measured | **PASS** (Kreo: 60.15 fps, latency 262 ms) |
| A4 | the whole projection visible with a margin | visible after re-aiming; saturation not recorded |
| A5 | calibration works, reloads, refuses mismatches | **PASS** (automatic, 10-19) |
| A6 | repeatability ≤ 2 camera px | **PASS** (0.04 px) |
| A7 | accuracy: mean ≤ 5 / max ≤ 12 px (stretch 3 / 8) | **PASS, stretch PASS** (Kreo: 1.05 / 2.54 px) |
| A8 | live mapping checked with a ruler | not done |
| A9 | unit tests | **PASS** |

### Phase 1B–1D

| Test | Status |
|---|---|
| B1–B5 detector (Brio) | **PASS** |
| B1, B3, B4 (Kreo) | **PASS**; B2 FAIL because of the projector's blue pointer (R28), to be re-run |
| Automatic calibration and validation (1C) | **PASS** (0.61 / 1.31 px with the Brio) |
| Fingertip cursor works live | yes (54 fps, 97 % tracked, Kreo) |
| Fingertip accuracy (1D) | **not passed**: no final criterion; hover parallax limits it (R12, open question 12) |

### Phase 2 (drawing with gestures)

| Test | What | Status |
|---|---|---|
| G1″ | pointing recognised from 5 angles; open hand and fist never draw | **PASS** (dark room and with room light) |
| G2 | 60 s of free movement → 0 strokes | **PASS** |
| G3 | 10 deliberate strokes → exactly 10, no gaps | **PASS** (runs 4 and 5) |
| G4′ | partial erase | **PASS** |
| G5′ | 20 toolbar presses, 0 wrong; 5 MOVE drags | presses measured reliable (32/32), protocol not completed; MOVE not run |
| G6 | ≥ 30 fps and slowest 5 % ≤ 33 ms while drawing | **not passed** (the hand search frames are slower) |
| G7 | undo/redo exact | unit tests pass; 5 live round trips not run |
| G8 | light on the hand finds the hand ≥ 90 % on a busy canvas | **FAIL** (74.3 %); light off by your decision |

### Phase 3A (AI on selected writing)

| Test | What | Status |
|---|---|---|
| S1 | a loop selects exactly the word, ≥ 9 of 10 tries | **working on completed loops** (22/22 exact, runs 2–3); strict count with broken loops 10 of 12 (R34 open) |
| S2 | handwritten sentence → SUMMARIZE, ≥ 4 of 5 judged correct | **PASS** (your judgment, 2026-10-25) |
| S3 | ≥ 30 fps and drawing works while the AI answers | **not run formally**; measured 32.5 fps (S2), 26.0 and 23.6 fps (EXPLORE runs) |
| S4 | with AI off: no AI button, no network, no AI package needed | covered by unit tests |
| S5 | a clear message when the AI is unavailable; the app keeps running | covered by unit tests; one live check not run |

### EXPLORE (D54; criteria proposed 2026-10-25 before any physical run)

| Test | What | Status |
|---|---|---|
| X1 | 3 handwritten topics → right topic and 3–4 useful points beyond the writing | 4 tries done (SQL, Flight, Friendship ×2), all topics found; your judgment pending |
| X2 | 2 scribbles → the "could not read a clear topic" note, no topic | **not run on the wall yet** (6 of 6 offline) |
| X3 | SUMMARIZE still works | **done** (2026-10-26) |

**EXPLORE is not complete** until X2 is run and you have judged X1.

---

## 10. All decisions (D1–D54) in one line each

| ID | Date | Decision |
|---|---|---|
| D1 | 10-08 | Python 3.12 (for MediaPipe) |
| D2 | 10-08 | projector output through an OpenCV full-screen window |
| D3 | 10-08 | calibration = a homography from four points, computed in numpy |
| D4 | 10-08 | accuracy measured only on held-out points |
| D5 | 10-08 | calibrations saved as JSON with a history |
| D6 | 10-08 | settings in a TOML file; unknown keys rejected |
| D7 | 10-08 | displays, DPI and camera names through Windows functions (ctypes) |
| D8 | 10-08 | DirectShow camera backend (validated 10-09) |
| D9 | 10-08 | the camera thread keeps only the newest frame |
| D10 | 10-08 | standard project layout (`src/`, `pyproject.toml`, `.venv`) |
| D11 | 10-08 | phase naming: Phase N = tier P(N−1) |
| D12 | 10-08 | (you) Python installed per user; Phase 1 packages: numpy, OpenCV, pytest |
| D13 | 10-08 | (you) a vertical flat wall; keystone not relied on |
| D14 | 10-08 | (you) the Brio 100 as the first camera |
| D15 | 10-08 | (you) git; commit each milestone |
| D16 | 10-08 | (you) Phase 1 split: manual first, automatic next; manual stays as fallback |
| D17 | 10-08 | (you) accuracy targets: mean ≤ 5 / max ≤ 12 px, stretch 3 / 8; repeatability ≤ 2 px |
| D18 | 10-08 | (you) hardware diagnostics before calibration |
| D19 | 10-08 | Phase 1A validation by manual clicks |
| D20 | 10-08 | 1 ms Windows timer |
| D21 | 10-08 | per-frame image work with OpenCV, not slow numpy operations |
| D22 | 10-08 | definitions of sustained fps and latency |
| D23 | 10-08 | calibration targets exactly symmetric about their pixel |
| D24 | 10-09 | manual exposure from the config, verified and kept applied |
| D25 | 10-09 | Brio mode: MJPG 1080p30, exposure −5 |
| D26 | 10-09 | camera format set last (else it falls back to 5 fps) |
| D27 | 10-09 | a latency run counts only if every flash was seen |
| D28 | 10-09 | setup check before validation |
| D29 | 10-10 | automatic cross detection, with criteria B1–B5 |
| D30 | 10-10 | automatic calibration and validation |
| D31 | 10-10 | automatic mode becomes the default |
| D32 | 10-10 | setup check limit stays 2 px (the setup drifts) |
| D33 | 10-10 | MediaPipe hand tracking; OpenCV contrib |
| D34 | 10-10 | brighter canvas: the hand needs light |
| D35 | 10-10 | accuracy defined with the finger's shadow; hover parallax found |
| D36 | 10-10 | camera closer to the projector; tiled hand search |
| D37 | 10-11 | tracking audit fixes (confirmed search hits, faster smoothing, traces) |
| D38 | 10-12 | glitch diagnostics (observation only) |
| D39 | 10-12 | automatic, validated calibration recovery |
| D40 | 10-12 | hand search limited to 2 views per frame |
| D41 | 10-17 | (you) Kreo Owl 4K Pro replaces the Brio |
| D42 | 10-19 | (you) Kreo at 1080p60, exposure −6, focus locked |
| D43 | 10-19 | (you) Kreo gain locked at 15 |
| D44 | 10-22 | (you) Phase 2 gesture design |
| D45 | 10-22 | finger state by fold angle; 3-D hand points |
| D46 | 10-22 | (you) one gesture + toolbar tools; dwell to press |
| D47 | 10-22 | (you) keep-drawing band |
| D48 | 10-22 | (you) multi-angle pointing (video recording, replay, new rules) |
| D49 | 10-22 | (you) pen-lift delay 0.6 s |
| D50 | 10-23 | (you) light on the hand; off by default since G8 |
| D51 | 10-23 | (you) Phase 3A: SELECT, AI panel, acceptance S1–S5 |
| D52 | 10-23 | (you) free local AI: Ollama + qwen3-vl:8b-instruct |
| D53 | 10-24 | (you approved) the SELECT loop closes at its tightest point |
| D54 | 10-25 | (you asked) EXPLORE action |

---

## 11. Known problems and risks that are still open

| ID | Problem | What we know / do |
|---|---|---|
| R3 | projector keystone or focus could re-adjust itself | keep auto keystone off; recalibrate |
| R4 | ~260–290 ms from finger to picture | camera + projector hardware; the projector's game mode / settings not tried yet |
| R7 | white balance still automatic | exposure, focus and gain are locked |
| R9 | glossy or uneven surface | use a matte, flat wall |
| R10 | **the camera keeps moving or getting knocked** (it moved before almost every session; 155 px overnight on 10-26) | automatic recovery handles it; a rigid mount would remove it |
| R12 | **hover parallax** limits fingertip accuracy | needs a depth measurement, a second camera, or a "hover band" rule |
| R17 | DirectShow camera opens are slow (2–10 s), sometimes fail right after another session | wait a few seconds between sessions |
| R23, R24 | the finger's shadow is not usable as an accuracy reference at this camera position | marked invalid rather than guessed |
| R25 | MediaPipe sometimes labels another finger as the index for a frame | recorded and diagnosed; no fix yet |
| R26 | some Kreo properties still unmeasured (lens distortion details) | measured as needed |
| R27 | laptop sleep during a session drops the projector and camera locks | disable sleep; restart the tools after sleep |
| R28 | the projector's blue mouse pointer can cover the picture | switch off the remote's mouse mode |
| R29–R31 | gesture trade-offs (a lazy pen lift can add a tail; a pinch seen from behind can read as pointing; pointing depends on your posture) | open hand or fist to stop drawing; point sideways or upward as recorded |
| R34 | **SELECT loops break off** when the hand is lost over the writing (9 of 43 loops in S1) | you redo the loop; to be fixed later (tracking over projected content) |
| R35 | **EXPLORE facts can be wrong** (the 8B model answers from memory, offline) | READ line shows what was read; no statements about named people; your judgment in X1 |

Resolved or handled along the way (examples): R1 Python missing (resolved), R20 a second camera window holding the
camera (watched: run one camera tool at a time), R21 exposure resets (handled by the keeper), R32 the stray tail
(fixed), R33 Smart App Control (resolved by your setting).

---

## 12. Open questions

- **5.** Does the projector have a low-latency picture mode that shortens the ~260 ms delay?
- **6.** What moves the setup so often? (Until the camera is mounted rigidly, every calibration has a short life.)
- **10, 11, 12.** How to handle hover parallax, and which fingertip accuracy rule and reference to use for Phase 1D.
- **13.** Should repeated recoveries in a short time stop with a warning instead (a mount that keeps moving)?
- **15.** Is the Kreo camera permanent or temporary?
- **17.** Should EXPLORE correct an obvious misspelling (it read "FLIGT" and explored "Flight", and now "Pengyien" →
  "Penguin") or refuse it with the note?

---

## 13. What is left to do

**To finish EXPLORE (D54):**
1. X2 on the wall: two scribbles → the note, no topic.
2. Your judgment of the four EXPLORE answers (SQL, Flight, Friendship ×2).
3. Your answer to open question 17 (correct or refuse misspellings).

**To finish Phase 3A:**
- S3: a formal test of the frame rate and drawing while the AI answers (measured 23.6–32.5 fps so far; target ≥ 30).
- S5: one live check of the failure message (for example with Ollama stopped).
- R34: the broken SELECT loops (tracking over projected writing).

**Phase 2 leftovers:** G5′ MOVE drags and the full 20-press protocol, G6 (speed of the hand search), G7 live
undo/redo round trips.

**Phase 1 leftovers:** B2 re-run without the projector's pointer, A8 ruler check, A2 line-pair check, projector picture
settings vs latency, the fingertip accuracy rule (Phase 1D).

**Later phases:** Phase 3B (files and images from your phone onto the canvas), Teacher Reach, 3D visualization,
presentation mode.

**Housekeeping:** the 61 newest commits are only on the laptop; push to GitHub when you decide.

---

## 14. Glossary

| Word | Meaning |
|---|---|
| **Calibration** | finding the formula that converts camera pixels into projector pixels |
| **Homography** | that formula: a 3×3 matrix that maps one flat view onto another |
| **Held-out points** | test points not used for calibration, so they show the real error |
| **Camera px / projector px** | a pixel in the camera image (1920×1080) / in the projected image (1280×720) |
| **Setup check** | re-finding the four corners to see whether the camera or projector moved |
| **Recovery** | automatically building, checking and saving a new calibration after a move |
| **fps** | frames per second: how many camera images are processed each second |
| **Latency** | the delay between something happening and the system showing it |
| **Pipeline time / p95** | the time to process one frame / the time that 95 % of frames stay under |
| **MediaPipe** | Google's hand-tracking library that finds 21 points on a hand |
| **Landmarks** | those 21 points (wrist, knuckles, finger joints, fingertips) |
| **Fold angle** | how much a finger bends at its knuckle; used to tell pointing from other shapes |
| **POINT** | the index finger out, the other fingers curled: the "use the tool" shape |
| **Debounce** | waiting for several frames in a row before changing mode, so single misreads do nothing |
| **Pen-lift delay** | the 0.6 s the pen waits before lifting, so short tracking gaps do not break a stroke |
| **Dwell** | holding the cursor on a button for 1 s to press it |
| **Tiled search** | looking for a lost hand in overlapping parts of the image, where it appears larger |
| **Hover parallax** | the shift between where the camera sees a hovering fingertip and the wall point under it |
| **Trace** | a per-frame log of what the system measured and decided, for later analysis |
| **Ollama** | free software that runs AI models on the laptop |
| **qwen3-vl:8b-instruct** | the local vision AI model that reads the handwriting (8 billion parameters, on the RTX 5070) |
| **Transcription** | what the AI read from the writing (the READ line) |
| **Structured output** | the AI must answer in a fixed JSON format, so the program can read it reliably |
| **Token** | a small piece of text the AI produces; answers are capped in tokens |
| **Regression test** | a test that reproduces a past bug, so it can never come back unnoticed |
