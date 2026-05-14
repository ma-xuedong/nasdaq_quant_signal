"""Tests for local CSV data provider."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from config import settings
from src.data_provider.csv_provider import CSVProvider, symbol_to_csv_filename
from src.data_provider.provider_factory import get_data_provider


def _write_csv(path: Path, rows: int = 420) -> None:
    dates = pd.date_range("2023-01-01", periods=rows, freq="D")
    closes = [100 + idx * 0.1 for idx in range(rows)]
    df = pd.DataFrame(
        {
            "Date": dates,
            "Open": [value - 0.2 for value in closes],
            "High": [value + 0.5 for value in closes],
            "Low": [value - 0.5 for value in closes],
            "Close": closes,
            "Adj Close": closes,
            "Volume": [1_000_000] * rows,
        }
    )
    df.to_csv(path, index=False)


def test_symbol_to_csv_filename() -> None:
    assert symbol_to_csv_filename("QQQ") == "QQQ.csv"
    assert symbol_to_csv_filename("^VIX") == "VIX.csv"
    assert symbol_to_csv_filename("NQ=F") == "NQ_F.csv"


def test_csv_provider_reads_yahoo_format_and_standardizes_fields(tmp_path: Path) -> None:
    _write_csv(tmp_path / "QQQ.csv")
    provider = CSVProvider(data_dir=tmp_path)

    df = provider.get_daily_data("QQQ", period="2y")

    assert not df.empty
    assert list(df.columns) == ["date", "open", "high", "low", "close", "adj_close", "volume", "symbol"]
    assert df.iloc[0]["symbol"] == "QQQ"
    assert isinstance(df.iloc[0]["date"], pd.Timestamp)


def test_csv_provider_missing_file_returns_empty_dataframe(tmp_path: Path) -> None:
    provider = CSVProvider(data_dir=tmp_path)

    assert provider.get_daily_data("QQQ", period="1y").empty


def test_csv_provider_missing_columns_returns_empty_dataframe(tmp_path: Path) -> None:
    pd.DataFrame({"Date": ["2025-01-01"], "Close": [100]}).to_csv(tmp_path / "QQQ.csv", index=False)
    provider = CSVProvider(data_dir=tmp_path)

    assert provider.get_daily_data("QQQ", period="1y").empty


def test_csv_provider_period_filters_recent_year(tmp_path: Path) -> None:
    _write_csv(tmp_path / "QQQ.csv", rows=800)
    provider = CSVProvider(data_dir=tmp_path)

    df = provider.get_daily_data("QQQ", period="1y")

    assert not df.empty
    assert (df["date"].max() - df["date"].min()).days <= 365


def test_csv_provider_latest_quote(tmp_path: Path) -> None:
    _write_csv(tmp_path / "QQQ.csv", rows=10)
    provider = CSVProvider(data_dir=tmp_path)

    quote = provider.get_latest_quote("QQQ")

    assert quote["symbol"] == "QQQ"
    assert quote["source"] == "csv"
    assert quote["price"] > 0


def test_provider_factory_returns_csv_provider(tmp_path: Path) -> None:
    original_provider = settings.DATA_PROVIDER
    original_data_dir = settings.CSV_DATA_DIR
    try:
        settings.DATA_PROVIDER = "csv"
        settings.CSV_DATA_DIR = str(tmp_path)
        provider = get_data_provider()
    finally:
        settings.DATA_PROVIDER = original_provider
        settings.CSV_DATA_DIR = original_data_dir

    assert isinstance(provider, CSVProvider)


def main() -> None:
    import tempfile

    test_symbol_to_csv_filename()
    with tempfile.TemporaryDirectory() as temp_dir:
        test_csv_provider_reads_yahoo_format_and_standardizes_fields(Path(temp_dir))
    with tempfile.TemporaryDirectory() as temp_dir:
        test_csv_provider_missing_file_returns_empty_dataframe(Path(temp_dir))
    with tempfile.TemporaryDirectory() as temp_dir:
        test_csv_provider_missing_columns_returns_empty_dataframe(Path(temp_dir))
    with tempfile.TemporaryDirectory() as temp_dir:
        test_csv_provider_period_filters_recent_year(Path(temp_dir))
    with tempfile.TemporaryDirectory() as temp_dir:
        test_csv_provider_latest_quote(Path(temp_dir))
    with tempfile.TemporaryDirectory() as temp_dir:
        test_provider_factory_returns_csv_provider(Path(temp_dir))
    print("test_csv_provider passed")


if __name__ == "__main__":
    main()
