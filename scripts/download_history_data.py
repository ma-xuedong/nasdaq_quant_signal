"""Download historical daily prices into CSVProvider-compatible files."""

from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from typing import Any

import pandas as pd
import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from config import settings
from src.data_provider.csv_provider import symbol_to_csv_filename
from src.data_provider.tiingo_provider import (
    SUPPORTED_PERIOD_DAYS,
    TIINGO_EOD_URL,
    UNSUPPORTED_TIINGO_SYMBOLS,
    normalize_tiingo_eod_dataframe,
    period_to_start_date,
)


DEFAULT_SYMBOLS = [
    "QQQ",
    "TQQQ",
    "SQQQ",
    "SPY",
    "QQQE",
    "NVDA",
    "MSFT",
    "AAPL",
    "AMZN",
    "META",
    "GOOGL",
    "AVGO",
    "TSLA",
    "^VIX",
    "^VXN",
    "NQ=F",
    "ES=F",
]
CRITICAL_SYMBOLS = ["QQQ", "TQQQ", "SQQQ"]
OUTPUT_COLUMNS = ["Date", "Open", "High", "Low", "Close", "Adj Close", "Volume"]
STOOQ_EOD_URL = "https://stooq.com/q/d/l/"


@dataclass
class DownloadResult:
    success_symbols: list[str] = field(default_factory=list)
    failed_symbols: list[str] = field(default_factory=list)
    skipped_symbols: list[str] = field(default_factory=list)
    critical_missing: list[str] = field(default_factory=list)
    file_summaries: dict[str, dict[str, Any]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    output_dir: Path = Path("data/raw")


def parse_symbols(symbols_arg: str | None) -> list[str]:
    if not symbols_arg:
        return DEFAULT_SYMBOLS.copy()
    return [symbol.strip() for symbol in symbols_arg.split(",") if symbol.strip()]


def period_to_dates(period: str) -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    return period_to_start_date(period, end_date=now), now.strftime("%Y-%m-%d")


def to_yahoo_format(df: pd.DataFrame) -> pd.DataFrame:
    """Convert provider-normalized daily data to CSVProvider's accepted Yahoo format."""
    if df is None or df.empty:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    normalized = df.copy()
    normalized.columns = [str(column).strip().lower().replace(" ", "_") for column in normalized.columns]

    if "date" not in normalized.columns:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)
    if "adj_close" not in normalized.columns:
        normalized["adj_close"] = normalized.get("close")
    if "volume" not in normalized.columns:
        normalized["volume"] = 0

    for column in ["open", "high", "low", "close"]:
        if column not in normalized.columns:
            return pd.DataFrame(columns=OUTPUT_COLUMNS)
        normalized[column] = pd.to_numeric(normalized[column], errors="coerce")
    normalized["adj_close"] = pd.to_numeric(normalized["adj_close"], errors="coerce").fillna(normalized["close"])
    normalized["volume"] = pd.to_numeric(normalized["volume"], errors="coerce").fillna(0)
    normalized["date"] = pd.to_datetime(normalized["date"], errors="coerce")

    normalized = normalized.dropna(subset=["date", "open", "high", "low", "close"])
    if normalized.empty:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    normalized = normalized.sort_values("date").reset_index(drop=True)
    output = pd.DataFrame(
        {
            "Date": normalized["date"].dt.strftime("%Y-%m-%d"),
            "Open": normalized["open"],
            "High": normalized["high"],
            "Low": normalized["low"],
            "Close": normalized["close"],
            "Adj Close": normalized["adj_close"],
            "Volume": normalized["volume"],
        }
    )
    return output[OUTPUT_COLUMNS]


def save_symbol_csv(df: pd.DataFrame, symbol: str, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / symbol_to_csv_filename(symbol)
    yahoo_df = to_yahoo_format(df)
    yahoo_df.to_csv(output_path, index=False)
    return output_path


def summarize_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"rows": 0, "start_date": "", "end_date": ""}
    df = pd.read_csv(path)
    if df.empty or "Date" not in df.columns:
        return {"rows": len(df), "start_date": "", "end_date": ""}
    dates = pd.to_datetime(df["Date"], errors="coerce").dropna()
    if dates.empty:
        return {"rows": len(df), "start_date": "", "end_date": ""}
    return {
        "rows": len(df),
        "start_date": dates.min().strftime("%Y-%m-%d"),
        "end_date": dates.max().strftime("%Y-%m-%d"),
    }


def download_tiingo_symbol(
    symbol: str,
    period: str,
    api_key: str,
    session: Any | None = None,
    timeout: int = 20,
) -> tuple[pd.DataFrame, str | None]:
    if symbol in UNSUPPORTED_TIINGO_SYMBOLS:
        return pd.DataFrame(), f"Tiingo EOD does not support {symbol}"

    start_date, end_date = period_to_dates(period)
    client = session or requests.Session()
    response = client.get(
        TIINGO_EOD_URL.format(symbol=symbol),
        params={
            "startDate": start_date,
            "endDate": end_date,
            "format": "json",
            "token": api_key,
        },
        timeout=timeout,
    )
    if response.status_code >= 400:
        return pd.DataFrame(), f"Tiingo HTTP error for {symbol}: status={response.status_code}"

    df = normalize_tiingo_eod_dataframe(response.json(), symbol)
    if df.empty:
        return pd.DataFrame(), f"Tiingo returned no daily data for {symbol}"
    return df, None


def stooq_symbol(symbol: str) -> str | None:
    if symbol.startswith("^") or "=" in symbol:
        return None
    return f"{symbol.lower()}.us"


def download_stooq_symbol(
    symbol: str,
    period: str,
    session: Any | None = None,
    timeout: int = 20,
) -> tuple[pd.DataFrame, str | None]:
    stooq_code = stooq_symbol(symbol)
    if not stooq_code:
        return pd.DataFrame(), f"Stooq source skipped unsupported symbol {symbol}"

    start_date, end_date = period_to_dates(period)
    client = session or requests.Session()
    response = client.get(
        STOOQ_EOD_URL,
        params={
            "s": stooq_code,
            "i": "d",
            "d1": start_date.replace("-", ""),
            "d2": end_date.replace("-", ""),
        },
        timeout=timeout,
    )
    if response.status_code >= 400:
        return pd.DataFrame(), f"Stooq HTTP error for {symbol}: status={response.status_code}"

    response_text = response.text or ""
    first_line = next((line.strip() for line in response_text.splitlines() if line.strip()), "")
    if "get your apikey" in response_text.lower():
        return pd.DataFrame(), f"Stooq CSV download requires an API key/captcha for {symbol}"
    if first_line != "Date,Open,High,Low,Close,Volume":
        return pd.DataFrame(), f"Stooq returned non-CSV data for {symbol}"

    try:
        raw = pd.read_csv(StringIO(response_text))
    except Exception as exc:
        return pd.DataFrame(), f"Stooq CSV parse failed for {symbol}: {exc}"
    if raw.empty or "Date" not in raw.columns:
        return pd.DataFrame(), f"Stooq returned no daily data for {symbol}"

    raw = raw.rename(columns={"Date": "date", "Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"})
    raw["adj_close"] = raw["close"]
    raw["symbol"] = symbol
    return raw[["date", "open", "high", "low", "close", "adj_close", "volume", "symbol"]], None


def download_history_data(
    source: str = "tiingo",
    period: str = "3y",
    output_dir: str | Path = "data/raw",
    symbols: list[str] | None = None,
    sleep_seconds: float = 0.8,
    overwrite: bool = False,
    session: Any | None = None,
    api_key: str | None = None,
) -> DownloadResult:
    source = source.strip().lower()
    selected_symbols = symbols or DEFAULT_SYMBOLS.copy()
    result = DownloadResult(output_dir=Path(output_dir))

    if period not in SUPPORTED_PERIOD_DAYS:
        result.errors.append(f"Unsupported period: {period}")
        result.failed_symbols.extend(selected_symbols)
        result.critical_missing = [symbol for symbol in CRITICAL_SYMBOLS if symbol in selected_symbols]
        return result

    if source not in {"tiingo", "stooq"}:
        result.errors.append(f"Unsupported source: {source}")
        result.failed_symbols.extend(selected_symbols)
        result.critical_missing = [symbol for symbol in CRITICAL_SYMBOLS if symbol in selected_symbols]
        return result

    resolved_api_key = (api_key if api_key is not None else (getattr(settings, "TIINGO_API_KEY", "") or os.getenv("TIINGO_API_KEY", ""))).strip()
    if source == "tiingo" and not resolved_api_key:
        result.errors.append("TIINGO_API_KEY is required for Tiingo download")
        result.failed_symbols.extend(selected_symbols)
        result.critical_missing = [symbol for symbol in CRITICAL_SYMBOLS if symbol in selected_symbols]
        return result

    result.output_dir.mkdir(parents=True, exist_ok=True)
    for index, symbol in enumerate(selected_symbols):
        output_path = result.output_dir / symbol_to_csv_filename(symbol)
        if output_path.exists() and not overwrite:
            result.skipped_symbols.append(symbol)
            result.file_summaries[symbol] = summarize_file(output_path)
            continue

        try:
            if source == "tiingo":
                df, warning = download_tiingo_symbol(symbol, period, resolved_api_key, session=session)
            else:
                df, warning = download_stooq_symbol(symbol, period, session=session)
        except Exception as exc:
            df = pd.DataFrame()
            warning = f"{symbol} download failed: {exc}"

        if warning:
            result.warnings.append(warning)
        if df.empty:
            result.failed_symbols.append(symbol)
        else:
            saved_path = save_symbol_csv(df, symbol, result.output_dir)
            result.success_symbols.append(symbol)
            result.file_summaries[symbol] = summarize_file(saved_path)

        if sleep_seconds > 0 and index < len(selected_symbols) - 1:
            time.sleep(sleep_seconds)

    missing_or_failed = set(result.failed_symbols)
    for symbol in CRITICAL_SYMBOLS:
        output_path = result.output_dir / symbol_to_csv_filename(symbol)
        if symbol in selected_symbols and (symbol in missing_or_failed or not output_path.exists()):
            result.critical_missing.append(symbol)
    return result


def print_summary(result: DownloadResult, period: str) -> None:
    print(f"output_dir: {result.output_dir}")
    print(f"success_symbols: {result.success_symbols}")
    print(f"failed_symbols: {result.failed_symbols}")
    print(f"skipped_symbols: {result.skipped_symbols}")
    print(f"critical_missing: {result.critical_missing}")

    for symbol, summary in result.file_summaries.items():
        print(
            f"file: {symbol} rows={summary['rows']} "
            f"date_range={summary['start_date'] or 'n/a'} -> {summary['end_date'] or 'n/a'}"
        )
    for warning in result.warnings:
        print(f"warning: {warning}")
    for error in result.errors:
        print(f"error: {error}")

    if not result.critical_missing:
        min_history_days = 120 if period == "1y" else 200
        print("can run:")
        print(
            "py scripts/build_research_dataset.py --provider csv "
            f"--period {period} --output data/research_dataset.csv --min-history-days {min_history_days}"
        )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download daily history CSV files for research datasets.")
    parser.add_argument("--source", default="tiingo", choices=["tiingo", "stooq"])
    parser.add_argument("--period", default="3y", choices=["1y", "2y", "3y", "5y"])
    parser.add_argument("--output-dir", default="data/raw")
    parser.add_argument("--symbols", default=None, help="Comma-separated symbol list.")
    parser.add_argument("--sleep-seconds", type=float, default=0.8)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = download_history_data(
        source=args.source,
        period=args.period,
        output_dir=args.output_dir,
        symbols=parse_symbols(args.symbols),
        sleep_seconds=args.sleep_seconds,
        overwrite=args.overwrite,
    )
    print_summary(result, args.period)
    return 1 if result.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
