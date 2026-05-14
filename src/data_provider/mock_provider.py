"""Mock market data provider for development-only testing."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd

from src.data_provider.base_provider import BaseDataProvider


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MockProvider(BaseDataProvider):
    """Synthetic provider used only in explicit mock test mode."""

    def is_test_mode(self) -> bool:
        return True

    def get_daily_data(self, symbol: str, period: str = "1y") -> pd.DataFrame:
        end = _utc_now().replace(hour=0, minute=0, second=0, microsecond=0)
        dates = pd.date_range(end=end, periods=260, freq="B", tz="UTC")
        base = 100.0 + (abs(hash(symbol)) % 25)
        closes = [base + idx * 0.15 for idx in range(len(dates))]
        return pd.DataFrame(
            {
                "date": dates.tz_convert(None),
                "open": closes,
                "high": [value + 1.0 for value in closes],
                "low": [value - 1.0 for value in closes],
                "close": closes,
                "adj_close": closes,
                "volume": [1_000_000.0] * len(dates),
                "symbol": [symbol] * len(dates),
            }
        )

    def get_intraday_data(
        self,
        symbol: str,
        interval: str = "5m",
        period: str = "5d",
    ) -> pd.DataFrame:
        end = _utc_now().replace(second=0, microsecond=0)
        times = pd.date_range(end=end, periods=24, freq="5min", tz="UTC")
        base = 100.0 + (abs(hash(symbol)) % 25)
        closes = [base + idx * 0.05 for idx in range(len(times))]
        return pd.DataFrame(
            {
                "datetime": times.tz_convert(None),
                "open": closes,
                "high": [value + 0.3 for value in closes],
                "low": [value - 0.3 for value in closes],
                "close": closes,
                "volume": [100_000.0] * len(times),
                "symbol": [symbol] * len(times),
            }
        )

    def get_latest_quote(self, symbol: str) -> dict[str, Any]:
        price = 100.0 + (abs(hash(symbol)) % 25)
        return {
            "symbol": symbol,
            "price": price,
            "previous_close": price - 1.0,
            "change": 1.0,
            "change_pct": 0.01,
            "source": self.get_provider_name(),
            "timestamp": (_utc_now() - timedelta(minutes=1)).isoformat(),
        }

    def get_provider_name(self) -> str:
        return "mock"