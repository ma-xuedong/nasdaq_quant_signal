"""Local CSV historical daily data provider."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from config import settings
from src.data_provider.base_provider import BaseDataProvider
from src.utils import setup_logger

logger = setup_logger("csv_provider")


DAILY_COLUMNS = ["date", "open", "high", "low", "close", "adj_close", "volume", "symbol"]
PERIOD_DAYS = {
    "1y": 365,
    "2y": 365 * 2,
    "3y": 365 * 3,
    "5y": 365 * 5,
}


def symbol_to_csv_filename(symbol: str) -> str:
    """Convert a market symbol to a safe CSV filename."""
    safe_symbol = str(symbol).strip()
    if safe_symbol.startswith("^"):
        safe_symbol = safe_symbol[1:]
    safe_symbol = safe_symbol.replace("=", "_")
    safe_symbol = safe_symbol.replace("/", "_")
    safe_symbol = safe_symbol.replace("\\", "_")
    return f"{safe_symbol}.csv"


def _normalize_csv_columns(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    normalized = df.copy()
    normalized.columns = [str(column).strip().lower().replace(" ", "_") for column in normalized.columns]
    if "adj_close" not in normalized.columns and "adjclose" in normalized.columns:
        normalized = normalized.rename(columns={"adjclose": "adj_close"})

    required_columns = ["date", "open", "high", "low", "close", "adj_close", "volume"]
    missing_columns = [column for column in required_columns if column not in normalized.columns]
    if missing_columns:
        logger.warning("CSV data missing columns for %s: %s", symbol, ", ".join(missing_columns))
        return pd.DataFrame()

    normalized["date"] = pd.to_datetime(normalized["date"], errors="coerce")
    normalized = normalized.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
    if normalized.empty:
        logger.warning("CSV data has no valid dates for %s", symbol)
        return pd.DataFrame()

    for column in ["open", "high", "low", "close", "adj_close", "volume"]:
        normalized[column] = pd.to_numeric(normalized[column], errors="coerce")

    normalized["symbol"] = symbol
    return normalized[DAILY_COLUMNS]


def _filter_period(df: pd.DataFrame, period: str) -> pd.DataFrame:
    if df.empty or "date" not in df.columns:
        return pd.DataFrame()
    days = PERIOD_DAYS.get(period, PERIOD_DAYS["1y"])
    latest_date = pd.to_datetime(df["date"], errors="coerce").max()
    if pd.isna(latest_date):
        return pd.DataFrame()
    start_date = latest_date - pd.Timedelta(days=days)
    return df[df["date"] >= start_date].reset_index(drop=True)


class CSVProvider(BaseDataProvider):
    """Provider for local daily OHLCV CSV files."""

    def __init__(self, data_dir: str | Path | None = None) -> None:
        self.data_dir = Path(data_dir or getattr(settings, "CSV_DATA_DIR", "data/raw"))

    def get_daily_data(self, symbol: str, period: str = "1y") -> pd.DataFrame:
        csv_path = self.data_dir / symbol_to_csv_filename(symbol)
        if not csv_path.exists():
            logger.warning("CSV file missing for %s: %s", symbol, str(csv_path))
            return pd.DataFrame()

        try:
            raw_df = pd.read_csv(csv_path)
            normalized = _normalize_csv_columns(raw_df, symbol)
            return _filter_period(normalized, period)
        except Exception as exc:
            logger.warning("CSV daily data read failed for %s: %s", symbol, str(exc))
            return pd.DataFrame()

    def get_intraday_data(
        self,
        symbol: str,
        interval: str = "5m",
        period: str = "5d",
    ) -> pd.DataFrame:
        del symbol, interval, period
        logger.warning("CSVProvider does not implement intraday data")
        return pd.DataFrame()

    def get_latest_quote(self, symbol: str) -> dict[str, Any]:
        df = self.get_daily_data(symbol, period="5y")
        if df.empty:
            return {}
        latest = df.iloc[-1]
        return {
            "symbol": symbol,
            "price": float(latest["close"]),
            "source": self.get_provider_name(),
            "is_test_mode": False,
        }

    def get_provider_name(self) -> str:
        return "csv"
