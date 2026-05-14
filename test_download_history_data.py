"""Tests for historical daily data downloader."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts.download_history_data import (
    OUTPUT_COLUMNS,
    download_history_data,
)
from src.data_provider.csv_provider import symbol_to_csv_filename


class FakeResponse:
    def __init__(self, status_code: int = 200, payload=None, text: str = "") -> None:
        self.status_code = status_code
        self.payload = payload if payload is not None else []
        self.text = text

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, responses: dict[str, FakeResponse] | None = None, default: FakeResponse | None = None) -> None:
        self.responses = responses or {}
        self.default = default or FakeResponse(status_code=404)
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        symbol = params.get("s") if params and "s" in params else url.rstrip("/").split("/")[-2]
        return self.responses.get(symbol, self.default)


def _tiingo_payload(close: float = 101.0) -> list[dict]:
    return [
        {
            "date": "2025-01-02T00:00:00.000Z",
            "open": close - 1,
            "high": close + 1,
            "low": close - 2,
            "close": close,
            "adjClose": close,
            "volume": 1_000_000,
        },
        {
            "date": "2025-01-03T00:00:00.000Z",
            "open": close,
            "high": close + 2,
            "low": close - 1,
            "close": close + 1,
            "adjClose": close + 1,
            "volume": 1_100_000,
        },
    ]


def _stooq_csv(close: float = 101.0) -> str:
    return "\n".join(
        [
            "Date,Open,High,Low,Close,Volume",
            f"2025-01-02,{close - 1},{close + 1},{close - 2},{close},1000000",
            f"2025-01-03,{close},{close + 2},{close - 1},{close + 1},1100000",
        ]
    )


def _assert_standard_csv(path: Path) -> None:
    df = pd.read_csv(path)
    assert list(df.columns) == OUTPUT_COLUMNS
    assert len(df) == 2
    assert df.iloc[0]["Date"] == "2025-01-02"
    assert float(df.iloc[0]["Adj Close"]) == float(df.iloc[0]["Close"])


def test_tiingo_download_saves_standard_csv(tmp_path: Path) -> None:
    session = FakeSession(
        responses={
            "QQQ": FakeResponse(payload=_tiingo_payload()),
        }
    )

    result = download_history_data(
        source="tiingo",
        period="1y",
        output_dir=tmp_path,
        symbols=["QQQ"],
        sleep_seconds=0,
        api_key="test-key",
        session=session,
    )

    assert result.success_symbols == ["QQQ"]
    _assert_standard_csv(tmp_path / "QQQ.csv")


def test_stooq_download_saves_standard_csv(tmp_path: Path) -> None:
    session = FakeSession(responses={"qqq.us": FakeResponse(text=_stooq_csv())})

    result = download_history_data(
        source="stooq",
        period="1y",
        output_dir=tmp_path,
        symbols=["QQQ"],
        sleep_seconds=0,
        session=session,
    )

    assert result.success_symbols == ["QQQ"]
    _assert_standard_csv(tmp_path / "QQQ.csv")


def test_symbol_to_csv_filename_is_reused(tmp_path: Path) -> None:
    session = FakeSession(responses={"qqq.us": FakeResponse(text=_stooq_csv())})

    download_history_data(
        source="stooq",
        period="1y",
        output_dir=tmp_path,
        symbols=["QQQ"],
        sleep_seconds=0,
        session=session,
    )

    assert (tmp_path / symbol_to_csv_filename("QQQ")).exists()


def test_missing_tiingo_api_key_returns_clear_error(tmp_path: Path) -> None:
    result = download_history_data(
        source="tiingo",
        period="1y",
        output_dir=tmp_path,
        symbols=["QQQ"],
        sleep_seconds=0,
        api_key="",
        session=FakeSession(),
    )

    assert "TIINGO_API_KEY is required for Tiingo download" in result.errors
    assert result.critical_missing == ["QQQ"]


def test_single_symbol_failure_does_not_stop_others(tmp_path: Path) -> None:
    session = FakeSession(
        responses={
            "qqq.us": FakeResponse(text=_stooq_csv()),
            "spy.us": FakeResponse(status_code=500),
        }
    )

    result = download_history_data(
        source="stooq",
        period="1y",
        output_dir=tmp_path,
        symbols=["QQQ", "SPY"],
        sleep_seconds=0,
        session=session,
    )

    assert result.success_symbols == ["QQQ"]
    assert result.failed_symbols == ["SPY"]
    assert (tmp_path / "QQQ.csv").exists()


def test_stooq_apikey_page_is_reported_as_failure(tmp_path: Path) -> None:
    session = FakeSession(responses={"qqq.us": FakeResponse(text="Get your apikey:\n1. Open Stooq")})

    result = download_history_data(
        source="stooq",
        period="1y",
        output_dir=tmp_path,
        symbols=["QQQ"],
        sleep_seconds=0,
        session=session,
    )

    assert result.failed_symbols == ["QQQ"]
    assert any("requires an API key/captcha" in warning for warning in result.warnings)


def test_critical_symbols_missing_are_reported(tmp_path: Path) -> None:
    session = FakeSession(responses={"spy.us": FakeResponse(text=_stooq_csv())})

    result = download_history_data(
        source="stooq",
        period="1y",
        output_dir=tmp_path,
        symbols=["QQQ", "TQQQ", "SQQQ", "SPY"],
        sleep_seconds=0,
        session=session,
    )

    assert result.success_symbols == ["SPY"]
    assert result.critical_missing == ["QQQ", "TQQQ", "SQQQ"]


def test_existing_file_skipped_without_overwrite(tmp_path: Path) -> None:
    existing = pd.DataFrame(
        {
            "Date": ["2025-01-01"],
            "Open": [1],
            "High": [1],
            "Low": [1],
            "Close": [1],
            "Adj Close": [1],
            "Volume": [1],
        }
    )
    existing.to_csv(tmp_path / "QQQ.csv", index=False)

    result = download_history_data(
        source="stooq",
        period="1y",
        output_dir=tmp_path,
        symbols=["QQQ"],
        sleep_seconds=0,
        session=FakeSession(responses={"qqq.us": FakeResponse(text=_stooq_csv())}),
    )

    assert result.skipped_symbols == ["QQQ"]
    df = pd.read_csv(tmp_path / "QQQ.csv")
    assert len(df) == 1


def test_output_columns_are_exact(tmp_path: Path) -> None:
    session = FakeSession(responses={"qqq.us": FakeResponse(text=_stooq_csv())})

    download_history_data(
        source="stooq",
        period="1y",
        output_dir=tmp_path,
        symbols=["QQQ"],
        sleep_seconds=0,
        session=session,
    )

    assert list(pd.read_csv(tmp_path / "QQQ.csv").columns) == [
        "Date",
        "Open",
        "High",
        "Low",
        "Close",
        "Adj Close",
        "Volume",
    ]


def main() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as temp_dir:
        test_tiingo_download_saves_standard_csv(Path(temp_dir))
    with tempfile.TemporaryDirectory() as temp_dir:
        test_stooq_download_saves_standard_csv(Path(temp_dir))
    with tempfile.TemporaryDirectory() as temp_dir:
        test_symbol_to_csv_filename_is_reused(Path(temp_dir))
    with tempfile.TemporaryDirectory() as temp_dir:
        test_missing_tiingo_api_key_returns_clear_error(Path(temp_dir))
    with tempfile.TemporaryDirectory() as temp_dir:
        test_single_symbol_failure_does_not_stop_others(Path(temp_dir))
    with tempfile.TemporaryDirectory() as temp_dir:
        test_stooq_apikey_page_is_reported_as_failure(Path(temp_dir))
    with tempfile.TemporaryDirectory() as temp_dir:
        test_critical_symbols_missing_are_reported(Path(temp_dir))
    with tempfile.TemporaryDirectory() as temp_dir:
        test_existing_file_skipped_without_overwrite(Path(temp_dir))
    with tempfile.TemporaryDirectory() as temp_dir:
        test_output_columns_are_exact(Path(temp_dir))
    print("test_download_history_data passed")


if __name__ == "__main__":
    main()
