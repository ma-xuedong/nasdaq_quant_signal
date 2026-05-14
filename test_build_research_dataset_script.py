"""Tests for the research dataset build script."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pandas as pd

from scripts.build_research_dataset import build_dataset_from_provider


class FakeProvider:
    def __init__(self, missing_symbols: set[str] | None = None, failing_symbols: set[str] | None = None) -> None:
        self.missing_symbols = missing_symbols or set()
        self.failing_symbols = failing_symbols or set()

    def get_daily_data(self, symbol: str, period: str = "3y") -> pd.DataFrame:
        del period
        if symbol in self.failing_symbols:
            raise RuntimeError("fetch boom")
        if symbol in self.missing_symbols:
            return pd.DataFrame()
        return _price_frame(symbol)


def _price_frame(symbol: str, periods: int = 206) -> pd.DataFrame:
    dates = pd.date_range("2025-01-01", periods=periods, freq="D")
    slope = 0.5 + (len(symbol) % 4) * 0.1
    closes = [100 + slope * idx for idx in range(periods)]
    return pd.DataFrame(
        {
            "date": dates,
            "open": [value - 0.2 for value in closes],
            "high": [value + 0.8 for value in closes],
            "low": [value - 0.8 for value in closes],
            "close": closes,
            "adj_close": closes,
            "volume": [1_000_000] * periods,
            "symbol": [symbol] * periods,
        }
    )


def _run_with_temp_output(provider: FakeProvider, symbols: list[str]) -> tuple[Path, object]:
    temp_dir = tempfile.TemporaryDirectory()
    output_path = Path(temp_dir.name) / "research_dataset.csv"
    result = build_dataset_from_provider(
        provider=provider,
        period="3y",
        output=output_path,
        min_history_days=200,
        symbols=symbols,
    )
    result._temp_dir = temp_dir  # type: ignore[attr-defined]
    return output_path, result


def test_build_research_dataset_script_generates_csv_with_mock_source() -> None:
    output_path, result = _run_with_temp_output(
        FakeProvider(),
        ["QQQ", "TQQQ", "SQQQ", "SPY", "QQQE", "^VIX", "^VXN", "NQ=F", "ES=F"],
    )

    assert result.status == "success"
    assert output_path.exists()
    loaded = pd.read_csv(output_path)
    assert not loaded.empty
    assert len(loaded) == len(result.dataset)


def test_build_research_dataset_script_fails_when_qqq_missing() -> None:
    output_path, result = _run_with_temp_output(
        FakeProvider(missing_symbols={"QQQ"}),
        ["QQQ", "TQQQ", "SQQQ", "SPY"],
    )

    assert result.status == "error"
    assert not output_path.exists()
    assert result.errors


def test_build_research_dataset_script_continues_when_auxiliary_symbol_missing() -> None:
    output_path, result = _run_with_temp_output(
        FakeProvider(missing_symbols={"SPY", "^VIX"}, failing_symbols={"NQ=F"}),
        ["QQQ", "TQQQ", "SQQQ", "SPY", "^VIX", "NQ=F"],
    )

    assert result.status == "success"
    assert output_path.exists()
    assert not result.dataset.empty
    assert result.warnings


def main() -> None:
    test_build_research_dataset_script_generates_csv_with_mock_source()
    test_build_research_dataset_script_fails_when_qqq_missing()
    test_build_research_dataset_script_continues_when_auxiliary_symbol_missing()
    print("test_build_research_dataset_script passed")


if __name__ == "__main__":
    main()
