"""Console entry point for TQQQ / SQQQ signal system."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from config.settings import RISK_DISCLOSURE
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


def main() -> None:
    """Run the main signal pipeline and print a console report."""
    print("====== TQQQ / SQQQ Signal Report ======")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    result = run_signal_pipeline(save_to_db=True, use_cache=True)

    if not isinstance(result, dict):
        print("信号流程返回结果异常：result 不是 dict。")
        print(RISK_DISCLOSURE)
        return

    if not result.get("success", False):
        print("信号流程执行失败。")
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

    print_section("Data Quality")
    print(
        f"Quality: {data_quality.get('quality_level', 'unknown')} "
        f"({safe_get_number(data_quality, 'quality_score'):.2f})"
    )

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
