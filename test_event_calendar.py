"""Unit tests for local event calendar helpers."""

from unittest.mock import patch

from src.event_calendar import (
    build_event_risk_snapshot,
    calculate_event_risk,
    get_events_for_date,
    get_upcoming_events,
    load_risk_events,
)
from src.risk_filter import get_risk_deduction


SAMPLE_RISK_EVENTS = {
    "2026-05-14": [
        {"type": "CPI", "label": "美国 CPI", "severity": "high"},
        {"type": "EARNINGS", "label": "NVDA 财报", "deduction": 12},
    ],
    "2026-05-16": [
        {"type": "FOMC", "label": "FOMC 纪要", "severity": "high"},
    ],
}


ALIAS_RISK_EVENTS = {
    "2026-05-18": [
        {"event_type": "cpi", "title": "美国 CPI 别名", "importance": "high", "risk_score": 18},
    ]
}


def test_load_risk_events_normalizes_entries() -> None:
    with patch("src.event_calendar.settings.RISK_EVENTS", SAMPLE_RISK_EVENTS):
        events = load_risk_events()

    assert "2026-05-14" in events
    assert events["2026-05-14"][0]["type"] == "CPI"
    assert events["2026-05-14"][1]["deduction"] == 12


def test_get_events_and_upcoming_events() -> None:
    with patch("src.event_calendar.settings.RISK_EVENTS", SAMPLE_RISK_EVENTS):
        today_events = get_events_for_date("2026-05-14")
        upcoming_events = get_upcoming_events("2026-05-14", lookahead_days=3)

    assert len(today_events) == 2
    assert len(upcoming_events) == 1
    assert upcoming_events[0]["date"] == "2026-05-16"


def test_calculate_event_risk_and_snapshot() -> None:
    with patch("src.event_calendar.settings.RISK_EVENTS", SAMPLE_RISK_EVENTS):
        risk_result = calculate_event_risk("2026-05-14")
        snapshot = build_event_risk_snapshot("2026-05-14")

    assert risk_result["deduction"] == 27
    assert risk_result["risk_level"] == "high"
    assert snapshot["today_event_count"] == 2
    assert snapshot["upcoming_event_count"] == 1
    assert snapshot["has_high_risk_event"] is True


def test_risk_filter_uses_event_calendar_snapshot() -> None:
    with patch("src.event_calendar.settings.RISK_EVENTS", SAMPLE_RISK_EVENTS):
        result = get_risk_deduction("2026-05-14")

    assert result["deduction"] == 27
    assert "美国 CPI" in result["events"]
    assert result["event_risk_snapshot"]["today_event_count"] == 2


def test_alias_fields_are_normalized() -> None:
    with patch("src.event_calendar.settings.RISK_EVENTS", ALIAS_RISK_EVENTS):
        events = load_risk_events()
        snapshot = build_event_risk_snapshot("2026-05-18")

    event = events["2026-05-18"][0]
    assert event["type"] == "CPI"
    assert event["label"] == "美国 CPI 别名"
    assert event["name"] == "美国 CPI 别名"
    assert event["severity"] == "high"
    assert event["deduction"] == 18
    assert snapshot["deduction"] == 18


def main() -> None:
    test_load_risk_events_normalizes_entries()
    test_get_events_and_upcoming_events()
    test_calculate_event_risk_and_snapshot()
    test_risk_filter_uses_event_calendar_snapshot()
    test_alias_fields_are_normalized()
    print("test_event_calendar passed")


if __name__ == "__main__":
    main()