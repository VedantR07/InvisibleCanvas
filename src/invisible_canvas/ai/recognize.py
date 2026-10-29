"""Smart Lines recognition (brain.md D64): one completed line of handwriting read by the local vision model
(`[ai] local_model`, Qwen3-VL 8B through Ollama: free and offline, whatever `[ai] backend` says), as two texts in
one request:

- `written`: a literal transcription, the characters as written (spelling kept, [?] for a character not read);
- `text`: the same line with contextual spelling corrections (clear misspellings and missing spaces between words
  fixed; no word added, removed, completed, reordered or translated).

Neither is accepted on its own: the teacher confirms one of them, types the line, or keeps the ink (canvas/lines.py).
A corrected text needs a readable literal one: when `written` has no letter or digit, the line is not recognised,
whatever `text` says. Every failure (Ollama not running, the model not downloaded, a timeout, an answer cut off or
not readable, nothing readable) is a reading with ok False and a message; nothing raises. `RecognitionWorker` runs
the requests one after another in a background thread, so the tracking loop never waits for them.
"""

from __future__ import annotations

import base64
import json
import queue
import threading
import time
import urllib.request
from pathlib import Path

from ..config import AIConfig
from .local import KEEP_ALIVE, LocalAssistant, local_error_message

# The `written` instructions are the Phase 0 transcription-only prompt's (brain.md §9.15), word for word.
SYSTEM = (
    "You read one line of handwriting for a teacher's notes. The image shows the line, drawn with a fingertip on a "
    "wall, so the letters can be rough. Return two texts.\n"
    "written: copy exactly the characters that are written, in reading order, on one line, with single spaces "
    "between words. Do not correct spelling. Do not complete, guess or replace words with real or more likely "
    "words. Do not translate, paraphrase, explain or add anything. Keep letters, digits and symbols as written, in "
    "upper or lower case as written. Write [?] for each character you cannot read.\n"
    "text: the same line as the teacher meant it. Correct clear spelling mistakes and put back missing spaces "
    "between words, using the words around them. Keep every word, number and symbol, in their order and in upper "
    "or lower case as written. Do not add, remove, translate, rephrase or complete words. Keep [?] where a "
    "character cannot be read. If the line has no mistake, text is the same as written.\n"
    "If nothing is written, both texts are empty."
)
TASK = "Read this line of handwriting."
SCHEMA = {"type": "object", "properties": {"written": {"type": "string"}, "text": {"type": "string"}},
          "required": ["written", "text"]}
# One line in two texts: ~20-60 tokens each. A model repeating "[?]" ends here after ~6 s instead of running on.
LINE_MAX_TOKENS = 256


def readable(text: str) -> bool:
    """A letter or a digit besides the [?] marks."""
    return any(ch.isalnum() for ch in text.replace("[?]", ""))


def failed(error: str, **extra) -> dict:
    return {"ok": False, "written": "", "text": "", "error": error, **extra}


def build_line_request(cfg: AIConfig, png: bytes) -> dict:
    """The JSON body of Ollama's /api/chat for one line image. Pure."""
    return {
        "model": cfg.local_model,
        "stream": False,
        "format": SCHEMA,
        "keep_alive": KEEP_ALIVE,
        "options": {"temperature": 0, "num_predict": LINE_MAX_TOKENS},
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": TASK, "images": [base64.standard_b64encode(png).decode("ascii")]},
        ],
    }


def reading_from_response(data: dict) -> dict:
    """Ollama's /api/chat reply -> a reading {"ok", "written", "text", "error", "model", "eval_count"}. Pure."""
    meta = {"model": str(data.get("model", "")), "eval_count": data.get("eval_count")}
    if data.get("done_reason") == "length":
        return failed("The reading was cut off.", **meta)
    content = (data.get("message") or {}).get("content")
    if not content:
        return failed("The local AI returned no text.", **meta)
    try:
        answer = json.loads(content)
        written, text = (" ".join(str(answer.get(k) or "").split()) for k in ("written", "text"))
    except (ValueError, AttributeError, TypeError):
        return failed("The local AI's answer could not be read.", **meta)
    if not readable(written):                        # nothing read: no suggestion either (it would be invented)
        return failed("Nothing readable in the line.", **meta, raw_written=written, raw_text=text)
    if not readable(text):
        text = written
    return {"ok": True, "written": written, "text": text, "error": "", **meta}


class LineRecognizer:
    """`read(png)` -> a reading, through Ollama. Blocking: run it in the recognition worker thread."""

    def __init__(self, cfg: AIConfig, opener=urllib.request.urlopen):
        self.cfg = cfg
        self._local = LocalAssistant(cfg, opener)

    def read(self, png: bytes) -> dict:
        t0 = time.perf_counter()
        try:
            reading = reading_from_response(self._local._post("/api/chat", build_line_request(self.cfg, png),
                                                              self.cfg.timeout_s))
        except Exception as e:                           # every failure becomes a reading, never an exception
            reading = failed(local_error_message(e, self.cfg), model=self.cfg.local_model)
        reading["latency_s"] = round(time.perf_counter() - t0, 3)
        return reading


class RecognitionWorker:
    """Reads Smart Lines one after another in a background thread (D64). `submit` queues a request (never refused);
    `cancel` drops one that has not started (its result comes back as None); `poll()`, once per frame, returns the
    finished (request, reading) pairs. Each line's image and reading are saved under `save_dir`
    (data/ai/lines/<stamp>-<request>-p<page>-l<line>.png / .json)."""

    def __init__(self, recognizer, save_dir: Path | None = None):
        self.recognizer = recognizer
        self.save_dir = None if save_dir is None else Path(save_dir)
        self._jobs: queue.Queue = queue.Queue()
        self._done: queue.Queue = queue.Queue()
        self._lock = threading.Lock()
        self._cancelled: set[int] = set()
        self._pending = 0
        self.readings: list[dict] = []               # every reading made, in order, with its request (the report)
        self._thread = threading.Thread(target=self._run, name="line-reader", daemon=True)
        self._thread.start()

    @property
    def busy(self) -> bool:
        """A request is queued or being read."""
        return self._pending > 0

    def submit(self, request: int, png: bytes, context: dict | None = None) -> None:
        with self._lock:
            self._pending += 1
        self._jobs.put((request, png, dict(context or {})))

    def cancel(self, request: int) -> None:
        with self._lock:
            self._cancelled.add(request)

    def poll(self) -> list[tuple[int, dict | None]]:
        out = []
        while True:
            try:
                out.append(self._done.get_nowait())
            except queue.Empty:
                return out

    def _run(self) -> None:
        while True:
            job = self._jobs.get()
            if job is None:
                return
            request, png, context = job
            with self._lock:
                skip = request in self._cancelled
                self._cancelled.discard(request)
            reading = None if skip else self.recognizer.read(png)
            if reading is not None:
                self.readings.append({"request": request, **context, **reading})
                self._save(request, png, context, reading)
            with self._lock:
                self._pending -= 1
            self._done.put((request, reading))

    def _save(self, request: int, png: bytes, context: dict, reading: dict) -> None:
        if self.save_dir is None:
            return
        try:
            self.save_dir.mkdir(parents=True, exist_ok=True)
            base = self.save_dir / (f"{time.strftime('%Y%m%d-%H%M%S')}-{request:03d}"
                                    f"-p{context.get('page', 0)}-l{context.get('line', 0)}")
            base.with_suffix(".png").write_bytes(png)
            base.with_suffix(".json").write_text(json.dumps({**context, **reading}, indent=2), encoding="utf-8")
        except OSError:
            pass                                      # a failed save never stops the reading reaching the line

    def close(self, timeout: float = 2.0) -> None:
        self._jobs.put(None)
        self._thread.join(timeout)
