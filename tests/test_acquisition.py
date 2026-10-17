"""Tiled hand acquisition and region tracking (vision/hands.py, brain.md D36)."""

from pathlib import Path

import numpy as np
import pytest

from invisible_canvas.config import REPO_ROOT
from invisible_canvas.vision import hands
from invisible_canvas.vision.hands import HandTracker, Region, square_tiles

FRAME = (1920, 1080)
needs_mediapipe = pytest.mark.skipif(not hands.DEFAULT_MODEL.is_file(), reason="hand model not downloaded")
# A real camera frame from 2026-10-10 02:02 (top-left target): the hand is visible but was lost by the
# full-frame tracker for 18 s. Local hardware data (not in the repository): the test is skipped without it.
LOST_FRAME = REPO_ROOT / "data/diagnostics/cursor-20261010-020046/t0009.1_lost_target1.jpg"


def test_tiles_cover_the_frame_and_any_hand_sized_box_lies_inside_one():
    tiles = square_tiles(FRAME, 720)
    assert len(tiles) == 8 and all(s == 720 for _, _, s in tiles)
    assert all(0 <= x and x + s <= FRAME[0] and 0 <= y and y + s <= FRAME[1] for x, y, s in tiles)
    rng = np.random.default_rng(0)
    for _ in range(500):                       # hand boxes up to 300 px (a hand is ~150-250 camera px)
        bw, bh = rng.uniform(50, 300, 2)
        x, y = rng.uniform(0, FRAME[0] - bw), rng.uniform(0, FRAME[1] - bh)
        assert any(tx <= x and x + bw <= tx + s and ty <= y and y + bh <= ty + s for tx, ty, s in tiles)


def test_tiles_can_be_limited_to_an_area_and_never_exceed_the_frame():
    tiles = square_tiles(FRAME, 720, area=(300, 150, 1700, 1000))
    assert all(x + s <= FRAME[0] and y + s <= FRAME[1] for x, y, s in tiles)
    assert min(x for x, _, _ in tiles) <= 300 and max(x + s for x, _, s in tiles) >= 1700
    assert square_tiles((640, 480), 720) == [(0, 0, 480), (160, 0, 480)]   # tile clipped to the frame height


def test_region_is_centred_on_the_hand_with_a_minimum_size_and_stays_in_the_frame():
    hand = np.array([[900.0, 500.0], [1000.0, 620.0]])
    r = Region.around(hand, FRAME)
    assert r.side == 720 and (r.x0 + r.side / 2, r.y0 + r.side / 2) == pytest.approx((950, 560), abs=1)   # D37 minimum
    edge = Region.around(np.array([[5.0, 1000.0], [120.0, 1075.0]]), FRAME)
    assert edge.x0 == 0 and edge.y0 + edge.side == FRAME[1]
    big = Region.around(np.array([[0.0, 0.0], [600.0, 600.0]]), FRAME)
    assert big.side == FRAME[1]                                       # at most the frame height


def test_region_size_changes_slowly_while_tracking():
    prev = Region(600, 300, 700)
    grown = Region.around(np.array([[600.0, 300.0], [1000.0, 700.0]]), FRAME, previous=prev)
    assert grown.side == round(700 * 1.15)


def test_region_coordinates_round_trip_to_camera_px():
    r = Region(300, 200, 640)
    crop = r.crop(np.zeros((FRAME[1], FRAME[0], 3), np.uint8))
    assert crop.shape == (640, 640, 3)
    # the centre of crop pixel (i, j) is at normalized ((i + 0.5) / side, (j + 0.5) / side)
    assert r.to_camera((10 + 0.5) / 640, (20 + 0.5) / 640) == pytest.approx((310.0, 220.0))


@needs_mediapipe
def test_unknown_acquisition_mode_is_refused():
    with pytest.raises(ValueError, match="acquisition"):
        HandTracker(acquisition="grid")


@needs_mediapipe
@pytest.mark.skipif(not LOST_FRAME.is_file(), reason="local 2026-10-10 hardware frame not present")
def test_tiles_acquire_a_hand_the_full_frame_misses_then_one_region_track_follows_it():
    import cv2
    img = cv2.imread(str(LOST_FRAME))
    with HandTracker() as full:
        assert all(full.process(img, k / 30) is None for k in range(5))          # D33 path: never found
    with HandTracker(acquisition="tiled") as tr:
        sources = [getattr(tr.process(img, k / 30), "source", None) for k in range(8)]
        assert sources[0] in ("search-tile", "search-full")
        assert sources[1:] == ["track"] * 7                                        # tracked, no new search
        assert tr.stats.search_frames == 1 and tr.stats.track_frames == 7 and tr.stats.unconfirmed == 0


# -- D37 tracking audit: restoration, consistency, statistics, confirmation (fake MediaPipe results) ----

def _result(points, score=0.9):
    """A MediaPipe-like HandLandmarkerResult with one hand; points = 21 normalized (x, y)."""
    from types import SimpleNamespace
    return SimpleNamespace(hand_landmarks=[[SimpleNamespace(x=x, y=y) for x, y in points]],
                           handedness=[[SimpleNamespace(category_name="Right", score=score)]])


def _hand_points(cx, cy, tip=None, spread=0.06):
    pts = [(cx + spread * np.cos(a), cy + spread * np.sin(a)) for a in np.linspace(0, 2 * np.pi, 21, endpoint=False)]
    if tip is not None:
        pts[hands.INDEX_TIP] = tip
    return pts


def _no_hand():
    from types import SimpleNamespace
    return SimpleNamespace(hand_landmarks=[], handedness=[])


def test_landmarks_are_restored_from_a_crop_and_flagged_outside_it():
    region = Region(300, 200, 720)
    obs = HandTracker._observation(_result(_hand_points(0.3, 0.7, tip=(0.25, 0.75))), region.to_camera, "track",
                                   (300, 200, 720), FRAME)
    assert obs.tip == pytest.approx((300 + 0.25 * 720 - 0.5, 200 + 0.75 * 720 - 0.5))
    assert obs.tip_norm == pytest.approx((0.25, 0.75)) and obs.view == (300, 200, 720) and obs.tip_in_view
    assert np.allclose(obs.landmarks[hands.INDEX_TIP], obs.tip)
    edge = HandTracker._observation(_result(_hand_points(0.3, 0.7, tip=(0.0, 1.0))), region.to_camera, "track",
                                    (300, 200, 720), FRAME)
    assert edge.tip == pytest.approx((299.5, 919.5)) and edge.tip_in_view          # pixel edges are in view
    beyond = HandTracker._observation(_result(_hand_points(0.3, 0.7, tip=(1.05, 0.5))), region.to_camera, "track",
                                      (300, 200, 720), FRAME)
    assert 0 <= beyond.tip[0] < FRAME[0] and not beyond.tip_in_view               # in the frame, not in the crop


def test_full_frame_and_crop_views_restore_one_point_to_the_same_camera_px():
    from invisible_canvas.vision.hands import Letterbox, letterboxed_to_camera
    box = Letterbox.for_frame(FRAME, (960, 540))
    region = Region(1100, 300, 720)
    for p in np.array([[1200.25, 400.75], [1100.0, 300.0], [1819.4, 1019.4]]):
        n_full = (((p[0] + 0.5) / box.scale_x + box.pad_x) / box.side, ((p[1] + 0.5) / box.scale_y + box.pad_y) / box.side)
        n_crop = ((p[0] - region.x0 + 0.5) / region.side, (p[1] - region.y0 + 0.5) / region.side)
        full = HandTracker._observation(_result(_hand_points(0.5, 0.5, tip=n_full)),
                                        lambda x, y: letterboxed_to_camera(x, y, box), "frame", None, FRAME)
        crop = HandTracker._observation(_result(_hand_points(0.5, 0.5, tip=n_crop)), region.to_camera, "track",
                                        (region.x0, region.y0, region.side), FRAME)
        assert full.tip == pytest.approx(tuple(p), abs=1e-9) and crop.tip == pytest.approx(tuple(p), abs=1e-9)
        assert full.tip_in_view and crop.tip_in_view
    padding = HandTracker._observation(_result(_hand_points(0.5, 0.5, tip=(0.5, 0.1))),     # in the black bar
                                       lambda x, y: letterboxed_to_camera(x, y, box), "frame", None, FRAME)
    assert padding.tip[1] < -0.5 and not padding.tip_in_view


class _FakeLandmarker:
    def __init__(self, script):
        self.script, self.calls, self.last = script, [], None

    def detect_for_video(self, image, ms):
        self.calls.append((image.width, ms))
        self.last = image                                  # scripts may look at the image they were given
        return self.script(image.width, len(self.calls) - 1)

    def detect(self, image):
        self.calls.append((image.width, None))
        self.last = image
        return self.script(image.width, len(self.calls) - 1)

    def close(self):
        pass


@pytest.fixture
def fake_tracker(monkeypatch, tmp_path):
    """HandTracker with scripted MediaPipe landmarkers: video(width, call) / image(width, call) -> result."""
    hl = pytest.importorskip("mediapipe.tasks.python.vision.hand_landmarker")
    model = tmp_path / "fake.task"
    model.write_bytes(b"not a model")

    def make(acquisition, video, image=None, **kw):
        made = {}

        def create(options):
            mode = options.running_mode.name
            made[mode] = _FakeLandmarker(video if mode == "VIDEO" else image)
            return made[mode]
        monkeypatch.setattr(hl.HandLandmarker, "create_from_options", staticmethod(create))
        tr = HandTracker(model, expected_sha256="", acquisition=acquisition, **kw)
        return tr, made
    return make


BLACK_FRAME = np.zeros((FRAME[1], FRAME[0], 3), np.uint8)


def test_full_mode_reports_its_search_frames_acquisitions_and_losses(fake_tracker):
    """2026-10-11: full mode reported 0 search frames although it searched; MediaPipe's VIDEO mode runs the
    palm detector on every frame after a frame without a hand, and those are now counted."""
    present = [False, False, True, True, True, False, True]
    tr, _ = fake_tracker("full", lambda w, k: _result(_hand_points(0.5, 0.5)) if present[k] else _no_hand())
    actions = []
    for k in range(len(present)):
        tr.process(BLACK_FRAME, k / 30)
        actions.append(tr.action)
    assert actions == ["search-miss", "search-miss", "search-hit", "track", "track", "track-lost", "search-hit"]
    s = tr.stats
    assert (s.frames, s.search_frames, s.acquisitions["frame"], s.track_frames, s.track_losses) == (7, 4, 2, 2, 1)


def test_a_search_hit_returns_the_region_trackers_landmarks_from_the_same_frame(fake_tracker):
    """D37: no jump after acquisition. The tiles find the hand (tip at 0.50, 0.40 of the tile); the region
    tracker, given the same frame at once, puts the tip at 0.52, 0.41 of its region: that is returned."""
    tr, made = fake_tracker("tiled",
                            video=lambda w, k: _result(_hand_points(0.5, 0.5, tip=(0.52, 0.41))),
                            image=lambda w, k: _result(_hand_points(0.5, 0.5, tip=(0.50, 0.40))) if w == 720 else _no_hand())
    first = tr.process(BLACK_FRAME, 0.0)
    assert first is not None and first.source == "search-tile" and tr.action == "search-hit"
    region = Region(*first.view)
    assert first.tip == pytest.approx(region.to_camera(0.52, 0.41))                  # the tracker's, not the tile's
    assert made["VIDEO"].calls[0][1] == 0                                              # same frame (0 ms)
    second = tr.process(BLACK_FRAME, 1 / 30)
    assert second.source == "track" and tr.action == "track"
    assert np.hypot(*np.subtract(second.tip, first.tip)) < 40                         # region re-centred only
    s = tr.stats
    assert (s.search_frames, s.acquisitions["search-tile"], s.track_frames, s.unconfirmed) == (1, 1, 1, 0)


def test_an_unconfirmed_search_hit_is_never_returned(fake_tracker):
    tr, _ = fake_tracker("tiled", video=lambda w, k: _no_hand(),
                         image=lambda w, k: _result(_hand_points(0.5, 0.5)) if w == 720 else _no_hand())
    out, actions = [], []
    for k in range(5):
        out.append(tr.process(BLACK_FRAME, k / 30))
        actions.append(tr.action)
    assert out == [None] * 5
    assert actions == ["search-hit-unconfirmed", "track-miss", "track-miss", "region-dropped", "search-hit-unconfirmed"]
    s = tr.stats
    assert (s.search_frames, s.unconfirmed, s.region_losses, s.track_losses, s.track_frames) == (2, 1, 1, 0, 0)


def test_a_hit_confirmed_one_frame_late_is_tracked_and_its_loss_counted(fake_tracker):
    seen = [False, True, True, False, False, False]                   # region tracker calls, in order
    tr, _ = fake_tracker("tiled", video=lambda w, k: _result(_hand_points(0.5, 0.5)) if seen[k] else _no_hand(),
                         image=lambda w, k: _result(_hand_points(0.5, 0.5)) if w == 720 else _no_hand())
    sources = [getattr(tr.process(BLACK_FRAME, k / 30), "source", None) for k in range(6)]
    assert sources == [None, "track", "track", None, None, None]
    s = tr.stats
    assert (s.unconfirmed, s.track_losses, s.region_losses, s.track_frames) == (0, 1, 1, 2)


def test_a_fingertip_outside_the_view_is_counted(fake_tracker):
    tr, _ = fake_tracker("full", lambda w, k: _result(_hand_points(0.5, 0.5, tip=(0.5, 0.1))))   # black bar
    obs = tr.process(BLACK_FRAME, 0.0)
    assert obs is not None and not obs.tip_in_view and tr.stats.tip_outside_view == 1


# A frame of the same run where both the full frame and a region see the whole pointing hand.
BOTH_FRAME = REPO_ROOT / "data/diagnostics/cursor-20261010-020046/t0089.3_tracking_target7.jpg"


@needs_mediapipe
@pytest.mark.skipif(not BOTH_FRAME.is_file(), reason="local 2026-10-10 hardware frame not present")
def test_the_full_frame_and_a_region_put_the_fingertip_at_the_same_camera_px():
    """D37: the two coordinate paths (letterboxed 960-px frame, 720-px camera-resolution crop) agree on
    real data (1.9 px when measured; the landmark model itself differs a little between scales)."""
    import cv2
    img = cv2.imread(str(BOTH_FRAME))
    with HandTracker(acquisition="tiled") as tr:
        full = tr.search(img, ["full"])
        region = Region.around(full.landmarks, FRAME)
        crop = tr.search(img, [(region.x0, region.y0, region.side)])
    assert full.tip_in_view and crop.tip_in_view and crop.view == (region.x0, region.y0, region.side)
    assert np.hypot(*np.subtract(full.tip, crop.tip)) < 4.0
    assert np.abs(full.landmarks - crop.landmarks).max() < 10.0


# -- D40 search budget: at most 2 views per search frame, the full frame first in every new search -------

TILES = square_tiles(FRAME, 720)


def _log_views(tr):
    """Record the views of every search frame (the real search still runs)."""
    log, search = [], tr.search

    def spy(frame, views):
        log.append(list(views))
        return search(frame, views)
    tr.search = spy
    return log


def test_frames_without_a_hand_run_two_views_each_and_cover_the_frame_in_turn(fake_tracker):
    """2026-10-12 20:13: 3 inferences per search frame (full + 2 tiles, ~36 ms) made frames without a hand
    fall behind the camera. Now 2 per frame, in turn: full, tile 1..8, full, ..."""
    tr, made = fake_tracker("tiled", video=lambda w, k: _no_hand(), image=lambda w, k: _no_hand())
    log = _log_views(tr)
    for k in range(9):
        assert tr.process(BLACK_FRAME, k / 30) is None and tr.action == "search-miss"
    T = TILES
    assert log == [["full", T[0]], [T[1], T[2]], [T[3], T[4]], [T[5], T[6]], [T[7], "full"],
                   [T[0], T[1]], [T[2], T[3]], [T[4], T[5]], [T[6], T[7]]]
    assert [w for w, _ in made["IMAGE"].calls] == [960, 720] + [720] * 7 + [960] + [720] * 8   # 960: letterboxed full frame
    assert made["VIDEO"].calls == []                                     # no region tracker while searching
    s = tr.stats
    assert (s.frames, s.search_frames, s.search_views, len(s.search_ms)) == (9, 9, 18, 9)


def test_every_view_recurs_within_five_search_frames(fake_tracker):
    tr, _ = fake_tracker("tiled", video=lambda w, k: _no_hand(), image=lambda w, k: _no_hand())
    log = _log_views(tr)
    for k in range(45):
        tr.process(BLACK_FRAME, k / 30)
    assert all(len(views) == 2 for views in log)
    for i in range(len(log) - 4):
        seen = [v for views in log[i:i + 5] for v in views]
        assert "full" in seen and all(t in seen for t in TILES)


def test_a_hand_only_one_tile_can_see_is_reacquired_when_its_tile_comes_round(fake_tracker):
    """The full frame misses the hand (as for 45 % of hands, D37); only the bottom-right tile finds it.
    It is found on the 5th search frame (the 9th view), confirmed by the region tracker in the same frame
    and then tracked; the hit ends that frame's search."""
    frame = BLACK_FRAME.copy()
    frame[900:960, 1600:1660] = 255                                      # inside the last tile only
    assert [t for t in TILES if t[0] <= 1600 and 1660 <= t[0] + t[2] and t[1] <= 900 and 960 <= t[1] + t[2]] == [TILES[7]]
    made_ref = {}

    def image(w, k):
        seen = made_ref["IMAGE"].last.numpy_view().max() > 0
        return _result(_hand_points(0.5, 0.5)) if w == 720 and seen else _no_hand()
    tr, made = fake_tracker("tiled", video=lambda w, k: _result(_hand_points(0.5, 0.5)), image=image)
    made_ref.update(made)
    log = _log_views(tr)
    sources = [getattr(tr.process(frame, k / 30), "source", None) for k in range(7)]
    assert sources == [None, None, None, None, "search-tile", "track", "track"]
    assert log[4][0] == TILES[7] and len(log) == 5
    s = tr.stats
    assert (s.search_frames, s.search_views, s.acquisitions["search-tile"], s.track_frames, s.unconfirmed) == (5, 9, 1, 2, 0)


def test_tracking_loss_starts_a_new_search_with_the_full_frame_and_the_hand_is_reacquired(fake_tracker):
    """Transitions: search hit (full) -> tracking -> 3 region misses (dropped) -> a new search that starts with
    the full frame while the tiles continue in turn -> reacquired by a tile -> tracking again."""
    present = [True, True, True, False, False, False, False, False, True, True]
    state = {"k": 0}
    hand_now = lambda w, k: _result(_hand_points(0.5, 0.5)) if present[state["k"]] else _no_hand()   # noqa: E731
    tr, made = fake_tracker("tiled", video=hand_now, image=hand_now)
    log = _log_views(tr)
    actions, sources = [], []
    for k in range(len(present)):
        state["k"] = k
        sources.append(getattr(tr.process(BLACK_FRAME, k / 30), "source", None))
        actions.append(tr.action)
    assert actions == ["search-hit", "track", "track", "track-miss", "track-miss", "region-dropped",
                       "search-miss", "search-miss", "search-hit", "track"]
    assert sources == ["search-full", "track", "track", None, None, None, None, None, "search-tile", "track"]
    T = TILES
    # The first search stopped at its first view (the full frame hit); tile 1 was planned, so the rotation goes on.
    assert log == [["full", T[0]], ["full", T[1]], [T[2], T[3]], [T[4], T[5]]]
    s = tr.stats
    assert (s.search_frames, s.search_views, s.track_frames, s.track_losses, s.region_losses) == (4, 6, 3, 1, 1)
    assert s.acquisitions == {"search-full": 1, "search-tile": 1, "frame": 0}


def test_the_view_budget_is_configurable_and_must_be_positive(fake_tracker):
    tr, _ = fake_tracker("tiled", video=lambda w, k: _no_hand(), image=lambda w, k: _no_hand(), views_per_frame=1)
    log = _log_views(tr)
    for k in range(3):
        tr.process(BLACK_FRAME, k / 30)
    assert log == [["full"], [TILES[0]], [TILES[1]]]
    with pytest.raises(ValueError, match="views_per_frame"):
        fake_tracker("tiled", video=lambda w, k: _no_hand(), image=lambda w, k: _no_hand(), views_per_frame=0)
