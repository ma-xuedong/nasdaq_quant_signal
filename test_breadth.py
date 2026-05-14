"""Unit tests for Nasdaq-100 breadth helpers."""

import pandas as pd

from config.nasdaq100_symbols import NASDAQ100_SYMBOLS
from src.breadth import (
    build_breadth_snapshot,
    calculate_ma_position,
    calculate_symbol_return,
)


def _symbol_df(closes: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.date_range("2026-01-01", periods=len(closes), freq="D"),
            "open": closes,
            "high": [value + 1 for value in closes],
            "low": [value - 1 for value in closes],
            "close": closes,
            "volume": [1000.0] * len(closes),
            "symbol": ["TEST"] * len(closes),
        }
    )


def test_calculate_symbol_return() -> None:
    result = calculate_symbol_return(_symbol_df([100.0, 102.0]))
    assert result is not None
    assert result > 0


def test_calculate_ma_position() -> None:
    df = _symbol_df(list(range(1, 251)))
    result = calculate_ma_position(df)
    assert result["above_ma20"] is True
    assert result["above_ma50"] is True
    assert result["above_ma200"] is True


def test_strong_breadth_status() -> None:
    symbol_data = {symbol: _symbol_df([100.0, 101.0, 102.0]) for symbol in NASDAQ100_SYMBOLS}
    snapshot = build_breadth_snapshot(symbol_data=symbol_data, min_required_symbols=20)

    assert snapshot["breadth_status"] == "strong"


def test_weak_breadth_status() -> None:
    symbol_data = {symbol: _symbol_df([102.0, 101.0, 100.0]) for symbol in NASDAQ100_SYMBOLS}
    snapshot = build_breadth_snapshot(symbol_data=symbol_data, min_required_symbols=20)

    assert snapshot["breadth_status"] == "weak"


def test_insufficient_when_available_too_low() -> None:
    symbol_data = {"AAPL": _symbol_df([100.0, 101.0]), "MSFT": _symbol_df([100.0, 99.0])}
    snapshot = build_breadth_snapshot(symbol_data=symbol_data, min_required_symbols=5)

    assert snapshot["breadth_status"] == "insufficient"
    assert snapshot["available"] is False


def test_ratios_and_missing_data_safe() -> None:
    symbol_data = {
        "AAPL": _symbol_df([100.0, 101.0, 102.0]),
        "MSFT": _symbol_df([100.0, 99.0, 98.0]),
        "NVDA": pd.DataFrame(),
    }
    snapshot = build_breadth_snapshot(symbol_data=symbol_data, min_required_symbols=2)

    assert snapshot["up_count"] == 1
    assert snapshot["down_count"] == 1
    assert snapshot["up_ratio"] == 0.5
    assert snapshot["down_ratio"] == 0.5
    assert snapshot["above_ma20_ratio"] >= 0.0
    assert snapshot["above_ma50_ratio"] >= 0.0
    assert isinstance(snapshot["missing_symbols"], list)


def main() -> None:
    test_calculate_symbol_return()
    test_calculate_ma_position()
    test_strong_breadth_status()
    test_weak_breadth_status()
    test_insufficient_when_available_too_low()
    test_ratios_and_missing_data_safe()
    print("test_breadth passed")


if __name__ == "__main__":
    main()