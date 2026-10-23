"""Runs AI requests in a background thread so the tracking/drawing loop never waits (brain.md §9.11, S3).

One request at a time: `submit` returns False while one is running (the panel shows it is busy). The frame loop
calls `poll()` once per frame and gets the finished answers. Each request's image and answer are saved under
`save_dir` (data/ai/<stamp>-<n>-<action>.png / .json).
"""

from __future__ import annotations

import json
import queue
import threading
import time
from pathlib import Path


class AIWorker:
    def __init__(self, assistant, save_dir: Path | None = None):
        self.assistant = assistant
        self.save_dir = None if save_dir is None else Path(save_dir)
        self._jobs: queue.Queue = queue.Queue()
        self._done: queue.Queue = queue.Queue()
        self._busy = threading.Event()
        self._count = 0
        self.answers: list = []                      # every finished answer, in order (for the report)
        self._thread = threading.Thread(target=self._run, name="ai-worker", daemon=True)
        self._thread.start()

    @property
    def busy(self) -> bool:
        return self._busy.is_set()

    def submit(self, action: str, png: bytes) -> bool:
        if self._busy.is_set():
            return False
        self._busy.set()
        self._count += 1
        self._jobs.put((self._count, action, png))
        return True

    def poll(self) -> list:
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
            n, action, png = job
            answer = self.assistant.ask(action, png)
            self._save(n, action, png, answer)
            self.answers.append(answer)
            self._busy.clear()
            self._done.put(answer)

    def _save(self, n: int, action: str, png: bytes, answer) -> None:
        if self.save_dir is None:
            return
        try:
            self.save_dir.mkdir(parents=True, exist_ok=True)
            base = self.save_dir / f"{time.strftime('%Y%m%d-%H%M%S')}-{n:02d}-{action}"
            base.with_suffix(".png").write_bytes(png)
            base.with_suffix(".json").write_text(json.dumps(answer.to_dict(), indent=2), encoding="utf-8")
        except OSError:
            pass                                      # a failed save never stops the answer reaching the panel

    def close(self, timeout: float = 2.0) -> None:
        self._jobs.put(None)
        self._thread.join(timeout)
