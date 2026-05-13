"""Unit tests for cache freshness and fallback flow."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pandas as pd

from src.cache import (
    build_cache_key,
    get_daily_data_with_cache,
    get_cache_metadata,
    init_cache_metadata_table,
    is_cache_fresh,
    update_cache_metadata,
)
from src.database import init_database, save_daily_prices

TEST_DB = "data/test_cache.db"


class _FakeProviderFail:
    def get_provider_name(self) -> str:
        return "fake"

    def get_daily_data(self, symbol: str, period: str = "1y") -> pd.DataFrame:
        return pd.DataFrame()

    def get_intraday_data(self, symbol: str, interval: str = "5m", period: str = "5d") -> pd.DataFrame:
        return pd.DataFrame()

    def get_latest_quote(self, symbol: str) -> dict:
        return {"symbol": symbol, "price": None}


class _FakeProviderOk(_FakeProviderFail):
    def __init__(self) -> None:
        self.call_count = 0

    def get_daily_data(self, symbol: str, period: str = "1y") -> pd.DataFrame:
        self.call_count += 1
        return pd.DataFrame(
            {
                "date": pd.date_range("2026-02-01", periods=3, freq="D"),
                "open": [200.0, 201.0, 202.0],
                "high": [201.0, 202.0, 203.0],
                "low": [199.0, 200.0, 201.0],
                "close": [200.5, 201.5, 202.5],
                "adj_close": [200.5, 201.5, 202.5],
                "volume": [2_000_000.0, 2_000_000.0, 2_000_000.0],
                "symbol": [symbol, symbol, symbol],
            }
        )


def _sample_cached_df(symbol: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.date_range("2026-01-01", periods=2, freq="D"),
            "open": [100.0, 101.0],
            "high": [101.0, 102.0],
            "low": [99.0, 100.0],
            "close": [100.5, 101.5],
            "adj_close": [100.5, 101.5],
            "volume": [1_000_000.0, 1_000_000.0],
            "symbol": [symbol, symbol],
        }
    )


def _prepare_db() -> None:
    init_database(TEST_DB)
    init_cache_metadata_table(TEST_DB)


def test_build_cache_key() -> None:
    key = build_cache_key("QQQ", "daily", period="1y")
    assert key == "QQQ_daily_1y"


def test_cache_metadata_fresh_and_expired() -> None:
    _prepare_db()

    key = build_cache_key("QQQ", "daily", period="1y")
    future = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
    past = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()

    update_cache_metadata(
        cache_key=key,
        symbol="QQQ",
        data_type="daily",
        provider="fake",
        row_count=1,
        expires_at=future,
        status="fresh",
        db_path=TEST_DB,
    )
    assert is_cache_fresh(key, TEST_DB) is True

    update_cache_metadata(
        cache_key=key,
        symbol="QQQ",
        data_type="daily",
        provider="fake",
        row_count=1,
        expires_at=past,
        status="expired",
        db_path=TEST_DB,
    )
    assert is_cache_fresh(key, TEST_DB) is False


def test_fresh_cache_should_not_call_api() -> None:
    _prepare_db()

    symbol = "QQQ"
    key = build_cache_key(symbol, "daily", period="1y")
    save_daily_prices(symbol, _sample_cached_df(symbol), db_path=TEST_DB)
    update_cache_metadata(
        cache_key=key,
        symbol=symbol,
        data_type="daily",
        provider="fake",
        row_count=2,
        expires_at=(datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
        status="fresh",
        db_path=TEST_DB,
    )

    provider = _FakeProviderOk()
    out_df, meta = get_daily_data_with_cache(symbol=symbol, period="1y", provider=provider, db_path=TEST_DB)

    assert provider.call_count == 0
    assert not out_df.empty
    assert meta["source"] == "cache"
    assert meta["is_fresh"] is True
    assert meta["is_fallback"] is False


def test_expired_cache_api_success_updates_metadata() -> None:
    _prepare_db()

    symbol = "SPY"
    key = build_cache_key(symbol, "daily", period="1y")
    save_daily_prices(symbol, _sample_cached_df(symbol), db_path=TEST_DB)
    update_cache_metadata(
        cache_key=key,
        symbol=symbol,
        data_type="daily",
        provider="fake",
        row_count=2,
        expires_at=(datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat(),
        status="expired",
        db_path=TEST_DB,
    )

    provider = _FakeProviderOk()
    out_df, meta = get_daily_data_with_cache(symbol=symbol, period="1y", provider=provider, db_path=TEST_DB)

    assert provider.call_count == 1
    assert not out_df.empty
    assert meta["source"] == "api"

    stored = get_cache_metadata(key, db_path=TEST_DB)
    assert stored.get("status") == "fresh"


def test_expired_cache_api_fail_with_fallback() -> None:
    _prepare_db()

    symbol = "QQQE"
    key = build_cache_key(symbol, "daily", period="1y")
    save_daily_prices(symbol, _sample_cached_df(symbol), db_path=TEST_DB)
    update_cache_metadata(
        cache_key=key,
        symbol=symbol,
        data_type="daily",
        provider="fake",
        row_count=2,
        expires_at=(datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat(),
        status="expired",
        db_path=TEST_DB,
    )

    with patch("src.cache.get_data_provider", return_value=_FakeProviderFail()):
        out_df, meta = get_daily_data_with_cache(symbol=symbol, period="1y", db_path=TEST_DB)

    assert not out_df.empty
    assert meta["source"] == "fallback_cache"
    assert meta["is_fresh"] is False
    assert meta["is_fallback"] is True


def test_expired_cache_api_fail_without_fallback() -> None:
    _prepare_db()

    symbol = "ZZZ"
    key = build_cache_key(symbol, "daily", period="1y")
    update_cache_metadata(
        cache_key=key,
        symbol=symbol,
        data_type="daily",
        provider="fake",
        row_count=0,
        expires_at=(datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat(),
        status="expired",
        db_path=TEST_DB,
    )

    with patch("src.cache.get_data_provider", return_value=_FakeProviderFail()):
        out_df, meta = get_daily_data_with_cache(symbol=symbol, period="1y", db_path=TEST_DB)

    assert out_df.empty
    assert meta["source"] == "missing"
    assert meta["is_fresh"] is False
    assert meta["is_fallback"] is False


def main() -> None:
    test_build_cache_key()
    test_cache_metadata_fresh_and_expired()
    test_fresh_cache_should_not_call_api()
    test_expired_cache_api_success_updates_metadata()
    test_expired_cache_api_fail_with_fallback()
    test_expired_cache_api_fail_without_fallback()
    print("test_cache passed")


if __name__ == "__main__":
    main()
