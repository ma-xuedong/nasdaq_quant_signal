"""Unit tests for unified signal pipeline."""

from unittest.mock import patch

import pandas as pd

from src.pipeline import run_signal_pipeline
from src.scoring import calculate_sqqq_score, calculate_tqqq_score
from src.snapshot_builder import build_scoring_snapshot


def _sample_daily(symbol: str = "QQQ") -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.date_range("2025-01-01", periods=260, freq="D"),
            "open": [100.0] * 260,
            "high": [101.0] * 260,
            "low": [99.0] * 260,
            "close": [100.0 + i * 0.1 for i in range(260)],
            "adj_close": [100.0 + i * 0.1 for i in range(260)],
            "volume": [1_000_000.0] * 260,
            "symbol": [symbol] * 260,
        }
    )


def _sample_intraday(symbol: str = "QQQ") -> pd.DataFrame:
    return pd.DataFrame(
        {
            "datetime": pd.date_range("2025-01-01 09:30", periods=20, freq="5min"),
            "open": [100.0] * 20,
            "high": [101.0] * 20,
            "low": [99.0] * 20,
            "close": [100.0] * 20,
            "volume": [100000.0] * 20,
            "symbol": [symbol] * 20,
        }
    )


def _score_result(base_score: float) -> dict:
    return {"base_score": base_score, "reasons": [], "warnings": []}


def test_pipeline_success() -> None:
    def fake_daily(symbol: str, **kwargs):
        return _sample_daily(symbol), {"source": "api", "is_fresh": True, "is_fallback": False}

    def fake_intraday(symbol: str, **kwargs):
        return _sample_intraday(symbol), {"source": "api", "is_fresh": True, "is_fallback": False}

    with patch("src.pipeline.get_daily_data_with_cache", side_effect=fake_daily), patch(
        "src.pipeline.get_intraday_data_with_cache", side_effect=fake_intraday
    ), patch("src.pipeline.sleep_between_requests", return_value=None), patch(
        "src.pipeline.calculate_tqqq_score", return_value=_score_result(95)
    ), patch("src.pipeline.calculate_sqqq_score", return_value=_score_result(20)), patch(
        "src.pipeline.get_risk_deduction", return_value={"deduction": 0, "reasons": []}
    ):
        result = run_signal_pipeline(save_to_db=False, use_cache=True)

    assert result["success"] is True
    assert result["is_realtime_usable"] is True
    assert result["is_test_mode"] is False
    assert "futures_snapshot" in result
    assert "breadth_snapshot" in result
    assert "event_risk_snapshot" in result
    assert result["event_risk_snapshot"]["available"] is True
    for key in [
        "indicator_snapshot",
        "tqqq_result",
        "sqqq_result",
        "risk_result",
        "final_scores",
        "market_state",
        "data_quality",
        "data_source_status",
        "warnings",
    ]:
        assert key in result


def test_pipeline_snapshot_contains_unified_scoring_fields() -> None:
    market_data = {
        "daily_data": {
            "QQQ": _sample_daily("QQQ"),
            "SPY": _sample_daily("SPY"),
            "QQQE": _sample_daily("QQQE"),
            "TQQQ": _sample_daily("TQQQ"),
            "SQQQ": _sample_daily("SQQQ"),
            "NQ=F": _sample_daily("NQ=F"),
            "ES=F": _sample_daily("ES=F"),
            "NVDA": _sample_daily("NVDA"),
            "MSFT": _sample_daily("MSFT"),
            "AAPL": _sample_daily("AAPL"),
            "AMZN": _sample_daily("AMZN"),
            "META": _sample_daily("META"),
            "GOOGL": _sample_daily("GOOGL"),
            "AVGO": _sample_daily("AVGO"),
            "TSLA": _sample_daily("TSLA"),
        },
        "intraday_data": {"QQQ": _sample_intraday("QQQ")},
    }

    snapshot = build_scoring_snapshot(market_data, current_date=pd.Timestamp("2025-09-17"), mode="live")

    assert "ma20_slope" in snapshot["qqq"]
    assert "ma50_slope" in snapshot["qqq"]
    assert "up_count" in snapshot["mega_cap_tech"]
    assert "down_count" in snapshot["mega_cap_tech"]
    assert "strong_count" in snapshot["mega_cap_tech"]
    assert "available_count" in snapshot["mega_cap_tech"]


def test_pipeline_and_backtest_like_snapshot_scores_match_on_same_data() -> None:
    market_data = {
        "daily_data": {
            "QQQ": _sample_daily("QQQ"),
            "SPY": _sample_daily("SPY"),
            "QQQE": _sample_daily("QQQE"),
            "TQQQ": _sample_daily("TQQQ"),
            "SQQQ": _sample_daily("SQQQ"),
            "NQ=F": _sample_daily("NQ=F"),
            "ES=F": _sample_daily("ES=F"),
            "NVDA": _sample_daily("NVDA"),
            "MSFT": _sample_daily("MSFT"),
            "AAPL": _sample_daily("AAPL"),
            "AMZN": _sample_daily("AMZN"),
            "META": _sample_daily("META"),
            "GOOGL": _sample_daily("GOOGL"),
            "AVGO": _sample_daily("AVGO"),
            "TSLA": _sample_daily("TSLA"),
        },
        "intraday_data": {"QQQ": _sample_intraday("QQQ")},
    }
    current_date = pd.Timestamp("2025-09-17")

    live_snapshot = build_scoring_snapshot(market_data, current_date=current_date, mode="live")
    backtest_snapshot = build_scoring_snapshot(market_data, current_date=current_date, mode="backtest")

    assert calculate_tqqq_score(live_snapshot)["base_score"] == calculate_tqqq_score(backtest_snapshot)["base_score"]
    assert calculate_sqqq_score(live_snapshot)["base_score"] == calculate_sqqq_score(backtest_snapshot)["base_score"]


def test_pipeline_fallback_cache_degrades_signal() -> None:
    def fake_daily(symbol: str, **kwargs):
        if symbol == "QQQ":
            return _sample_daily(symbol), {"source": "fallback_cache", "is_fresh": False, "is_fallback": True}
        return _sample_daily(symbol), {"source": "api", "is_fresh": True, "is_fallback": False}

    def fake_intraday(symbol: str, **kwargs):
        return _sample_intraday(symbol), {"source": "fallback_cache", "is_fresh": False, "is_fallback": True}

    with patch("src.pipeline.get_daily_data_with_cache", side_effect=fake_daily), patch(
        "src.pipeline.get_intraday_data_with_cache", side_effect=fake_intraday
    ), patch("src.pipeline.sleep_between_requests", return_value=None), patch(
        "src.pipeline.calculate_tqqq_score", return_value=_score_result(95)
    ), patch("src.pipeline.calculate_sqqq_score", return_value=_score_result(10)), patch(
        "src.pipeline.get_risk_deduction", return_value={"deduction": 0, "reasons": []}
    ):
        result = run_signal_pipeline(save_to_db=False, use_cache=True)

    assert result["success"] is True
    assert result["is_realtime_usable"] is False
    assert result["final_scores"]["tqqq_final_score"] < 75
    assert "fallback_cache" in result["summary"]


def test_pipeline_futures_and_breadth_degrade_without_crash() -> None:
    def fake_daily(symbol: str, **kwargs):
        if symbol in {"NQ=F", "ES=F", "AAPL", "MSFT", "NVDA", "AMZN"}:
            return pd.DataFrame(), {"source": "missing", "is_fresh": False, "is_fallback": False}
        return _sample_daily(symbol), {"source": "api", "is_fresh": True, "is_fallback": False}

    def fake_intraday(symbol: str, **kwargs):
        return _sample_intraday(symbol), {"source": "api", "is_fresh": True, "is_fallback": False}

    with patch("src.pipeline.get_daily_data_with_cache", side_effect=fake_daily), patch(
        "src.pipeline.get_intraday_data_with_cache", side_effect=fake_intraday
    ), patch("src.pipeline.sleep_between_requests", return_value=None):
        result = run_signal_pipeline(save_to_db=False, use_cache=True)

    assert result["success"] is True
    assert result["futures_snapshot"]["available"] is False
    assert result["breadth_snapshot"]["available"] is False
    assert result["data_quality"]["quality_score"] < 100


def test_pipeline_fail_when_qqq_missing() -> None:
    def fake_daily(symbol: str, **kwargs):
        if symbol == "QQQ":
            return pd.DataFrame(), {"source": "missing", "is_fresh": False, "is_fallback": False}
        return _sample_daily(symbol), {"source": "api", "is_fresh": True, "is_fallback": False}

    def fake_intraday(symbol: str, **kwargs):
        return pd.DataFrame(), {"source": "missing", "is_fresh": False, "is_fallback": False}

    with patch("src.pipeline.get_daily_data_with_cache", side_effect=fake_daily), patch(
        "src.pipeline.get_intraday_data_with_cache", side_effect=fake_intraday
    ), patch("src.pipeline.sleep_between_requests", return_value=None):
        result = run_signal_pipeline(save_to_db=False, use_cache=True)

    assert result["success"] is False


def test_pipeline_mock_mode_blocks_real_signal() -> None:
    def fake_daily(symbol: str, **kwargs):
        return _sample_daily(symbol), {"source": "mock", "is_fresh": True, "is_fallback": False, "is_test_mode": True}

    def fake_intraday(symbol: str, **kwargs):
        return _sample_intraday(symbol), {"source": "mock", "is_fresh": True, "is_fallback": False, "is_test_mode": True}

    with patch("src.pipeline.get_daily_data_with_cache", side_effect=fake_daily), patch(
        "src.pipeline.get_intraday_data_with_cache", side_effect=fake_intraday
    ), patch("src.pipeline.sleep_between_requests", return_value=None), patch(
        "src.pipeline.calculate_tqqq_score", return_value=_score_result(95)
    ), patch("src.pipeline.calculate_sqqq_score", return_value=_score_result(10)), patch(
        "src.pipeline.get_risk_deduction", return_value={"deduction": 0, "reasons": []}
    ):
        result = run_signal_pipeline(save_to_db=False, use_cache=True)

    assert result["success"] is True
    assert result["is_test_mode"] is True
    assert result["final_scores"]["tqqq_final_score"] < 60
    assert "测试" in result["summary"]


def main() -> None:
    test_pipeline_success()
    test_pipeline_snapshot_contains_unified_scoring_fields()
    test_pipeline_and_backtest_like_snapshot_scores_match_on_same_data()
    test_pipeline_fallback_cache_degrades_signal()
    test_pipeline_futures_and_breadth_degrade_without_crash()
    test_pipeline_fail_when_qqq_missing()
    test_pipeline_mock_mode_blocks_real_signal()
    print("test_pipeline passed")


if __name__ == "__main__":
    main()
