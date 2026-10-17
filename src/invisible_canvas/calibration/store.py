"""Calibration persistence: versioned JSON with history (brain.md D5).

`<dir>/current.json` is the active calibration; every save also goes to
`<dir>/history/<timestamp>.json`, which the repeatability test reads.
On load, H is recomputed from the stored point pairs and must agree with the stored
H, so a damaged or hand-edited file is refused instead of silently mis-mapping.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np

from ..geometry.homography import GeometryError, apply_homography, estimate_homography

log = logging.getLogger(__name__)

SCHEMA_VERSION = 1
CURRENT_FILE = "current.json"
HISTORY_DIR = "history"


class CalibrationError(RuntimeError):
    """No usable calibration: missing, damaged, or made for different hardware."""


@dataclass(frozen=True)
class Calibration:
    created_at: str                    # ISO 8601 with UTC offset
    method: str                        # "manual" (1A); "auto" (1B)
    camera_name: str
    camera_size: tuple[int, int]       # (width, height) of the frames the clicks were made in
    projector_name: str
    projector_size: tuple[int, int]
    projector_points: np.ndarray       # (4, 2) target positions, TL TR BR BL
    camera_points: np.ndarray          # (4, 2) where they were seen in the camera
    homography: np.ndarray             # (3, 3) camera -> projector

    @classmethod
    def create(cls, *, method, camera_name, camera_size, projector_name, projector_size,
               projector_points, camera_points) -> Calibration:
        projector_points = np.asarray(projector_points, dtype=np.float64)
        camera_points = np.asarray(camera_points, dtype=np.float64)
        return cls(
            created_at=datetime.now().astimezone().isoformat(timespec="milliseconds"),
            method=method,
            camera_name=camera_name,
            camera_size=(int(camera_size[0]), int(camera_size[1])),
            projector_name=projector_name,
            projector_size=(int(projector_size[0]), int(projector_size[1])),
            projector_points=projector_points,
            camera_points=camera_points,
            homography=estimate_homography(camera_points, projector_points),
        )

    def to_dict(self) -> dict:
        return {
            "schema_version": SCHEMA_VERSION,
            "created_at": self.created_at,
            "method": self.method,
            "camera": {"name": self.camera_name, "width": self.camera_size[0], "height": self.camera_size[1]},
            "projector": {"name": self.projector_name, "width": self.projector_size[0],
                          "height": self.projector_size[1]},
            "projector_points": self.projector_points.tolist(),
            "camera_points": self.camera_points.tolist(),
            "homography_camera_to_projector": self.homography.tolist(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> Calibration:
        version = data.get("schema_version")
        if version != SCHEMA_VERSION:
            raise CalibrationError(f"unsupported calibration schema version {version!r} (expected {SCHEMA_VERSION})")
        try:
            calibration = cls(
                created_at=data["created_at"],
                method=data["method"],
                camera_name=data["camera"]["name"],
                camera_size=(int(data["camera"]["width"]), int(data["camera"]["height"])),
                projector_name=data["projector"]["name"],
                projector_size=(int(data["projector"]["width"]), int(data["projector"]["height"])),
                projector_points=np.asarray(data["projector_points"], dtype=np.float64),
                camera_points=np.asarray(data["camera_points"], dtype=np.float64),
                homography=np.asarray(data["homography_camera_to_projector"], dtype=np.float64),
            )
        except (KeyError, TypeError, ValueError) as e:
            raise CalibrationError(f"malformed calibration file: {e!r}") from None
        calibration._check_integrity()
        return calibration

    def _check_integrity(self) -> None:
        if self.homography.shape != (3, 3):
            raise CalibrationError("stored homography is not 3x3")
        try:
            recomputed = estimate_homography(self.camera_points, self.projector_points)
        except GeometryError as e:
            raise CalibrationError(f"stored points are degenerate: {e}") from None
        stored = apply_homography(self.homography, self.camera_points)
        expected = apply_homography(recomputed, self.camera_points)
        if not np.all(np.isfinite(stored)) or np.max(np.abs(stored - expected)) > 1e-6:
            raise CalibrationError("stored homography does not match the stored points (file damaged or edited)")


def check_compatible(calibration: Calibration, camera_size: tuple[int, int],
                     projector_size: tuple[int, int]) -> None:
    """Refuse a calibration made for a different camera mode or projector resolution."""
    problems = []
    if tuple(camera_size) != calibration.camera_size:
        problems.append(f"camera frames are {camera_size[0]}x{camera_size[1]}, calibration was made at "
                        f"{calibration.camera_size[0]}x{calibration.camera_size[1]}")
    if tuple(projector_size) != calibration.projector_size:
        problems.append(f"projector is {projector_size[0]}x{projector_size[1]}, calibration was made for "
                        f"{calibration.projector_size[0]}x{calibration.projector_size[1]}")
    if problems:
        raise CalibrationError("calibration does not match this setup: " + "; ".join(problems) + ". Recalibrate.")


def _write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _history_path(calibration: Calibration, directory: Path) -> Path:
    stamp = datetime.fromisoformat(calibration.created_at).strftime("%Y%m%d-%H%M%S-%f")[:-3]
    return Path(directory) / HISTORY_DIR / f"{stamp}.json"


def save_calibration(calibration: Calibration, directory: Path) -> Path:
    """Write current.json and a history copy. Returns the current.json path."""
    directory = Path(directory)
    text = json.dumps(calibration.to_dict(), indent=2)
    _write_atomic(_history_path(calibration, directory), text)
    current = directory / CURRENT_FILE
    _write_atomic(current, text)
    return current


def archive_calibration(calibration: Calibration, directory: Path) -> Path:
    """Make sure `calibration` is in the history (D39: before it is replaced). An existing history
    entry is never rewritten. Returns the history path."""
    path = _history_path(calibration, directory)
    if not path.exists():
        _write_atomic(path, json.dumps(calibration.to_dict(), indent=2))
    return path


def _load_file(path: Path) -> Calibration:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise CalibrationError(f"no calibration found at {path}; run `calibrate` first") from None
    except json.JSONDecodeError as e:
        raise CalibrationError(f"{path} is not valid JSON: {e}") from None
    return Calibration.from_dict(data)


def load_calibration(directory: Path) -> Calibration:
    return _load_file(Path(directory) / CURRENT_FILE)


def load_history(directory: Path) -> list[Calibration]:
    """All readable history entries, oldest first. Damaged entries are skipped with a warning."""
    history_dir = Path(directory) / HISTORY_DIR
    entries = []
    for path in sorted(history_dir.glob("*.json")):
        try:
            entries.append(_load_file(path))
        except CalibrationError as e:
            log.warning("skipping %s: %s", path.name, e)
    entries.sort(key=lambda c: datetime.fromisoformat(c.created_at))
    return entries
