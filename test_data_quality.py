"""Unit tests for data quality scoring."""

import pandas as pd

from src.data_quality import assess_data_quality


def _df() -> pd.DataFrame:
    return pd.DataFrame({"date": ["2026-01-01"], "close": [100.0]})


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

    result = assess_data_quality(daily_data, cache_status)
    assert result["core_data_available"] is True
    assert result["quality_score"] >= 80
    assert result["quality_level"] in {"high", "medium"}


def test_missing_qqq_sets_core_false() -> None:
    daily_data = {"SPY": _df(), "QQQE": _df(), "^VIX": _df(), "^VXN": _df()}
    cache_status = {"QQQ": {"source": "missing", "is_fresh": False}}

    result = assess_data_quality(daily_data, cache_status)
    assert result["core_data_available"] is False
    assert "QQQ" in result["missing_symbols"]


def test_vxn_missing_warning() -> None:
    daily_data = {"QQQ": _df(), "SPY": _df(), "QQQE": _df(), "^VIX": _df()}
    cache_status = {"QQQ": {"source": "api", "is_fresh": True}}

    result = assess_data_quality(daily_data, cache_status)
    assert any("VXN" in msg for msg in result["warnings"])


def test_fallback_penalty() -> None:
    daily_data = {"QQQ": _df(), "SPY": _df(), "QQQE": _df(), "^VIX": _df(), "^VXN": _df()}
    cache_status = {
        "QQQ": {"source": "fallback_cache", "is_fresh": False},
        "SPY": {"source": "fallback_cache", "is_fresh": False},
        "QQQE": {"source": "fallback_cache", "is_fresh": False},
    }

    result = assess_data_quality(daily_data, cache_status)
    assert result["cache_fallback_count"] >= 3
    assert result["quality_score"] < 70
    assert result["confidence"] in {"low", "very_low", "medium"}


def main() -> None:
    test_all_good_quality()
    test_missing_qqq_sets_core_false()
    test_vxn_missing_warning()
    test_fallback_penalty()
    print("test_data_quality passed")


if __name__ == "__main__":
    main()
