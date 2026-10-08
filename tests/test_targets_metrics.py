import numpy as np
import pytest

from invisible_canvas.calibration.metrics import accuracy_stats, corner_repeatability
from invisible_canvas.calibration.targets import corner_targets, grid_targets, min_distance
from invisible_canvas.config import load_config


def test_corner_targets_are_inset_symmetric_integer_pixels():
    t = corner_targets(1280, 720, 0.06)
    assert t.tolist() == [[77, 43], [1202, 43], [1202, 676], [77, 676]]
    # Symmetric about the canvas centre (639.5, 359.5).
    assert t[0, 0] + t[1, 0] == 1279
    assert t[0, 1] + t[3, 1] == 719


def test_corner_targets_zero_inset_hit_the_edge_pixels():
    assert corner_targets(1280, 720, 0.0).tolist() == [[0, 0], [1279, 0], [1279, 719], [0, 719]]


def test_grid_targets_row_major_integer_inside_canvas():
    g = grid_targets(1280, 720, 5, 4, 0.04)
    assert g.shape == (20, 2)
    assert np.all(g == np.round(g))
    assert g[0].tolist() == [51, 29]
    assert g[4].tolist() == [1228, 29]
    assert g[-1].tolist() == [1228, 690]
    assert np.all((g[:, 0] >= 0) & (g[:, 0] < 1280) & (g[:, 1] >= 0) & (g[:, 1] < 720))


def test_default_validation_grid_is_held_out_from_calibration_targets():
    config = load_config()
    w, h = config.projector.expected_width, config.projector.expected_height
    corners = corner_targets(w, h, config.calibration.target_inset)
    grid = grid_targets(w, h, config.validation.grid_cols, config.validation.grid_rows, config.validation.grid_inset)
    assert min_distance(grid, corners) > 20


def test_accuracy_stats():
    s = accuracy_stats([1.0, 2.0, 3.0, 4.0])
    assert (s.count, s.mean, s.median, s.max) == (4, 2.5, 2.5, 4.0)
    assert s.rms == pytest.approx(np.sqrt(7.5))
    assert s.meets(mean_limit=5, max_limit=12)
    assert not s.meets(mean_limit=2, max_limit=12)
    assert not s.meets(mean_limit=5, max_limit=3.9)


@pytest.mark.parametrize("bad", [[], [1.0, np.nan], [[1.0, 2.0]]])
def test_accuracy_stats_rejects_bad_input(bad):
    with pytest.raises(ValueError):
        accuracy_stats(bad)


def test_repeatability_of_identical_runs_is_zero():
    corners = corner_targets(1920, 1080, 0.2)
    r = corner_repeatability([corners, corners, corners])
    assert r.runs == 3
    assert r.mean_variation == 0.0 and r.max_variation == 0.0


def test_repeatability_known_offsets():
    a = np.array([[100.0, 100], [900, 100], [900, 600], [100, 600]])
    b = a.copy()
    b[0] += [2.0, 0.0]   # only the top-left corner moves, by 2 px
    r = corner_repeatability([a, b])
    # TL mean sits 1 px from each run; other corners do not vary.
    assert r.per_corner_mean == (1.0, 0.0, 0.0, 0.0)
    assert r.mean_variation == pytest.approx(0.25)
    assert r.max_variation == pytest.approx(1.0)


def test_repeatability_needs_two_runs():
    with pytest.raises(ValueError):
        corner_repeatability([np.zeros((4, 2))])
