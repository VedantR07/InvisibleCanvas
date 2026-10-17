"""Regression tests for the 2026-10-10 0 %-hand-detection diagnosis (brain.md D34).

Cause found on hardware: the cursor's default canvas (grey 40) left the scene almost black for
the camera (canvas region 23, black level ~16), so the hand was invisible; with the same hand,
grey 80/128/200 gave 100 % detection. The pipeline (model, colour order, preprocessing) was
cleared by a positive control (the official MediaPipe sample image) through the same code.
"""

import argparse

import cv2
import numpy as np
import pytest
from synthetic_camera import CAMERA, CANVAS, H_REAL, warp

from invisible_canvas.display import patterns
from invisible_canvas.mapping.mapper import CoordinateMapper
from invisible_canvas.tools import cursor as cursor_tool
from invisible_canvas.tools.hand_check import (
    DARK_REGION_LUMA,
    MIN_HAND_LENGTH_PX,
    canvas_mask,
    diagnose,
    region_luma,
)
from invisible_canvas.vision import hands
from invisible_canvas.vision.hands import HandObservation, HandTracker

needs_mediapipe = pytest.mark.skipif(not hands.DEFAULT_MODEL.is_file(), reason="hand model not downloaded")


def test_the_measured_dark_scene_is_diagnosed_as_too_dark():
    verdict = diagnose(0.0, 23.0, [])                       # grey 40 on 2026-10-10
    assert "TOO DARK" in verdict and "23" in verdict


def test_a_visible_scene_without_detections_is_not_called_dark():
    verdict = diagnose(0.0, 142.0, [])                      # grey 128, no hand shown
    assert "TOO DARK" not in verdict and "no hand in view" in verdict
    assert f"{MIN_HAND_LENGTH_PX:.0f}" in verdict


def test_detections_and_small_hands_are_reported():
    assert diagnose(1.0, 142.0, [214.0, 216.0]).startswith("hand detected in 100 %")
    assert "smaller than 140 px" in diagnose(0.5, 142.0, [120.0, 220.0])


def test_cursor_default_canvas_is_bright_enough():
    """Grey 40 gave 0 % detection; 80-200 gave 100 % (D34). The default must stay in that range."""
    parser = argparse.ArgumentParser()
    cursor_tool.add_parser(parser.add_subparsers())
    default = parser._subparsers._group_actions[0].choices["cursor"].get_default("background")
    assert default == cursor_tool.DEFAULT_BACKGROUND
    assert 80 <= default <= 200


def test_canvas_region_brightness_uses_the_calibrated_canvas():
    mapper = CoordinateMapper(H_REAL, CANVAS)
    mask = canvas_mask(mapper, CAMERA)
    assert 0.4 < mask.mean() < 0.9                           # the canvas covers part of the frame
    lit = np.clip(warp(patterns.blank(CANVAS, 128), H_REAL), 0, 255).astype(np.uint8)
    assert region_luma(lit, mask) == pytest.approx(128, abs=2)
    dark = np.full((CAMERA[1], CAMERA[0]), 18, np.uint8)
    assert region_luma(dark, mask) == 18.0 < DARK_REGION_LUMA


def test_hand_length_is_wrist_to_middle_fingertip():
    lm = np.zeros((21, 2))
    lm[12] = (120.0, 160.0)
    assert HandObservation((0.0, 0.0), lm, "Right", 0.9).length_px == 200.0


@needs_mediapipe
@pytest.mark.parametrize("bad", [np.zeros((1080, 1920), np.uint8), np.zeros((1080, 1920, 3), np.float32),
                                 np.zeros((1080, 1920, 4), np.uint8)])
def test_invalid_frames_are_refused_before_mediapipe(bad):
    with HandTracker() as tracker:
        with pytest.raises(ValueError, match="BGR uint8"):
            tracker.prepare(bad)


@needs_mediapipe
def test_mediapipe_receives_rgb_in_a_square():
    frame = np.zeros((1080, 1920, 3), np.uint8)
    frame[500:580, 900:1020] = (255, 0, 0)                   # pure BLUE in OpenCV's BGR order
    with HandTracker() as tracker:
        rgb, box = tracker.prepare(frame)
    assert rgb.shape == (960, 960, 3) and rgb.dtype == np.uint8 and rgb.flags["C_CONTIGUOUS"]
    patch = rgb[box.pad_y + 260:box.pad_y + 280, 460:500]     # the patch, downscaled by 2 and letterboxed
    assert (patch[..., 2] == 255).all() and (patch[..., 0] == 0).all()      # blue is channel 2 in RGB
    assert (rgb[:box.pad_y] == 0).all() and (rgb[box.pad_y + 540:] == 0).all()   # black bars
    assert cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)[box.pad_y + 270, 480].tolist() == [255, 0, 0]
