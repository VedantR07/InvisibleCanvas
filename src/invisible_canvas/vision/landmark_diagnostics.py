"""Diagnostic-only detection of suspicious hand-landmark frames (Phase 1D, brain.md D38). Pure: no camera, no GUI.

OBSERVATIONAL ONLY. Nothing here feeds the cursor: it never suppresses, delays, holds, hides or moves it. The
cursor tool records the result in its trace and report for later inspection.

Two independent signals, in camera px (ratios are unitless; projector px are never used here):
- relative motion: the change of the index tip-to-knuckle vector (landmark 8 - landmark 5) between two
  consecutive camera frames of one continuous track, divided by this frame's palm length |landmark 5 -
  landmark 0|. A MediaPipe glitch moves the fingertip landmark against its own knuckle; moving or rotating
  the whole hand barely does. Flagged above MOTION_LIMIT.
- extension: |landmark 8 - landmark 5| / |landmark 5 - landmark 0|. A skeleton misfit (the index read as
  curled while it points) or a genuinely curled index gives a low value. Flagged below EXTENSION_LIMIT.
The combined flag is their OR (Kleene logic: True if either is True, False if both are False, otherwise no
decision). A handedness label is not an input: label flips alone can never raise a flag.

No decision (None) instead of a guess when: no hand, a landmark missing or not two finite numbers, a palm
shorter than MIN_PALM_PX, or (relative motion only) no usable previous frame: the first frame, a skipped
camera frame (sequence number not previous + 1), a frame after a frame without a usable hand, or a fresh
acquisition by the hand search. Any of these resets the temporal baseline.

Thresholds (D38, offline analysis of the four 2026-10-11 traces, derived from frames without glitches, not
from the glitch examples): on 13,998 clean frames the relative motion never exceeded 0.168 and the extension
never fell below 0.48; 0.25 is ~1.5x that maximum and 0.43 ~0.9x that minimum (leave-one-run-out gave
0.24-0.25 and 0.43-0.44). Genuine finger bends and pointing towards the camera were NOT in that data.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass

import numpy as np

MOTION_LIMIT = 0.25          # palm-normalised change of the tip-knuckle vector between consecutive frames
EXTENSION_LIMIT = 0.43       # |tip - knuckle| / |knuckle - wrist|
MIN_PALM_PX = 2.0            # below this the palm length cannot normalise anything (real palms are ~70-95 px)
WRIST, INDEX_MCP, INDEX_TIP = 0, 5, 8
SEARCH_SOURCES = ("search-full", "search-tile")   # HandObservation.source of a fresh acquisition (D36/D37)
MOTION, EXTENSION = "relative motion", "low extension"


@dataclass(frozen=True)
class LandmarkDiagnostic:
    """One frame. None = no decision for that signal; `no_decision` says why."""
    motion: float | None
    extension: float | None
    motion_flag: bool | None
    extension_flag: bool | None
    suspicious: bool | None
    reasons: tuple[str, ...] = ()          # the signal(s) that raised a flag
    no_decision: tuple[str, ...] = ()      # why a signal could not be decided

    def to_json(self) -> dict:
        r4 = lambda v: None if v is None else round(v, 4)      # noqa: E731
        return {"motion": r4(self.motion), "extension": r4(self.extension), "motion_flag": self.motion_flag,
                "extension_flag": self.extension_flag, "suspicious": self.suspicious, "reasons": list(self.reasons),
                "no_decision": list(self.no_decision)}


def _point(landmarks, k: int) -> np.ndarray:
    """Landmark k from a (21, 2) array/sequence or a mapping keyed by int or str (trace lines use "0", "5", ...)."""
    if hasattr(landmarks, "keys"):
        p = landmarks[k] if k in landmarks else landmarks[str(k)]
    else:
        p = landmarks[k]
    if p is None:
        raise ValueError("landmark is None")
    p = np.asarray(p, dtype=np.float64)
    if p.shape != (2,):
        raise ValueError(f"landmark {k} has shape {p.shape}")
    return p


class LandmarkDiagnostics:
    """Frame-by-frame diagnostics; keeps only the previous frame's tip-knuckle vector as its temporal state."""

    def __init__(self, motion_limit: float = MOTION_LIMIT, extension_limit: float = EXTENSION_LIMIT,
                 min_palm_px: float = MIN_PALM_PX):
        self.motion_limit, self.extension_limit, self.min_palm_px = motion_limit, extension_limit, min_palm_px
        self.reset()

    def reset(self) -> None:
        self._prev_seq: int | None = None
        self._prev_rel: np.ndarray | None = None

    def _undecided(self, reason: str) -> LandmarkDiagnostic:
        self.reset()
        return LandmarkDiagnostic(None, None, None, None, None, (), (reason,))

    def update(self, seq, landmarks, *, reacquired: bool = False) -> LandmarkDiagnostic:
        """seq: camera frame sequence number; landmarks: camera px (None = no hand this frame); reacquired: this
        observation is a fresh acquisition (no motion decision against the previous track)."""
        if landmarks is None:
            return self._undecided("no hand")
        try:
            wrist, mcp, tip = (_point(landmarks, k) for k in (WRIST, INDEX_MCP, INDEX_TIP))
        except (KeyError, IndexError, TypeError, ValueError):
            return self._undecided("missing or malformed landmarks")
        if not (np.all(np.isfinite(wrist)) and np.all(np.isfinite(mcp)) and np.all(np.isfinite(tip))):
            return self._undecided("invalid coordinates")
        palm = float(np.linalg.norm(mcp - wrist))
        if not math.isfinite(palm) or palm < self.min_palm_px:
            return self._undecided("palm length too small")
        rel = tip - mcp
        extension = float(np.linalg.norm(rel)) / palm
        extension_flag = extension < self.extension_limit
        try:
            seq = int(seq)
        except (TypeError, ValueError):
            seq = None
        motion = motion_flag = None
        no_decision: tuple[str, ...] = ()
        if seq is None:
            no_decision = ("motion: no sequence number",)
        elif reacquired:
            no_decision = ("motion: reacquisition",)
        elif self._prev_rel is None or self._prev_seq is None:
            no_decision = ("motion: no previous usable frame",)
        elif seq != self._prev_seq + 1:
            no_decision = ("motion: skipped camera frames",)
        else:
            motion = float(np.linalg.norm(rel - self._prev_rel)) / palm
            motion_flag = motion > self.motion_limit
        self._prev_seq, self._prev_rel = seq, rel
        if motion_flag or extension_flag:
            suspicious = True
        elif motion_flag is False and extension_flag is False:
            suspicious = False
        else:
            suspicious = None
        reasons = tuple(name for name, flag in ((MOTION, motion_flag), (EXTENSION, extension_flag)) if flag)
        return LandmarkDiagnostic(motion, extension, motion_flag, extension_flag, suspicious, reasons, no_decision)


def episodes(times, results) -> list[dict]:
    """Runs of consecutive frames (in processing order) whose combined flag is True."""
    out, cur = [], []
    for t, r in list(zip(times, results)) + [(None, None)]:
        if r is not None and r.suspicious:
            cur.append((t, r))
            continue
        if cur:
            motions = [r.motion for _, r in cur if r.motion is not None]
            exts = [r.extension for _, r in cur if r.extension is not None]
            out.append({"start_s": float(cur[0][0]), "end_s": float(cur[-1][0]),
                        "duration_s": float(cur[-1][0] - cur[0][0]), "frames": len(cur),
                        "peak_motion": max(motions) if motions else None,
                        "min_extension": min(exts) if exts else None,
                        "reasons": sorted({x for _, r in cur for x in r.reasons})})
            cur = []
    return out


def summary(times, results) -> dict:
    """Report section: thresholds, counts per signal, no-decision reasons and the episodes."""
    results = list(results)
    nd = Counter(x for r in results for x in r.no_decision)
    return {"motion_limit": MOTION_LIMIT, "extension_limit": EXTENSION_LIMIT, "units": "camera px ratios (unitless)",
            "observational_only": True, "frames": len(results),
            "motion_decided": sum(r.motion_flag is not None for r in results),
            "extension_decided": sum(r.extension_flag is not None for r in results),
            "motion_flagged": sum(bool(r.motion_flag) for r in results),
            "extension_flagged": sum(bool(r.extension_flag) for r in results),
            "suspicious_frames": sum(bool(r.suspicious) for r in results),
            "no_decision": dict(nd), "episodes": episodes(times, results)}


def replay(trace_lines) -> list[LandmarkDiagnostic]:
    """Offline: the same diagnostics over `cursor --trace` lines (dicts with seq, hand, landmarks, source)."""
    d = LandmarkDiagnostics()
    return [d.update(a.get("seq"), a.get("landmarks") if a.get("hand") else None,
                     reacquired=a.get("source") in SEARCH_SOURCES) for a in trace_lines]
