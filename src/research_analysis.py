"""Research analysis helpers for score calibration reports.

These functions summarize an already-built research dataset. They do not train
models, change scoring weights, or emit trading decisions.
"""

from __future__ import annotations

from typing import Any

import pandas as pd


SCORE_BUCKET_LABELS = ["<50", "50-60", "60-70", "70-80", "80-90", "90+"]
SCORE_BUCKET_EDGES = [-float("inf"), 50, 60, 70, 80, 90, float("inf")]
TQQQ_RETURN_COLS = ["next_1d_tqqq_return", "next_3d_tqqq_return", "next_5d_tqqq_return"]
SQQQ_RETURN_COLS = ["next_1d_sqqq_return", "next_3d_sqqq_return", "next_5d_sqqq_return"]
ALL_RETURN_COLS = TQQQ_RETURN_COLS + SQQQ_RETURN_COLS

GROUP_STATS_COLUMNS = [
    "group",
    "return_col",
    "count",
    "avg_return",
    "median_return",
    "win_rate",
    "max_loss",
    "std_return",
]


def _available_return_cols(df: pd.DataFrame, return_cols: list[str] | tuple[str, ...] | None = None) -> list[str]:
    selected_cols = list(return_cols or ALL_RETURN_COLS)
    return [column for column in selected_cols if column in df.columns]


def _empty_group_stats(extra_columns: list[str] | None = None) -> pd.DataFrame:
    columns = list(extra_columns or []) + GROUP_STATS_COLUMNS
    return pd.DataFrame(columns=columns)


def _calculate_return_stats(values: pd.Series) -> dict[str, Any]:
    numeric_values = pd.to_numeric(values, errors="coerce").dropna()
    if numeric_values.empty:
        return {
            "count": 0,
            "avg_return": 0.0,
            "median_return": 0.0,
            "win_rate": 0.0,
            "max_loss": 0.0,
            "std_return": 0.0,
        }

    return {
        "count": int(len(numeric_values)),
        "avg_return": float(numeric_values.mean()),
        "median_return": float(numeric_values.median()),
        "win_rate": float((numeric_values > 0).mean()),
        "max_loss": float(numeric_values.min()),
        "std_return": float(numeric_values.std(ddof=0)),
    }


def _group_return_stats(
    df: pd.DataFrame,
    group_col: str,
    return_cols: list[str] | tuple[str, ...] | None = None,
    group_order: list[str] | None = None,
) -> pd.DataFrame:
    if df is None or df.empty or group_col not in df.columns:
        return _empty_group_stats()

    available_return_cols = _available_return_cols(df, return_cols)
    if not available_return_cols:
        return _empty_group_stats()

    rows: list[dict[str, Any]] = []
    groups = group_order or [str(value) for value in pd.Series(df[group_col]).dropna().unique().tolist()]

    for group in groups:
        group_df = df[df[group_col].astype("string") == str(group)]
        for return_col in available_return_cols:
            row = {
                "group": group,
                "return_col": return_col,
            }
            row.update(_calculate_return_stats(group_df[return_col]))
            rows.append(row)

    return pd.DataFrame(rows, columns=GROUP_STATS_COLUMNS)


def analyze_score_buckets(
    df: pd.DataFrame,
    score_col: str,
    return_cols: list[str] | tuple[str, ...],
) -> pd.DataFrame:
    """Bucket a score column and summarize forward returns per bucket."""
    if df is None or df.empty or score_col not in df.columns:
        return pd.DataFrame(columns=["score_col"] + GROUP_STATS_COLUMNS)

    available_return_cols = _available_return_cols(df, return_cols)
    if not available_return_cols:
        return pd.DataFrame(columns=["score_col"] + GROUP_STATS_COLUMNS)

    working_df = df.copy()
    working_df["_score_bucket"] = pd.cut(
        pd.to_numeric(working_df[score_col], errors="coerce"),
        bins=SCORE_BUCKET_EDGES,
        labels=SCORE_BUCKET_LABELS,
        right=False,
    )
    working_df["_score_bucket"] = working_df["_score_bucket"].astype("string").fillna("unknown")

    bucket_stats = _group_return_stats(
        working_df,
        "_score_bucket",
        available_return_cols,
        group_order=SCORE_BUCKET_LABELS,
    )
    bucket_stats.insert(0, "score_col", score_col)
    return bucket_stats


def analyze_futures_effect(df: pd.DataFrame) -> pd.DataFrame:
    """Analyze whether NQ relative strength versus ES aligns with forward returns."""
    if df is None or df.empty or "nq_vs_es" not in df.columns:
        return pd.DataFrame(columns=["module", "interpretation"] + GROUP_STATS_COLUMNS)

    working_df = df.copy()
    nq_vs_es = pd.to_numeric(working_df["nq_vs_es"], errors="coerce")
    working_df["_futures_group"] = "flat"
    working_df.loc[nq_vs_es > 0, "_futures_group"] = "nq_stronger"
    working_df.loc[nq_vs_es < 0, "_futures_group"] = "nq_weaker"

    stats = _group_return_stats(
        working_df,
        "_futures_group",
        ALL_RETURN_COLS,
        group_order=["nq_stronger", "nq_weaker", "flat"],
    )
    stats.insert(0, "module", "futures")
    stats.insert(1, "interpretation", _interpret_futures(stats))
    return stats


def analyze_breadth_effect(df: pd.DataFrame) -> pd.DataFrame:
    """Analyze forward returns grouped by breadth status."""
    if df is None or df.empty or "breadth_status" not in df.columns:
        return pd.DataFrame(columns=["module", "interpretation"] + GROUP_STATS_COLUMNS)

    stats = _group_return_stats(
        df,
        "breadth_status",
        ALL_RETURN_COLS,
        group_order=["strong", "mixed", "weak", "insufficient"],
    )
    stats.insert(0, "module", "breadth")
    stats.insert(1, "interpretation", _interpret_breadth(stats))
    return stats


def analyze_event_risk_effect(df: pd.DataFrame) -> pd.DataFrame:
    """Analyze forward returns grouped by event-risk level."""
    if df is None or df.empty:
        return pd.DataFrame(columns=["module", "interpretation"] + GROUP_STATS_COLUMNS)

    working_df = df.copy()
    if "event_risk_level" in working_df.columns:
        group_col = "event_risk_level"
        group_order = ["low", "medium", "high"]
    elif "event_risk_score" in working_df.columns:
        score = pd.to_numeric(working_df["event_risk_score"], errors="coerce").fillna(0)
        working_df["_event_risk_group"] = "low"
        working_df.loc[(score > 0) & (score < 25), "_event_risk_group"] = "medium"
        working_df.loc[score >= 25, "_event_risk_group"] = "high"
        group_col = "_event_risk_group"
        group_order = ["low", "medium", "high"]
    else:
        return pd.DataFrame(columns=["module", "interpretation"] + GROUP_STATS_COLUMNS)

    stats = _group_return_stats(working_df, group_col, ALL_RETURN_COLS, group_order=group_order)
    stats.insert(0, "module", "event_risk")
    stats.insert(1, "interpretation", _interpret_event_risk(stats))
    return stats


def analyze_data_quality_effect(df: pd.DataFrame) -> pd.DataFrame:
    """Analyze forward returns grouped by data-quality level."""
    if df is None or df.empty or "data_quality_level" not in df.columns:
        return pd.DataFrame(columns=["module", "interpretation"] + GROUP_STATS_COLUMNS)

    stats = _group_return_stats(
        df,
        "data_quality_level",
        ALL_RETURN_COLS,
        group_order=["high", "medium", "low", "poor"],
    )
    stats.insert(0, "module", "data_quality")
    stats.insert(1, "interpretation", _interpret_data_quality(stats))
    return stats


def build_research_analysis_report(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Build all research analysis tables from a research dataset."""
    if df is None or df.empty:
        return {
            "score_buckets": pd.DataFrame(columns=["score_col"] + GROUP_STATS_COLUMNS),
            "futures_effect": pd.DataFrame(columns=["module", "interpretation"] + GROUP_STATS_COLUMNS),
            "breadth_effect": pd.DataFrame(columns=["module", "interpretation"] + GROUP_STATS_COLUMNS),
            "event_risk_effect": pd.DataFrame(columns=["module", "interpretation"] + GROUP_STATS_COLUMNS),
            "data_quality_effect": pd.DataFrame(columns=["module", "interpretation"] + GROUP_STATS_COLUMNS),
            "summary": pd.DataFrame(columns=["metric", "value"]),
        }

    score_buckets = pd.concat(
        [
            analyze_score_buckets(df, "tqqq_score", TQQQ_RETURN_COLS),
            analyze_score_buckets(df, "sqqq_score", SQQQ_RETURN_COLS),
        ],
        ignore_index=True,
    )
    futures_effect = analyze_futures_effect(df)
    breadth_effect = analyze_breadth_effect(df)
    event_risk_effect = analyze_event_risk_effect(df)
    data_quality_effect = analyze_data_quality_effect(df)

    return {
        "score_buckets": score_buckets,
        "futures_effect": futures_effect,
        "breadth_effect": breadth_effect,
        "event_risk_effect": event_risk_effect,
        "data_quality_effect": data_quality_effect,
        "summary": _build_summary(
            df,
            futures_effect=futures_effect,
            breadth_effect=breadth_effect,
            event_risk_effect=event_risk_effect,
            data_quality_effect=data_quality_effect,
        ),
    }


def _group_avg(stats: pd.DataFrame, group: str, return_col: str) -> float | None:
    if stats.empty:
        return None
    matched = stats[(stats["group"] == group) & (stats["return_col"] == return_col)]
    if matched.empty or int(matched.iloc[0].get("count", 0) or 0) == 0:
        return None
    return float(matched.iloc[0]["avg_return"])


def _group_max_loss(stats: pd.DataFrame, group: str, return_col: str) -> float | None:
    if stats.empty:
        return None
    matched = stats[(stats["group"] == group) & (stats["return_col"] == return_col)]
    if matched.empty or int(matched.iloc[0].get("count", 0) or 0) == 0:
        return None
    return float(matched.iloc[0]["max_loss"])


def _interpret_futures(stats: pd.DataFrame) -> str:
    stronger_tqqq = _group_avg(stats, "nq_stronger", "next_3d_tqqq_return")
    weaker_tqqq = _group_avg(stats, "nq_weaker", "next_3d_tqqq_return")
    if stronger_tqqq is None or weaker_tqqq is None:
        return "insufficient_data"
    return "nq_strength_favors_tqqq" if stronger_tqqq > weaker_tqqq else "nq_strength_not_confirmed"


def _interpret_breadth(stats: pd.DataFrame) -> str:
    strong_tqqq = _group_avg(stats, "strong", "next_3d_tqqq_return")
    weak_tqqq = _group_avg(stats, "weak", "next_3d_tqqq_return")
    weak_sqqq = _group_avg(stats, "weak", "next_3d_sqqq_return")
    strong_sqqq = _group_avg(stats, "strong", "next_3d_sqqq_return")
    if None in {strong_tqqq, weak_tqqq, weak_sqqq, strong_sqqq}:
        return "insufficient_data"
    tqqq_confirmed = bool(strong_tqqq > weak_tqqq)
    sqqq_confirmed = bool(weak_sqqq > strong_sqqq)
    if tqqq_confirmed and sqqq_confirmed:
        return "breadth_direction_confirmed"
    if tqqq_confirmed:
        return "strong_breadth_favors_tqqq"
    if sqqq_confirmed:
        return "weak_breadth_favors_sqqq"
    return "breadth_effect_not_confirmed"


def _interpret_event_risk(stats: pd.DataFrame) -> str:
    low_loss = _group_max_loss(stats, "low", "next_3d_tqqq_return")
    high_loss = _group_max_loss(stats, "high", "next_3d_tqqq_return")
    if low_loss is None or high_loss is None:
        return "insufficient_data"
    return "high_event_risk_has_larger_drawdown" if high_loss < low_loss else "event_risk_drawdown_not_confirmed"


def _interpret_data_quality(stats: pd.DataFrame) -> str:
    high_count = _group_avg(stats, "high", "next_3d_tqqq_return")
    low_avg = _group_avg(stats, "low", "next_3d_tqqq_return")
    poor_avg = _group_avg(stats, "poor", "next_3d_tqqq_return")
    weak_quality_values = [value for value in [low_avg, poor_avg] if value is not None]
    if high_count is None or not weak_quality_values:
        return "insufficient_data"
    weak_quality_avg = sum(weak_quality_values) / len(weak_quality_values)
    return "low_quality_should_reduce_confidence" if weak_quality_avg < high_count else "quality_penalty_not_confirmed"


def _build_summary(
    df: pd.DataFrame,
    futures_effect: pd.DataFrame,
    breadth_effect: pd.DataFrame,
    event_risk_effect: pd.DataFrame,
    data_quality_effect: pd.DataFrame,
) -> pd.DataFrame:
    start_date = ""
    end_date = ""
    if "date" in df.columns:
        dates = pd.to_datetime(df["date"], errors="coerce").dropna()
        if not dates.empty:
            start_date = dates.min().strftime("%Y-%m-%d")
            end_date = dates.max().strftime("%Y-%m-%d")

    summary_rows = [
        {"metric": "row_count", "value": len(df)},
        {"metric": "field_count", "value": len(df.columns)},
        {"metric": "start_date", "value": start_date},
        {"metric": "end_date", "value": end_date},
        {"metric": "futures_interpretation", "value": _first_interpretation(futures_effect)},
        {"metric": "breadth_interpretation", "value": _first_interpretation(breadth_effect)},
        {"metric": "event_risk_interpretation", "value": _first_interpretation(event_risk_effect)},
        {"metric": "data_quality_interpretation", "value": _first_interpretation(data_quality_effect)},
    ]
    return pd.DataFrame(summary_rows, columns=["metric", "value"])


def _first_interpretation(df: pd.DataFrame) -> str:
    if df is None or df.empty or "interpretation" not in df.columns:
        return "insufficient_data"
    values = df["interpretation"].dropna().astype(str)
    return values.iloc[0] if not values.empty else "insufficient_data"
