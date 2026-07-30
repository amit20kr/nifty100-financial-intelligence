"""
config_loader.py
================
Loads and strictly validates the screener configuration YAML.
"""

from typing import Any, Dict, Set
from pathlib import Path
import yaml

VALID_OPERATORS = {"min", "max", "eq"}


class ConfigValidationError(Exception):
    """Raised when the screener configuration is invalid."""

    pass


def load_screener_config(
    config_path: str | Path, available_columns: Set[str]
) -> Dict[str, Any]:
    """
    Load and validate the screener configuration YAML.

    Args:
        config_path: Path to the screener_config.yaml file.
        available_columns: The set of column names produced by the FilterEngine's base join.

    Returns:
        The validated configuration dictionary.

    Raises:
        ConfigValidationError: If the schema, types, operators, or column mappings are invalid.
        FileNotFoundError: If the config file does not exist.
    """
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    try:
        with open(path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ConfigValidationError(f"YAML parsing error: {e}")

    if not isinstance(config, dict) or "metrics" not in config:
        raise ConfigValidationError("Config must contain a 'metrics' top-level key.")

    metrics = config["metrics"]
    if not isinstance(metrics, dict):
        raise ConfigValidationError("'metrics' must be a dictionary.")

    for metric_name, criteria in metrics.items():
        if not isinstance(criteria, dict):
            raise ConfigValidationError(
                f"Criteria for '{metric_name}' must be a dictionary."
            )

        column = criteria.get("column")
        if not column:
            raise ConfigValidationError(
                f"Metric '{metric_name}' missing 'column' mapping."
            )

        if column not in available_columns:
            raise ConfigValidationError(
                f"Metric '{metric_name}' maps to column '{column}' which is not in the engine's joined column set."
            )

        operator = criteria.get("operator")
        if operator not in VALID_OPERATORS:
            raise ConfigValidationError(
                f"Metric '{metric_name}' has invalid operator '{operator}'. Must be one of {VALID_OPERATORS}."
            )

        threshold = criteria.get("default_threshold")
        if threshold is not None:
            # allow int or float
            if not isinstance(threshold, (int, float)) or isinstance(threshold, bool):
                raise ConfigValidationError(
                    f"Metric '{metric_name}' default_threshold must be numeric."
                )

    return config
