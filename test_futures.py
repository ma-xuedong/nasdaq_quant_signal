"""Unit tests for futures confirmation helpers."""

import pandas as pd

from src.futures import (
    analyze_futures_trend,
    build_futures_snapshot,
    calculate_futures_return,
    calculate_gap_vs_atr,
    calculate_relative_strength,
)


def _futures_df(closes: list[float], highs: list[float] | None = None, lows: list[float] | None = None) -> pd.DataFrame:
    highs = highs or [value + 1.0 for value in closes]
    lows = lows or [value - 1.0 for value in closes]
    length = len(closes)
    return pd.DataFrame(
        {
            "date": pd.date_range("2026-01-01", periods=length, freq="h"),
            "open": closes,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": [1000.0] * length,
            "symbol": ["TEST"] * length,
        }
    )


def test_returns_and_relative_strength() -> None:
    nq_df = _futures_df([100.0, 101.0, 103.0])
    es_df = _futures_df([100.0, 100.5, 101.0])

    nq_return = calculate_futures_return(nq_df)
    es_return = calculate_futures_return(es_df)
    nq_vs_es = calculate_relative_strength(nq_return, es_return)

    assert nq_return > 0
    assert es_return > 0
    assert nq_vs_es > 0


def test_stronger_and_weaker_flags() -> None:
    stronger_snapshot = build_futures_snapshot(
        futures_data={
            "NQ=F": _futures_df([100.0, 101.0, 103.0]),
            "ES=F": _futures_df([100.0, 100.4, 100.8]),
        }
    )
    weaker_snapshot = build_futures_snapshot(
        futures_data={
            "NQ=F": _futures_df([100.0, 99.5, 99.0]),
            "ES=F": _futures_df([100.0, 100.1, 100.2]),
        }
    )

    assert stronger_snapshot["available"] is True
    assert stronger_snapshot["nq_stronger_than_es"] is True
    assert stronger_snapshot["nq_weaker_than_es"] is False

    assert weaker_snapshot["available"] is True
    assert weaker_snapshot["nq_stronger_than_es"] is False
    assert weaker_snapshot["nq_weaker_than_es"] is True


def test_empty_data_degrades_safely() -> None:
    snapshot = build_futures_snapshot(futures_data={"NQ=F": pd.DataFrame(), "ES=F": pd.DataFrame()})

    assert snapshot["available"] is False
    assert snapshot["nq_return"] == 0.0
    assert snapshot["es_return"] == 0.0
    assert snapshot["warnings"]


def test_trend_analysis_returns_up_down_mixed() -> None:
    up = analyze_futures_trend(
        _futures_df(
            [100, 101, 102, 103, 104, 105],
            highs=[101, 102, 103, 104, 105, 106],
            lows=[99, 100, 101, 102, 103, 104],
        )
    )
    down = analyze_futures_trend(
        _futures_df(
            [105, 104, 103, 102, 101, 100],
            highs=[106, 105, 104, 103, 102, 101],
            lows=[104, 103, 102, 101, 100, 99],
        )
    )
    mixed = analyze_futures_trend(
        _futures_df(
            [100, 101, 100, 102, 101, 103],
            highs=[101, 103, 102, 104, 103, 105],
            lows=[99, 100, 99.5, 100.5, 100.0, 100.2],
        )
    )

    assert up["trend"] == "up"
    assert down["trend"] == "down"
    assert mixed["trend"] == "mixed"


def test_gap_vs_atr_safe_when_missing() -> None:
    assert calculate_gap_vs_atr(0.01, None) == 0.0
    assert calculate_gap_vs_atr(0.01, 0) == 0.0
    assert calculate_gap_vs_atr(0.02, 0.01) == 2.0


def main() -> None:
    test_returns_and_relative_strength()
    test_stronger_and_weaker_flags()
    test_empty_data_degrades_safely()
    test_trend_analysis_returns_up_down_mixed()
    test_gap_vs_atr_safe_when_missing()
    print("test_futures passed")


if __name__ == "__main__":
    main()