"""Hand and index-fingertip tracking with MediaPipe Hand Landmarker (Phase 1D, brain.md D33).

MediaPipe is imported only when a HandTracker is created, so the rest of the package (and the
pure tests) work without it. The model file is not in the repository: it is downloaded once
(brain.md D33 for the URL) and checked against MODEL_SHA256 before use.

Coordinates: MediaPipe landmarks are normalized to the image, 0 = left/top image EDGE and 1 =
right/bottom edge. Camera px in this project have pixel CENTRES at integers (brain.md 3), so the
image spans [-0.5, w - 0.5]: camera px = normalized * size - 0.5. The landmark is located on a
downscaled copy of the frame (inference_width) for speed; normalized coordinates do not depend
on that scale, so they are converted with the full camera frame size.

Square input: MediaPipe warned "Using NORM_RECT without IMAGE_DIMENSIONS is only supported for
the square ROI" on the 960x540 frames (2026-10-10), i.e. its crop-to-image landmark projection
assumes a square image. The downscaled frame is therefore letterboxed to a square (black bars;
MediaPipe letterboxes internally anyway) and the landmarks are converted back exactly
(letterboxed_to_camera).

Acquisition (D36): MediaPipe finds a NEW hand with its palm detector, which sees the whole input
scaled to 192x192 (~10 camera px per detector px on a 1920-px frame: a hand is ~20 px there). Once
found, the hand is tracked by the landmark model on a crop around it, which is reliable. With
acquisition="tiled", while no hand is tracked a stateless detector (IMAGE mode) looks at the full
frame and, in turn, at overlapping square tiles at camera resolution (a hand is ~2.7x larger to the
palm detector in a 720-px tile). After a find, ONE tracker (VIDEO mode) follows the hand in a square
region centred on it every frame, so the hand stays near the region centre and MediaPipe's own
frame-to-frame tracking keeps working; the region is dropped after a few missed frames and the
search starts again. There is never more than one track. acquisition="full" is the D33 behaviour.

D37 (2026-10-11 tracking audit): a search hit is returned only once the region tracker has found the
hand in the same frame (its landmarks are returned, so the first cursor point comes from the tracker
that follows the hand: on saved frames a search hit and the region put landmark 8 on different
fingers in 6 % of cases). An unconfirmed hit is not rendered. Each observation records the view its
landmarks came from and whether the fingertip lies inside that view (outside = extrapolated by the
model, not seen). AcquisitionStats now also counts the full-frame path: in VIDEO mode MediaPipe runs
its palm detector on every frame that follows a frame without a hand, so those are its search frames.

D40 (search budget): each search view is one MediaPipe palm-detector inference (~10.5 ms on this laptop
whether full frame or tile: the detector input is 192x192 either way). The D36 search ran the full frame
plus 2 tiles on EVERY search frame (3 inferences, ~36 ms > the 33-ms frame interval), so a frame without
a hand fell behind the camera (2026-10-12 20:13 run: 15.5 ms median queue age, ~24 fps while searching).
Now at most `views_per_frame` (2) views run per search frame, taken in turn from the cycle full frame,
tile 1 ... tile N, full frame, ...; every new search (at start, or after the region was dropped) begins
with the full frame. Every view is still searched, the full frame about every 4.5 frames instead of every
frame (on 1,347 saved frames it found a hand that no tile found in 42; it repeats its own miss on a
still scene). First hit wins, as before.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field, replace
from pathlib import Path

import cv2
import numpy as np

from ..config import REPO_ROOT

INDEX_TIP = 8                                     # MediaPipe hand landmark index of the index fingertip
DEFAULT_MODEL = REPO_ROOT / "models" / "hand_landmarker.task"
MODEL_SHA256 = "fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1"   # float16 v1 (D33)
MODEL_URL = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"


class HandTrackingError(RuntimeError):
    """The hand tracker cannot be created (missing package, missing or wrong model file)."""


def normalized_to_camera(x: float, y: float, size: tuple[int, int]) -> tuple[float, float]:
    """MediaPipe normalized image coordinates -> camera px (pixel centres at integers)."""
    w, h = size
    return float(x) * w - 0.5, float(y) * h - 0.5


@dataclass(frozen=True)
class Letterbox:
    """A (small_w x small_h) image centred on a side x side square; camera frame = small * scale."""
    side: int
    pad_x: int
    pad_y: int
    scale_x: float      # camera px per small-image px (edges aligned, as cv2.resize)
    scale_y: float

    @classmethod
    def for_frame(cls, camera_size: tuple[int, int], small_size: tuple[int, int]) -> Letterbox:
        (w, h), (sw, sh) = camera_size, small_size
        side = max(sw, sh)
        return cls(side, (side - sw) // 2, (side - sh) // 2, w / sw, h / sh)

    def pad(self, small: np.ndarray) -> np.ndarray:
        sh, sw = small.shape[:2]
        return cv2.copyMakeBorder(small, self.pad_y, self.side - sh - self.pad_y, self.pad_x,
                                  self.side - sw - self.pad_x, cv2.BORDER_CONSTANT, value=0)


def letterboxed_to_camera(x: float, y: float, box: Letterbox) -> tuple[float, float]:
    """Normalized coordinates on the letterboxed square -> camera px (pixel centres at integers)."""
    return ((float(x) * box.side - box.pad_x) * box.scale_x - 0.5,
            (float(y) * box.side - box.pad_y) * box.scale_y - 0.5)


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def square_tiles(frame_size: tuple[int, int], side: int, overlap: float = 0.3,
                 area: tuple[float, float, float, float] | None = None) -> list[tuple[int, int, int]]:
    """Square tiles (x0, y0, side) inside the frame covering `area` (x0, y0, x1, y1; default the whole
    frame), neighbours overlapping by at least `overlap` of a tile (a hand smaller than the overlap
    is wholly inside at least one tile)."""
    w, h = frame_size
    side = int(min(side, w, h))
    ax0, ay0, ax1, ay1 = area if area is not None else (0, 0, w, h)
    ax0, ay0, ax1, ay1 = max(0, ax0), max(0, ay0), min(w, ax1), min(h, ay1)

    def starts(a0: float, a1: float, limit: int) -> list[int]:
        span = a1 - a0
        if span <= side:
            return [int(min(max(round((a0 + a1 - side) / 2), 0), limit - side))]
        n = math.ceil((span - side) / (side * (1 - overlap))) + 1
        return sorted({int(min(max(round(a0 + k * (span - side) / (n - 1)), 0), limit - side)) for k in range(n)})

    return [(x, y, side) for y in starts(ay0, ay1, h) for x in starts(ax0, ax1, w)]


@dataclass(frozen=True)
class Region:
    """A square crop of the camera frame (x0, y0 = top-left pixel, side px), inside the frame."""
    x0: int
    y0: int
    side: int

    @classmethod
    def around(cls, landmarks: np.ndarray, frame_size: tuple[int, int], *, scale: float = 3.0,
               min_side: int = 720, previous: Region | None = None, max_change: float = 0.15) -> Region:
        """Centred on the hand's landmark box, `scale` times its larger extent (at least min_side, at most
        the frame); the size changes by at most max_change per call so the tracker sees a steady scale.
        min_side: on 2026-10-10 frames MediaPipe did not find the hand in 384-500 px crops around it
        (too little context) and did in every crop of 600 px or more (5 frames, 6 sizes). D37: on 854
        saved frames with a hand, a fresh detection on the region around a search hit found it in 81.5 %
        of 640-px regions, 89.5 % of 720-px and 89.2 % of 800-px ones (the tile size is also 720)."""
        w, h = frame_size
        lo, hi = landmarks.min(axis=0), landmarks.max(axis=0)
        side = min(max(scale * float(max(hi - lo)), min_side), w, h)
        if previous is not None:
            side = min(max(side, previous.side * (1 - max_change)), previous.side * (1 + max_change))
        side = int(round(min(side, w, h)))
        cx, cy = (lo + hi) / 2
        x0 = int(min(max(round(cx - side / 2), 0), w - side))
        y0 = int(min(max(round(cy - side / 2), 0), h - side))
        return cls(x0, y0, side)

    def crop(self, frame: np.ndarray) -> np.ndarray:
        return frame[self.y0:self.y0 + self.side, self.x0:self.x0 + self.side]

    def to_camera(self, x: float, y: float) -> tuple[float, float]:
        """Normalized coordinates on the crop -> camera px (pixel centres at integers)."""
        return self.x0 + float(x) * self.side - 0.5, self.y0 + float(y) * self.side - 0.5


@dataclass(frozen=True)
class HandObservation:
    tip: tuple[float, float]       # index fingertip, camera px
    landmarks: np.ndarray          # (21, 2) camera px
    handedness: str                # "Left" / "Right" as MediaPipe reports it
    score: float                   # handedness score (MediaPipe's per-hand confidence)
    source: str = "frame"          # "frame" (full-frame tracker), "track" (region), "search-full", "search-tile"
    view: tuple[int, int, int] | None = None     # (x0, y0, side) of the crop MediaPipe saw; None = whole frame
    tip_norm: tuple[float, float] | None = None  # the fingertip as MediaPipe returned it (normalized to its input)
    tip_in_view: bool = True       # False: the fingertip lies outside the image MediaPipe saw (extrapolated)
    world: np.ndarray | None = None  # (21, 3) MediaPipe world landmarks: metres, hand-centred (D44); None if absent

    @property
    def length_px(self) -> float:
        """Wrist -> middle fingertip in camera px (the hand-size measure of brain.md D34)."""
        return float(np.linalg.norm(self.landmarks[12] - self.landmarks[0]))


@dataclass
class AcquisitionStats:
    """Acquisition counters (D36; D37: also for acquisition="full", where a search frame is a frame that
    follows a frame without a hand: MediaPipe's VIDEO mode runs its palm detector on those)."""
    search_frames: int = 0
    search_views: int = 0
    acquisitions: dict = field(default_factory=lambda: {"search-full": 0, "search-tile": 0, "frame": 0})
    unconfirmed: int = 0          # found by the search, but the region tracker never confirmed it
    track_frames: int = 0
    region_losses: int = 0
    search_ms: list = field(default_factory=list)
    frames: int = 0               # frames processed
    track_losses: int = 0         # a tracked hand was not found again (full: next frame; tiled: region dropped)
    tip_outside_view: int = 0     # observations whose fingertip lay outside the image MediaPipe saw


class HandTracker:
    """One hand, MediaPipe VIDEO mode (frames in order, monotonic timestamps). acquisition="tiled":
    see the module docstring (D36)."""

    def __init__(self, model_path: Path | None = None, *, inference_width: int = 960, num_hands: int = 1,
                 min_detection: float = 0.5, min_presence: float = 0.5, min_tracking: float = 0.5,
                 expected_sha256: str | None = None, acquisition: str = "full", tile_side: int = 720,
                 views_per_frame: int = 2, region_patience: int = 2):
        if acquisition not in ("full", "tiled"):
            raise ValueError(f"acquisition must be 'full' or 'tiled', not {acquisition!r}")
        if views_per_frame < 1:
            raise ValueError(f"views_per_frame must be at least 1, not {views_per_frame!r}")
        model_path = Path(model_path or DEFAULT_MODEL)
        if not model_path.is_file():
            raise HandTrackingError(f"hand model not found: {model_path} (download it, brain.md D33)")
        expected = expected_sha256 if expected_sha256 is not None else MODEL_SHA256
        if expected and file_sha256(model_path) != expected:
            raise HandTrackingError(f"hand model {model_path} does not have the expected SHA-256 {expected}")
        try:
            import mediapipe as mp
            from mediapipe.tasks.python.core.base_options import BaseOptions
            from mediapipe.tasks.python.vision.core.vision_task_running_mode import VisionTaskRunningMode
            from mediapipe.tasks.python.vision.hand_landmarker import HandLandmarker, HandLandmarkerOptions
        except ImportError as e:
            raise HandTrackingError(f"MediaPipe is not installed ({e}); see brain.md D33") from None
        self._mp = mp
        options = HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(model_path)),
            running_mode=VisionTaskRunningMode.VIDEO,
            num_hands=num_hands,
            min_hand_detection_confidence=min_detection,
            min_hand_presence_confidence=min_presence,
            min_tracking_confidence=min_tracking,
        )
        self._landmarker = HandLandmarker.create_from_options(options)
        self.inference_width = inference_width
        self._last_ms = -1
        self.acquisition = acquisition
        self.stats = AcquisitionStats()
        self._detector = None
        if acquisition == "tiled":       # stateless search detector: no track of its own
            options.running_mode = VisionTaskRunningMode.IMAGE
            self._detector = HandLandmarker.create_from_options(options)
        self.tile_side, self.views_per_frame, self.region_patience = tile_side, views_per_frame, region_patience
        self._region: Region | None = None
        self._misses = 0
        self._confirmed = False
        self._next_tile = 0
        self._full_due = True            # D40: the next search view is the full frame (each new search starts so)
        self._tiles_since_full = 0
        self._tracking = False           # full: the previous frame had a hand (MediaPipe tracks, no palm search)
        self.action = "none"             # what the last process() call did (for the per-frame trace)

    def prepare(self, frame_bgr: np.ndarray) -> tuple[np.ndarray, Letterbox]:
        """The exact image MediaPipe receives (RGB uint8, square) and how it maps back to camera px."""
        if frame_bgr.ndim != 3 or frame_bgr.shape[2] != 3 or frame_bgr.dtype != np.uint8:
            raise ValueError(f"expected a BGR uint8 camera frame, got {frame_bgr.shape} {frame_bgr.dtype}")
        h, w = frame_bgr.shape[:2]
        small = frame_bgr
        if self.inference_width and w > self.inference_width:
            small = cv2.resize(frame_bgr, (self.inference_width, round(h * self.inference_width / w)),
                               interpolation=cv2.INTER_AREA)
        box = Letterbox.for_frame((w, h), (small.shape[1], small.shape[0]))
        return np.ascontiguousarray(cv2.cvtColor(box.pad(small), cv2.COLOR_BGR2RGB)), box

    def _ms(self, timestamp_s: float) -> int:
        ms = max(int(round(timestamp_s * 1000)), self._last_ms + 1)     # strictly increasing
        self._last_ms = ms
        return ms

    def _image(self, rgb: np.ndarray):
        return self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb))

    @staticmethod
    def _observation(result, to_camera, source: str, view: tuple[int, int, int] | None,
                     frame_size: tuple[int, int]) -> HandObservation | None:
        """MediaPipe result -> observation in camera px. view: the (x0, y0, side) crop MediaPipe saw, or None
        for the whole frame; the fingertip is in view when it lies on that image (pixel edges included)."""
        if not result.hand_landmarks:
            return None
        points = np.array([to_camera(p.x, p.y) for p in result.hand_landmarks[0]])
        category = result.handedness[0][0] if result.handedness and result.handedness[0] else None
        tip = (float(points[INDEX_TIP, 0]), float(points[INDEX_TIP, 1]))
        x0, y0, x1, y1 = ((-0.5, -0.5, frame_size[0] - 0.5, frame_size[1] - 0.5) if view is None else
                          (view[0] - 0.5, view[1] - 0.5, view[0] + view[2] - 0.5, view[1] + view[2] - 0.5))
        raw = result.hand_landmarks[0][INDEX_TIP]
        world_landmarks = getattr(result, "hand_world_landmarks", None)
        world = (np.array([(p.x, p.y, p.z) for p in world_landmarks[0]], dtype=np.float64)
                 if world_landmarks and len(world_landmarks[0]) == len(points) else None)
        return HandObservation(
            tip=tip,
            landmarks=points,
            handedness=category.category_name if category else "",
            score=float(category.score) if category else 0.0,
            source=source,
            view=None if view is None else tuple(int(v) for v in view),
            tip_norm=(float(raw.x), float(raw.y)),
            tip_in_view=bool(np.all(np.isfinite(tip)) and x0 <= tip[0] <= x1 and y0 <= tip[1] <= y1),
            world=world,
        )

    def process(self, frame_bgr: np.ndarray, timestamp_s: float) -> HandObservation | None:
        if self.acquisition == "tiled":
            obs = self._process_tiled(frame_bgr, timestamp_s)
        else:
            obs = self._process_full(frame_bgr, timestamp_s)
        self.stats.frames += 1
        if obs is not None and not obs.tip_in_view:
            self.stats.tip_outside_view += 1
        return obs

    def _process_full(self, frame_bgr: np.ndarray, timestamp_s: float) -> HandObservation | None:
        """D33 path. MediaPipe (VIDEO mode) runs its palm detector on the whole frame whenever the previous
        frame had no hand, and otherwise tracks the hand from its previous landmarks."""
        rgb, box = self.prepare(frame_bgr)
        h, w = frame_bgr.shape[:2]
        result = self._landmarker.detect_for_video(self._image(rgb), self._ms(timestamp_s))
        obs = self._observation(result, lambda x, y: letterboxed_to_camera(x, y, box), "frame", None, (w, h))
        s = self.stats
        if self._tracking:
            if obs is not None:
                s.track_frames += 1
                self.action = "track"
            else:
                s.track_losses += 1
                self.action = "track-lost"
        else:
            s.search_frames += 1
            s.search_views += 1
            if obs is not None:
                s.acquisitions["frame"] += 1
                self.action = "search-hit"
            else:
                self.action = "search-miss"
        self._tracking = obs is not None
        return obs

    def tiles(self, frame_size: tuple[int, int]) -> list[tuple[int, int, int]]:
        return square_tiles(frame_size, self.tile_side)

    def next_views(self, frame_size: tuple[int, int]) -> list:
        """D40: the views of the next search frame, at most views_per_frame, in turn from the cycle full frame,
        tile 1 .. tile N; the full frame comes first in every new search and again after every N tiles."""
        tiles = self.tiles(frame_size)
        views = []
        for _ in range(self.views_per_frame):
            if self._full_due or self._tiles_since_full >= len(tiles):
                views.append("full")
                self._full_due, self._tiles_since_full = False, 0
            else:
                views.append(tiles[self._next_tile % len(tiles)])
                self._next_tile = (self._next_tile + 1) % len(tiles)
                self._tiles_since_full += 1
        return views

    def search(self, frame_bgr: np.ndarray, views: list) -> HandObservation | None:
        """Stateless detection on the given views ("full" or a (x0, y0, side) tile); first hit wins."""
        h, w = frame_bgr.shape[:2]
        for view in views:
            self.stats.search_views += 1
            if view == "full":
                rgb, box = self.prepare(frame_bgr)
                obs = self._observation(self._detector.detect(self._image(rgb)),
                                        lambda x, y, b=box: letterboxed_to_camera(x, y, b), "search-full", None, (w, h))
            else:
                region = Region(*view)
                rgb = cv2.cvtColor(region.crop(frame_bgr), cv2.COLOR_BGR2RGB)
                obs = self._observation(self._detector.detect(self._image(rgb)), region.to_camera, "search-tile",
                                        view, (w, h))
            if obs is not None:
                return obs
        return None

    def _track(self, frame_bgr: np.ndarray, timestamp_s: float, region: Region) -> HandObservation | None:
        """The VIDEO tracker on one region of the frame."""
        h, w = frame_bgr.shape[:2]
        rgb = cv2.cvtColor(region.crop(frame_bgr), cv2.COLOR_BGR2RGB)
        result = self._landmarker.detect_for_video(self._image(rgb), self._ms(timestamp_s))
        return self._observation(result, region.to_camera, "track", (region.x0, region.y0, region.side), (w, h))

    def _process_tiled(self, frame_bgr: np.ndarray, timestamp_s: float) -> HandObservation | None:
        if frame_bgr.ndim != 3 or frame_bgr.shape[2] != 3 or frame_bgr.dtype != np.uint8:
            raise ValueError(f"expected a BGR uint8 camera frame, got {frame_bgr.shape} {frame_bgr.dtype}")
        h, w = frame_bgr.shape[:2]
        if self._region is not None:                       # tracking: one VIDEO tracker on the region
            region = self._region
            obs = self._track(frame_bgr, timestamp_s, region)
            if obs is not None:
                self.stats.track_frames += 1
                self._misses, self._confirmed = 0, True
                self._region = Region.around(obs.landmarks, (w, h), previous=region)
                self.action = "track"
                return obs
            self._misses += 1
            self.action = "track-miss"
            if self._misses > self.region_patience:
                self.stats.region_losses += 1
                if self._confirmed:
                    self.stats.track_losses += 1
                else:
                    self.stats.unconfirmed += 1
                self._region = None
                self._full_due = True    # D40: the next search starts with the full frame
                self.action = "region-dropped"
            return None
        # searching: the full frame, then the next tiles in turn
        import time
        t0 = time.perf_counter()
        views = self.next_views((w, h))
        self.stats.search_frames += 1
        found = self.search(frame_bgr, views)
        self.stats.search_ms.append((time.perf_counter() - t0) * 1000)
        if found is None:
            self.action = "search-miss"
            return None
        self.stats.acquisitions[found.source] += 1
        self._region = Region.around(found.landmarks, (w, h))
        self._misses, self._confirmed = 0, False
        # D37: the region tracker must find the hand in this same frame before anything is returned, and its
        # landmarks (the hand it will follow) are returned. Otherwise it gets region_patience more frames.
        obs = self._track(frame_bgr, timestamp_s, self._region)
        if obs is None:
            self.action = "search-hit-unconfirmed"
            return None
        self._confirmed = True
        self._region = Region.around(obs.landmarks, (w, h), previous=self._region)
        self.action = "search-hit"
        return replace(obs, source=found.source)

    def close(self) -> None:
        self._landmarker.close()
        if self._detector is not None:
            self._detector.close()

    def __enter__(self) -> HandTracker:
        return self

    def __exit__(self, *exc) -> None:
        self.close()
