"""Camera video for offline replay (D48): the frames a tool's tracker saw, as an MJPG AVI.

A background thread encodes and writes (~6 ms per 1080p frame on this laptop), so the tracking loop only
queues the frame. When the queue is full the frame is dropped and counted, never waited for: recording must
not slow the live pipeline it records. Each queued frame gets its index in the video; a frame record with no
index was dropped.
"""

from __future__ import annotations

import queue
import threading
from pathlib import Path

import cv2
import numpy as np


class VideoRecorder:
    def __init__(self, path: Path, size: tuple[int, int], fps: float = 60.0, queue_size: int = 240):
        self.path = Path(path)
        self.size = (int(size[0]), int(size[1]))
        self._writer = cv2.VideoWriter(str(self.path), cv2.VideoWriter_fourcc(*"MJPG"), fps, self.size)
        if not self._writer.isOpened():
            raise OSError(f"cannot write video {self.path}")
        self._queue: queue.Queue = queue.Queue(maxsize=queue_size)
        self._next = 0
        self.written = 0
        self.dropped = 0
        self._thread = threading.Thread(target=self._run, name="video-recorder", daemon=True)
        self._thread.start()

    def add(self, image: np.ndarray) -> int | None:
        """Queue one BGR frame of `size`; its index in the video, or None if it was dropped (queue full)."""
        if image.shape[1] != self.size[0] or image.shape[0] != self.size[1]:
            raise ValueError(f"frame {image.shape[1]}x{image.shape[0]} does not match the video {self.size}")
        try:
            self._queue.put_nowait(image)
        except queue.Full:
            self.dropped += 1
            return None
        index, self._next = self._next, self._next + 1
        return index

    def _run(self) -> None:
        while True:
            image = self._queue.get()
            if image is None:
                return
            self._writer.write(image)
            self.written += 1

    def close(self) -> None:
        if self._thread.is_alive():
            self._queue.put(None)
            self._thread.join()
        self._writer.release()

    def summary(self) -> dict:
        return {"file": str(self.path), "frames": self.written, "dropped": self.dropped}

    def __enter__(self) -> VideoRecorder:
        return self

    def __exit__(self, *exc) -> None:
        self.close()
