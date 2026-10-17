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


def test_default_exposure_is_manual_minus_5():
    camera = load_config().camera
    assert (camera.backend, camera.fourcc, camera.width, camera.height, camera.fps) == ("dshow", "MJPG", 1920, 1080, 30)
    assert (camera.exposure_mode, camera.exposure_value) == ("manual", -5)


def test_invalid_exposure_mode_is_rejected(data):
    data["camera"]["exposure_mode"] = "off"
    with pytest.raises(ConfigError, match="exposure_mode must be manual, auto or unchanged"):
        config_from_dict(data)


@pytest.mark.parametrize("mode", ["manual", "auto"])
def test_exposure_control_needs_dshow(data, mode):
    data["camera"]["backend"] = "msmf"
    data["camera"]["exposure_mode"] = mode
    with pytest.raises(ConfigError, match='needs backend = "dshow"'):
        config_from_dict(data)


def test_unchanged_exposure_works_with_any_backend(data):
    data["camera"]["backend"] = "msmf"
    data["camera"]["exposure_mode"] = "unchanged"
    assert config_from_dict(data).camera.exposure_mode == "unchanged"


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


def test_auto_setup_limit_is_never_looser_than_the_manual_limit(data):
    data["validation"]["auto_setup_limit_px"] = data["validation"]["repeatability_mean_px"] + 0.5
    with pytest.raises(ConfigError, match="auto_setup_limit_px"):
        config_from_dict(data)
    data["validation"]["auto_setup_limit_px"] = 0.0
    with pytest.raises(ConfigError, match="auto_setup_limit_px"):
        config_from_dict(data)


def test_setup_limit_depends_on_how_the_calibration_was_made():
    from types import SimpleNamespace

    from invisible_canvas.tools.validate import setup_limit
    config = load_config()
    v = config.validation
    assert setup_limit(config, SimpleNamespace(method="auto")) == v.auto_setup_limit_px
    assert setup_limit(config, SimpleNamespace(method="manual")) == v.repeatability_mean_px == 2.0
