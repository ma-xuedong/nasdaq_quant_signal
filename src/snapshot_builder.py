"""Unified snapshot builder for live pipeline and backtest scoring."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd

from config.nasdaq100_symbols import NASDAQ100_SYMBOLS
from config.settings import EVENT_RISK_LOOKAHEAD_DAYS, FUTURES_SYMBOLS, MAX_BREADTH_SYMBOLS, MEGA_CAP_TECH_SYMBOLS
from src.breadth import build_breadth_snapshot
from src.data_quality import assess_data_quality
from src.event_calendar import build_event_risk_snapshot
from src.futures import build_futures_snapshot
from src.indicators import build_indicator_snapshot, calculate_daily_return
from src.utils import setup_logger

logger = setup_logger("snapshot_builder")


def _slice_frame(df: pd.DataFrame | None, current_date: Any = None) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    working_df = df.copy()
    sort_col = "datetime" if "datetime" in working_df.columns else "date" if "date" in working_df.columns else None
    if sort_col is None:
        return working_df.reset_index(drop=True)

    working_df[sort_col] = pd.to_datetime(working_df[sort_col], errors="coerce")
    working_df = working_df.dropna(subset=[sort_col]).sort_values(sort_col).reset_index(drop=True)

    if current_date is None:
        return working_df

    reference_ts = pd.to_datetime(current_date, errors="coerce")
    if pd.isna(reference_ts):
        return working_df

    return working_df[working_df[sort_col] <= reference_ts].reset_index(drop=True)


def _normalize_daily_data(daily_data: dict[str, pd.DataFrame], current_date: Any = None) -> dict[str, pd.DataFrame]:
    return {
        symbol: sliced_df
        for symbol, df in (daily_data or {}).items()
        if not (sliced_df := _slice_frame(df, current_date)).empty
    }


def _normalize_intraday_data(intraday_data: dict[str, pd.DataFrame], current_date: Any = None) -> dict[str, pd.DataFrame]:
    return {
        symbol: sliced_df
        for symbol, df in (intraday_data or {}).items()
        if not (sliced_df := _slice_frame(df, current_date)).empty
    }


def _default_cache_status(
    daily_data: dict[str, pd.DataFrame],
    intraday_data: dict[str, pd.DataFrame],
) -> dict[str, dict[str, Any]]:
    cache_status: dict[str, dict[str, Any]] = {}

    for symbol, df in daily_data.items():
        available = df is not None and not df.empty
        cache_status[symbol] = {
            "source": "api" if available else "missing",
            "is_fresh": available,
            "is_fallback": False,
            "used_cache": False,
        }

    for symbol, df in intraday_data.items():
        key = f"{symbol}_intraday_5m"
        available = df is not None and not df.empty
        cache_status[key] = {
            "source": "api" if available else "missing",
            "is_fresh": available,
            "is_fallback": False,
            "used_cache": False,
        }

    cache_status.setdefault(
        "QQQ_intraday_5m",
        {
            "source": "missing",
            "is_fresh": False,
            "is_fallback": False,
            "used_cache": False,
        },
    )
    return cache_status


def _resolve_reference_timestamp(daily_data: dict[str, pd.DataFrame], current_date: Any = None) -> pd.Timestamp:
    reference_ts = pd.to_datetime(current_date, errors="coerce") if current_date is not None else pd.NaT
    if not pd.isna(reference_ts):
        return reference_ts

    qqq_df = daily_data.get("QQQ")
    if qqq_df is not None and not qqq_df.empty and "date" in qqq_df.columns:
        qqq_dates = pd.to_datetime(qqq_df["date"], errors="coerce").dropna()
        if not qqq_dates.empty:
            return qqq_dates.max()

    return pd.Timestamp(datetime.now())


def _safe_latest_close(df: pd.DataFrame | None) -> float | None:
    if df is None or df.empty or "close" not in df.columns:
        return None

    closes = pd.to_numeric(df["close"], errors="coerce").dropna()
    if closes.empty:
        return None
    return float(closes.iloc[-1])


def _build_volatility_snapshot(daily_data: dict[str, pd.DataFrame], cache_status: dict[str, dict[str, Any]]) -> dict[str, Any]:
    warnings: list[str] = []
    vix_close = _safe_latest_close(daily_data.get("^VIX"))
    vxn_close = _safe_latest_close(daily_data.get("^VXN"))

    if vix_close is None:
        warnings.append("VIX 数据缺失，波动率模块降级。")
    if vxn_close is None:
        warnings.append("VXN 数据缺失，波动率模块降级。")

    return {
        "available": vix_close is not None or vxn_close is not None,
        "vix_close": vix_close,
        "vxn_close": vxn_close,
        "vix_daily_return": calculate_daily_return(daily_data.get("^VIX", pd.DataFrame())),
        "vxn_daily_return": calculate_daily_return(daily_data.get("^VXN", pd.DataFrame())),
        "source_status": {
            "^VIX": cache_status.get("^VIX", {}),
            "^VXN": cache_status.get("^VXN", {}),
        },
        "warnings": warnings,
    }


def _normalize_mega_cap_snapshot(snapshot: dict[str, Any], daily_data: dict[str, pd.DataFrame]) -> dict[str, Any]:
    tech_snapshot = dict(snapshot or {})
    up_count = int(tech_snapshot.get("up_count", 0) or 0)
    down_count = int(tech_snapshot.get("down_count", 0) or 0)
    flat_count = int(tech_snapshot.get("flat_count", 0) or 0)
    available_count = int(tech_snapshot.get("available_count", 0) or 0)
    if available_count <= 0:
        available_count = max(len(tech_snapshot.get("details", {})), up_count + down_count + flat_count)

    missing_symbols = [
        symbol
        for symbol in MEGA_CAP_TECH_SYMBOLS
        if symbol not in daily_data or daily_data.get(symbol) is None or daily_data.get(symbol).empty
    ]
    warnings = list(tech_snapshot.get("warnings", []))
    if missing_symbols:
        warnings.append(f"科技权重股缺失 {len(missing_symbols)} 只，权重股模块降级。")

    tech_snapshot.update(
        {
            "up_count": up_count,
            "down_count": down_count,
            "strong_count": int(tech_snapshot.get("strong_count", up_count) or up_count),
            "available_count": available_count,
            "total_count": len(MEGA_CAP_TECH_SYMBOLS),
            "warnings": warnings,
        }
    )
    return tech_snapshot


def _normalize_qqq_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    qqq_snapshot = dict(snapshot or {})
    price = float(qqq_snapshot.get("price", qqq_snapshot.get("close", 0)) or 0)
    atr14 = float(qqq_snapshot.get("atr14", 0) or 0)
    qqq_snapshot.setdefault("price", price)
    qqq_snapshot["close"] = float(qqq_snapshot.get("close", price) or price)
    qqq_snapshot["atr14"] = atr14
    qqq_snapshot["atr_pct"] = float(qqq_snapshot.get("atr_pct", (atr14 / price) if price else 0) or 0)
    return qqq_snapshot


def build_scoring_snapshot(
    market_data: dict,
    current_date=None,
    mode: str = "live",
) -> dict[str, Any]:
    """Build a unified scoring snapshot for both live and backtest flows."""
    del mode

    daily_data = _normalize_daily_data(market_data.get("daily_data", {}), current_date=current_date)
    intraday_data = _normalize_intraday_data(market_data.get("intraday_data", {}), current_date=current_date)
    cache_status = dict(market_data.get("cache_status") or market_data.get("data_source_status") or {})
    if not cache_status:
        cache_status = _default_cache_status(daily_data, intraday_data)

    reference_ts = _resolve_reference_timestamp(daily_data, current_date=current_date)
    reference_date_str = reference_ts.strftime("%Y-%m-%d")

    snapshot = build_indicator_snapshot(daily_data, intraday_data)
    snapshot["qqq"] = _normalize_qqq_snapshot(snapshot.get("qqq", {}))
    snapshot["mega_cap_tech"] = _normalize_mega_cap_snapshot(snapshot.get("mega_cap_tech", {}), daily_data)
    snapshot["volatility"] = _build_volatility_snapshot(daily_data, cache_status)

    qqq_atr_pct = snapshot.get("qqq", {}).get("atr_pct")
    snapshot["futures_snapshot"] = build_futures_snapshot(
        futures_data={
            FUTURES_SYMBOLS["NQ"]: daily_data.get(FUTURES_SYMBOLS["NQ"], pd.DataFrame()),
            FUTURES_SYMBOLS["ES"]: daily_data.get(FUTURES_SYMBOLS["ES"], pd.DataFrame()),
            FUTURES_SYMBOLS["MNQ"]: daily_data.get(FUTURES_SYMBOLS["MNQ"], pd.DataFrame()),
            FUTURES_SYMBOLS["MES"]: daily_data.get(FUTURES_SYMBOLS["MES"], pd.DataFrame()),
        },
        qqq_atr_pct=qqq_atr_pct,
        data_source_status=cache_status,
    )

    breadth_symbols = NASDAQ100_SYMBOLS[:MAX_BREADTH_SYMBOLS]
    snapshot["breadth_snapshot"] = build_breadth_snapshot(
        symbol_data={symbol: daily_data.get(symbol, pd.DataFrame()) for symbol in breadth_symbols},
        min_required_symbols=min(len(breadth_symbols), market_data.get("min_required_symbols", len(breadth_symbols))),
    )
    if len(breadth_symbols) < len(NASDAQ100_SYMBOLS):
        snapshot["breadth_snapshot"].setdefault("warnings", []).append("当前仅使用部分 Nasdaq-100 成分股计算市场宽度。")

    snapshot["event_risk_snapshot"] = build_event_risk_snapshot(
        reference_date_str,
        indicator_snapshot=snapshot,
        lookahead_days=market_data.get("lookahead_days", EVENT_RISK_LOOKAHEAD_DAYS),
        risk_events=market_data.get("risk_events"),
    )
    snapshot["data_quality"] = assess_data_quality(daily_data=daily_data, cache_status=cache_status)
    snapshot["reference_date"] = reference_date_str
    snapshot["reference_timestamp"] = reference_ts
    snapshot["cache_status"] = cache_status
    snapshot["warnings"] = list(snapshot.get("warnings", []))
    return snapshot