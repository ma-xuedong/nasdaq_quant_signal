"""Tests for Tiingo historical EOD provider."""

from __future__ import annotations

import os
from unittest.mock import patch

import pandas as pd

from config import settings
from src.data_provider.provider_factory import get_data_provider
from src.data_provider.tiingo_provider import TiingoProvider


class FakeResponse:
    def __init__(self, status_code: int = 200, payload=None) -> None:
        self.status_code = status_code
        self.payload = payload if payload is not None else []

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        return self.response


def _tiingo_payload() -> list[dict]:
    return [
        {
            "date": "2025-01-02T00:00:00.000Z",
            "open": 100.0,
            "high": 102.0,
            "low": 99.0,
            "close": 101.0,
            "adjClose": 101.0,
            "volume": 1_000_000,
        },
        {
            "date": "2025-01-03T00:00:00.000Z",
            "open": 101.0,
            "high": 103.0,
            "low": 100.0,
            "close": 102.0,
            "adjClose": 102.0,
            "volume": 1_100_000,
        },
    ]


def test_tiingo_provider_standardizes_daily_fields() -> None:
    session = FakeSession(FakeResponse(payload=_tiingo_payload()))
    provider = TiingoProvider(api_key="test-key", session=session)

    df = provider.get_daily_data("QQQ", period="1y")

    assert list(df.columns) == ["date", "open", "high", "low", "close", "adj_close", "volume", "symbol"]
    assert len(df) == 2
    assert df.iloc[0]["symbol"] == "QQQ"
    assert float(df.iloc[0]["adj_close"]) == 101.0
    assert isinstance(df.iloc[0]["date"], pd.Timestamp)
    assert session.calls[0]["params"]["token"] == "test-key"
    assert "startDate" in session.calls[0]["params"]
    assert "endDate" in session.calls[0]["params"]


def test_tiingo_provider_without_api_key_returns_empty_dataframe() -> None:
    provider = TiingoProvider(api_key="", session=FakeSession(FakeResponse(payload=_tiingo_payload())))

    df = provider.get_daily_data("QQQ", period="1y")

    assert df.empty


def test_tiingo_provider_http_error_returns_empty_dataframe() -> None:
    provider = TiingoProvider(api_key="test-key", session=FakeSession(FakeResponse(status_code=500)))

    df = provider.get_daily_data("QQQ", period="1y")

    assert df.empty


def test_tiingo_provider_unsupported_symbols_return_empty_dataframe() -> None:
    provider = TiingoProvider(api_key="test-key", session=FakeSession(FakeResponse(payload=_tiingo_payload())))

    assert provider.get_daily_data("^VIX", period="1y").empty
    assert provider.get_daily_data("NQ=F", period="1y").empty


def test_provider_factory_returns_tiingo_provider() -> None:
    original_provider = settings.DATA_PROVIDER
    try:
        settings.DATA_PROVIDER = "tiingo"
        with patch.dict(os.environ, {"TIINGO_API_KEY": "test-key"}):
            provider = get_data_provider()
    finally:
        settings.DATA_PROVIDER = original_provider

    assert isinstance(provider, TiingoProvider)


def main() -> None:
    test_tiingo_provider_standardizes_daily_fields()
    test_tiingo_provider_without_api_key_returns_empty_dataframe()
    test_tiingo_provider_http_error_returns_empty_dataframe()
    test_tiingo_provider_unsupported_symbols_return_empty_dataframe()
    test_provider_factory_returns_tiingo_provider()
    print("test_tiingo_provider passed")


if __name__ == "__main__":
    main()
