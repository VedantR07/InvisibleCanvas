"""Helpers shared by the command-line tools."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from ..config import Config


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def stamp() -> str:
    """Filesystem-safe local timestamp, e.g. 20261008-201503."""
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def save_report(config: Config, name: str, data: dict) -> Path:
    """Write `data` as JSON to <reports>/<name>-<stamp>.json and return the path."""
    config.reports_dir.mkdir(parents=True, exist_ok=True)
    path = config.reports_dir / f"{name}-{stamp()}.json"
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    return path
