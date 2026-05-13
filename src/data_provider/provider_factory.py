"""Provider factory for selecting data source by config."""

from config.settings import DATA_PROVIDER
from src.data_provider.provider_types import ProviderType
from src.data_provider.yfinance_provider import YFinanceProvider


def get_data_provider():
    """根据配置返回数据源实例。"""
    if DATA_PROVIDER == ProviderType.YFINANCE.value:
        return YFinanceProvider()
    raise ValueError(f"Unsupported data provider: {DATA_PROVIDER}")
