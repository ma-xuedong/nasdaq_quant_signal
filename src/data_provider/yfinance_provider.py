"""YFinance-based data provider implementation."""

from __future__ import annotations

from typing import Any

import pandas as pd
import yfinance as yf

from src.data_provider.base_provider import BaseDataProvider
from src.rate_limiter import retry_on_failure, sleep_between_requests
from src.utils import setup_logger

logger = setup_logger("yfinance_provider")


def normalize_ohlcv_dataframe(
    df: pd.DataFrame,
    symbol: str,
    is_intraday: bool = False,
) -> pd.DataFrame:
    """标准化 yfinance 返回字段到统一小写结构。"""
    if df is None or df.empty:
        return pd.DataFrame()

    normalized = df.copy()
    normalized = normalized.reset_index(drop=False)
    normalized.columns = [str(col).strip().lower().replace(" ", "_") for col in normalized.columns]

    if "adj_close" not in normalized.columns and "adjclose" in normalized.columns:
        normalized = normalized.rename(columns={"adjclose": "adj_close"})

    if is_intraday:
        if "datetime" not in normalized.columns:
            if "date" in normalized.columns:
                normalized = normalized.rename(columns={"date": "datetime"})
            elif "index" in normalized.columns:
                normalized = normalized.rename(columns={"index": "datetime"})
        if "datetime" in normalized.columns:
            normalized["datetime"] = pd.to_datetime(normalized["datetime"], errors="coerce")
    else:
        if "date" not in normalized.columns:
            if "datetime" in normalized.columns:
                normalized = normalized.rename(columns={"datetime": "date"})
            elif "index" in normalized.columns:
                normalized = normalized.rename(columns={"index": "date"})
        if "date" in normalized.columns:
            normalized["date"] = pd.to_datetime(normalized["date"], errors="coerce")

    normalized["symbol"] = symbol

    if is_intraday:
        required_columns = ["datetime", "open", "high", "low", "close", "volume", "symbol"]
    else:
        required_columns = ["date", "open", "high", "low", "close", "volume", "symbol"]

    for col in required_columns:
        if col not in normalized.columns:
            normalized[col] = pd.NA

    sort_col = "datetime" if is_intraday else "date"
    normalized = normalized.sort_values(sort_col).reset_index(drop=True)

    keep_cols = required_columns.copy()
    if not is_intraday:
        if "adj_close" not in normalized.columns:
            normalized["adj_close"] = pd.NA
        keep_cols.insert(5, "adj_close")

    return normalized[keep_cols]


class YFinanceProvider(BaseDataProvider):
    """YFinance provider with retry and throttling."""

    @retry_on_failure(max_retries=2, delay_seconds=1.5)
    def _fetch_history(self, symbol: str, period: str, interval: str | None = None) -> pd.DataFrame:
        sleep_between_requests(0.8)
        ticker = yf.Ticker(symbol)
        if interval:
            return ticker.history(period=period, interval=interval)
        return ticker.history(period=period)

    def get_daily_data(self, symbol: str, period: str = "1y") -> pd.DataFrame:
        try:
            logger.info("抓取日线数据: %s, period=%s", symbol, period)
            df = self._fetch_history(symbol=symbol, period=period)
            if df is None or df.empty:
                logger.warning("日线数据为空: %s", symbol)
                return pd.DataFrame()
            return normalize_ohlcv_dataframe(df, symbol=symbol, is_intraday=False)
        except Exception as exc:
            logger.error("抓取日线失败: %s, error=%s", symbol, str(exc))
            return pd.DataFrame()

    def get_intraday_data(
        self,
        symbol: str,
        interval: str = "5m",
        period: str = "5d",
    ) -> pd.DataFrame:
        try:
            logger.info("抓取分钟线数据: %s, interval=%s, period=%s", symbol, interval, period)
            df = self._fetch_history(symbol=symbol, period=period, interval=interval)
            if df is None or df.empty:
                logger.warning("分钟线数据为空: %s", symbol)
                return pd.DataFrame()
            return normalize_ohlcv_dataframe(df, symbol=symbol, is_intraday=True)
        except Exception as exc:
            logger.error("抓取分钟线失败: %s, error=%s", symbol, str(exc))
            return pd.DataFrame()

    def get_latest_quote(self, symbol: str) -> dict[str, Any]:
        sleep_between_requests(0.6)
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            price = info.get("currentPrice") or info.get("regularMarketPrice")
            previous_close = info.get("previousClose") or info.get("regularMarketPreviousClose")
            if price is None:
                return {"symbol": symbol, "price": None, "error": "无法获取最新价格"}
            change = price - previous_close if previous_close else None
            change_pct = (change / previous_close) if previous_close and previous_close != 0 else None
            return {
                "symbol": symbol,
                "price": price,
                "previous_close": previous_close,
                "change": change,
                "change_pct": change_pct,
                "source": self.get_provider_name(),
            }
        except Exception as exc:
            logger.error("抓取最新报价失败: %s, error=%s", symbol, str(exc))
            return {"symbol": symbol, "price": None, "error": str(exc)}

    def get_provider_name(self) -> str:
        return "yfinance"
