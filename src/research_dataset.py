"""Research dataset construction for score and label analysis.

This module intentionally builds features through ``build_scoring_snapshot`` so
research rows use the same scoring inputs as live and backtest flows.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from src.data_quality import assess_data_quality
from src.market_state import classify_overall_market_state
from src.risk_filter import get_risk_deduction
from src.scoring import calculate_final_score, calculate_sqqq_score, calculate_tqqq_score
from src.snapshot_builder import build_scoring_snapshot
from src.utils import setup_logger

logger = setup_logger("research_dataset")


DEFAULT_OUTPUT_PATH = Path("data") / "research_dataset.csv"
DEFAULT_MIN_HISTORY_DAYS = 200
LABEL_HORIZONS = (1, 3, 5)


def _normalize_price_frame(df: pd.DataFrame | None) -> pd.DataFrame:
    if df is None or df.empty or "date" not in df.columns:
        return pd.DataFrame()

    working_df = df.copy()
    working_df["date"] = pd.to_datetime(working_df["date"], errors="coerce")
    working_df = working_df.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
    return working_df


def _normalize_historical_data(historical_data: dict[str, pd.DataFrame] | None) -> dict[str, pd.DataFrame]:
    normalized: dict[str, pd.DataFrame] = {}
    for symbol, df in (historical_data or {}).items():
        normalized_df = _normalize_price_frame(df)
        if not normalized_df.empty:
            normalized[symbol] = normalized_df
    return normalized


def _build_research_cache_status(historical_slice: dict[str, pd.DataFrame]) -> dict[str, dict[str, Any]]:
    cache_status: dict[str, dict[str, Any]] = {}
    for symbol, df in historical_slice.items():
        available = bool(df is not None and not df.empty)
        cache_status[symbol] = {
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


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _future_return(price_df: pd.DataFrame | None, current_date: pd.Timestamp, horizon: int) -> float | None:
    if price_df is None or price_df.empty or "date" not in price_df.columns or "close" not in price_df.columns:
        return None

    working_df = price_df.sort_values("date").reset_index(drop=True)
    matching_idx = working_df.index[working_df["date"] == current_date].tolist()
    if not matching_idx:
        return None

    current_idx = int(matching_idx[-1])
    future_idx = current_idx + horizon
    if future_idx >= len(working_df):
        return None

    current_close = _safe_float(working_df.iloc[current_idx].get("close"))
    future_close = _safe_float(working_df.iloc[future_idx].get("close"))
    if current_close == 0:
        return None

    return float((future_close / current_close) - 1)


def _extract_row(
    current_date: pd.Timestamp,
    snapshot: dict[str, Any],
    tqqq_score: float,
    sqqq_score: float,
    market_state: str,
    labels: dict[str, float | None],
) -> dict[str, Any]:
    data_quality = snapshot.get("data_quality", {}) or {}
    futures = snapshot.get("futures_snapshot", {}) or {}
    breadth = snapshot.get("breadth_snapshot", {}) or {}
    event_risk = snapshot.get("event_risk_snapshot", {}) or {}
    qqq = snapshot.get("qqq", {}) or {}

    row: dict[str, Any] = {
        "date": current_date,
        "tqqq_score": tqqq_score,
        "sqqq_score": sqqq_score,
        "market_state": market_state,
        "data_quality_score": _safe_float(data_quality.get("quality_score")),
        "data_quality_level": data_quality.get("quality_level", "poor"),
        "nq_return": _safe_float(futures.get("nq_return")),
        "es_return": _safe_float(futures.get("es_return")),
        "nq_vs_es": _safe_float(futures.get("nq_vs_es")),
        "up_ratio": _safe_float(breadth.get("up_ratio")),
        "down_ratio": _safe_float(breadth.get("down_ratio")),
        "above_ma20_ratio": _safe_float(breadth.get("above_ma20_ratio")),
        "breadth_status": breadth.get("breadth_status", "insufficient"),
        "event_risk_score": _safe_float(event_risk.get("deduction")),
        "event_risk_level": event_risk.get("risk_level", "low"),
        "close": _safe_float(qqq.get("close", qqq.get("price"))),
        "ma20": _safe_float(qqq.get("ma20")),
        "ma50": _safe_float(qqq.get("ma50")),
        "ma200": _safe_float(qqq.get("ma200")),
        "ma20_slope": _safe_float(qqq.get("ma20_slope")),
        "ma50_slope": _safe_float(qqq.get("ma50_slope")),
        "atr_pct": _safe_float(qqq.get("atr_pct")),
    }
    row.update(labels)
    return row


def build_research_dataset(
    historical_data: dict[str, pd.DataFrame] | None,
    min_history_days: int = DEFAULT_MIN_HISTORY_DAYS,
) -> pd.DataFrame:
    """Build one research row per QQQ trading day using only point-in-time features."""
    normalized_data = _normalize_historical_data(historical_data)
    qqq_df = normalized_data.get("QQQ")
    if qqq_df is None or qqq_df.empty or len(qqq_df) < min_history_days:
        return pd.DataFrame(columns=research_dataset_columns())

    rows: list[dict[str, Any]] = []
    label_frames = {
        "TQQQ": normalized_data.get("TQQQ", pd.DataFrame()),
        "SQQQ": normalized_data.get("SQQQ", pd.DataFrame()),
    }

    for current_date in qqq_df["date"].tolist():
        current_ts = pd.to_datetime(current_date)
        historical_slice = {
            symbol: df[df["date"] <= current_ts].copy()
            for symbol, df in normalized_data.items()
        }

        if len(historical_slice.get("QQQ", pd.DataFrame())) < min_history_days:
            continue

        cache_status = _build_research_cache_status(historical_slice)
        snapshot = build_scoring_snapshot(
            {
                "daily_data": historical_slice,
                "intraday_data": {},
                "cache_status": cache_status,
            },
            current_date=current_ts,
            mode="research",
        )

        tqqq_result = calculate_tqqq_score(snapshot)
        sqqq_result = calculate_sqqq_score(snapshot)
        risk_result = get_risk_deduction(
            str(current_ts.date()),
            snapshot,
            event_risk_snapshot=snapshot.get("event_risk_snapshot"),
        )
        risk_score = _safe_float(risk_result.get("deduction"))
        tqqq_score = calculate_final_score(_safe_float(tqqq_result.get("base_score")), risk_score)
        sqqq_score = calculate_final_score(_safe_float(sqqq_result.get("base_score")), risk_score)
        market_state = classify_overall_market_state(tqqq_score, sqqq_score)

        if "data_quality" not in snapshot:
            snapshot["data_quality"] = assess_data_quality(historical_slice, cache_status)

        labels: dict[str, float | None] = {}
        for symbol in ["TQQQ", "SQQQ"]:
            for horizon in LABEL_HORIZONS:
                labels[f"next_{horizon}d_{symbol.lower()}_return"] = _future_return(
                    label_frames.get(symbol),
                    current_ts,
                    horizon,
                )

        rows.append(_extract_row(current_ts, snapshot, tqqq_score, sqqq_score, market_state, labels))

    if not rows:
        return pd.DataFrame(columns=research_dataset_columns())

    return pd.DataFrame(rows, columns=research_dataset_columns())


def export_research_dataset(
    historical_data: dict[str, pd.DataFrame] | None,
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
    min_history_days: int = DEFAULT_MIN_HISTORY_DAYS,
) -> pd.DataFrame:
    """Build and export the research dataset to CSV."""
    dataset = build_research_dataset(historical_data, min_history_days=min_history_days)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    dataset.to_csv(path, index=False)
    logger.info("research dataset exported: %s rows -> %s", len(dataset), str(path))
    return dataset


def research_dataset_columns() -> list[str]:
    return [
        "date",
        "tqqq_score",
        "sqqq_score",
        "market_state",
        "data_quality_score",
        "data_quality_level",
        "nq_return",
        "es_return",
        "nq_vs_es",
        "up_ratio",
        "down_ratio",
        "above_ma20_ratio",
        "breadth_status",
        "event_risk_score",
        "event_risk_level",
        "close",
        "ma20",
        "ma50",
        "ma200",
        "ma20_slope",
        "ma50_slope",
        "atr_pct",
        "next_1d_tqqq_return",
        "next_3d_tqqq_return",
        "next_5d_tqqq_return",
        "next_1d_sqqq_return",
        "next_3d_sqqq_return",
        "next_5d_sqqq_return",
    ]
