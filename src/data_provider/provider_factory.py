"""Provider factory for selecting data source by config."""

from config import settings
from src.data_provider.mock_provider import MockProvider
from src.data_provider.provider_types import ProviderType
from src.data_provider.yfinance_provider import YFinanceProvider


def get_data_provider():
    """根据配置返回数据源实例。"""
    provider_name = settings.DATA_PROVIDER

    if provider_name == ProviderType.YFINANCE.value:
        return YFinanceProvider()
    if provider_name == ProviderType.MOCK.value:
        return MockProvider()
    raise ValueError(f"Unsupported data provider: {provider_name}")
