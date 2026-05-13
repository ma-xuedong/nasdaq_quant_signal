"""Utility helpers for the nasdaq_quant_signal project."""

from __future__ import annotations

import logging
from typing import Any


def setup_logger(name: str = "nasdaq_quant_signal"):
    """
    Create and return a configured logger.

    The log format includes time, log level, module name, and message.
    """
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.propagate = False
    return logger


def safe_float(value: Any, default: float = 0.0) -> float:
    """
    Safely convert a value to float.

    Returns default when conversion fails.
    """
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def format_pct(value: float) -> str:
    """
    Format a decimal value as a percentage string.

    Example: 0.0123 -> '1.23%'
    """
    return f"{safe_float(value) * 100:.2f}%"
