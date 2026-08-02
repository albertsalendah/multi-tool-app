import tempfile
from pathlib import Path

from app.config import Config


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
