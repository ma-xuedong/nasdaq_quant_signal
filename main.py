"""Console entry point for TQQQ / SQQQ signal system."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from config.settings import CORE_REALTIME_SYMBOLS, RISK_DISCLOSURE
from src.pipeline import run_signal_pipeline


def print_section(title: str) -> None:
    """Print a simple console section title."""
    print()
    print("=" * 12 + f" {title} " + "=" * 12)


def print_warnings(warnings: list[str]) -> None:
    """Print warnings in a readable format."""
    if not warnings:
        return

    print_section("Warnings")
    for warning in warnings:
        print(f"- {warning}")


def safe_get_number(data: dict[str, Any], key: str, default: float = 0.0) -> float:
    """Safely read a numeric value from dict."""
    value = data.get(key, default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def print_data_source_status(data_source_status: dict[str, dict]) -> None:
    """Print source, freshness and timestamps for core symbols."""
    if not data_source_status:
        return

    print_section("Data Source Status")
    keys = CORE_REALTIME_SYMBOLS + ["QQQ_intraday_5m"]
    for key in keys:
        meta = data_source_status.get(key, {})
        if not meta:
            print(f"{key}: source=missing")
            continue

        print(
            f"{key}: source={meta.get('source', 'missing')}, "
            f"fresh={meta.get('is_fresh', False)}, "
            f"fallback={meta.get('is_fallback', False)}, "
            f"last_updated={meta.get('last_updated', '') or '-'}, "
            f"data_timestamp={meta.get('data_timestamp', '') or '-'}"
        )


def print_futures_and_breadth(result: dict) -> None:
    """Print futures confirmation and breadth summary from pipeline output."""
    futures_snapshot = result.get("futures_snapshot", {})
    breadth_snapshot = result.get("breadth_snapshot", {})

    print_section("Futures")
    if futures_snapshot:
        print(
            f"NQ vs ES: {safe_get_number(futures_snapshot, 'nq_vs_es'):.4f}, "
            f"trend={futures_snapshot.get('nq_trend', {}).get('trend', 'unknown')}, "
            f"available={futures_snapshot.get('available', False)}"
        )
    else:
        print("Futures snapshot unavailable")

    print_section("Breadth")
    if breadth_snapshot:
        print(
            f"up_ratio={safe_get_number(breadth_snapshot, 'up_ratio'):.2f}, "
            f"down_ratio={safe_get_number(breadth_snapshot, 'down_ratio'):.2f}, "
            f"status={breadth_snapshot.get('breadth_status', 'unknown')}"
        )
    else:
        print("Breadth snapshot unavailable")


def print_event_risk(result: dict) -> None:
    """Print event risk calendar summary from pipeline output."""
    event_risk_snapshot = result.get("event_risk_snapshot", {})

    print_section("Event Risk")
    if not event_risk_snapshot:
        print("Event risk snapshot unavailable")
        return

    print(
        f"today_events={event_risk_snapshot.get('today_event_count', 0)}, "
        f"upcoming_events={event_risk_snapshot.get('upcoming_event_count', 0)}, "
        f"risk_level={event_risk_snapshot.get('risk_level', 'low')}, "
        f"deduction={safe_get_number(event_risk_snapshot, 'deduction'):.0f}"
    )


def main() -> None:
    """Run the main signal pipeline and print a console report."""
    print("====== TQQQ / SQQQ Signal Report ======")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    result = run_signal_pipeline(save_to_db=True, use_cache=True)

    if not isinstance(result, dict):
        print("信号流程返回结果异常：result 不是 dict。")
        print(RISK_DISCLOSURE)
        return

    print_data_source_status(result.get("data_source_status", {}))

    print_section("Runtime Flags")
    print(f"Realtime Usable: {result.get('is_realtime_usable', False)}")
    print(f"Test Mode: {result.get('is_test_mode', False)}")

    if not result.get("success", False):
        print("信号流程执行失败。")
        print_section("Data Quality")
        print(result.get("data_quality", {}))
        print_warnings(result.get("warnings", []))
        print()
        print(RISK_DISCLOSURE)
        return

    final_scores = result.get("final_scores", {})
    data_quality = result.get("data_quality", {})

    tqqq_score = safe_get_number(final_scores, "tqqq_final_score")
    sqqq_score = safe_get_number(final_scores, "sqqq_final_score")

    print_section("Scores")
    print(f"TQQQ Final Score: {tqqq_score:.2f}")
    print(f"SQQQ Final Score: {sqqq_score:.2f}")
    print(f"Market State: {result.get('market_state', '未知')}")

    print_futures_and_breadth(result)
    print_event_risk(result)

    print_section("Data Quality")
    print(
        f"Quality: {data_quality.get('quality_level', 'unknown')} "
        f"({safe_get_number(data_quality, 'quality_score'):.2f})"
    )
    print(f"Realtime Usable: {result.get('is_realtime_usable', False)}")
    print(f"Test Mode: {result.get('is_test_mode', False)}")

    missing_symbols = data_quality.get("missing_symbols", [])
    if missing_symbols:
        print(f"Missing Symbols: {', '.join(missing_symbols)}")

    cache_fallback_count = data_quality.get("cache_fallback_count", 0)
    print(f"Cache Fallback Count: {cache_fallback_count}")

    summary = result.get("summary", "")
    if summary:
        print_section("Summary")
        print(summary)

    print_warnings(result.get("warnings", []))

    print()
    print(RISK_DISCLOSURE)


if __name__ == "__main__":
    main()
