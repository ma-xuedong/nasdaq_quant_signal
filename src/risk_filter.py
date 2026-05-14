"""Risk filter module for TQQQ/SQQQ scoring."""

from __future__ import annotations

import logging
from typing import Any

from src.event_calendar import build_event_risk_snapshot, get_events_for_date
from src.utils import setup_logger

logger = setup_logger("risk_filter")


def check_risk_events(date_str: str) -> list[str]:
    """
    根据本地事件日历检查当天是否有风险事件。

    参数：
        date_str: 日期字符串，格式如 "2026-05-13"

    返回：
        ["CPI", "FOMC"] 或 []
    """
    try:
        return [event.get("label") or event.get("type") or "" for event in get_events_for_date(date_str)]

    except Exception as e:
        logger.error(f"检查风险事件失败：{str(e)}")
        return []


def get_risk_deduction(
    date_str: str,
    indicator_snapshot: dict | None = None,
    event_risk_snapshot: dict | None = None,
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
    deduction = 0.0
    events: list[str] = []
    reasons: list[str] = []

    try:
        snapshot = event_risk_snapshot or build_event_risk_snapshot(
            date_str,
            indicator_snapshot=indicator_snapshot,
        )

        deduction += float(snapshot.get("deduction", 0) or 0)
        events.extend(
            [event.get("label") or event.get("type") or "" for event in snapshot.get("today_events", [])]
        )
        reasons.extend(snapshot.get("reasons", []))

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
            "reasons": reasons,
            "event_risk_snapshot": snapshot,
        }

    except Exception as e:
        logger.error(f"计算风险扣分失败：{str(e)}")
        return {
            "deduction": 0,
            "events": [],
            "reasons": [f"风险评估异常：{str(e)}"],
            "event_risk_snapshot": event_risk_snapshot or {"available": False, "date": date_str},
        }


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
