"""Unit tests for mock provider restrictions and behavior."""

from unittest.mock import patch

from config import settings
from src.data_provider.mock_provider import MockProvider
from src.data_provider.provider_factory import get_data_provider


def test_mock_provider_basic_behavior() -> None:
    provider = MockProvider()
    assert provider.is_test_mode() is True
    assert provider.get_provider_name() == "mock"
    assert not provider.get_daily_data("QQQ").empty
    assert not provider.get_intraday_data("QQQ").empty


def test_factory_returns_mock_only_when_enabled() -> None:
    with patch.object(settings, "DATA_PROVIDER", "mock"):
        provider = get_data_provider()
    assert isinstance(provider, MockProvider)
    assert provider.is_test_mode() is True


def main() -> None:
    test_mock_provider_basic_behavior()
    test_factory_returns_mock_only_when_enabled()
    print("test_mock_provider passed")


if __name__ == "__main__":
    main()