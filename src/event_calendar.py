"""Local event calendar and event-risk helpers."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import config.settings as settings
from src.utils import setup_logger

logger = setup_logger("event_calendar")


DEFAULT_EVENT_RULES = {
    "CPI": {"severity": "high", "deduction": 15},
    "FOMC": {"severity": "high", "deduction": 20},
    "NFP": {"severity": "high", "deduction": 12},
    "NFPYY": {"severity": "high", "deduction": 12},
    "EARNINGS": {"severity": "medium", "deduction": 15},
    "GAP": {"severity": "medium", "deduction": 15},
}


def _parse_date(date_str: str) -> datetime | None:
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except (TypeError, ValueError):
        return None


def _normalize_event(raw_event: Any) -> dict[str, Any] | None:
    if isinstance(raw_event, str):
        event_type = raw_event.strip().upper()
        if not event_type:
            return None
        rule = DEFAULT_EVENT_RULES.get(event_type, {})
        return {
            "name": event_type,
            "type": event_type,
            "label": event_type,
            "severity": rule.get("severity", "medium"),
            "deduction": float(rule.get("deduction", 10)),
            "description": "",
            "symbols": [],
        }

    if not isinstance(raw_event, dict):
        return None

    raw_type = raw_event.get("type") or raw_event.get("name") or raw_event.get("event")
    event_type = str(raw_type or "UNKNOWN").strip().upper()
    if not event_type:
        return None

    rule = DEFAULT_EVENT_RULES.get(event_type, {})
    severity = str(raw_event.get("severity") or rule.get("severity", "medium")).strip().lower()
    if severity not in {"low", "medium", "high"}:
        severity = "medium"

    deduction = raw_event.get("deduction", rule.get("deduction", 10))
    try:
        deduction_value = float(deduction)
    except (TypeError, ValueError):
        deduction_value = float(rule.get("deduction", 10))

    symbols = raw_event.get("symbols", [])
    if not isinstance(symbols, list):
        symbols = [symbols] if symbols else []

    return {
        "name": str(raw_event.get("name") or event_type),
        "type": event_type,
        "label": str(raw_event.get("label") or raw_event.get("name") or event_type),
        "severity": severity,
        "deduction": deduction_value,
        "description": str(raw_event.get("description") or ""),
        "symbols": [str(symbol) for symbol in symbols if symbol],
    }


def load_risk_events() -> dict[str, list[dict[str, Any]]]:
    """Load and normalize local risk events from settings."""
    normalized: dict[str, list[dict[str, Any]]] = {}

    raw_events = getattr(settings, "RISK_EVENTS", {}) or {}
    if not isinstance(raw_events, dict):
        return normalized

    for date_str, events in raw_events.items():
        if _parse_date(date_str) is None:
            logger.warning("忽略非法风险事件日期: %s", date_str)
            continue

        event_list = events if isinstance(events, list) else [events]
        normalized_events = []
        for raw_event in event_list:
            event = _normalize_event(raw_event)
            if event is not None:
                normalized_events.append(event)

        normalized[date_str] = normalized_events

    return normalized


def get_events_for_date(date_str: str, risk_events: dict[str, list[dict[str, Any]]] | None = None) -> list[dict[str, Any]]:
    """Return normalized events for a given date."""
    events = risk_events if risk_events is not None else load_risk_events()
    return list(events.get(date_str, []))


def get_upcoming_events(
    date_str: str,
    lookahead_days: int | None = None,
    risk_events: dict[str, list[dict[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    """Return normalized upcoming events within the configured window."""
    current_date = _parse_date(date_str)
    if current_date is None:
        return []

    lookahead = int(lookahead_days or getattr(settings, "EVENT_RISK_LOOKAHEAD_DAYS", 7) or 7)
    events = risk_events if risk_events is not None else load_risk_events()
    upcoming: list[dict[str, Any]] = []

    end_date = current_date + timedelta(days=lookahead)
    for event_date, daily_events in events.items():
        parsed_date = _parse_date(event_date)
        if parsed_date is None or parsed_date <= current_date or parsed_date > end_date:
            continue

        for event in daily_events:
            event_with_date = dict(event)
            event_with_date["date"] = event_date
            upcoming.append(event_with_date)

    upcoming.sort(key=lambda item: (item.get("date", ""), item.get("deduction", 0) * -1))
    return upcoming


def _build_event_reason(event: dict[str, Any]) -> str:
    label = event.get("label") or event.get("type") or "风险事件"
    description = event.get("description")
    deduction = float(event.get("deduction", 0) or 0)
    if description:
        return f"{label}：{description}，扣分 {deduction:.0f} 分。"
    return f"{label} 风险较高，扣分 {deduction:.0f} 分。"


def calculate_event_risk(
    date_str: str,
    indicator_snapshot: dict | None = None,
    risk_events: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Calculate the event-driven risk for a given date."""
    del indicator_snapshot

    events = get_events_for_date(date_str, risk_events=risk_events)
    deduction = sum(float(event.get("deduction", 0) or 0) for event in events)
    risk_level = "low"
    if deduction >= 25 or any(event.get("severity") == "high" for event in events):
        risk_level = "high"
    elif deduction > 0:
        risk_level = "medium"

    return {
        "date": date_str,
        "deduction": min(deduction, 100),
        "risk_level": risk_level,
        "events": [str(event.get("label") or event.get("type") or "") for event in events],
        "event_details": events,
        "reasons": [_build_event_reason(event) for event in events],
    }


def build_event_risk_snapshot(
    date_str: str,
    indicator_snapshot: dict | None = None,
    lookahead_days: int | None = None,
    risk_events: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Build a UI-friendly snapshot for today's and upcoming event risk."""
    events = risk_events if risk_events is not None else load_risk_events()
    today_risk = calculate_event_risk(date_str, indicator_snapshot=indicator_snapshot, risk_events=events)
    upcoming_events = get_upcoming_events(date_str, lookahead_days=lookahead_days, risk_events=events)

    configured_event_count = sum(len(daily_events) for daily_events in events.values())
    return {
        "available": True,
        "date": date_str,
        "configured_event_count": configured_event_count,
        "today_events": today_risk.get("event_details", []),
        "today_event_count": len(today_risk.get("event_details", [])),
        "upcoming_events": upcoming_events,
        "upcoming_event_count": len(upcoming_events),
        "risk_level": today_risk.get("risk_level", "low"),
        "deduction": float(today_risk.get("deduction", 0) or 0),
        "reasons": today_risk.get("reasons", []),
        "has_high_risk_event": any(event.get("severity") == "high" for event in today_risk.get("event_details", [])),
    }