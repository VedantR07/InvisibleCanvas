import copy
import tomllib

import pytest

from invisible_canvas.config import (
    DEFAULT_CONFIG_PATH,
    ConfigError,
    config_from_dict,
    load_config,
    with_overrides,
)


@pytest.fixture
def data():
    with open(DEFAULT_CONFIG_PATH, "rb") as f:
        return copy.deepcopy(tomllib.load(f))


def test_default_config_loads():
    config = load_config()
    assert config.camera.match == "brio"
    assert (config.projector.expected_width, config.projector.expected_height) == (1280, 720)
    assert config.validation.required_mean_px == 5.0
    assert config.validation.required_max_px == 12.0
    assert config.validation.repeatability_mean_px == 2.0


def test_unknown_key_is_rejected(data):
    data["camera"]["widht"] = 1920
    with pytest.raises(ConfigError, match="unknown keys: widht"):
        config_from_dict(data)


def test_missing_key_is_rejected(data):
    del data["camera"]["fps"]
    with pytest.raises(ConfigError, match="missing keys: fps"):
        config_from_dict(data)


def test_missing_section_is_rejected(data):
    del data["surface"]
    with pytest.raises(ConfigError, match="missing sections: surface"):
        config_from_dict(data)


def test_wrong_type_is_rejected(data):
    data["camera"]["width"] = "1920"
    with pytest.raises(ConfigError, match="width must be int"):
        config_from_dict(data)


def test_bool_is_not_accepted_as_int(data):
    data["camera"]["index"] = True
    with pytest.raises(ConfigError):
        config_from_dict(data)


def test_int_is_accepted_for_float(data):
    data["surface"]["width_mm"] = 1300
    assert config_from_dict(data).surface.width_mm == 1300.0


def test_invalid_backend_is_rejected(data):
    data["camera"]["backend"] = "v4l2"
    with pytest.raises(ConfigError, match="backend"):
        config_from_dict(data)


def test_paths_resolve_against_root(data, tmp_path):
    config = config_from_dict(data, root=tmp_path)
    assert config.calibration_dir == tmp_path / "data" / "calibration"
    assert config.reports_dir == tmp_path / "data" / "reports"


def test_overrides_replace_only_given_values():
    config = load_config()
    changed = with_overrides(config, display="WZATCO")
    assert changed.projector.match == "WZATCO"
    assert changed.camera.match == config.camera.match
    assert with_overrides(config, camera="acer").camera.match == "acer"
