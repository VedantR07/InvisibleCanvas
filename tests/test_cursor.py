"""Fingertip cursor logic (vision/cursor.py). Pure; real tracking is measured on hardware (D33)."""

import numpy as np
import pytest

from invisible_canvas.vision.cursor import HOLDING, LOST, OUTSIDE, TRACKING, CursorTracker, OneEuroFilter, dwell

CANVAS = (1280, 720)


def test_tracking_draws_the_mapped_point():
    c = CursorTracker(CANVAS)
    u = c.update(0.0, (640.2, 360.7))
    assert u.status == TRACKING and u.position == (640.2, 360.7) and u.raw == (640.2, 360.7)


def test_short_dropout_holds_the_last_position_then_hides():
    c = CursorTracker(CANVAS, hold_s=0.15)
    c.update(0.000, (100.0, 200.0))
    assert c.update(0.033, None) == c.update(0.100, None)
    held = c.update(0.140, None)
    assert held.status == HOLDING and held.position == (100.0, 200.0)
    gone = c.update(0.200, None)
    assert gone.status == LOST and gone.position is None and c.losses == 1
    assert c.update(0.233, None).status == LOST and c.losses == 1      # counted once


def test_recovery_jumps_to_the_new_position():
    c = CursorTracker(CANVAS, hold_s=0.1, smoothing=OneEuroFilter())
    for k in range(10):
        c.update(k / 30, (100.0, 100.0))
    c.update(0.5, None)
    assert c.status == LOST
    u = c.update(0.6, (900.0, 500.0))                   # reappears elsewhere: no glide from (100, 100)
    assert u.status == TRACKING and u.position == pytest.approx((900.0, 500.0))


@pytest.mark.parametrize("point", [(-0.6, 100.0), (1279.5, 100.0), (640.0, 719.5), (640.0, -3.0),
                                   (np.nan, 10.0), (np.inf, 10.0)])
def test_points_off_the_canvas_hide_the_cursor(point):
    c = CursorTracker(CANVAS)
    c.update(0.0, (640.0, 360.0))
    u = c.update(0.033, point)
    assert u.status == OUTSIDE and u.position is None


def test_canvas_edges_use_pixel_edges():
    c = CursorTracker(CANVAS)
    assert c.update(0.0, (-0.5, -0.5)).status == TRACKING
    assert c.update(0.1, (1279.49, 719.49)).status == TRACKING


def test_one_euro_reduces_jitter_but_follows_motion():
    rng = np.random.default_rng(0)
    f = OneEuroFilter(min_cutoff_hz=1.0, beta=0.02)
    t = np.arange(90) / 30
    still = np.array([f(ti, (500 + rng.normal(0, 1), 300 + rng.normal(0, 1))) for ti in t])
    assert still[30:].std(axis=0).max() < 0.5                    # raw sd is 1.0
    f.reset()
    moving = np.array([f(ti, (100 + 600 * ti, 300)) for ti in t])  # 600 px/s
    assert abs(moving[-1, 0] - (100 + 600 * t[-1])) < 25          # small lag at speed


def test_dwell_needs_a_still_fingertip_for_the_whole_window():
    still = [(k / 30, (400 + 0.3 * (-1) ** k, 300.0)) for k in range(40)]
    d = dwell(still, 1.0, 3.0)
    assert d is not None and d.mean == pytest.approx((400.0, 300.0), abs=0.05) and d.spread < 0.5
    assert dwell(still[:20], 1.0, 3.0) is None                     # not yet a full second
    moving = [(k / 30, (400 + 2 * k, 300.0)) for k in range(40)]
    assert dwell(moving, 1.0, 3.0) is None
    assert dwell([], 1.0, 3.0) is None


def test_accuracy_capture_radius_accepts_a_measured_still_fingertip():
    """D34: on hardware a held fingertip scattered up to 2.37 px rms about its mean; the first 4 px
    capture radius then accepted only ~20 % of 1 s holds (5 of 9 targets skipped). The radius in use
    must accept such holds, and the captured mean must still be the fingertip position."""
    from invisible_canvas.tools import cursor as cursor_tool

    sigma = 2.37 / np.sqrt(2)                                      # per axis, from the radial rms
    rng = np.random.default_rng(0)
    holds = [[(k / 30, tuple(p)) for k, p in enumerate(rng.normal(0, sigma, (31, 2)) + (640, 360))]
             for _ in range(200)]
    rate = lambda radius: np.mean([dwell(s, cursor_tool.DWELL_S, radius) is not None for s in holds])  # noqa: E731
    assert rate(cursor_tool.DWELL_RADIUS_PX) >= 0.97
    assert rate(4.0) <= 0.4                                        # the old radius: why targets were skipped
    means = [dwell(s, cursor_tool.DWELL_S, cursor_tool.DWELL_RADIUS_PX).mean for s in holds[:20]]
    assert np.abs(np.subtract(means, (640, 360))).max() < 1.5    # error comes from the mean, not the radius


# -- D37 tracking audit ---------------------------------------------------------------------------

def test_default_one_euro_on_a_still_and_a_moving_fingertip():
    """The default filter (beta 0.05, D37) halves the jitter of a still fingertip and keeps a fingertip
    moving at 300 px/s within 5 px (the old beta 0.01 lagged ~12 px there)."""
    rng = np.random.default_rng(1)
    t = np.arange(90) / 30
    f = OneEuroFilter()
    still = np.array([f(ti, (500 + rng.normal(0, 1), 300 + rng.normal(0, 1))) for ti in t])
    assert still[30:].std(axis=0).max() < 0.6                    # raw sd 1.0
    f.reset()
    moving = np.array([f(ti, (100 + 300 * ti, 300)) for ti in t])
    lag = (100 + 300 * t) - moving[:, 0]
    assert 0 < lag[-1] < 5.0 and lag[45:].max() < 6.0
    old = OneEuroFilter(beta=0.01)
    assert (100 + 300 * t[-1]) - [old(ti, (100 + 300 * ti, 300)) for ti in t][-1][0] > 2 * lag[-1]


def test_every_state_transition_has_a_reason_and_is_counted():
    c = CursorTracker(CANVAS, hold_s=0.15)
    steps = [(0.00, (100.0, 100.0), TRACKING, "reacquired"),             # first detection (from the initial lost)
             (0.03, (101.0, 100.0), TRACKING, "detected"),
             (0.06, None, HOLDING, "no fingertip: holding the last position"),
             (0.09, (102.0, 100.0), TRACKING, "detected after a dropout"),
             (0.12, None, HOLDING, "no fingertip: holding the last position"),
             (0.30, None, LOST, "no fingertip for more than 150 ms"),
             (0.33, None, LOST, "no fingertip"),
             (0.36, (-5.0, 100.0), OUTSIDE, "fingertip off the canvas"),
             (0.39, (200.0, 200.0), TRACKING, "reacquired"),
             (0.42, (np.nan, 1.0), OUTSIDE, "fingertip not finite"),
             (0.45, None, LOST, "no fingertip")]
    for t, p, status, reason in steps:
        u = c.update(t, p)
        assert (u.status, u.reason) == (status, reason), t
    assert c.transitions == {"lost->tracking": 1, "tracking->holding": 2, "holding->tracking": 1, "holding->lost": 1,
                             "lost->outside": 1, "outside->tracking": 1, "tracking->outside": 1, "outside->lost": 1}
    assert c.losses == 1


def test_holding_never_presents_a_stale_point_as_fresh():
    c = CursorTracker(CANVAS, hold_s=0.15)
    c.update(0.0, (300.0, 200.0))
    u = c.update(0.1, None)
    assert u.status == HOLDING and u.raw is None and u.position == (300.0, 200.0)
    assert u.since_seen_s == pytest.approx(0.1)
    gone = c.update(0.2, None)                                     # older than hold_s: hidden, not frozen
    assert gone.status == LOST and gone.position is None and gone.since_seen_s == pytest.approx(0.2)


def test_long_loss_then_reacquisition_records_the_hidden_time():
    c = CursorTracker(CANVAS, hold_s=0.15, smoothing=OneEuroFilter())
    for k in range(30):
        c.update(k / 30, (640.0, 360.0))
    for k in range(30, 30 + 150):                                  # 5 s without a hand
        assert c.update(k / 30, None).position is None or k / 30 - 29 / 30 <= 0.15
    u = c.update(6.0, (200.0, 600.0))
    assert u.status == TRACKING and u.reason == "reacquired" and u.position == pytest.approx((200.0, 600.0))
    assert c.reacquired_after_s == [pytest.approx(6.0 - (29 / 30 + 0.15), abs=0.04)]


def test_no_jump_or_glide_after_reacquisition_with_smoothing():
    """After a loss the filter restarts at the new point: the first drawn point is the detection and the
    next ones stay at a still fingertip (no pull towards the old position, no stale velocity)."""
    c = CursorTracker(CANVAS, hold_s=0.1, smoothing=OneEuroFilter())
    for k in range(20):                                            # moving fast to the right, then lost
        c.update(k / 30, (100.0 + 30 * k, 300.0))
    c.update(1.0, None)
    c.update(1.2, None)
    drawn = [c.update(1.3 + k / 30, (400.0, 500.0)).position for k in range(10)]
    assert all(np.hypot(*np.subtract(p, (400.0, 500.0))) < 1e-9 for p in drawn)


def test_smoothing_restarts_after_the_fingertip_was_off_the_canvas():
    c = CursorTracker(CANVAS, hold_s=0.1, smoothing=OneEuroFilter())
    for k in range(10):
        c.update(k / 30, (50.0, 50.0))
    assert c.update(10 / 30, (-40.0, 50.0)).status == OUTSIDE
    u = c.update(11 / 30, (1000.0, 600.0))
    assert u.status == TRACKING and u.position == pytest.approx((1000.0, 600.0))
