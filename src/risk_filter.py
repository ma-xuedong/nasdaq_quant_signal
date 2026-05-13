"""Risk filter module for TQQQ/SQQQ scoring."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from config.settings import RISK_EVENTS
from src.utils import setup_logger

logger = setup_logger("risk_filter")


def check_risk_events(date_str: str) -> list[str]:
    """
    根据 config/settings.py 中的 RISK_EVENTS 检查当天是否有风险事件。

    参数：
        date_str: 日期字符串，格式如 "2026-05-13"

    返回：
        ["CPI", "FOMC"] 或 []
    """
    try:
        if not RISK_EVENTS:
            return []

        if date_str in RISK_EVENTS:
            return RISK_EVENTS[date_str]

        return []

    except Exception as e:
        logger.error(f"检查风险事件失败：{str(e)}")
        return []


def get_risk_deduction(
    date_str: str,
    indicator_snapshot: dict | None = None
) -> dict:
    """
    计算风险扣分。

    参数：
        date_str: 日期字符串，格式如 "2026-05-13"
        indicator_snapshot: 指标快照（可选，用于动态计算风险）

    返回：
    {
        "deduction": 10,
        "events": ["CPI"],
        "reasons": [
            "当天存在 CPI 数据公布，市场波动风险较高，扣分10分。"
        ]
    }
    """
    deduction = 0
    events = []
    reasons = []

    try:
        # 检查预定义的风险事件
        risk_events = check_risk_events(date_str)

        if risk_events:
            events.extend(risk_events)

            for event in risk_events:
                event_deduction = _get_event_deduction(event)
                deduction += event_deduction
                reasons.append(_get_event_reason(event, event_deduction))

        # 检查动态风险因素（如果提供了指标快照）
        if indicator_snapshot:
            dynamic_deduction, dynamic_reasons = _check_dynamic_risks(
                indicator_snapshot
            )
            deduction += dynamic_deduction
            reasons.extend(dynamic_reasons)

        # 限制总扣分不超过100
        deduction = min(deduction, 100)

        logger.info(f"风险扣分完成：{deduction}")

        return {
            "deduction": deduction,
            "events": events,
            "reasons": reasons
        }

    except Exception as e:
        logger.error(f"计算风险扣分失败：{str(e)}")
        return {
            "deduction": 0,
            "events": [],
            "reasons": [f"风险评估异常：{str(e)}"]
        }


def _get_event_deduction(event: str) -> float:
    """获取具体事件的扣分。"""
    deduction_map = {
        "CPI": 15,           # CPI公布：-10到-20，取中等值15
        "FOMC": 20,          # FOMC会议：-15到-25，取中等值20
        "NFPYY": 12,         # 非农公布：-10到-15，取中等值12
        "EARNINGS": 15,      # 权重股财报：-10到-20，取中等值15
        "GAP": 15,           # 盘前缺口：-10到-20，取中等值15
    }
    return deduction_map.get(event, 10)


def _get_event_reason(event: str, deduction: float) -> str:
    """获取事件的说明。"""
    reason_map = {
        "CPI": f"当天公布 CPI 数据，市场波动风险较高，扣分 {deduction:.0f} 分。",
        "FOMC": f"当天进行 FOMC 会议，政策变化可能导致剧烈波动，扣分 {deduction:.0f} 分。",
        "NFPYY": f"当天公布非农就业数据，市场波动风险较大，扣分 {deduction:.0f} 分。",
        "EARNINGS": f"权重股存在财报日期，风险集中，扣分 {deduction:.0f} 分。",
        "GAP": f"盘前存在大幅缺口，市场风险提升，扣分 {deduction:.0f} 分。",
    }
    return reason_map.get(event, f"存在风险事件，扣分 {deduction:.0f} 分。")


def _check_dynamic_risks(snapshot: dict) -> tuple[float, list[str]]:
    """检查动态风险因素。"""
    deduction = 0
    reasons = []

    try:
        qqq = snapshot.get("qqq", {})

        # 风险1：QQQ 位于 MA20 和 MA50 之间反复震荡
        price = qqq.get("price", 0)
        ma20 = qqq.get("ma20", 0)
        ma50 = qqq.get("ma50", 0)

        if ma20 and ma50 and ma20 < price < ma50:
            deduction += 10
            reasons.append(f"QQQ 价格位于 MA20 ${ma20:.2f} 和 MA50 ${ma50:.2f} 之间反复震荡，趋势不清，扣分 10 分。")

        # 风险2：VXN 暴涨但方向不清（简化处理）
        # 由于快照中没有VXN数据，这里先跳过

    except Exception as e:
        logger.warning(f"动态风险检查失败：{str(e)}")

    return deduction, reasons
