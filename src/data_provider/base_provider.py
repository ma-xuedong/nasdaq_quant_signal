"""Base interface for market data providers."""

from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd


class BaseDataProvider(ABC):
    """行情数据源抽象基类。"""

    @abstractmethod
    def get_daily_data(self, symbol: str, period: str = "1y") -> pd.DataFrame:
        """获取日线行情。"""
        raise NotImplementedError

    @abstractmethod
    def get_intraday_data(
        self,
        symbol: str,
        interval: str = "5m",
        period: str = "5d",
    ) -> pd.DataFrame:
        """获取分钟线行情。"""
        raise NotImplementedError

    @abstractmethod
    def get_latest_quote(self, symbol: str) -> dict:
        """获取最新报价。"""
        raise NotImplementedError

    @abstractmethod
    def get_provider_name(self) -> str:
        """返回数据源名称。"""
        raise NotImplementedError
