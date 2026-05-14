"""Command-line entry point for building the research dataset CSV."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from config import settings
from src.data_provider.provider_factory import get_data_provider
from src.research_dataset import build_research_dataset


DEFAULT_OUTPUT_PATH = Path("data") / "research_dataset.csv"
CORE_RESEARCH_SYMBOLS = [
    "QQQ",
    "TQQQ",
    "SQQQ",
    "SPY",
    "QQQE",
    "^VIX",
    "^VXN",
    "NQ=F",
    "ES=F",
    "NVDA",
    "MSFT",
    "AAPL",
    "AMZN",
    "META",
    "GOOGL",
    "AVGO",
    "TSLA",
]


@dataclass
class BuildResult:
    status: str
    dataset: pd.DataFrame = field(default_factory=pd.DataFrame)
    output_path: Path | None = None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    historical_data: dict[str, pd.DataFrame] = field(default_factory=dict)


def research_symbols() -> list[str]:
    """Return the configured symbol universe required for research rows."""
    configured_symbols: list[str] = []
    configured_symbols.extend(getattr(settings, "ETF_SYMBOLS", []))
    configured_symbols.extend(getattr(settings, "VOLATILITY_SYMBOLS", {}).values())

    futures_symbols = getattr(settings, "FUTURES_SYMBOLS", {})
    for key in ["NQ", "ES"]:
        symbol = futures_symbols.get(key)
        if symbol:
            configured_symbols.append(symbol)

    configured_symbols.extend(getattr(settings, "MEGA_CAP_TECH_SYMBOLS", []))
    configured_symbols.extend(CORE_RESEARCH_SYMBOLS)

    seen: set[str] = set()
    symbols: list[str] = []
    for symbol in configured_symbols:
        if symbol and symbol not in seen:
            seen.add(symbol)
            symbols.append(symbol)
    return symbols


def _is_valid_daily_frame(df: pd.DataFrame | None) -> bool:
    return bool(df is not None and not df.empty and "date" in df.columns and "close" in df.columns)


def fetch_historical_data(provider: Any, symbols: list[str], period: str) -> tuple[dict[str, pd.DataFrame], list[str]]:
    """Fetch daily history per symbol without letting one failure abort the batch."""
    historical_data: dict[str, pd.DataFrame] = {}
    warnings: list[str] = []

    for symbol in symbols:
        try:
            df = provider.get_daily_data(symbol=symbol, period=period)
        except Exception as exc:
            warnings.append(f"{symbol} fetch failed: {exc}")
            historical_data[symbol] = pd.DataFrame()
            continue

        if not _is_valid_daily_frame(df):
            warnings.append(f"{symbol} daily data missing or invalid")
            historical_data[symbol] = pd.DataFrame()
            continue

        historical_data[symbol] = df

    return historical_data, warnings


def _label_missing_count(dataset: pd.DataFrame) -> int:
    label_columns = [column for column in dataset.columns if column.startswith("next_")]
    if not label_columns or dataset.empty:
        return 0
    return int(dataset[label_columns].isna().sum().sum())


def _date_range(dataset: pd.DataFrame) -> tuple[str, str]:
    if dataset.empty or "date" not in dataset.columns:
        return "", ""
    dates = pd.to_datetime(dataset["date"], errors="coerce").dropna()
    if dates.empty:
        return "", ""
    return dates.min().strftime("%Y-%m-%d"), dates.max().strftime("%Y-%m-%d")


def build_dataset_from_provider(
    provider: Any,
    period: str = "3y",
    output: str | Path = DEFAULT_OUTPUT_PATH,
    min_history_days: int = 200,
    symbols: list[str] | None = None,
) -> BuildResult:
    """Fetch history, build the research dataset, and write it to CSV."""
    selected_symbols = symbols or research_symbols()
    historical_data, warnings = fetch_historical_data(provider, selected_symbols, period)

    if not _is_valid_daily_frame(historical_data.get("QQQ")):
        return BuildResult(
            status="error",
            output_path=Path(output),
            warnings=warnings,
            errors=["QQQ daily data is required to build the research dataset."],
            historical_data=historical_data,
        )

    for label_symbol in ["TQQQ", "SQQQ"]:
        if not _is_valid_daily_frame(historical_data.get(label_symbol)):
            warnings.append(f"{label_symbol} missing: forward return labels for {label_symbol} will be unavailable.")

    auxiliary_missing = [
        symbol
        for symbol in selected_symbols
        if symbol not in {"QQQ", "TQQQ", "SQQQ"} and not _is_valid_daily_frame(historical_data.get(symbol))
    ]
    if auxiliary_missing:
        warnings.append(f"Auxiliary symbols missing: {', '.join(auxiliary_missing)}")

    dataset = build_research_dataset(historical_data, min_history_days=min_history_days)
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    dataset.to_csv(output_path, index=False)

    return BuildResult(
        status="success",
        dataset=dataset,
        output_path=output_path,
        warnings=warnings,
        historical_data=historical_data,
    )


def print_summary(result: BuildResult) -> None:
    """Print a compact run summary for CLI users."""
    dataset = result.dataset
    start_date, end_date = _date_range(dataset)
    label_missing = _label_missing_count(dataset)

    print(f"status: {result.status}")
    print(f"dataset rows: {len(dataset)}")
    print(f"date range: {start_date or 'n/a'} -> {end_date or 'n/a'}")
    print(f"field count: {len(dataset.columns)}")
    print(f"missing label count: {label_missing}")
    print(f"output path: {result.output_path or 'n/a'}")

    for warning in result.warnings:
        print(f"warning: {warning}")
    for error in result.errors:
        print(f"error: {error}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build data/research_dataset.csv from historical daily prices.")
    parser.add_argument("--period", default="3y", help="Historical period to fetch, e.g. 1y, 3y, 5y.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="CSV output path.")
    parser.add_argument("--min-history-days", type=int, default=200, help="Minimum QQQ history before emitting rows.")
    parser.add_argument("--provider", default=settings.DATA_PROVIDER, help="Data provider name; defaults to DATA_PROVIDER.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    settings.DATA_PROVIDER = str(args.provider).strip().lower()
    provider = get_data_provider()
    result = build_dataset_from_provider(
        provider=provider,
        period=args.period,
        output=args.output,
        min_history_days=args.min_history_days,
    )
    print_summary(result)
    return 0 if result.status == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
