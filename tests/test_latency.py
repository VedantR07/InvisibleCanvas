from invisible_canvas.tools.latency import validity_problems


def test_clean_run_is_valid():
    assert validity_problems([0.27, 0.26, 0.28], threshold=79.6, black_end=16.2, white_end=142.9) == []


def test_missed_trials_make_the_run_invalid():
    # The 2026-10-09 18:32 run: 16 of 20 trials missed, median printed from the other 4.
    outcomes = [0.255, 0.289, 0.285, 0.274] + [None] * 16
    problems = validity_problems(outcomes, threshold=168.8, black_end=137.9, white_end=199.7)
    assert len(problems) == 1
    assert problems[0].startswith("16 of 20 trials missed (trials 5, 6,")


def test_levels_that_no_longer_straddle_the_threshold_make_the_run_invalid():
    # Reference levels from a brighter scene; the scene at the end is the dark-room one.
    problems = validity_problems([0.27] * 5, threshold=168.8, black_end=16.0, white_end=143.0)
    assert problems == ["levels changed during the run: at the end black 16.0, white 143.0 vs threshold 168.8 "
                        "(lighting, gain or camera aim changed)"]


def test_lost_exposure_makes_the_run_invalid():
    problems = validity_problems([0.27], 79.6, 16.2, 142.9, exposure_error="NOT APPLIED (requested manual -5)")
    assert problems == ["exposure at the end: NOT APPLIED (requested manual -5)"]
