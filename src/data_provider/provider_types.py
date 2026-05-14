"""Data provider type definitions."""

from enum import Enum


class ProviderType(str, Enum):
    """Supported provider names."""

    YFINANCE = "yfinance"
    FINNHUB = "finnhub"
    TIINGO = "tiingo"
    POLYGON = "polygon"
    IBKR = "ibkr"
    MOCK = "mock"
