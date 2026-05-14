"""Unit tests for backtest enhancements."""

from __future__ import annotations

from unittest.mock import patch
import tempfile
from pathlib import Path

import pandas as pd

from src.backtest import (
    analyze_quality_buckets,
    analyze_score_buckets,
    calculate_backtest_metrics,
    generate_score_history,
    generate_trade_signals,
    simulate_trades,
)
from src.database import init_backtest_tables, load_backtest_trades, save_backtest_trades


def _price_frame(symbol: str, start: str = "2025-01-01", periods: int = 210, slope: float = 1.0) -> pd.DataFrame:
    dates = pd.date_range(start, periods=periods, freq="D")
    closes = [100 + slope * idx for idx in range(periods)]
    return pd.DataFrame(
        {
            "date": dates,
            "open": [value + 0.5 for value in closes],
            "high": [value + 1.0 for value in closes],
            "low": [value - 1.0 for value in closes],
            "close": closes,
            "adj_close": closes,
            "volume": [1_000_000] * periods,
            "symbol": [symbol] * periods,
        }
    )


def _historical_data() -> dict[str, pd.DataFrame]:
    return {
        "QQQ": _price_frame("QQQ", slope=1.0),
        "SPY": _price_frame("SPY", slope=0.8),
        "QQQE": _price_frame("QQQE", slope=1.1),
        "TQQQ": _price_frame("TQQQ", slope=1.4),
        "SQQQ": _price_frame("SQQQ", slope=-0.6),
        "NVDA": _price_frame("NVDA", slope=1.6),
        "MSFT": _price_frame("MSFT", slope=1.0),
        "AAPL": _price_frame("AAPL", slope=0.9),
        "AMZN": _price_frame("AMZN", slope=1.2),
    }


def test_generate_score_history_avoids_future_data() -> None:
    observed_max_dates: list[pd.Timestamp] = []

    def fake_snapshot(historical_slice: dict[str, pd.DataFrame]) -> dict:
        observed_max_dates.append(historical_slice["QQQ"]["date"].max())
        return {
            "qqq": {"price": 100, "ma20": 99, "ma50": 98, "ma200": 97, "atr14": 2, "daily_return": 0.01, "volume_ratio": 1.0},
            "relative_strength": {"qqq_vs_spy": 0.02, "qqqe_vs_qqq": 0.01},
            "mega_cap_tech": {"status": "strong", "strong_count": 4, "available_count": 4},
            "intraday": {},
        }

    with patch("src.backtest._build_indicator_snapshot", side_effect=fake_snapshot), patch(
        "src.backtest.calculate_tqqq_score", return_value={"base_score": 80}
    ), patch("src.backtest.calculate_sqqq_score", return_value={"base_score": 40}), patch(
        "src.backtest.get_risk_deduction", return_value={"deduction": 5, "events": []}
    ), patch(
        "src.backtest.assess_data_quality", return_value={"quality_level": "high", "quality_score": 90}
    ):
        score_df = generate_score_history(_historical_data())

    assert not score_df.empty
    for score_date, observed in zip(score_df["date"], observed_max_dates):
        assert observed <= score_date


def test_generate_trade_signals_includes_quality_level() -> None:
    score_df = pd.DataFrame(
        [
            {"date": pd.Timestamp("2025-08-01"), "tqqq_score": 80, "sqqq_score": 40, "data_quality_level": "high", "market_state": "只观察 TQQQ"},
            {"date": pd.Timestamp("2025-08-02"), "tqqq_score": 30, "sqqq_score": 90, "data_quality_level": "medium", "market_state": "只观察 SQQQ"},
        ]
    )

    signals_df = generate_trade_signals(score_df)

    assert list(signals_df["signal"]) == ["BUY_TQQQ", "BUY_SQQQ"]
    assert list(signals_df["data_quality_level"]) == ["high", "medium"]


def test_simulate_trades_uses_next_open_and_next_close() -> None:
    signals_df = pd.DataFrame(
        [{"date": pd.Timestamp("2025-01-01"), "signal": "BUY_TQQQ", "tqqq_score": 80, "sqqq_score": 40, "data_quality_level": "high", "market_state": "只观察 TQQQ"}]
    )
    price_data = {
        "TQQQ": pd.DataFrame(
            {
                "date": pd.to_datetime(["2025-01-01", "2025-01-02", "2025-01-03", "2025-01-04"]),
                "open": [10.0, 11.0, 12.0, 13.0],
                "high": [10.5, 11.5, 12.5, 13.5],
                "low": [9.5, 10.5, 11.5, 12.5],
                "close": [10.2, 11.8, 12.8, 13.2],
                "adj_close": [10.2, 11.8, 12.8, 13.2],
                "volume": [1000, 1000, 1000, 1000],
            }
        )
    }

    trades_open = simulate_trades(signals_df, price_data, execution_mode="close_to_next_open")
    trades_close = simulate_trades(signals_df, price_data, execution_mode="close_to_next_close")

    assert float(trades_open.iloc[0]["entry_price"]) == 11.0
    assert float(trades_close.iloc[0]["entry_price"]) == 11.8


def test_simulate_trades_distinguishes_tqqq_and_sqqq() -> None:
    signals_df = pd.DataFrame(
        [
            {"date": pd.Timestamp("2025-01-01"), "signal": "BUY_TQQQ", "tqqq_score": 82, "sqqq_score": 40, "data_quality_level": "high", "market_state": "只观察 TQQQ"},
            {"date": pd.Timestamp("2025-01-05"), "signal": "BUY_SQQQ", "tqqq_score": 40, "sqqq_score": 90, "data_quality_level": "low", "market_state": "只观察 SQQQ"},
        ]
    )
    price_data = {
        "TQQQ": _price_frame("TQQQ", periods=10, slope=1.0),
        "SQQQ": _price_frame("SQQQ", periods=10, slope=-1.0),
    }

    trades_df = simulate_trades(signals_df, price_data)

    assert set(trades_df["symbol"]) == {"TQQQ", "SQQQ"}
    assert set(trades_df["data_quality_level"]) == {"high", "low"}


def test_calculate_backtest_metrics_and_bucket_analysis() -> None:
    trades_df = pd.DataFrame(
        [
            {"entry_date": pd.Timestamp("2025-01-02"), "exit_date": pd.Timestamp("2025-01-03"), "symbol": "TQQQ", "entry_price": 10, "exit_price": 11, "return_pct": 0.10, "exit_reason": "TakeProfit", "holding_days": 2, "signal_score": 86, "data_quality_level": "high", "execution_mode": "close_to_next_open"},
            {"entry_date": pd.Timestamp("2025-01-04"), "exit_date": pd.Timestamp("2025-01-05"), "symbol": "SQQQ", "entry_price": 20, "exit_price": 18, "return_pct": -0.10, "exit_reason": "StopLoss", "holding_days": 2, "signal_score": 78, "data_quality_level": "medium", "execution_mode": "close_to_next_open"},
            {"entry_date": pd.Timestamp("2025-01-06"), "exit_date": pd.Timestamp("2025-01-07"), "symbol": "TQQQ", "entry_price": 30, "exit_price": 31.5, "return_pct": 0.05, "exit_reason": "TimeOut", "holding_days": 2, "signal_score": 72, "data_quality_level": "high", "execution_mode": "close_to_next_open"},
        ]
    )

    metrics = calculate_backtest_metrics(trades_df)
    score_bucket_df = analyze_score_buckets(trades_df)
    quality_bucket_df = analyze_quality_buckets(trades_df)

    assert metrics["total_trades"] == 3
    assert metrics["win_rate"] > 0
    assert metrics["profit_factor"] > 0
    assert metrics["max_drawdown"] <= 0
    assert metrics["max_consecutive_losses"] >= 1
    assert metrics["tqqq_trade_count"] == 2
    assert metrics["sqqq_trade_count"] == 1
    assert not score_bucket_df.empty
    assert not quality_bucket_df.empty


def test_empty_trades_do_not_crash() -> None:
    empty_trades = pd.DataFrame()
    metrics = calculate_backtest_metrics(empty_trades)
    score_bucket_df = analyze_score_buckets(empty_trades)
    quality_bucket_df = analyze_quality_buckets(empty_trades)

    assert metrics["total_trades"] == 0
    assert score_bucket_df.empty
    assert quality_bucket_df.empty


def test_backtest_trade_storage_fields_roundtrip() -> None:
    trades_df = pd.DataFrame(
        [
            {
                "entry_date": "2025-01-02",
                "exit_date": "2025-01-03",
                "symbol": "TQQQ",
                "entry_price": 10.0,
                "exit_price": 10.5,
                "return_pct": 0.05,
                "exit_reason": "TimeOut",
                "holding_days": 2,
                "signal_score": 88,
                "data_quality_level": "high",
                "execution_mode": "close_to_next_open",
            }
        ]
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = str(Path(temp_dir) / "backtest.db")
        init_backtest_tables(db_path)
        saved = save_backtest_trades(trades_df, db_path=db_path)
        loaded = load_backtest_trades(limit=10, db_path=db_path)

    assert saved == 1
    assert not loaded.empty
    assert "signal_score" in loaded.columns
    assert "data_quality_level" in loaded.columns
    assert "execution_mode" in loaded.columns
    assert loaded.iloc[0]["data_quality_level"] == "high"
    assert loaded.iloc[0]["execution_mode"] == "close_to_next_open"


def main() -> None:
    test_generate_score_history_avoids_future_data()
    test_generate_trade_signals_includes_quality_level()
    test_simulate_trades_uses_next_open_and_next_close()
    test_simulate_trades_distinguishes_tqqq_and_sqqq()
    test_calculate_backtest_metrics_and_bucket_analysis()
    test_empty_trades_do_not_crash()
    test_backtest_trade_storage_fields_roundtrip()
    print("test_backtest passed")


if __name__ == "__main__":
    main()