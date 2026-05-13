"""Data quality scoring for signal confidence control."""

from __future__ import annotations


def _source_of(cache_status: dict[str, dict], key: str) -> str:
    """Read source field from cache_status with default missing."""
    return cache_status.get(key, {}).get("source", "missing")


def assess_data_quality(
    daily_data: dict,
    cache_status: dict[str, dict],
) -> dict:
    """Evaluate data availability/freshness and return quality metrics."""
    warnings: list[str] = []
    missing_symbols: list[str] = []

    qqq_source = _source_of(cache_status, "QQQ")
    spy_source = _source_of(cache_status, "SPY")
    qqqe_source = _source_of(cache_status, "QQQE")
    vix_source = _source_of(cache_status, "^VIX")
    vxn_source = _source_of(cache_status, "^VXN")

    qqq_ok = bool(daily_data.get("QQQ") is not None and not daily_data.get("QQQ").empty)
    spy_ok = bool(daily_data.get("SPY") is not None and not daily_data.get("SPY").empty)
    qqqe_ok = bool(daily_data.get("QQQE") is not None and not daily_data.get("QQQE").empty)

    vix_ok = bool(daily_data.get("^VIX") is not None and not daily_data.get("^VIX").empty)
    vxn_ok = bool(daily_data.get("^VXN") is not None and not daily_data.get("^VXN").empty)

    futures_count = sum(
        1 for symbol in ["NQ=F", "ES=F"] if daily_data.get(symbol) is not None and not daily_data.get(symbol).empty
    )
    futures_ok = futures_count >= 1

    mega_caps = ["NVDA", "MSFT", "AAPL", "AMZN", "META", "GOOGL", "AVGO", "TSLA"]
    mega_cap_available_count = sum(
        1 for symbol in mega_caps if daily_data.get(symbol) is not None and not daily_data.get(symbol).empty
    )

    cache_fallback_count = sum(1 for _, meta in cache_status.items() if meta.get("source") == "fallback_cache")

    if not qqq_ok:
        missing_symbols.append("QQQ")
        warnings.append("QQQ 核心数据缺失，无法保证评分有效性。")
    if not spy_ok:
        missing_symbols.append("SPY")
        warnings.append("SPY 缺失，相对强弱模块将降级处理。")
    if not qqqe_ok:
        missing_symbols.append("QQQE")
        warnings.append("QQQE 缺失，市场宽度模块将降级处理。")
    if not vxn_ok:
        missing_symbols.append("^VXN")
        warnings.append("VXN 缺失，波动率模块优先使用 VIX 替代。")

    if qqq_source == "fallback_cache":
        warnings.append("QQQ 核心数据来自 fallback_cache，建议不要进行激进交易。")
    if spy_source == "fallback_cache":
        warnings.append("SPY 使用 fallback_cache，相对强弱信号可信度下降。")
    if qqqe_source == "fallback_cache":
        warnings.append("QQQE 使用 fallback_cache，市场宽度模块可信度下降。")

    if not futures_ok:
        warnings.append("NQ/ES 缺失，期货模块降级处理。")

    score = 0
    if qqq_ok:
        score += 30
    if spy_ok:
        score += 10
    if qqqe_ok:
        score += 10
    if vix_ok:
        score += 8
    if vxn_ok:
        score += 7
    if mega_cap_available_count >= 6:
        score += 15
    elif mega_cap_available_count >= 4:
        score += 8
    if futures_ok:
        score += 10

    if cache_fallback_count == 0:
        score += 10
    elif cache_fallback_count <= 2:
        score += 5

    # source-level penalties (核心数据权重更高)
    if qqq_source == "fallback_cache":
        score -= 20
    elif qqq_source in {"none", "missing"}:
        score -= 40

    if spy_source == "fallback_cache":
        score -= 8
    if qqqe_source == "fallback_cache":
        score -= 6
    if vxn_source in {"none", "missing"}:
        score -= 5
    if vix_source in {"none", "missing"}:
        score -= 5

    if cache_fallback_count >= 5:
        score -= 12
    elif cache_fallback_count >= 3:
        score -= 6

    score = max(0, min(100, score))

    if score >= 85:
        quality_level = "high"
    elif score >= 70:
        quality_level = "medium"
    elif score >= 50:
        quality_level = "low"
    else:
        quality_level = "poor"

    if score >= 85:
        confidence = "high"
    elif score >= 70:
        confidence = "medium"
    elif score >= 50:
        confidence = "low"
    else:
        confidence = "very_low"

    if score < 50:
        warnings.append("数据质量较低，当前评分可信度不足，建议仅观察，不作为交易参考。")
    elif score < 70:
        warnings.append("数据质量一般，信号仅作弱参考，不建议重仓。")

    return {
        "core_data_available": qqq_ok,
        "qqq_fresh": cache_status.get("QQQ", {}).get("is_fresh", False),
        "spy_fresh": cache_status.get("SPY", {}).get("is_fresh", False),
        "source_by_symbol": {k: v.get("source", "missing") for k, v in cache_status.items()},
        "vxn_available": vxn_ok,
        "futures_available": futures_ok,
        "mega_cap_available_count": mega_cap_available_count,
        "cache_fallback_count": cache_fallback_count,
        "missing_symbols": missing_symbols,
        "quality_score": score,
        "quality_level": quality_level,
        "confidence": confidence,
        "warnings": warnings,
    }
