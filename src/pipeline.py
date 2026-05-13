"""Unified signal pipeline for CLI and Streamlit."""

from __future__ import annotations

from datetime import datetime

from config.settings import (
    DATABASE_PATH,
    FUTURES_SYMBOLS,
    MEGA_CAP_TECH_SYMBOLS,
    VOLATILITY_SYMBOLS,
)
from src.cache import (
    get_daily_data_with_cache,
    get_intraday_data_with_cache,
    init_cache_metadata_table,
)
from src.data_quality import assess_data_quality
from src.database import init_database, save_indicator_daily, save_market_score
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

    data_quality = assess_data_quality(daily_data=daily_data, cache_status=cache_status)
    warnings.extend(data_quality.get("warnings", []))

    if daily_data.get("QQQ") is None or daily_data.get("QQQ").empty:
        return {
            "success": False,
            "datetime": now.isoformat(),
            "message": "QQQ 核心数据缺失且无可用缓存，停止评分。",
            "data_quality": data_quality,
            "cache_status": cache_status,
            "warnings": warnings,
        }

    indicator_snapshot = build_indicator_snapshot(daily_data, intraday_data)

    tqqq_result = calculate_tqqq_score(indicator_snapshot)
    sqqq_result = calculate_sqqq_score(indicator_snapshot)

    tqqq_base = tqqq_result.get("base_score", 0)
    sqqq_base = sqqq_result.get("base_score", 0)

    risk_result = get_risk_deduction(now_str, indicator_snapshot)
    risk_deduction = risk_result.get("deduction", 0)

    tqqq_final = calculate_final_score(tqqq_base, risk_deduction)
    sqqq_final = calculate_final_score(sqqq_base, risk_deduction)

    market_state = classify_overall_market_state(tqqq_final, sqqq_final)

    final_scores = {"tqqq": tqqq_final, "sqqq": sqqq_final}
    summary = generate_market_summary(tqqq_result, sqqq_result, risk_result, final_scores)

    if data_quality.get("quality_score", 0) < 50:
        warnings.append("数据质量较低，当前评分可信度不足，建议仅观察。")
        market_state = "仅观察（数据质量不足）"
        summary = summary + "\n\n【数据质量附加提示】\n数据质量较低，当前评分仅可用于观察，不建议据此交易。"
    elif data_quality.get("quality_score", 0) < 70:
        warnings.append("数据质量一般，信号仅作弱参考，不建议重仓。")
        summary = summary + "\n\n【数据质量附加提示】\n数据质量一般，建议轻仓或继续观察。"

    if cache_status.get("QQQ", {}).get("source") == "fallback_cache":
        warnings.append("QQQ 使用 fallback_cache，核心行情非最新 API，建议避免激进交易。")

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
                    "tqqq_final_score": tqqq_final,
                    "sqqq_final_score": sqqq_final,
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
        "data_quality": data_quality,
        "cache_status": cache_status,
        "indicator_snapshot": indicator_snapshot,
        "tqqq_result": tqqq_result,
        "sqqq_result": sqqq_result,
        "risk_result": risk_result,
        "final_scores": {
            "tqqq_final_score": tqqq_final,
            "sqqq_final_score": sqqq_final,
        },
        "tqqq_base": tqqq_base,
        "sqqq_base": sqqq_base,
        "risk_deduction": risk_deduction,
        "tqqq_final": tqqq_final,
        "sqqq_final": sqqq_final,
        "market_state": market_state,
        "summary": summary,
        "daily_data": daily_data,
        "intraday_data": intraday_data,
        "warnings": warnings,
    }
