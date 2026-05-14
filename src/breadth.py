"""Nasdaq-100 breadth helpers for internal market participation analysis."""

from __future__ import annotations

from statistics import median
from typing import Any

import pandas as pd

from config.nasdaq100_symbols import NASDAQ100_SYMBOLS
from src.indicators import calculate_moving_averages
from src.utils import setup_logger

logger = setup_logger("breadth")


def _sort_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """Sort a standard OHLCV dataframe by datetime or date."""
    if df is None or df.empty:
        return pd.DataFrame()

    ordered = df.copy()
    sort_col = "datetime" if "datetime" in ordered.columns else "date" if "date" in ordered.columns else None
    if sort_col is None:
        return ordered.reset_index(drop=True)

    ordered[sort_col] = pd.to_datetime(ordered[sort_col], errors="coerce")
    return ordered.sort_values(sort_col).reset_index(drop=True)


def calculate_symbol_return(df: pd.DataFrame) -> float | None:
    """计算单个成分股最新涨跌幅。"""
    try:
        ordered = _sort_ohlcv(df)
        if ordered.empty or "close" not in ordered.columns or len(ordered) < 2:
            return None

        closes = pd.to_numeric(ordered["close"], errors="coerce").dropna()
        if len(closes) < 2:
            return None

        latest_close = closes.iloc[-1]
        prev_close = closes.iloc[-2]
        if prev_close == 0:
            return None

        return float((latest_close / prev_close) - 1)
    except Exception as exc:
        logger.warning("calculate_symbol_return failed: %s", str(exc))
        return None


def calculate_ma_position(df: pd.DataFrame) -> dict[str, bool | None]:
    """判断单个 symbol 是否站上 MA20 / MA50 / MA200。"""
    default_result = {
        "above_ma20": None,
        "above_ma50": None,
        "above_ma200": None,
    }

    try:
        ordered = _sort_ohlcv(df)
        if ordered.empty or "close" not in ordered.columns:
            return default_result

        enriched = ordered
        if not {"ma20", "ma50", "ma200"}.issubset(enriched.columns):
            enriched = calculate_moving_averages(enriched)

        latest = enriched.iloc[-1]
        close = pd.to_numeric(pd.Series([latest.get("close")]), errors="coerce").iloc[0]
        if pd.isna(close):
            return default_result

        result = {}
        for ma_col, result_key in [("ma20", "above_ma20"), ("ma50", "above_ma50"), ("ma200", "above_ma200")]:
            ma_value = pd.to_numeric(pd.Series([latest.get(ma_col)]), errors="coerce").iloc[0]
            result[result_key] = None if pd.isna(ma_value) else bool(close > ma_value)

        return result
    except Exception as exc:
        logger.warning("calculate_ma_position failed: %s", str(exc))
        return default_result


def _safe_ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(float(numerator) / float(denominator), 4)


def _safe_stat(values: list[float], mode: str) -> float:
    if not values:
        return 0.0
    if mode == "mean":
        return round(sum(values) / len(values), 6)
    return round(float(median(values)), 6)


def _determine_breadth_status(
    available_symbols: int,
    min_required_symbols: int,
    up_ratio: float,
    down_ratio: float,
    above_ma20_ratio: float,
) -> str:
    """Classify overall breadth condition."""
    if available_symbols < min_required_symbols:
        return "insufficient"
    if up_ratio >= 0.65 and above_ma20_ratio >= 0.60:
        return "strong"
    if down_ratio >= 0.65 or above_ma20_ratio < 0.40:
        return "weak"
    return "mixed"


def build_breadth_snapshot(
    symbol_data: dict[str, pd.DataFrame],
    min_required_symbols: int = 30,
) -> dict[str, Any]:
    """构建市场宽度快照。"""
    warnings: list[str] = []
    missing_symbols: list[str] = []
    returns: list[float] = []
    up_count = 0
    down_count = 0
    flat_count = 0
    ma20_count = 0
    ma50_count = 0
    ma200_count = 0
    available_for_ma20 = 0
    available_for_ma50 = 0
    available_for_ma200 = 0

    total_symbols = len(NASDAQ100_SYMBOLS)
    tracked_symbols = NASDAQ100_SYMBOLS.copy()

    for symbol in tracked_symbols:
        df = symbol_data.get(symbol)
        if df is None or df.empty:
            missing_symbols.append(symbol)
            continue

        symbol_return = calculate_symbol_return(df)
        ma_position = calculate_ma_position(df)

        if symbol_return is None:
            missing_symbols.append(symbol)
            continue

        returns.append(symbol_return)
        if symbol_return > 0:
            up_count += 1
        elif symbol_return < 0:
            down_count += 1
        else:
            flat_count += 1

        if ma_position["above_ma20"] is not None:
            available_for_ma20 += 1
            if ma_position["above_ma20"]:
                ma20_count += 1
        if ma_position["above_ma50"] is not None:
            available_for_ma50 += 1
            if ma_position["above_ma50"]:
                ma50_count += 1
        if ma_position["above_ma200"] is not None:
            available_for_ma200 += 1
            if ma_position["above_ma200"]:
                ma200_count += 1

    available_symbols = len(returns)
    up_ratio = _safe_ratio(up_count, available_symbols)
    down_ratio = _safe_ratio(down_count, available_symbols)
    above_ma20_ratio = _safe_ratio(ma20_count, available_for_ma20)
    above_ma50_ratio = _safe_ratio(ma50_count, available_for_ma50)
    above_ma200_ratio = _safe_ratio(ma200_count, available_for_ma200)

    breadth_status = _determine_breadth_status(
        available_symbols=available_symbols,
        min_required_symbols=min_required_symbols,
        up_ratio=up_ratio,
        down_ratio=down_ratio,
        above_ma20_ratio=above_ma20_ratio,
    )

    if available_symbols < min_required_symbols:
        warnings.append("可用成分股数量不足，市场宽度模块降级。")
    if missing_symbols:
        warnings.append(f"部分成分股缺失：{len(missing_symbols)} 只。")

    return {
        "available": available_symbols >= min_required_symbols,
        "total_symbols": total_symbols,
        "available_symbols": available_symbols,
        "missing_symbols": missing_symbols,
        "up_count": up_count,
        "down_count": down_count,
        "flat_count": flat_count,
        "up_ratio": up_ratio,
        "down_ratio": down_ratio,
        "avg_return": _safe_stat(returns, "mean"),
        "median_return": _safe_stat(returns, "median"),
        "above_ma20_ratio": above_ma20_ratio,
        "above_ma50_ratio": above_ma50_ratio,
        "above_ma200_ratio": above_ma200_ratio,
        "breadth_status": breadth_status,
        "warnings": warnings,
    }
