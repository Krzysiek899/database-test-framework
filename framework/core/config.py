"""
Configuration loader – reads and validates config.yaml.
"""

from __future__ import annotations

import os
from typing import Any, Dict

import yaml


def load_config(path: str = "config.yaml") -> Dict[str, Any]:
    """Load the YAML configuration file and return a dict.

    Raises FileNotFoundError if the file does not exist.
    """
    path = os.path.abspath(path)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Config file not found: {path}")
    with open(path, "r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    _validate(cfg)
    return cfg


def _validate(cfg: Dict[str, Any]) -> None:
    """Minimal structural validation."""
    if "engines" not in cfg or not cfg["engines"]:
        raise ValueError("config.yaml must define at least one engine under 'engines'.")
    for name, eng in cfg["engines"].items():
        for key in ("engine_type", "image", "port", "host_port"):
            if key not in eng:
                raise ValueError(
                    f"Engine '{name}' is missing required field '{key}'."
                )

