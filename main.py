"""Console entry point for TQQQ / SQQQ signal system."""

from __future__ import annotations

import sys
from datetime import datetime

from config.settings import BACKTEST_DISCLOSURE, RISK_DISCLOSURE
from src.backtest import run_backtest
from src.pipeline import run_signal_pipeline


def print_warnings(warnings: list[str]) -> None:
    """Print warnings in a readable format."""
    if not warnings:
        return

    print("\nWarnings:")
    for warning in warnings:
        print(f"- {warning}")


def main() -> None:
    """Run the signal pipeline and print a concise report."""
    print("====== TQQQ / SQQQ Signal Report ======")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    result = run_signal_pipeline(save_to_db=True, use_cache=True)
    if not result.get("success", False):
        print("信号流程执行失败。")
        print_warnings(result.get("warnings", []))
        print()
        print(RISK_DISCLOSURE)
        return

    final_scores = result.get("final_scores", {})
    data_quality = result.get("data_quality", {})

    print(f"TQQQ Final Score: {final_scores.get('tqqq_final_score', 0):.2f}")
    print(f"SQQQ Final Score: {final_scores.get('sqqq_final_score', 0):.2f}")
    print(f"Market State: {result.get('market_state', '未知')}")
    print(
        "Data Quality: "
        f"{data_quality.get('quality_level', 'unknown')} "
        f"({data_quality.get('quality_score', 0):.2f})"
    )
    print()

    summary = result.get("summary", "")
    if summary:
        print(summary)

    print_warnings(result.get("warnings", []))

    print()
    print(RISK_DISCLOSURE)


def run_backtest_report() -> None:
    """Run backtest from CLI and print metrics."""
    print("====== Backtest Report ======")

    try:
        result = run_backtest()
    except Exception as exc:
        print(f"回测执行失败：{exc}")
        return

    if result.get("status") != "success":
        print(result.get("message", "暂无可用回测结果。"))
        return

    metrics = result.get("metrics", {})
    if not metrics:
        print("暂无可用回测结果。")
        return

    for key, value in metrics.items():
        print(f"{key}: {value}")

    print()
    print(BACKTEST_DISCLOSURE)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--backtest":
        run_backtest_report()
    else:
        main()
