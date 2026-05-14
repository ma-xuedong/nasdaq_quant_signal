"""Unit tests for data quality scoring."""

import pandas as pd

from src.data_quality import assess_data_quality


def _df() -> pd.DataFrame:
    return pd.DataFrame({"date": ["2026-01-01"], "close": [100.0]})


def _intraday_df() -> pd.DataFrame:
    return pd.DataFrame({"datetime": ["2026-01-01 09:35:00"], "close": [100.0]})


def test_all_good_quality() -> None:
    daily_data = {
        "QQQ": _df(),
        "SPY": _df(),
        "QQQE": _df(),
        "^VIX": _df(),
        "^VXN": _df(),
        "NQ=F": _df(),
        "ES=F": _df(),
        "NVDA": _df(),
        "MSFT": _df(),
        "AAPL": _df(),
        "AMZN": _df(),
        "META": _df(),
        "GOOGL": _df(),
        "AVGO": _df(),
        "TSLA": _df(),
    }
    cache_status = {k: {"source": "api", "is_fresh": True} for k in daily_data.keys()}
    cache_status["QQQ_intraday_5m"] = {"source": "api", "is_fresh": True}

    result = assess_data_quality(daily_data, cache_status)
    assert result["core_data_available"] is True
    assert result["quality_score"] >= 80
    assert result["quality_level"] in {"high", "medium"}
    assert result["is_realtime_usable"] is True


def test_missing_qqq_sets_core_false() -> None:
    daily_data = {"SPY": _df(), "QQQE": _df(), "^VIX": _df(), "^VXN": _df()}
    cache_status = {
        "QQQ": {"source": "missing", "is_fresh": False},
        "QQQ_intraday_5m": {"source": "missing", "is_fresh": False},
    }

    result = assess_data_quality(daily_data, cache_status)
    assert result["core_data_available"] is False
    assert "QQQ" in result["missing_symbols"]
    assert result["is_realtime_usable"] is False


def test_vxn_missing_warning() -> None:
    daily_data = {"QQQ": _df(), "SPY": _df(), "QQQE": _df(), "^VIX": _df()}
    cache_status = {
        "QQQ": {"source": "api", "is_fresh": True},
        "SPY": {"source": "api", "is_fresh": True},
        "QQQ_intraday_5m": {"source": "api", "is_fresh": True},
    }

    result = assess_data_quality(daily_data, cache_status)
    assert any("VXN" in msg for msg in result["warnings"])


def test_fallback_penalty() -> None:
    daily_data = {"QQQ": _df(), "SPY": _df(), "QQQE": _df(), "^VIX": _df(), "^VXN": _df()}
    cache_status = {
        "QQQ": {"source": "fallback_cache", "is_fresh": False},
        "SPY": {"source": "fallback_cache", "is_fresh": False},
        "QQQE": {"source": "fallback_cache", "is_fresh": False},
        "QQQ_intraday_5m": {"source": "fallback_cache", "is_fresh": False},
    }

    result = assess_data_quality(daily_data, cache_status)
    assert result["cache_fallback_count"] >= 3
    assert result["quality_score"] < 70
    assert result["confidence"] in {"low", "very_low", "medium"}
    assert result["is_realtime_usable"] is False


def test_mock_source_marks_test_mode() -> None:
    daily_data = {"QQQ": _df(), "SPY": _df(), "QQQE": _df(), "^VIX": _df(), "^VXN": _df()}
    cache_status = {
        "QQQ": {"source": "mock", "is_fresh": True, "is_test_mode": True},
        "SPY": {"source": "mock", "is_fresh": True, "is_test_mode": True},
        "QQQ_intraday_5m": {"source": "mock", "is_fresh": True, "is_test_mode": True},
    }

    result = assess_data_quality(daily_data, cache_status)
    assert result["is_test_mode"] is True
    assert result["is_realtime_usable"] is False
    assert result["quality_score"] < 50


def test_auxiliary_missing_reduces_quality_without_crash() -> None:
    daily_data = {"QQQ": _df(), "SPY": _df(), "QQQE": _df()}
    cache_status = {
        "QQQ": {"source": "api", "is_fresh": True},
        "SPY": {"source": "api", "is_fresh": True},
        "QQQE": {"source": "missing", "is_fresh": False},
        "QQQ_intraday_5m": {"source": "api", "is_fresh": True},
    }

    result = assess_data_quality(daily_data, cache_status)
    assert isinstance(result, dict)
    assert result["quality_score"] < 85


def main() -> None:
    test_all_good_quality()
    test_missing_qqq_sets_core_false()
    test_vxn_missing_warning()
    test_fallback_penalty()
    test_mock_source_marks_test_mode()
    test_auxiliary_missing_reduces_quality_without_crash()
    print("test_data_quality passed")


if __name__ == "__main__":
    main()
