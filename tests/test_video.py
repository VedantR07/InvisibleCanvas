import threading
import time

import cv2
import numpy as np
import pytest

from invisible_canvas.tools.video import VideoRecorder


def test_frames_are_written_in_order_with_their_indices(tmp_path):
    path = tmp_path / "v.avi"
    with VideoRecorder(path, (64, 48), fps=30) as video:
        indices = [video.add(np.full((48, 64, 3), 20 * k, np.uint8)) for k in range(5)]
    assert indices == [0, 1, 2, 3, 4] and video.summary() == {"file": str(path), "frames": 5, "dropped": 0}
    cap = cv2.VideoCapture(str(path))
    means = []
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        means.append(frame.mean())
    cap.release()
    assert len(means) == 5 and means == sorted(means)                 # same order, MJPG close to the input
    assert means[0] == pytest.approx(0, abs=3) and means[-1] == pytest.approx(80, abs=3)


def test_a_full_queue_drops_frames_instead_of_waiting(tmp_path):
    video = VideoRecorder(tmp_path / "v.avi", (64, 48), queue_size=2)
    gate, real = threading.Event(), video._writer

    class StalledWriter:                       # the encoder is stuck: the tracking loop must not wait for it
        def write(self, image):
            gate.wait(5)

        def release(self):
            real.release()

    video._writer = StalledWriter()
    frame = np.zeros((48, 64, 3), np.uint8)
    t0 = time.perf_counter()
    indices = [video.add(frame) for _ in range(8)]
    assert time.perf_counter() - t0 < 0.5
    gate.set()
    video.close()
    accepted = [i for i in indices if i is not None]
    assert accepted == list(range(len(accepted))) and len(accepted) <= 3     # 1 in the writer + 2 queued
    assert video.dropped == indices.count(None) >= 5 and video.written == len(accepted)


def test_wrong_frame_size_is_refused(tmp_path):
    with VideoRecorder(tmp_path / "v.avi", (64, 48)) as video:
        with pytest.raises(ValueError):
            video.add(np.zeros((40, 64, 3), np.uint8))
