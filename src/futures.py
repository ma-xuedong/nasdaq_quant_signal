"""Futures confirmation helpers for NQ / ES short-term market context."""

from __future__ import annotations

from typing import Any

import pandas as pd

from src.utils import setup_logger

logger = setup_logger("futures")


def _normalize_numeric_series(df: pd.DataFrame, column: str) -> pd.Series:
    """Read a numeric series safely from a futures dataframe."""
    if df is None or df.empty or column not in df.columns:
        return pd.Series(dtype="float64")
    return pd.to_numeric(df[column], errors="coerce").dropna()


def _sort_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """Sort standard OHLCV data by datetime/date when possible."""
    if df is None or df.empty:
        return pd.DataFrame()

    sorted_df = df.copy()
    sort_col = "datetime" if "datetime" in sorted_df.columns else "date" if "date" in sorted_df.columns else None
    if sort_col is None:
        return sorted_df.reset_index(drop=True)

    sorted_df[sort_col] = pd.to_datetime(sorted_df[sort_col], errors="coerce")
    return sorted_df.sort_values(sort_col).reset_index(drop=True)


def calculate_futures_return(df: pd.DataFrame) -> float:
    """计算期货最新涨跌幅。"""
    try:
        ordered = _sort_ohlcv(df)
        closes = _normalize_numeric_series(ordered, "close")
        if len(closes) < 2:
            return 0.0

        latest_close = closes.iloc[-1]
        prev_close = closes.iloc[-2]
        if prev_close == 0:
            return 0.0

        return float((latest_close / prev_close) - 1)
    except Exception as exc:
        logger.warning("calculate_futures_return failed: %s", str(exc))
        return 0.0


def calculate_relative_strength(nq_return: float, es_return: float) -> float:
    """计算 NQ 相对 ES 的强弱。"""
    try:
        return float(nq_return) - float(es_return)
    except Exception:
        return 0.0


def analyze_futures_trend(df: pd.DataFrame, lookback: int = 6) -> dict[str, Any]:
    """分析期货短周期趋势。"""
    default_result = {
        "trend": "unknown",
        "higher_lows": False,
        "lower_highs": False,
        "description": "期货数据不足，无法判断趋势。",
    }

    try:
        ordered = _sort_ohlcv(df)
        if ordered.empty or not {"high", "low"}.issubset(ordered.columns):
            return default_result

        recent = ordered.tail(max(lookback, 2)).copy()
        highs = _normalize_numeric_series(recent, "high")
        lows = _normalize_numeric_series(recent, "low")

        if len(highs) < 2 or len(lows) < 2 or len(highs) != len(lows):
            return default_result

        high_diff = highs.diff().dropna()
        low_diff = lows.diff().dropna()

        higher_highs = bool((high_diff > 0).all())
        higher_lows = bool((low_diff > 0).all())
        lower_highs = bool((high_diff < 0).all())
        lower_lows = bool((low_diff < 0).all())

        if higher_highs and higher_lows:
            trend = "up"
            description = "最近期货高点和低点同步抬高，短线趋势向上。"
        elif lower_highs and lower_lows:
            trend = "down"
            description = "最近期货高点和低点同步走低，短线趋势向下。"
        else:
            trend = "mixed"
            description = "最近期货高低点结构不一致，趋势混合。"

        return {
            "trend": trend,
            "higher_lows": higher_lows,
            "lower_highs": lower_highs,
            "description": description,
        }
    except Exception as exc:
        logger.warning("analyze_futures_trend failed: %s", str(exc))
        return default_result


def calculate_gap_vs_atr(futures_return: float, qqq_atr_pct: float | None) -> float:
    """计算期货缺口相对于 QQQ ATR 的比例。"""
    try:
        if qqq_atr_pct is None:
            return 0.0

        atr_pct = float(qqq_atr_pct)
        if atr_pct <= 0:
            return 0.0

        return float(abs(float(futures_return)) / atr_pct)
    except Exception:
        return 0.0


def build_futures_snapshot(
    futures_data: dict[str, pd.DataFrame],
    qqq_atr_pct: float | None = None,
    data_source_status: dict | None = None,
) -> dict[str, Any]:
    """构建期货快照。"""
    warnings: list[str] = []
    data_source_status = data_source_status or {}

    nq_df = futures_data.get("NQ=F", pd.DataFrame())
    es_df = futures_data.get("ES=F", pd.DataFrame())

    nq_available = nq_df is not None and not nq_df.empty
    es_available = es_df is not None and not es_df.empty

    source_status = {
        symbol: data_source_status.get(symbol, {})
        for symbol in ["NQ=F", "ES=F", "MNQ=F", "MES=F"]
        if symbol in data_source_status
    }

    if not nq_available and not es_available:
        warnings.append("NQ / ES 期货数据缺失，期货确认模块降级。")
        return {
            "available": False,
            "nq_return": 0.0,
            "es_return": 0.0,
            "nq_vs_es": 0.0,
            "nq_stronger_than_es": False,
            "nq_weaker_than_es": False,
            "nq_trend": analyze_futures_trend(pd.DataFrame()),
            "gap_vs_atr": 0.0,
            "source_status": source_status,
            "warnings": warnings,
        }

    nq_return = calculate_futures_return(nq_df)
    es_return = calculate_futures_return(es_df)
    nq_trend = analyze_futures_trend(nq_df)
    gap_vs_atr = calculate_gap_vs_atr(nq_return, qqq_atr_pct)

    if not nq_available:
        warnings.append("NQ 期货数据缺失，期货模块不可完整判断。")
        nq_vs_es = 0.0
        stronger = False
        weaker = False
        available = False
    elif not es_available:
        warnings.append("ES 期货数据缺失，无法计算 NQ 相对 ES 强弱，期货模块降级。")
        nq_vs_es = 0.0
        stronger = False
        weaker = False
        available = False
    else:
        nq_vs_es = calculate_relative_strength(nq_return, es_return)
        stronger = nq_vs_es > 0
        weaker = nq_vs_es < 0
        available = True

    return {
        "available": available,
        "nq_return": nq_return,
        "es_return": es_return,
        "nq_vs_es": nq_vs_es,
        "nq_stronger_than_es": stronger,
        "nq_weaker_than_es": weaker,
        "nq_trend": nq_trend,
        "gap_vs_atr": gap_vs_atr,
        "source_status": source_status,
        "warnings": warnings,
    }