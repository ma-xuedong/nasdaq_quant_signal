"""Market state classification and summary generation."""

from __future__ import annotations

import logging
from typing import Any

from src.utils import setup_logger

logger = setup_logger("market_state")


def classify_tqqq_state(score: float) -> str:
    """
    根据 TQQQ 最终评分返回市场状态。

    规则：
        score >= 85：强多环境
        75 <= score < 85：偏多环境
        65 <= score < 75：弱多观察
        score < 65：不适合做多
    """
    try:
        score = float(score)

        if score >= 85:
            return "强多环境"
        elif score >= 75:
            return "偏多环境"
        elif score >= 65:
            return "弱多观察"
        else:
            return "不适合做多"

    except Exception as e:
        logger.error(f"分类 TQQQ 状态失败：{str(e)}")
        return "状态评估异常"


def classify_sqqq_state(score: float) -> str:
    """
    根据 SQQQ 最终评分返回市场状态。

    规则：
        score >= 85：强空环境
        75 <= score < 85：偏空环境
        65 <= score < 75：弱空观察
        score < 65：不适合做空
    """
    try:
        score = float(score)

        if score >= 85:
            return "强空环境"
        elif score >= 75:
            return "偏空环境"
        elif score >= 65:
            return "弱空观察"
        else:
            return "不适合做空"

    except Exception as e:
        logger.error(f"分类 SQQQ 状态失败：{str(e)}")
        return "状态评估异常"


def classify_overall_market_state(tqqq_score: float, sqqq_score: float) -> str:
    """
    综合判断市场状态。

    规则：
        TQQQ >= 75 且 SQQQ < 65：只观察 TQQQ
        SQQQ >= 75 且 TQQQ < 65：只观察 SQQQ
        TQQQ < 65 且 SQQQ < 65：空仓等待
        TQQQ >= 65 且 SQQQ >= 65：市场混乱，不交易
        两者分数接近（差值 < 5）：方向不明确，不交易
    """
    try:
        tqqq_score = float(tqqq_score)
        sqqq_score = float(sqqq_score)

        # 检查两者分数是否接近
        if abs(tqqq_score - sqqq_score) < 5:
            return "方向不明确，不交易"

        # TQQQ 强势
        if tqqq_score >= 75 and sqqq_score < 65:
            return "只观察 TQQQ"

        # SQQQ 强势
        if sqqq_score >= 75 and tqqq_score < 65:
            return "只观察 SQQQ"

        # 都弱
        if tqqq_score < 65 and sqqq_score < 65:
            return "空仓等待"

        # 都强（市场混乱）
        if tqqq_score >= 65 and sqqq_score >= 65:
            return "市场混乱，不交易"

        # 默认
        return "持观察态度"

    except Exception as e:
        logger.error(f"分类综合市场状态失败：{str(e)}")
        return "市场评估异常"


def generate_market_summary(
    tqqq_result: dict,
    sqqq_result: dict,
    risk_result: dict,
    final_scores: dict,
    futures_snapshot: dict | None = None,
    breadth_snapshot: dict | None = None,
    event_risk_snapshot: dict | None = None,
) -> str:
    """
    生成中文市场解释。

    输入：
        tqqq_result: TQQQ 评分结果
        sqqq_result: SQQQ 评分结果
        risk_result: 风险扣分结果
        final_scores: 最终分数 {"tqqq": score, "sqqq": score}

    返回：
        中文市场总结字符串
    """
    try:
        summary_lines = []

        # 1. 当前市场状态
        tqqq_final = final_scores.get("tqqq", 0)
        sqqq_final = final_scores.get("sqqq", 0)

        tqqq_state = classify_tqqq_state(tqqq_final)
        sqqq_state = classify_sqqq_state(sqqq_final)
        overall_state = classify_overall_market_state(tqqq_final, sqqq_final)

        summary_lines.append("【市场评估】")
        summary_lines.append(f"TQQQ 状态：{tqqq_state}")
        summary_lines.append(f"SQQQ 状态：{sqqq_state}")
        summary_lines.append(f"综合判断：{overall_state}")
        summary_lines.append("")

        # 2. 评分详情
        summary_lines.append("【评分详情】")
        tqqq_base = tqqq_result.get("base_score", 0)
        sqqq_base = sqqq_result.get("base_score", 0)
        risk_deduction = risk_result.get("deduction", 0)

        summary_lines.append(f"TQQQ 基础评分：{tqqq_base:.0f} 分")
        summary_lines.append(f"SQQQ 基础评分：{sqqq_base:.0f} 分")
        summary_lines.append(f"风险扣分：{risk_deduction:.0f} 分")
        summary_lines.append(f"TQQQ 最终评分：{tqqq_final:.0f} 分")
        summary_lines.append(f"SQQQ 最终评分：{sqqq_final:.0f} 分")
        summary_lines.append("")

        # 3. 主要支持理由（TQQQ 的正理由）
        summary_lines.append("【TQQQ 做多理由】")
        tqqq_reasons = tqqq_result.get("reasons", [])
        if tqqq_reasons:
            for i, reason in enumerate(tqqq_reasons[:5], 1):  # 只显示前5个
                if reason:
                    summary_lines.append(f"  {i}. {reason}")
        else:
            summary_lines.append("  - 无明显做多理由")
        summary_lines.append("")

        # 4. 主要反对理由（SQQQ 的正理由或风险提示）
        summary_lines.append("【做多风险与反对理由】")
        sqqq_reasons = sqqq_result.get("reasons", [])
        if sqqq_reasons:
            for i, reason in enumerate(sqqq_reasons[:3], 1):  # 只显示前3个
                if reason:
                    summary_lines.append(f"  {i}. {reason}")
        else:
            summary_lines.append("  - 无明显空头理由")

        risk_reasons = risk_result.get("reasons", [])
        if risk_reasons:
            for i, reason in enumerate(risk_reasons, 1):
                if reason:
                    summary_lines.append(f"  {i+3}. {reason}")
        summary_lines.append("")

        # 5. 警告与数据缺失说明
        summary_lines.append("【数据完整性说明】")
        tqqq_warnings = tqqq_result.get("warnings", [])
        sqqq_warnings = sqqq_result.get("warnings", [])
        all_warnings = list(set(tqqq_warnings + sqqq_warnings))  # 去重

        if all_warnings:
            for warning in all_warnings[:3]:  # 只显示前3个警告
                if warning:
                    summary_lines.append(f"  ⚠ {warning}")
        else:
            summary_lines.append("  ✓ 所有数据完整")
        summary_lines.append("")

        summary_lines.append("【期货确认】")
        futures_snapshot = futures_snapshot or {}
        if futures_snapshot.get("available"):
            nq_vs_es = futures_snapshot.get("nq_vs_es", 0)
            direction = "偏多" if nq_vs_es > 0 else "偏空" if nq_vs_es < 0 else "不明"
            summary_lines.append(
                f"  NQ 当前 {'强于' if nq_vs_es > 0 else '弱于' if nq_vs_es < 0 else '接近'} ES，期货方向 {direction}。"
            )
            summary_lines.append(
                f"  NQ 涨跌幅 {futures_snapshot.get('nq_return', 0)*100:.2f}%，相对 ES 强弱 {nq_vs_es*100:.2f}%。"
            )
        else:
            summary_lines.append("  NQ/ES 数据缺失，期货确认模块降级。")
        summary_lines.append("")

        summary_lines.append("【市场宽度】")
        breadth_snapshot = breadth_snapshot or {}
        if breadth_snapshot.get("available"):
            summary_lines.append(
                f"  Nasdaq-100 内部上涨比例为 {breadth_snapshot.get('up_ratio', 0)*100:.0f}%，"
                f"站上 MA20 比例为 {breadth_snapshot.get('above_ma20_ratio', 0)*100:.0f}%，"
                f"宽度状态为 {breadth_snapshot.get('breadth_status', 'unknown')}。"
            )
        else:
            summary_lines.append("  市场宽度可用成分股不足，宽度判断可信度下降。")
        summary_lines.append("")

        summary_lines.append("【事件风险日历】")
        event_risk_snapshot = event_risk_snapshot or {}
        today_events = event_risk_snapshot.get("today_events", [])
        upcoming_events = event_risk_snapshot.get("upcoming_events", [])
        if today_events:
            labels = [event.get("label") or event.get("type") or "事件" for event in today_events]
            summary_lines.append(
                f"  今日事件风险等级为 {event_risk_snapshot.get('risk_level', 'low')}，"
                f"共 {len(today_events)} 项事件，预计扣分 {event_risk_snapshot.get('deduction', 0):.0f} 分。"
            )
            summary_lines.append(f"  重点事件：{', '.join(labels[:3])}。")
        elif upcoming_events:
            next_event = upcoming_events[0]
            summary_lines.append(
                f"  今日无重大事件，下一项重点事件为 {next_event.get('date', '-') } 的 "
                f"{next_event.get('label') or next_event.get('type') or '事件'}。"
            )
        else:
            summary_lines.append("  当前本地事件日历未配置当日或近期重大事件。")
        summary_lines.append("")

        # 6. 结论
        summary_lines.append("【交易建议】")
        if overall_state == "只观察 TQQQ":
            summary_lines.append("  当前市场偏多，仅适合追踪 TQQQ 做多机会。")
            summary_lines.append("  不建议做空 SQQQ。")
        elif overall_state == "只观察 SQQQ":
            summary_lines.append("  当前市场偏空，仅适合追踪 SQQQ 做空机会。")
            summary_lines.append("  不建议做多 TQQQ。")
        elif overall_state == "空仓等待":
            summary_lines.append("  当前市场信号不明，TQQQ 和 SQQQ 都不具有明确优势。")
            summary_lines.append("  建议空仓等待，观察市场进一步表现。")
        elif overall_state == "市场混乱，不交易":
            summary_lines.append("  TQQQ 和 SQQQ 评分都较高，市场处于混乱状态。")
            summary_lines.append("  建议停止交易，等待市场方向明确。")
        elif overall_state == "方向不明确，不交易":
            summary_lines.append("  TQQQ 和 SQQQ 评分接近，市场方向不明确。")
            summary_lines.append("  建议继续观察，不进行交易操作。")
        else:
            summary_lines.append("  请根据风险承受能力灵活操作。")
        summary_lines.append("")

        # 7. 风险提示
        summary_lines.append("【风险提示】")
        summary_lines.append("  • TQQQ/SQQQ 为三倍杠杆 ETF，日内波动剧烈。")
        summary_lines.append("  • 本系统仅作参考，不构成投资建议。")
        summary_lines.append("  • 请严格控制仓位和风险，设置好止损。")
        summary_lines.append("  • 历史表现不代表未来结果。")

        return "\n".join(summary_lines)

    except Exception as e:
        logger.error(f"生成市场总结失败：{str(e)}")
        return f"市场总结生成异常：{str(e)}"
