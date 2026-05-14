"""Unified signal pipeline for CLI and Streamlit."""

from __future__ import annotations

from datetime import datetime

from config.settings import (
    BREADTH_MIN_REQUIRED_SYMBOLS,
    DATABASE_PATH,
    FUTURES_SYMBOLS,
    MAX_BREADTH_SYMBOLS,
    MEGA_CAP_TECH_SYMBOLS,
    VOLATILITY_SYMBOLS,
)
from config.nasdaq100_symbols import NASDAQ100_SYMBOLS
from src.breadth import build_breadth_snapshot
from src.cache import (
    get_daily_data_with_cache,
    get_intraday_data_with_cache,
    init_cache_metadata_table,
)
from src.data_quality import assess_data_quality
from src.database import init_database, save_indicator_daily, save_market_score
from src.event_calendar import build_event_risk_snapshot
from src.futures import build_futures_snapshot
from src.indicators import build_full_indicator_dataframe, build_indicator_snapshot
from src.market_state import classify_overall_market_state, generate_market_summary
from src.risk_filter import get_risk_deduction
from src.rate_limiter import sleep_between_requests
from src.scoring import calculate_final_score, calculate_sqqq_score, calculate_tqqq_score
from src.utils import setup_logger

logger = setup_logger("pipeline")


SYMBOL_BATCHES = [
    ["QQQ", "SPY", "TQQQ", "SQQQ"],
    ["QQQE", VOLATILITY_SYMBOLS["VIX"], VOLATILITY_SYMBOLS["VXN"]],
    MEGA_CAP_TECH_SYMBOLS,
    [
        FUTURES_SYMBOLS["NQ"],
        FUTURES_SYMBOLS["ES"],
        FUTURES_SYMBOLS["MNQ"],
        FUTURES_SYMBOLS["MES"],
    ],
]


def _cap_signal_scores(tqqq_score: float, sqqq_score: float, max_score: float) -> tuple[float, float]:
    """Cap effective scores so guardrails can suppress strong conclusions."""
    return min(float(tqqq_score), max_score), min(float(sqqq_score), max_score)


def _refresh_quality_labels(data_quality: dict) -> dict:
    """Recalculate quality bands after pipeline-level adjustments."""
    score = max(0, min(100, float(data_quality.get("quality_score", 0) or 0)))
    data_quality["quality_score"] = score

    if score >= 85:
        data_quality["quality_level"] = "high"
        data_quality["confidence"] = "high"
    elif score >= 70:
        data_quality["quality_level"] = "medium"
        data_quality["confidence"] = "medium"
    elif score >= 50:
        data_quality["quality_level"] = "low"
        data_quality["confidence"] = "low"
    else:
        data_quality["quality_level"] = "poor"
        data_quality["confidence"] = "very_low"
    return data_quality


def run_signal_pipeline(save_to_db: bool = True, use_cache: bool = True) -> dict:
    """Execute the complete first-class signal workflow with cache and quality control."""
    now = datetime.now()
    now_str = now.strftime("%Y-%m-%d")

    init_database(DATABASE_PATH)
    init_cache_metadata_table(DATABASE_PATH)

    daily_data: dict = {}
    intraday_data: dict = {}
    cache_status: dict[str, dict] = {}
    warnings: list[str] = []

    for batch_idx, batch in enumerate(SYMBOL_BATCHES):
        for symbol in batch:
            if use_cache:
                df, meta = get_daily_data_with_cache(
                    symbol=symbol,
                    period="1y",
                    max_age_minutes=30,
                    db_path=DATABASE_PATH,
                )
            else:
                df, meta = get_daily_data_with_cache(
                    symbol=symbol,
                    period="1y",
                    max_age_minutes=0,
                    db_path=DATABASE_PATH,
                )
            daily_data[symbol] = df
            cache_status[symbol] = meta
        if batch_idx < len(SYMBOL_BATCHES) - 1:
            sleep_between_requests(2.0)

    if use_cache:
        qqq_intraday, intraday_meta = get_intraday_data_with_cache(
            symbol="QQQ",
            interval="5m",
            period="1d",
            max_age_minutes=5,
            db_path=DATABASE_PATH,
        )
    else:
        qqq_intraday, intraday_meta = get_intraday_data_with_cache(
            symbol="QQQ",
            interval="5m",
            period="1d",
            max_age_minutes=0,
            db_path=DATABASE_PATH,
        )
    intraday_data["QQQ"] = qqq_intraday
    cache_status["QQQ_intraday_5m"] = intraday_meta

    data_source_status = dict(cache_status)

    data_quality = assess_data_quality(daily_data=daily_data, cache_status=cache_status)
    warnings.extend(data_quality.get("warnings", []))
    is_test_mode = bool(data_quality.get("is_test_mode", False))
    is_realtime_usable = bool(data_quality.get("is_realtime_usable", False))
    event_risk_snapshot = build_event_risk_snapshot(now_str)

    if daily_data.get("QQQ") is None or daily_data.get("QQQ").empty:
        return {
            "success": False,
            "datetime": now.isoformat(),
            "message": "QQQ 核心数据缺失且无可用缓存，停止评分。",
            "data_source_status": data_source_status,
            "data_quality": data_quality,
            "cache_status": cache_status,
            "is_realtime_usable": False,
            "is_test_mode": is_test_mode,
            "event_risk_snapshot": event_risk_snapshot,
            "warnings": warnings,
        }

    indicator_snapshot = build_indicator_snapshot(daily_data, intraday_data)

    qqq_atr = indicator_snapshot.get("qqq", {}).get("atr14")
    qqq_price = indicator_snapshot.get("qqq", {}).get("price")
    qqq_atr_pct = None
    if qqq_atr not in {None, 0} and qqq_price not in {None, 0}:
        qqq_atr_pct = float(qqq_atr) / float(qqq_price)

    futures_snapshot = build_futures_snapshot(
        futures_data={
            FUTURES_SYMBOLS["NQ"]: daily_data.get(FUTURES_SYMBOLS["NQ"], None),
            FUTURES_SYMBOLS["ES"]: daily_data.get(FUTURES_SYMBOLS["ES"], None),
            FUTURES_SYMBOLS["MNQ"]: daily_data.get(FUTURES_SYMBOLS["MNQ"], None),
            FUTURES_SYMBOLS["MES"]: daily_data.get(FUTURES_SYMBOLS["MES"], None),
        },
        qqq_atr_pct=qqq_atr_pct,
        data_source_status=data_source_status,
    )

    breadth_symbols = NASDAQ100_SYMBOLS[:MAX_BREADTH_SYMBOLS]
    breadth_snapshot = build_breadth_snapshot(
        symbol_data={symbol: daily_data.get(symbol) for symbol in breadth_symbols},
        min_required_symbols=min(BREADTH_MIN_REQUIRED_SYMBOLS, len(breadth_symbols)),
    )

    if len(breadth_symbols) < len(NASDAQ100_SYMBOLS):
        breadth_snapshot.setdefault("warnings", []).append("当前仅使用部分 Nasdaq-100 成分股计算市场宽度。")

    if not futures_snapshot.get("available", False):
        warnings.extend(futures_snapshot.get("warnings", []))

    if not breadth_snapshot.get("available", False):
        warnings.extend(breadth_snapshot.get("warnings", []))
        warnings.append("市场宽度模块降级，可继续使用原有 QQQE / 科技权重股逻辑。")
        data_quality["quality_score"] = max(0, float(data_quality.get("quality_score", 0) or 0) - 10)
        data_quality["breadth_available"] = False
    else:
        warnings.extend(breadth_snapshot.get("warnings", []))
        data_quality["breadth_available"] = True

    data_quality = _refresh_quality_labels(data_quality)
    indicator_snapshot["futures_snapshot"] = futures_snapshot
    indicator_snapshot["breadth_snapshot"] = breadth_snapshot
    indicator_snapshot["event_risk_snapshot"] = event_risk_snapshot

    tqqq_result = calculate_tqqq_score(indicator_snapshot)
    sqqq_result = calculate_sqqq_score(indicator_snapshot)

    tqqq_base = tqqq_result.get("base_score", 0)
    sqqq_base = sqqq_result.get("base_score", 0)

    risk_result = get_risk_deduction(
        now_str,
        indicator_snapshot,
        event_risk_snapshot=event_risk_snapshot,
    )
    risk_deduction = risk_result.get("deduction", 0)

    raw_tqqq_final = calculate_final_score(tqqq_base, risk_deduction)
    raw_sqqq_final = calculate_final_score(sqqq_base, risk_deduction)

    effective_tqqq_final = raw_tqqq_final
    effective_sqqq_final = raw_sqqq_final

    qqq_source = data_source_status.get("QQQ", {}).get("source")

    if is_test_mode:
        effective_tqqq_final, effective_sqqq_final = _cap_signal_scores(raw_tqqq_final, raw_sqqq_final, 59)
        warnings.append("当前为测试模式，不可用于真实交易判断。")
    elif data_quality.get("quality_score", 0) < 50:
        effective_tqqq_final, effective_sqqq_final = _cap_signal_scores(raw_tqqq_final, raw_sqqq_final, 59)
        warnings.append("数据质量不足，不建议交易。")
    elif (not is_realtime_usable) or qqq_source == "fallback_cache" or data_quality.get("quality_score", 0) < 70:
        effective_tqqq_final, effective_sqqq_final = _cap_signal_scores(raw_tqqq_final, raw_sqqq_final, 74)
        if qqq_source == "fallback_cache":
            warnings.append("QQQ 使用 fallback_cache，数据可能滞后，仅可观察。")
        if not is_realtime_usable:
            warnings.append("QQQ 实时/准实时数据不可用，仅可观察，不能输出强交易结论。")

    market_state = classify_overall_market_state(effective_tqqq_final, effective_sqqq_final)

    if is_test_mode:
        market_state = "测试模式"
    elif data_quality.get("quality_score", 0) < 50:
        market_state = "数据质量不足，不建议交易"
    elif qqq_source == "fallback_cache":
        market_state = "观察（数据可能滞后）"
    elif not is_realtime_usable:
        market_state = "观察（实时性不足）"
    elif data_quality.get("quality_score", 0) < 70:
        market_state = "观察（弱参考）"

    final_scores = {"tqqq": effective_tqqq_final, "sqqq": effective_sqqq_final}
    summary = generate_market_summary(
        tqqq_result,
        sqqq_result,
        risk_result,
        final_scores,
        futures_snapshot=futures_snapshot,
        breadth_snapshot=breadth_snapshot,
        event_risk_snapshot=event_risk_snapshot,
    )

    if is_test_mode:
        summary = "当前为模拟数据，仅用于开发测试，不可用于真实交易判断。\n\n" + summary
    elif qqq_source == "fallback_cache":
        summary = "核心行情使用 fallback_cache，数据可能滞后，仅可用于观察展示。\n\n" + summary
    elif not is_realtime_usable:
        summary = "QQQ 实时/准实时数据不可用，当前不能输出强交易建议。\n\n" + summary

    if data_quality.get("quality_score", 0) < 50:
        market_state = "数据质量不足，不建议交易"
        summary = summary + "\n\n【数据质量附加提示】\n数据质量较低，当前评分仅可用于观察，不建议据此交易。"
    elif data_quality.get("quality_score", 0) < 70:
        market_state = "观察（弱参考）"
        summary = summary + "\n\n【数据质量附加提示】\n数据质量一般，建议轻仓或继续观察。"

    if save_to_db:
        try:
            qqq_df = daily_data.get("QQQ")
            if qqq_df is not None and not qqq_df.empty:
                indicator_df = build_full_indicator_dataframe(qqq_df)
                save_indicator_daily("QQQ", indicator_df, db_path=DATABASE_PATH)

            save_market_score(
                {
                    "datetime": now.isoformat(),
                    "tqqq_base_score": tqqq_base,
                    "sqqq_base_score": sqqq_base,
                    "risk_deduction": risk_deduction,
                    "tqqq_final_score": effective_tqqq_final,
                    "sqqq_final_score": effective_sqqq_final,
                    "market_state": market_state,
                    "summary": summary,
                },
                db_path=DATABASE_PATH,
            )
        except Exception as exc:
            logger.warning("pipeline 数据库写入失败: %s", str(exc))
            warnings.append(f"数据库写入失败: {str(exc)}")

    return {
        "success": True,
        "datetime": now.isoformat(),
        "timestamp": now,
        "data_source_status": data_source_status,
        "data_quality": data_quality,
        "cache_status": cache_status,
        "is_realtime_usable": is_realtime_usable,
        "is_test_mode": is_test_mode,
        "indicator_snapshot": indicator_snapshot,
        "futures_snapshot": futures_snapshot,
        "breadth_snapshot": breadth_snapshot,
        "event_risk_snapshot": event_risk_snapshot,
        "tqqq_result": tqqq_result,
        "sqqq_result": sqqq_result,
        "risk_result": risk_result,
        "final_scores": {
            "tqqq_final_score": effective_tqqq_final,
            "sqqq_final_score": effective_sqqq_final,
        },
        "raw_final_scores": {
            "tqqq_final_score": raw_tqqq_final,
            "sqqq_final_score": raw_sqqq_final,
        },
        "tqqq_base": tqqq_base,
        "sqqq_base": sqqq_base,
        "risk_deduction": risk_deduction,
        "tqqq_final": effective_tqqq_final,
        "sqqq_final": effective_sqqq_final,
        "market_state": market_state,
        "summary": summary,
        "daily_data": daily_data,
        "intraday_data": intraday_data,
        "warnings": warnings,
    }
