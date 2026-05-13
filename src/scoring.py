"""TQQQ/SQQQ scoring model."""

from __future__ import annotations

import logging
from typing import Any

from src.utils import setup_logger

logger = setup_logger("scoring")


def calculate_tqqq_score(indicator_snapshot: dict) -> dict:
    """
    计算 TQQQ 做多基础评分（满分100分）。

    返回：
    {
        "base_score": 78,
        "module_scores": {
            "trend": 22,
            "futures": 8,
            "volatility": 10,
            "breadth": 11,
            "mega_cap_tech": 10,
            "intraday": 6,
            "macro": 5
        },
        "reasons": [
            "QQQ 位于 MA20 和 MA50 上方，趋势偏强。"
        ],
        "warnings": [
            "VXN 数据缺失，波动率模块使用 VIX 替代。"
        ]
    }
    """
    module_scores = {}
    reasons = []
    warnings = []

    try:
        # 模块1：QQQ趋势结构（25分）
        trend_score = _score_tqqq_trend(indicator_snapshot, reasons, warnings)
        module_scores["trend"] = trend_score

        # 模块2：期货确认（15分）
        futures_score = _score_tqqq_futures(indicator_snapshot, reasons, warnings)
        module_scores["futures"] = futures_score

        # 模块3：波动率环境（15分）
        volatility_score = _score_tqqq_volatility(indicator_snapshot, reasons, warnings)
        module_scores["volatility"] = volatility_score

        # 模块4：市场宽度（15分）
        breadth_score = _score_tqqq_breadth(indicator_snapshot, reasons, warnings)
        module_scores["breadth"] = breadth_score

        # 模块5：权重科技股强弱（10分）
        tech_score = _score_tqqq_mega_cap_tech(indicator_snapshot, reasons, warnings)
        module_scores["mega_cap_tech"] = tech_score

        # 模块6：成交量/VWAP/开盘结构（10分）
        intraday_score = _score_tqqq_intraday(indicator_snapshot, reasons, warnings)
        module_scores["intraday"] = intraday_score

        # 模块7：利率与美元（10分）
        macro_score = _score_tqqq_macro(indicator_snapshot, reasons, warnings)
        module_scores["macro"] = macro_score

        # 计算总分
        base_score = sum(module_scores.values())
        base_score = max(0, min(100, base_score))  # 限制在0-100之间

        logger.info(f"TQQQ 做多评分完成：{base_score}")

        return {
            "base_score": base_score,
            "module_scores": module_scores,
            "reasons": reasons,
            "warnings": warnings
        }

    except Exception as e:
        logger.error(f"计算 TQQQ 评分失败：{str(e)}")
        return {
            "base_score": 0,
            "module_scores": {},
            "reasons": [],
            "warnings": [f"评分计算失败：{str(e)}"]
        }


def _score_tqqq_trend(snapshot: dict, reasons: list, warnings: list) -> float:
    """TQQQ趋势结构：25分。"""
    score = 0
    qqq = snapshot.get("qqq", {})

    if not qqq:
        warnings.append("QQQ 数据缺失，趋势模块给 0 分。")
        return 0

    try:
        price = qqq.get("price", 0)
        ma20 = qqq.get("ma20", 0)
        ma50 = qqq.get("ma50", 0)
        ma20_slope = qqq.get("ma20_slope", 0)
        ma50_slope = qqq.get("ma50_slope", 0)

        # QQQ 当前价格 > MA20：+8
        if price > ma20:
            score += 8
            reasons.append(f"QQQ 价格 ${price:.2f} 位于 MA20 ${ma20:.2f} 上方。")
        else:
            reasons.append(f"QQQ 价格 ${price:.2f} 低于 MA20 ${ma20:.2f}。")

        # QQQ 当前价格 > MA50：+8
        if price > ma50:
            score += 8
            reasons.append(f"QQQ 价格 ${price:.2f} 位于 MA50 ${ma50:.2f} 上方。")
        else:
            reasons.append(f"QQQ 价格 ${price:.2f} 低于 MA50 ${ma50:.2f}。")

        # MA20 斜率向上：+5
        if ma20_slope > 0:
            score += 5
            reasons.append(f"MA20 斜率向上 {ma20_slope:.2f}，趋势向上。")
        else:
            reasons.append(f"MA20 斜率向下 {ma20_slope:.2f}，趋势向下。")

        # MA50 斜率向上：+4
        if ma50_slope > 0:
            score += 4
            reasons.append(f"MA50 斜率向上 {ma50_slope:.2f}，中期趋势向上。")
        else:
            reasons.append(f"MA50 斜率向下 {ma50_slope:.2f}，中期趋势向下。")

    except Exception as e:
        logger.warning(f"趋势模块计算失败：{str(e)}")
        warnings.append(f"趋势模块计算异常：{str(e)}")

    return min(score, 25)


def _score_tqqq_futures(snapshot: dict, reasons: list, warnings: list) -> float:
    """TQQQ期货确认：15分（第一版使用替代逻辑）。"""
    score = 0
    qqq = snapshot.get("qqq", {})

    if not qqq:
        return 0

    try:
        daily_return = qqq.get("daily_return", 0)

        # QQQ 当日涨幅 > 0：+5
        if daily_return > 0:
            score += 5
            reasons.append(f"QQQ 当日上涨 {daily_return*100:.2f}%。")
        else:
            reasons.append(f"QQQ 当日下跌 {daily_return*100:.2f}%。")

        # QQQ 当日涨幅 > 0.5%：额外 +3
        if daily_return > 0.005:
            score += 3
            reasons.append(f"QQQ 涨幅超过 0.5%，表现强势。")

        # QQQ 强于 SPY：+5
        qqq_vs_spy = snapshot.get("relative_strength", {}).get("qqq_vs_spy", 0)
        if qqq_vs_spy > 0:
            score += 5
            reasons.append(f"QQQ 相对 SPY 强势 {qqq_vs_spy:.4f}，科技相对大盘表现好。")
        else:
            reasons.append(f"QQQ 相对 SPY 弱势 {qqq_vs_spy:.4f}。")

        # 盘前趋势稳定上行：+2（简化处理）
        if daily_return > 0.002:
            score += 2
            reasons.append("盘前及日内趋势稳定向上。")

    except Exception as e:
        logger.warning(f"期货模块计算失败：{str(e)}")

    return min(score, 15)


def _score_tqqq_volatility(snapshot: dict, reasons: list, warnings: list) -> float:
    """TQQQ波动率环境：15分。"""
    score = 0
    vol = snapshot.get("relative_strength", {})  # 这里应该是波动率数据，但快照中没有，先用相对强弱替代

    # 首先检查是否有VXN和VIX数据
    # 在当前快照结构中，波动率数据可能不直接可得
    # 所以给中性分并说明

    try:
        # 由于指标快照可能不包含VXN/VIX，给中性分
        score = 7  # 中性分
        warnings.append("波动率数据（VIX/VXN）未在快照中，按中性处理，给 7 分。")

    except Exception as e:
        logger.warning(f"波动率模块计算失败：{str(e)}")
        warnings.append(f"波动率模块计算异常：{str(e)}")

    return min(score, 15)


def _score_tqqq_breadth(snapshot: dict, reasons: list, warnings: list) -> float:
    """TQQQ市场宽度：15分。"""
    score = 0

    try:
        qqq = snapshot.get("qqq", {})
        rel_strength = snapshot.get("relative_strength", {})

        # QQQE 涨幅接近或强于 QQQ：+6
        qqqe_vs_qqq = rel_strength.get("qqqe_vs_qqq", 0)
        if qqqe_vs_qqq >= 0:
            score += 6
            reasons.append(f"QQQE 相对 QQQ 强势或相当 {qqqe_vs_qqq:.4f}，市场宽度良好。")
        else:
            reasons.append(f"QQQE 相对 QQQ 弱势 {qqqe_vs_qqq:.4f}。")

        # 科技权重股多数上涨：+6
        tech = snapshot.get("mega_cap_tech", {})
        tech_up = tech.get("up_count", 0)
        if tech_up >= 6:
            score += 6
            reasons.append(f"权重科技股中 {tech_up} 只上涨，市场人气良好。")
        elif tech_up >= 4:
            reasons.append(f"权重科技股中 {tech_up} 只上涨，表现一般。")
        else:
            reasons.append(f"权重科技股中仅 {tech_up} 只上涨，市场人气不佳。")

        # QQQ 成交量不异常萎缩：+3
        volume_ratio = qqq.get("volume_ratio", 1.0)
        if volume_ratio >= 0.8:
            score += 3
            reasons.append(f"QQQ 成交量比例 {volume_ratio:.2f}x，成交量充足。")
        else:
            reasons.append(f"QQQ 成交量比例 {volume_ratio:.2f}x，成交量不足。")

    except Exception as e:
        logger.warning(f"市场宽度模块计算失败：{str(e)}")
        warnings.append(f"市场宽度模块计算异常：{str(e)}")

    return min(score, 15)


def _score_tqqq_mega_cap_tech(snapshot: dict, reasons: list, warnings: list) -> float:
    """TQQQ权重科技股强弱：10分。"""
    score = 0

    try:
        tech = snapshot.get("mega_cap_tech", {})
        tech_up = tech.get("up_count", 0)

        # 8只中，6只及以上上涨：+10
        if tech_up >= 6:
            score = 10
            reasons.append(f"8只权重科技股中 {tech_up} 只上涨，集体走强。")
        # 4到5只上涨：+5
        elif tech_up >= 4:
            score = 5
            reasons.append(f"8只权重科技股中 {tech_up} 只上涨，表现一般。")
        else:
            score = 0
            reasons.append(f"8只权重科技股中仅 {tech_up} 只上涨，集体走弱。")

    except Exception as e:
        logger.warning(f"权重科技股模块计算失败：{str(e)}")
        warnings.append(f"权重科技股模块计算异常：{str(e)}")

    return score


def _score_tqqq_intraday(snapshot: dict, reasons: list, warnings: list) -> float:
    """TQQQ成交量/VWAP/开盘结构：10分。"""
    score = 0

    try:
        qqq = snapshot.get("qqq", {})
        intraday = snapshot.get("intraday", {})

        # QQQ 成交量比例 >= 0.8：+3
        volume_ratio = qqq.get("volume_ratio", 1.0)
        if volume_ratio >= 0.8:
            score += 3
            reasons.append(f"QQQ 成交量比例 {volume_ratio:.2f}x，放量特征明显。")

        # QQQ 成交量比例 >= 1.0：额外 +2
        if volume_ratio >= 1.0:
            score += 2

        # QQQ 当前价格 > VWAP：+3（如果有分钟线数据）
        vwap = intraday.get("vwap", None)
        if vwap is not None:
            price = qqq.get("price", 0)
            if price > vwap:
                score += 3
                reasons.append(f"QQQ 价格 ${price:.2f} 位于 VWAP ${vwap:.2f} 上方，强势特征。")
            else:
                reasons.append(f"QQQ 价格 ${price:.2f} 低于 VWAP ${vwap:.2f}。")
        else:
            warnings.append("缺少分钟线数据，VWAP 模块仅根据成交量给分，最多 5 分。")

        # 开盘30分钟结构偏强：+2（如果有分钟线数据）
        opening = intraday.get("opening_30min", {})
        if opening.get("has_data"):
            if opening.get("is_strong_opening"):
                score += 2
                reasons.append(f"开盘30分钟结构偏强：{opening.get('description', '')}")
            else:
                reasons.append(f"开盘30分钟结构偏弱：{opening.get('description', '')}")

    except Exception as e:
        logger.warning(f"日内模块计算失败：{str(e)}")
        warnings.append(f"日内模块计算异常：{str(e)}")

    return min(score, 10)


def _score_tqqq_macro(snapshot: dict, reasons: list, warnings: list) -> float:
    """TQQQ利率与美元：10分（第一版中性处理）。"""
    score = 5
    warnings.append("利率与美元模块暂未接入真实数据，当前按中性处理，给 5 分。")
    return score


def calculate_sqqq_score(indicator_snapshot: dict) -> dict:
    """
    计算 SQQQ 做空基础评分（满分100分）。

    返回结构同 calculate_tqqq_score。
    """
    module_scores = {}
    reasons = []
    warnings = []

    try:
        # 模块1：QQQ破位程度（25分）
        breakdown_score = _score_sqqq_breakdown(indicator_snapshot, reasons, warnings)
        module_scores["breakdown"] = breakdown_score

        # 模块2：期货走弱（20分）
        weakness_score = _score_sqqq_weakness(indicator_snapshot, reasons, warnings)
        module_scores["weakness"] = weakness_score

        # 模块3：波动率上行（20分）
        volatility_score = _score_sqqq_volatility(indicator_snapshot, reasons, warnings)
        module_scores["volatility"] = volatility_score

        # 模块4：市场宽度恶化（15分）
        breadth_score = _score_sqqq_breadth(indicator_snapshot, reasons, warnings)
        module_scores["breadth"] = breadth_score

        # 模块5：权重科技股走弱（10分）
        tech_score = _score_sqqq_mega_cap_tech(indicator_snapshot, reasons, warnings)
        module_scores["mega_cap_tech"] = tech_score

        # 模块6：反弹失败形态（10分）
        reversal_score = _score_sqqq_reversal(indicator_snapshot, reasons, warnings)
        module_scores["reversal"] = reversal_score

        # 计算总分
        base_score = sum(module_scores.values())
        base_score = max(0, min(100, base_score))  # 限制在0-100之间

        logger.info(f"SQQQ 做空评分完成：{base_score}")

        return {
            "base_score": base_score,
            "module_scores": module_scores,
            "reasons": reasons,
            "warnings": warnings
        }

    except Exception as e:
        logger.error(f"计算 SQQQ 评分失败：{str(e)}")
        return {
            "base_score": 0,
            "module_scores": {},
            "reasons": [],
            "warnings": [f"评分计算失败：{str(e)}"]
        }


def _score_sqqq_breakdown(snapshot: dict, reasons: list, warnings: list) -> float:
    """SQQQ破位程度：25分。"""
    score = 0
    qqq = snapshot.get("qqq", {})

    if not qqq:
        warnings.append("QQQ 数据缺失，破位模块给 0 分。")
        return 0

    try:
        price = qqq.get("price", 0)
        ma20 = qqq.get("ma20", 0)
        ma50 = qqq.get("ma50", 0)
        ma20_slope = qqq.get("ma20_slope", 0)
        ma50_slope = qqq.get("ma50_slope", 0)

        # QQQ 当前价格 < MA20：+8
        if price < ma20:
            score += 8
            reasons.append(f"QQQ 价格 ${price:.2f} 跌破 MA20 ${ma20:.2f}。")

        # QQQ 当前价格 < MA50：+10
        if price < ma50:
            score += 10
            reasons.append(f"QQQ 价格 ${price:.2f} 跌破 MA50 ${ma50:.2f}，破位显著。")

        # MA20 斜率向下：+4
        if ma20_slope < 0:
            score += 4
            reasons.append(f"MA20 斜率向下 {ma20_slope:.2f}，短期趋势恶化。")

        # MA50 斜率向下：+3
        if ma50_slope < 0:
            score += 3
            reasons.append(f"MA50 斜率向下 {ma50_slope:.2f}，中期趋势恶化。")

    except Exception as e:
        logger.warning(f"破位模块计算失败：{str(e)}")
        warnings.append(f"破位模块计算异常：{str(e)}")

    return min(score, 25)


def _score_sqqq_weakness(snapshot: dict, reasons: list, warnings: list) -> float:
    """SQQQ期货走弱：20分。"""
    score = 0
    qqq = snapshot.get("qqq", {})

    if not qqq:
        return 0

    try:
        daily_return = qqq.get("daily_return", 0)

        # QQQ 当日下跌：+6
        if daily_return < 0:
            score += 6
            reasons.append(f"QQQ 当日下跌 {daily_return*100:.2f}%。")

        # QQQ 当日跌幅超过 0.5%：额外 +4
        if daily_return < -0.005:
            score += 4
            reasons.append(f"QQQ 跌幅超过 0.5%，下跌力度强。")

        # QQQ 弱于 SPY：+7
        qqq_vs_spy = snapshot.get("relative_strength", {}).get("qqq_vs_spy", 0)
        if qqq_vs_spy < 0:
            score += 7
            reasons.append(f"QQQ 相对 SPY 弱势 {abs(qqq_vs_spy):.4f}，科技相对大盘表现差。")

        # 盘前趋势持续走弱：+3（简化处理）
        if daily_return < -0.002:
            score += 3
            reasons.append("盘前及日内趋势持续走弱。")

    except Exception as e:
        logger.warning(f"弱势模块计算失败：{str(e)}")

    return min(score, 20)


def _score_sqqq_volatility(snapshot: dict, reasons: list, warnings: list) -> float:
    """SQQQ波动率上行：20分。"""
    score = 0

    try:
        # 由于指标快照中没有VIX/VXN直接数据，给中性分
        score = 10
        warnings.append("波动率数据（VIX/VXN）未在快照中，按中性处理，给 10 分。")

    except Exception as e:
        logger.warning(f"波动率模块计算失败：{str(e)}")
        warnings.append(f"波动率模块计算异常：{str(e)}")

    return min(score, 20)


def _score_sqqq_breadth(snapshot: dict, reasons: list, warnings: list) -> float:
    """SQQQ市场宽度恶化：15分。"""
    score = 0

    try:
        qqq = snapshot.get("qqq", {})
        rel_strength = snapshot.get("relative_strength", {})

        # QQQE 弱于 QQQ：+5
        qqqe_vs_qqq = rel_strength.get("qqqe_vs_qqq", 0)
        if qqqe_vs_qqq < 0:
            score += 5
            reasons.append(f"QQQE 相对 QQQ 弱势 {abs(qqqe_vs_qqq):.4f}，市场宽度恶化。")

        # 权重科技股多数下跌：+7
        tech = snapshot.get("mega_cap_tech", {})
        tech_down = tech.get("down_count", 0)
        if tech_down >= 6:
            score += 7
            reasons.append(f"权重科技股中 {tech_down} 只下跌，市场人气低迷。")

        # QQQ 下跌且成交量放大：+3
        daily_return = qqq.get("daily_return", 0)
        volume_ratio = qqq.get("volume_ratio", 1.0)
        if daily_return < 0 and volume_ratio > 1.2:
            score += 3
            reasons.append(f"QQQ 下跌且成交量放大 {volume_ratio:.2f}x，下跌力度强。")

    except Exception as e:
        logger.warning(f"市场宽度模块计算失败：{str(e)}")
        warnings.append(f"市场宽度模块计算异常：{str(e)}")

    return min(score, 15)


def _score_sqqq_mega_cap_tech(snapshot: dict, reasons: list, warnings: list) -> float:
    """SQQQ权重科技股走弱：10分。"""
    score = 0

    try:
        tech = snapshot.get("mega_cap_tech", {})
        tech_down = tech.get("down_count", 0)

        # 8只中，6只及以上下跌：+10
        if tech_down >= 6:
            score = 10
            reasons.append(f"8只权重科技股中 {tech_down} 只下跌，集体走弱。")
        # 4到5只下跌：+5
        elif tech_down >= 4:
            score = 5
            reasons.append(f"8只权重科技股中 {tech_down} 只下跌，表现一般。")
        else:
            score = 0
            reasons.append(f"8只权重科技股中仅 {tech_down} 只下跌，集体走强。")

    except Exception as e:
        logger.warning(f"权重科技股模块计算失败：{str(e)}")
        warnings.append(f"权重科技股模块计算异常：{str(e)}")

    return score


def _score_sqqq_reversal(snapshot: dict, reasons: list, warnings: list) -> float:
    """SQQQ反弹失败形态：10分。"""
    score = 0

    try:
        qqq = snapshot.get("qqq", {})
        intraday = snapshot.get("intraday", {})

        # QQQ 当前价格 < VWAP：+4
        vwap = intraday.get("vwap", None)
        if vwap is not None:
            price = qqq.get("price", 0)
            if price < vwap:
                score += 4
                reasons.append(f"QQQ 价格 ${price:.2f} 低于 VWAP ${vwap:.2f}，反弹失败。")

        # 开盘30分钟结构偏弱：+3
        opening = intraday.get("opening_30min", {})
        if opening.get("has_data"):
            if opening.get("is_weak_opening"):
                score += 3
                reasons.append(f"开盘30分钟结构偏弱：{opening.get('description', '')}")

        # 如果没有分钟线数据
        if not vwap and not opening.get("has_data"):
            warnings.append("缺少分钟线数据，反弹形态模块给 0 到 3 分。")

    except Exception as e:
        logger.warning(f"反弹形态模块计算失败：{str(e)}")
        warnings.append(f"反弹形态模块计算异常：{str(e)}")

    return min(score, 10)


def calculate_final_score(base_score: float, risk_deduction: float) -> float:
    """
    计算最终评分。
    
    final_score = max(base_score - risk_deduction, 0)
    """
    final = max(base_score - risk_deduction, 0)
    return final
