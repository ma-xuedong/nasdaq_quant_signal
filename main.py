"""Console entry point for complete scoring test."""

from config.settings import RISK_DISCLOSURE
from src.database import init_database
from src.pipeline import run_signal_pipeline


def main() -> None:
    """Main entry point for complete signal system test."""
    print("====== TQQQ / SQQQ Signal Report ======\n")

    result = run_signal_pipeline(save_to_db=True, use_cache=True)
    if not result.get("success", False):
        print(f"✗ 主流程失败：{result.get('message', '未知错误')}")
        if result.get("warnings"):
            print("\n【告警】")
            for warning in result["warnings"]:
                print(f"- {warning}")
        print("\n" + RISK_DISCLOSURE)
        return

    print("【最终评分阶段】\n")
    print(f"TQQQ 基础评分：{result.get('tqqq_base', 0):.0f} 分")
    print(f"SQQQ 基础评分：{result.get('sqqq_base', 0):.0f} 分")
    print(f"风险扣分：{result.get('risk_deduction', 0):.0f} 分")
    print(f"TQQQ 最终评分：{result.get('tqqq_final', 0):.0f} 分")
    print(f"SQQQ 最终评分：{result.get('sqqq_final', 0):.0f} 分")

    print("\n【市场总结与建议】\n")
    print(result.get("summary", ""))

    quality = result.get("data_quality", {})
    print("\n【数据质量】")
    print(f"质量分：{quality.get('quality_score', 0)}")
    print(f"质量等级：{quality.get('quality_level', 'unknown')}")
    missing_symbols = quality.get("missing_symbols", [])
    if missing_symbols:
        print(f"缺失数据：{', '.join(missing_symbols)}")

    print("\n【缓存状态】")
    for symbol, meta in result.get("cache_status", {}).items():
        print(f"{symbol}: {meta.get('source', 'none')} ({meta.get('message', '')})")

    print("\n" + RISK_DISCLOSURE)


def run_backtest_report():
    """
    执行回测并生成报告。
    """
    from src.backtest import run_backtest
    from src.database import (
        init_backtest_tables,
        save_backtest_scores,
        save_backtest_signals,
        save_backtest_trades,
        save_backtest_metrics,
    )

    print("=" * 50)
    print("TQQQ / SQQQ 回测报告")
    print("=" * 50 + "\n")

    # 初始化回测表
    try:
        init_database()
        init_backtest_tables()
    except Exception as e:
        print(f"✗ 初始化失败：{e}")
        return

    # 执行回测
    print("正在执行回测流程（可能需要数分钟）...\n")
    backtest_result = run_backtest()

    if backtest_result["status"] != "success":
        print(f"✗ 回测失败：{backtest_result['message']}")
        return

    # 保存结果到数据库
    print("保存回测结果到数据库...")
    save_backtest_scores(backtest_result["historical_scores"])
    save_backtest_signals(backtest_result["trade_signals"])
    save_backtest_trades(backtest_result["trades"])
    save_backtest_metrics(
        backtest_result["metrics"],
        backtest_result["start_date"],
        backtest_result["end_date"],
    )

    # 输出回测报告
    print("\n" + "=" * 50)
    print("【回测指标摘要】")
    print("=" * 50 + "\n")

    metrics = backtest_result["metrics"]

    print(f"回测时间段：{backtest_result['start_date']} 至 {backtest_result['end_date']}\n")

    print(f"总交易次数：{metrics.get('total_trades', 0)} 笔")
    print(f"  - 盈利交易：{metrics.get('win_count', 0)} 笔")
    print(f"  - 亏损交易：{metrics.get('loss_count', 0)} 笔")

    print(f"\n胜率：{metrics.get('win_rate', 0) * 100:.2f}%")
    print(f"平均盈利：{metrics.get('avg_win', 0) * 100:.2f}%")
    print(f"平均亏损：{metrics.get('avg_loss', 0) * 100:.2f}%")
    print(f"盈亏比（Profit Factor）：{metrics.get('profit_factor', 0):.2f}")

    print(f"\n平均收益率：{metrics.get('avg_return', 0) * 100:.2f}%")
    print(f"累计收益率：{metrics.get('cumulative_return', 0) * 100:.2f}%")
    print(f"最大回撤：{metrics.get('max_drawdown', 0) * 100:.2f}%")

    print(f"\n平均持仓天数：{metrics.get('avg_holding_days', 0):.1f} 天")
    print(f"连续亏损最多次数：{metrics.get('consecutive_losses', 0)} 笔")

    # 显示最近的几笔交易
    trades_df = backtest_result["trades"]
    if not trades_df.empty:
        print("\n【最近的10笔交易】\n")
        recent_trades = trades_df.tail(10)[
            ["entry_date", "symbol", "entry_price", "exit_price", "return_pct", "exit_reason"]
        ]
        print(recent_trades.to_string(index=False))

    # 输出风险提示
    from config.settings import BACKTEST_DISCLOSURE
    print("\n" + "=" * 50)
    print("【风险提示】")
    print("=" * 50)
    print("\n" + BACKTEST_DISCLOSURE)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--backtest":
        run_backtest_report()
    else:
        main()
