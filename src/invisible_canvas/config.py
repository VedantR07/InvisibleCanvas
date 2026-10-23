"""Configuration: TOML file -> frozen dataclasses.

The TOML file is the single source of defaults: every key is required and unknown
keys are rejected, so a typo fails loudly instead of silently using a default.
"""

import dataclasses
import tomllib
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = REPO_ROOT / "config" / "default.toml"


class ConfigError(ValueError):
    """The configuration file is missing, malformed or inconsistent."""


@dataclass(frozen=True)
class CameraConfig:
    match: str
    index: int
    backend: str
    width: int
    height: int
    fps: int
    fourcc: str
    exposure_mode: str       # manual | auto | unchanged (camera/exposure.py)
    exposure_value: int      # manual only; 2**value seconds
    focus_mode: str          # manual | auto | unchanged (camera/locks.py)
    focus_value: int         # manual only; camera units
    gain_mode: str           # manual | auto | unchanged (camera/locks.py)
    gain_value: int          # manual only; camera units


@dataclass(frozen=True)
class ProjectorConfig:
    match: str
    expected_width: int
    expected_height: int


@dataclass(frozen=True)
class CalibrationConfig:
    target_inset: float


@dataclass(frozen=True)
class ValidationConfig:
    grid_cols: int
    grid_rows: int
    grid_inset: float
    required_mean_px: float
    required_max_px: float
    stretch_mean_px: float
    stretch_max_px: float
    repeatability_mean_px: float
    repeatability_runs: int
    auto_setup_limit_px: float      # setup check for automatic calibrations (D32)


@dataclass(frozen=True)
class SurfaceConfig:
    width_mm: float


@dataclass(frozen=True)
class PathsConfig:
    calibration: str
    reports: str


@dataclass(frozen=True)
class AIConfig:
    """Phase 3A (brain.md D51, D52, §9.11): AI on selected writing. Off unless enabled (or `draw --ai`).
    backend "local" (D52, default): a vision model in Ollama on this laptop, free; "claude": the Claude API (paid)."""
    enabled: bool
    backend: str                   # "local" | "claude"
    local_model: str               # Ollama model tag (D52)
    local_url: str                 # Ollama server
    model: str                     # Claude model (backend "claude")
    effort: str                    # output_config.effort: low | medium | high | xhigh | max
    max_tokens: int
    timeout_s: float
    fallbacks: bool                # server-side refusal fallbacks ("default", beta server-side-fallback-2026-07-01)


@dataclass(frozen=True)
class Config:
    camera: CameraConfig
    projector: ProjectorConfig
    calibration: CalibrationConfig
    validation: ValidationConfig
    surface: SurfaceConfig
    paths: PathsConfig
    ai: AIConfig
    root: Path

    @property
    def calibration_dir(self) -> Path:
        return self.root / self.paths.calibration

    @property
    def reports_dir(self) -> Path:
        return self.root / self.paths.reports


_SECTIONS = {
    "camera": CameraConfig,
    "projector": ProjectorConfig,
    "calibration": CalibrationConfig,
    "validation": ValidationConfig,
    "surface": SurfaceConfig,
    "paths": PathsConfig,
    "ai": AIConfig,
}


def _build_section(name: str, cls: type, data: object):
    if not isinstance(data, dict):
        raise ConfigError(f"[{name}] must be a table")
    expected = {f.name: f.type for f in dataclasses.fields(cls)}
    unknown = sorted(set(data) - set(expected))
    missing = sorted(set(expected) - set(data))
    if unknown:
        raise ConfigError(f"[{name}] unknown keys: {', '.join(unknown)}")
    if missing:
        raise ConfigError(f"[{name}] missing keys: {', '.join(missing)}")
    values = {}
    for key, typ in expected.items():
        value = data[key]
        if typ is float and isinstance(value, int) and not isinstance(value, bool):
            value = float(value)
        if type(value) is not typ:
            raise ConfigError(
                f"[{name}] {key} must be {typ.__name__}, got {type(value).__name__}"
            )
        values[key] = value
    return cls(**values)


def config_from_dict(data: dict, root: Path = REPO_ROOT) -> Config:
    unknown = sorted(set(data) - set(_SECTIONS))
    missing = sorted(set(_SECTIONS) - set(data))
    if unknown:
        raise ConfigError(f"unknown sections: {', '.join(unknown)}")
    if missing:
        raise ConfigError(f"missing sections: {', '.join(missing)}")
    sections = {name: _build_section(name, cls, data[name]) for name, cls in _SECTIONS.items()}
    config = Config(root=root, **sections)
    _check(config)
    return config


AI_EFFORTS = ("low", "medium", "high", "xhigh", "max")


def _check(config: Config) -> None:
    ai = config.ai
    if ai.backend not in ("local", "claude"):
        raise ConfigError('[ai] backend must be "local" or "claude"')
    if not ai.local_url.startswith(("http://", "https://")) or not ai.local_model.strip():
        raise ConfigError("[ai] local_url must be an http(s) URL and local_model must not be empty")
    if ai.effort not in AI_EFFORTS:
        raise ConfigError(f"[ai] effort must be one of {', '.join(AI_EFFORTS)}")
    if not ai.model.strip():
        raise ConfigError("[ai] model must not be empty")
    if ai.max_tokens < 1024 or ai.timeout_s <= 0:
        raise ConfigError("[ai] max_tokens must be >= 1024 and timeout_s > 0")
    if config.camera.backend not in ("dshow", "msmf", "any"):
        raise ConfigError(f"[camera] backend must be dshow, msmf or any, got {config.camera.backend!r}")
    if len(config.camera.fourcc) != 4:
        raise ConfigError(f"[camera] fourcc must be 4 characters, got {config.camera.fourcc!r}")
    if config.camera.exposure_mode not in ("manual", "auto", "unchanged"):
        raise ConfigError(
            f"[camera] exposure_mode must be manual, auto or unchanged, got {config.camera.exposure_mode!r}"
        )
    if config.camera.exposure_mode != "unchanged" and config.camera.backend != "dshow":
        raise ConfigError(
            f'[camera] exposure_mode {config.camera.exposure_mode!r} needs backend = "dshow" '
            f'(exposure is set through DirectShow); use exposure_mode = "unchanged"'
        )
    for name in ("focus", "gain"):
        mode = getattr(config.camera, f"{name}_mode")
        if mode not in ("manual", "auto", "unchanged"):
            raise ConfigError(f"[camera] {name}_mode must be manual, auto or unchanged, got {mode!r}")
        if mode != "unchanged" and config.camera.backend != "dshow":
            raise ConfigError(
                f'[camera] {name}_mode {mode!r} needs backend = "dshow" '
                f'({name} is set through DirectShow); use {name}_mode = "unchanged"'
            )
    if not 0.0 <= config.calibration.target_inset < 0.5:
        raise ConfigError("[calibration] target_inset must be in [0, 0.5)")
    if not 0.0 <= config.validation.grid_inset < 0.5:
        raise ConfigError("[validation] grid_inset must be in [0, 0.5)")
    if config.validation.grid_cols < 2 or config.validation.grid_rows < 2:
        raise ConfigError("[validation] grid_cols and grid_rows must be >= 2")
    if config.validation.repeatability_runs < 2:
        raise ConfigError("[validation] repeatability_runs must be >= 2")
    if not 0.0 < config.validation.auto_setup_limit_px <= config.validation.repeatability_mean_px:
        raise ConfigError("[validation] auto_setup_limit_px must be > 0 and not looser than repeatability_mean_px")


def load_config(path: Path | None = None) -> Config:
    path = Path(path) if path else DEFAULT_CONFIG_PATH
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except FileNotFoundError:
        raise ConfigError(f"config file not found: {path}") from None
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{path}: {e}") from None
    return config_from_dict(data, root=REPO_ROOT)


def with_overrides(config: Config, *, display: str | None = None, camera: str | None = None) -> Config:
    """Apply command-line device overrides (`--display`, `--camera`)."""
    if display is not None:
        config = dataclasses.replace(
            config, projector=dataclasses.replace(config.projector, match=display)
        )
    if camera is not None:
        config = dataclasses.replace(config, camera=dataclasses.replace(config.camera, match=camera))
    return config
