"""Unit tests for cache module."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pandas as pd

from src.cache import (
    build_cache_key,
    get_daily_data_with_cache,
    get_cached_daily_data,
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
    def get_daily_data(self, symbol: str, period: str = "1y") -> pd.DataFrame:
        return pd.DataFrame(
            {
                "date": pd.date_range("2026-01-01", periods=3, freq="D"),
                "open": [100.0, 101.0, 102.0],
                "high": [101.0, 102.0, 103.0],
                "low": [99.0, 100.0, 101.0],
                "close": [100.5, 101.5, 102.5],
                "adj_close": [100.5, 101.5, 102.5],
                "volume": [1_000_000.0, 1_000_000.0, 1_000_000.0],
                "symbol": [symbol, symbol, symbol],
            }
        )


def test_build_cache_key() -> None:
    key = build_cache_key("QQQ", "daily", period="1y")
    assert key == "QQQ_daily_1y"


def test_cache_metadata_fresh_and_expired() -> None:
    init_database(TEST_DB)
    init_cache_metadata_table(TEST_DB)

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


def test_fallback_cache_when_api_fails() -> None:
    init_database(TEST_DB)
    init_cache_metadata_table(TEST_DB)

    symbol = "QQQ"
    df = pd.DataFrame(
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
    save_daily_prices(symbol, df, db_path=TEST_DB)

    key = build_cache_key(symbol, "daily", period="1y")
    past = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    update_cache_metadata(
        cache_key=key,
        symbol=symbol,
        data_type="daily",
        provider="fake",
        row_count=2,
        expires_at=past,
        status="expired",
        db_path=TEST_DB,
    )

    with patch("src.cache.get_data_provider", return_value=_FakeProviderFail()):
        out_df, meta = get_daily_data_with_cache(symbol=symbol, period="1y", db_path=TEST_DB)

    assert not out_df.empty
    assert meta["source"] == "fallback_cache"


def test_empty_when_no_cache_and_api_fail() -> None:
    init_database(TEST_DB)
    init_cache_metadata_table(TEST_DB)

    with patch("src.cache.get_data_provider", return_value=_FakeProviderFail()):
        out_df, meta = get_daily_data_with_cache(symbol="ZZZ", period="1y", db_path=TEST_DB)

    assert out_df.empty
    assert meta["source"] in {"none", "missing"}


def main() -> None:
    test_build_cache_key()
    test_cache_metadata_fresh_and_expired()
    test_fallback_cache_when_api_fails()
    test_empty_when_no_cache_and_api_fail()
    print("test_cache passed")


if __name__ == "__main__":
    main()
