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
                                          #          the hand is lit plain white, with a ring cursor, so writing
                                          #          already on the wall does not fall on it (D50; on by default
                                          #          since D69, --no-light for a session without it); the l key
                                          #          switches it on / off during a session (D68); it fits the
                                          #          hand's own shape, and [ / ] make it tighter / looser (D70)
python -m invisible_canvas replay DIR     # Phase 2: replay a `gestures --video` recording offline (D48)
python -m invisible_canvas draw          # with the AI (on by default, D57; `draw --no-ai` for a session
                                          #          without it): SELECT a loop around writing, AI button -> the AI
                                          #          summarizes / explains / ... / explores the topic (EXPLORE:
                                          #          background, key facts, a connected concept; D54).
                                          #          Free and offline by default:
                                          #          Ollama + `ollama pull qwen3-vl:8b-instruct` (D52). Optional paid
                                          #          backend: [ai] backend = "claude" + `pip install -e .[ai]`.
python -m invisible_canvas draw --resume  # continue the newest board: all its pages and the open document
                                          #          (--load FILE: a given board-*.json or canvas-*.json)
python -m pytest                          # unit tests
```

## Pages, documents and the AI on documents (`draw`)

- **Pages (D59).** The PAGES button on the toolbar opens a small panel at the top right: `< PAGE`, `PAGE >`,
  `+ PAGE` (a blank page after the current one), `OPEN FILE`, `SHOW DOC` / `SHOW BOARD`, `CLOSE DOC` and `CLOSE`.
  Buttons that cannot act (first or last page, no document) are greyed out. "Page 2 of 5" is shown at the top left.
  Every page keeps its own drawing and its own undo / redo; the pen, the eraser, SELECT and the AI work on the page
  shown.
- **Documents (D60).** OPEN FILE (or the `o` key) shows the Windows Open dialog on the laptop: PNG, JPG or PDF. The
  page is fitted to the wall with its aspect ratio kept. While it is shown, the panel's arrows turn its pages
  (`< DOC`, `DOC >`, "PDF page 3 of 12"), and what you draw is a separate annotation layer for that page: the file is
  only read, never changed. `SHOW BOARD` goes back to the whiteboard (the document stays open, `SHOW DOC` returns
  to it) and `CLOSE DOC` closes it; nothing on the whiteboard is touched. A file that cannot be opened (damaged,
  protected, not supported) gives a message on the wall and drawing goes on.
- **Zoom on a document (D72).** While a document is shown, a zoom bar sits at the bottom right above the toolbar
  (left of the AI panel while it is open): `-` and `+` step through 100 % (the page whole), 125, 150, 200, 250, 300
  and 400 %, keeping the middle of the view in place, and `FIT` shows the whole page again; hold the cursor on them
  as on the toolbar. To see the rest of a zoomed page, choose MOVE and drag the page (start where there is no ink;
  on ink, MOVE moves the ink as before); a slim scroll bar shows which part is seen. What you write stays on the same
  words at every zoom. A page turn keeps the zoom and starts at the top of the next page; the zoom is saved with the
  board. The AI still reads the whole page.
- **The AI on part of a document (D74).** With a document shown, SELECT draws a loop around a part of the page (a
  paragraph, a diagram, a table): it is framed in magenta, also while zoomed, and the AI panel ("AI on part of PDF
  page 2 of 12") then works on that part only, rendered sharply from the page itself (your ink on it is not sent).
  A loop off the page (or a slip) goes back to the whole page; a page turn, SHOW BOARD, CLOSE DOC and CLEAR drop
  the selection.
- **The AI on documents (D61).** With a document shown, the AI panel reads the page itself (the picture, or the PDF
  page rendered at 1600 px); its title says what it reads ("AI on PDF page 3 of 12", "AI on the selection", "AI
  on the whole canvas"). The six actions work on the page. **ASK**: type a question on the laptop keyboard; it
  appears in the panel as you type; Enter sends it, Esc cancels it (while you type, `z`, `s`, `c` and `o` are
  text, and Esc cancels the question instead of quitting). ASK also works on the writing. The answers come from the local model (Ollama),
  free and offline.
- **Smart Lines (D62, D64, D66, D71).** The LINES tool writes one line at a time in the writing area (marked by corner
  guides, a dashed frame and a baseline, at the middle height; "Write here" in it until you write). Ink appears only
  inside it: pointing elsewhere draws nothing, and the ink begins as soon as the fingertip enters the area (no need to
  open the hand first). **DONE** (right of it; blue when there is a line to keep) keeps the line exactly as written as
  the next numbered line in the notes panel at the top, which scrolls (the column right of it: arrows, a blue scroll
  bar and a "last line shown / all lines" counter) when it is full. With the AI on, each line is then read in the
  background by the local model (free, offline): the note turns blue with a suggestion, and the bar above the writing
  area offers **OK** (the suggestion; filled blue), **AS WRITTEN** (the literal reading), **EDIT** (type the line on
  the laptop: Enter saves, Esc cancels), **KEEP INK** (keep the handwriting) and **RETRY**. Nothing becomes text until
  you press one; hold the cursor on a note line to review it again. While the AI or PAGES panel is open, DONE, these
  buttons and the scroll column stand just left of it (D65), so they stay usable. The handwriting is always kept. With
  LINES, UNDO / REDO / CLEAR act on the Smart Lines only (CLEAR: the unfinished line); an unfinished line stays when
  you switch tools or pages. Smart Lines work on whiteboard pages (not on documents). Positions, numbering, font and
  text size: `[smart_lines]` in `config/default.toml`; line images and readings are saved in `data/ai/lines/`.
- **Saving.** On exit and with `s`: every page to `data/canvas/board-<time>.json` plus one PNG per page; an open
  document is stored by its path with its annotations (it is reopened by `--resume` if the file still exists).

The order of the hardware acceptance session is in brain.md §9.8.

## Layout

```
src/invisible_canvas/   application package
tests/                  unit tests
config/                 configuration (added in Phase 1)
data/                   runtime output: calibration, reports (not committed)
```
