import pytest
from src.screener.config_loader import load_screener_config, ConfigValidationError


def test_config_loader_valid(tmp_path):
    yaml_content = """
metrics:
  sales:
    column: sales
    operator: min
    default_threshold: 5000
    """
    config_file = tmp_path / "valid_config.yaml"
    config_file.write_text(yaml_content)

    available = {"sales", "net_profit"}
    config = load_screener_config(config_file, available)

    assert "metrics" in config
    assert config["metrics"]["sales"]["column"] == "sales"
    assert config["metrics"]["sales"]["operator"] == "min"
    assert config["metrics"]["sales"]["default_threshold"] == 5000


def test_config_loader_missing_column(tmp_path):
    yaml_content = """
metrics:
  sales:
    column: sales
    operator: min
    default_threshold: 5000
    """
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml_content)

    available = {"net_profit"}  # 'sales' is missing
    with pytest.raises(
        ConfigValidationError,
        match="maps to column 'sales' which is not in the engine's joined column set",
    ):
        load_screener_config(config_file, available)


def test_config_loader_invalid_operator(tmp_path):
    yaml_content = """
metrics:
  sales:
    column: sales
    operator: invalid_op
    default_threshold: 5000
    """
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml_content)

    available = {"sales"}
    with pytest.raises(ConfigValidationError, match="invalid operator"):
        load_screener_config(config_file, available)


def test_config_loader_invalid_threshold_type(tmp_path):
    yaml_content = """
metrics:
  sales:
    column: sales
    operator: min
    default_threshold: "5000"
    """
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml_content)

    available = {"sales"}
    with pytest.raises(
        ConfigValidationError, match="default_threshold must be numeric"
    ):
        load_screener_config(config_file, available)


def test_config_loader_file_not_found():
    with pytest.raises(FileNotFoundError):
        load_screener_config("nonexistent.yaml", set())
