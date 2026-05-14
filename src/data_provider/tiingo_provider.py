"""Tiingo EOD data provider implementation."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd
import requests

from config import settings
from src.data_provider.base_provider import BaseDataProvider
from src.utils import setup_logger

logger = setup_logger("tiingo_provider")


TIINGO_EOD_URL = "https://api.tiingo.com/tiingo/daily/{symbol}/prices"
SUPPORTED_PERIOD_DAYS = {
    "1y": 365,
    "2y": 365 * 2,
    "3y": 365 * 3,
    "5y": 365 * 5,
}
UNSUPPORTED_TIINGO_SYMBOLS = {"^VIX", "^VXN", "NQ=F", "ES=F", "MNQ=F", "MES=F"}
DAILY_COLUMNS = ["date", "open", "high", "low", "close", "adj_close", "volume", "symbol"]


def period_to_start_date(period: str, end_date: datetime | None = None) -> str:
    reference = end_date or datetime.now(timezone.utc)
    days = SUPPORTED_PERIOD_DAYS.get(period, SUPPORTED_PERIOD_DAYS["1y"])
    start = reference - timedelta(days=days)
    return start.strftime("%Y-%m-%d")


def _period_to_dates(period: str, now: datetime | None = None) -> tuple[str, str]:
    reference = now or datetime.now(timezone.utc)
    return period_to_start_date(period, end_date=reference), reference.strftime("%Y-%m-%d")


def normalize_tiingo_eod_dataframe(data: Any, symbol: str) -> pd.DataFrame:
    """Normalize Tiingo EOD JSON rows to the project OHLCV schema."""
    if not isinstance(data, list) or not data:
        return pd.DataFrame()

    df = pd.DataFrame(data)
    if df.empty:
        return pd.DataFrame()

    df = df.rename(
        columns={
            "adjClose": "adj_close",
            "adjOpen": "adj_open",
            "adjHigh": "adj_high",
            "adjLow": "adj_low",
            "adjVolume": "adj_volume",
        }
    )
    if "date" not in df.columns:
        return pd.DataFrame()

    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.tz_localize(None)
    df["symbol"] = symbol

    if "adj_close" not in df.columns and "close" in df.columns:
        df["adj_close"] = df["close"]
    if "volume" not in df.columns and "adj_volume" in df.columns:
        df["volume"] = df["adj_volume"]

    for column in ["open", "high", "low", "close", "adj_close", "volume"]:
        if column not in df.columns:
            df[column] = pd.NA

    df = df.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
    return df[DAILY_COLUMNS]


class TiingoProvider(BaseDataProvider):
    """Tiingo provider for historical daily EOD data."""

    def __init__(self, api_key: str | None = None, session: requests.Session | None = None, timeout: int = 20) -> None:
        configured_key = getattr(settings, "TIINGO_API_KEY", "") or os.getenv("TIINGO_API_KEY", "")
        self.api_key = api_key if api_key is not None else configured_key.strip()
        self.session = session or requests.Session()
        self.timeout = timeout

    def get_daily_data(self, symbol: str, period: str = "1y") -> pd.DataFrame:
        if not self.api_key:
            logger.warning("TIINGO_API_KEY is missing; cannot fetch %s", symbol)
            return pd.DataFrame()

        if symbol in UNSUPPORTED_TIINGO_SYMBOLS:
            logger.warning("Tiingo EOD does not support symbol %s in this provider", symbol)
            return pd.DataFrame()

        start_date, end_date = _period_to_dates(period)
        url = TIINGO_EOD_URL.format(symbol=symbol)
        params = {
            "startDate": start_date,
            "endDate": end_date,
            "format": "json",
            "token": self.api_key,
        }

        try:
            response = self.session.get(url, params=params, timeout=self.timeout)
            if response.status_code >= 400:
                logger.warning("Tiingo HTTP error for %s: status=%s", symbol, response.status_code)
                return pd.DataFrame()
            data = response.json()
            normalized = normalize_tiingo_eod_dataframe(data, symbol)
            if normalized.empty:
                logger.warning("Tiingo daily data is empty for %s", symbol)
            return normalized
        except Exception as exc:
            logger.warning("Tiingo daily data fetch failed for %s: %s", symbol, str(exc))
            return pd.DataFrame()

    def get_intraday_data(
        self,
        symbol: str,
        interval: str = "5m",
        period: str = "5d",
    ) -> pd.DataFrame:
        del symbol, interval, period
        logger.warning("TiingoProvider does not implement intraday data")
        return pd.DataFrame()

    def get_latest_quote(self, symbol: str) -> dict[str, Any]:
        return {"symbol": symbol, "price": None, "error": "TiingoProvider does not implement latest quotes"}

    def get_provider_name(self) -> str:
        return "tiingo"
