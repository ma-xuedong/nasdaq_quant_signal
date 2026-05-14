"""Tests for the unified scoring snapshot builder."""

from __future__ import annotations

import pandas as pd

from src.scoring import calculate_sqqq_score, calculate_tqqq_score
from src.snapshot_builder import build_scoring_snapshot


def _daily_frame(symbol: str, start: str = "2025-01-01", periods: int = 260, slope: float = 0.5) -> pd.DataFrame:
    dates = pd.date_range(start, periods=periods, freq="D")
    closes = [100 + slope * idx for idx in range(periods)]
    return pd.DataFrame(
        {
            "date": dates,
            "open": [value - 0.3 for value in closes],
            "high": [value + 0.8 for value in closes],
            "low": [value - 0.8 for value in closes],
            "close": closes,
            "adj_close": closes,
            "volume": [1_000_000 + idx * 1000 for idx in range(periods)],
            "symbol": [symbol] * periods,
        }
    )


def _intraday_frame(symbol: str = "QQQ") -> pd.DataFrame:
    return pd.DataFrame(
        {
            "datetime": pd.date_range("2025-09-17 09:30", periods=12, freq="5min"),
            "open": [120.0 + idx * 0.1 for idx in range(12)],
            "high": [120.4 + idx * 0.1 for idx in range(12)],
            "low": [119.8 + idx * 0.1 for idx in range(12)],
            "close": [120.2 + idx * 0.1 for idx in range(12)],
            "volume": [100_000] * 12,
            "symbol": [symbol] * 12,
        }
    )


def _market_data() -> dict:
    daily_data = {
        "QQQ": _daily_frame("QQQ", slope=0.6),
        "SPY": _daily_frame("SPY", slope=0.3),
        "QQQE": _daily_frame("QQQE", slope=0.7),
        "TQQQ": _daily_frame("TQQQ", slope=0.9),
        "SQQQ": _daily_frame("SQQQ", slope=-0.4),
        "NQ=F": _daily_frame("NQ=F", slope=0.55),
        "ES=F": _daily_frame("ES=F", slope=0.25),
        "MNQ=F": _daily_frame("MNQ=F", slope=0.54),
        "MES=F": _daily_frame("MES=F", slope=0.24),
        "^VIX": _daily_frame("^VIX", slope=0.05),
        "^VXN": _daily_frame("^VXN", slope=0.08),
        "NVDA": _daily_frame("NVDA", slope=1.1),
        "MSFT": _daily_frame("MSFT", slope=0.7),
        "AAPL": _daily_frame("AAPL", slope=0.5),
        "AMZN": _daily_frame("AMZN", slope=0.6),
        "META": _daily_frame("META", slope=0.65),
        "GOOGL": _daily_frame("GOOGL", slope=0.55),
        "AVGO": _daily_frame("AVGO", slope=0.75),
        "TSLA": _daily_frame("TSLA", slope=0.9),
    }
    return {
        "daily_data": daily_data,
        "intraday_data": {"QQQ": _intraday_frame("QQQ")},
    }


def test_live_like_and_backtest_snapshot_share_same_structure() -> None:
    market_data = _market_data()
    current_date = pd.Timestamp("2025-09-17")

    live_like_snapshot = build_scoring_snapshot(market_data, current_date=current_date, mode="live")
    backtest_snapshot = build_scoring_snapshot(market_data, current_date=current_date, mode="backtest")

    for snapshot in [live_like_snapshot, backtest_snapshot]:
        assert "qqq" in snapshot
        assert "relative_strength" in snapshot
        assert "volatility" in snapshot
        assert "mega_cap_tech" in snapshot
        assert "futures_snapshot" in snapshot
        assert "breadth_snapshot" in snapshot
        assert "event_risk_snapshot" in snapshot
        assert "data_quality" in snapshot
        for field in ["close", "ma20", "ma50", "ma200", "ma20_slope", "ma50_slope", "atr14", "atr_pct"]:
            assert field in snapshot["qqq"]
        for field in ["up_count", "down_count", "strong_count", "available_count", "total_count", "warnings"]:
            assert field in snapshot["mega_cap_tech"]

    assert live_like_snapshot["qqq"].keys() == backtest_snapshot["qqq"].keys()
    assert live_like_snapshot["mega_cap_tech"].keys() == backtest_snapshot["mega_cap_tech"].keys()
    assert live_like_snapshot["futures_snapshot"].keys() == backtest_snapshot["futures_snapshot"].keys()
    assert live_like_snapshot["breadth_snapshot"].keys() == backtest_snapshot["breadth_snapshot"].keys()


def test_same_snapshot_produces_same_scores() -> None:
    snapshot = build_scoring_snapshot(_market_data(), current_date=pd.Timestamp("2025-09-17"), mode="live")

    tqqq_result_first = calculate_tqqq_score(snapshot)
    tqqq_result_second = calculate_tqqq_score(snapshot)
    sqqq_result_first = calculate_sqqq_score(snapshot)
    sqqq_result_second = calculate_sqqq_score(snapshot)

    assert tqqq_result_first["base_score"] == tqqq_result_second["base_score"]
    assert sqqq_result_first["base_score"] == sqqq_result_second["base_score"]


def test_snapshot_builder_degrades_without_optional_modules() -> None:
    market_data = {
        "daily_data": {
            "QQQ": _daily_frame("QQQ", periods=240, slope=0.4),
            "SPY": _daily_frame("SPY", periods=240, slope=0.2),
            "QQQE": _daily_frame("QQQE", periods=240, slope=0.3),
        },
        "intraday_data": {},
    }

    snapshot = build_scoring_snapshot(market_data, current_date=pd.Timestamp("2025-08-28"), mode="backtest")

    assert snapshot["futures_snapshot"]["available"] is False
    assert snapshot["breadth_snapshot"]["available"] is False
    assert snapshot["event_risk_snapshot"]["available"] is True
    assert isinstance(snapshot["futures_snapshot"].get("warnings", []), list)
    assert isinstance(snapshot["breadth_snapshot"].get("warnings", []), list)


def main() -> None:
    test_live_like_and_backtest_snapshot_share_same_structure()
    test_same_snapshot_produces_same_scores()
    test_snapshot_builder_degrades_without_optional_modules()
    print("test_snapshot_builder passed")


if __name__ == "__main__":
    main()