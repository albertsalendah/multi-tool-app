import os
import tempfile
from pathlib import Path

from app.config import Config


def _set_env(key, value):
    old = os.environ.get(key)
    os.environ[key] = value
    return old


def _restore_env(key, old):
    if old is None:
        os.environ.pop(key, None)
    else:
        os.environ[key] = old


def test_env_override_coerces_to_int_when_default_is_int():
    old = _set_env("JOBS_MAX_WORKERS", "8")
    try:
        config = Config(config_file="/nonexistent/path/does-not-exist.yaml")
        value = config.get("jobs.max_workers", 4)
        assert value == 8
        assert isinstance(value, int)
    finally:
        _restore_env("JOBS_MAX_WORKERS", old)


def test_env_override_coerces_to_bool_when_default_is_bool():
    old = _set_env("BROWSER_HEADLESS", "false")
    try:
        config = Config(config_file="/nonexistent/path/does-not-exist.yaml")
        assert config.get("browser.headless", True) is False
    finally:
        _restore_env("BROWSER_HEADLESS", old)


def test_env_override_bool_true_variants_are_recognized():
    for raw in ("true", "1", "yes", "on", "TRUE"):
        old = _set_env("BROWSER_HEADLESS", raw)
        try:
            config = Config(config_file="/nonexistent/path/does-not-exist.yaml")
            assert config.get("browser.headless", False) is True
        finally:
            _restore_env("BROWSER_HEADLESS", old)


def test_env_override_invalid_int_falls_back_to_default_without_crashing():
    old = _set_env("JOBS_MAX_WORKERS", "not-a-number")
    try:
        config = Config(config_file="/nonexistent/path/does-not-exist.yaml")
        assert config.get("jobs.max_workers", 4) == 4
    finally:
        _restore_env("JOBS_MAX_WORKERS", old)


def test_env_override_coerces_to_float_when_default_is_float():
    old = _set_env("SOME_RATIO", "0.75")
    try:
        config = Config(config_file="/nonexistent/path/does-not-exist.yaml")
        assert config.get("some.ratio", 1.0) == 0.75
    finally:
        _restore_env("SOME_RATIO", old)


def test_env_override_without_typed_default_returns_raw_string():
    old = _set_env("APP_NAME", "Overridden")
    try:
        config = Config(config_file="/nonexistent/path/does-not-exist.yaml")
        assert config.get("app.name") == "Overridden"
    finally:
        _restore_env("APP_NAME", old)


def test_missing_config_file_falls_back_to_defaults_without_crashing():
    config = Config(config_file="/nonexistent/path/does-not-exist.yaml")

    assert config.get("app.name", "fallback") == "fallback"
    assert config.get("anything.at.all") is None


def test_malformed_yaml_falls_back_to_defaults_without_crashing():
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False
    ) as f:
        f.write("app:\n  name: [unclosed list\n")  # invalid YAML
        path = f.name

    try:
        config = Config(config_file=path)
        assert config.get("app.name", "fallback") == "fallback"
    finally:
        Path(path).unlink()


def test_valid_config_file_loads_normally():
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False
    ) as f:
        f.write("app:\n  name: Test App\n  debug: true\n")
        path = f.name

    try:
        config = Config(config_file=path)
        assert config.get("app.name") == "Test App"
        assert config.get("app.debug") is True
        assert config.get("app.missing_key", "default") == "default"
    finally:
        Path(path).unlink()


def test_empty_yaml_file_falls_back_to_defaults():
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False
    ) as f:
        f.write("")  # yaml.safe_load returns None for an empty file
        path = f.name

    try:
        config = Config(config_file=path)
        assert config.get("app.name", "fallback") == "fallback"
    finally:
        Path(path).unlink()


def test_dotted_key_lookup_stops_gracefully_on_non_dict_intermediate():
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False
    ) as f:
        f.write("app: not_a_dict\n")
        path = f.name

    try:
        config = Config(config_file=path)
        # app.name would need `app` to be a dict - it's a string here.
        assert config.get("app.name", "fallback") == "fallback"
    finally:
        Path(path).unlink()
