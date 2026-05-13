"""Console entry point for complete scoring test."""

from datetime import datetime

import pandas as pd

from config.settings import (
    RISK_DISCLOSURE,
    ETF_SYMBOLS,
    MEGA_CAP_TECH_SYMBOLS,
    VOLATILITY_SYMBOLS,
    FUTURES_SYMBOLS,
)
from src.data_fetcher import (
    fetch_daily_data,
    fetch_intraday_data,
    fetch_multiple_daily_data,
)
from src.indicators import (
    build_indicator_snapshot,
    build_full_indicator_dataframe,
)
from src.scoring import calculate_tqqq_score, calculate_sqqq_score, calculate_final_score
from src.risk_filter import get_risk_deduction
from src.market_state import generate_market_summary, classify_overall_market_state
from src.database import (
    init_database,
    save_daily_prices,
    save_indicator_daily,
    save_market_score,
    load_recent_market_scores,
)


def build_indicator_dataframe(symbol: str, df):
    """
    构建某个标的的指标数据框。
    
    参数：
        symbol: 标的代码
        df: 包含日线数据的 DataFrame
        
    返回：
        包含指标字段的 DataFrame
    """
    if df is None or df.empty:
        return pd.DataFrame()
    
    return build_full_indicator_dataframe(df)


def main() -> None:
    """Main entry point for complete signal system test."""
    print("====== TQQQ / SQQQ Signal Report ======\n")

    # 获取当前日期
    today = datetime.now().strftime("%Y-%m-%d")

    # 阶段1：数据抓取
    print(f"【数据抓取阶段】（日期：{today}）\n")

    symbols = ["QQQ", "SPY", "QQQE"] + MEGA_CAP_TECH_SYMBOLS
    daily_data = {}
    intraday_data = {}

    print("正在抓取日线数据...")
    for symbol in symbols:
        df = fetch_daily_data(symbol, period="1y")
        if not df.empty:
            daily_data[symbol] = df
            print(f"✓ {symbol} 日线数据已获取")
        else:
            print(f"✗ {symbol} 日线数据获取失败")

    print("\n正在抓取分钟线数据...")
    qqq_intraday = fetch_intraday_data("QQQ", interval="5m", period="1d")
    if not qqq_intraday.empty:
        intraday_data["QQQ"] = qqq_intraday
        print(f"✓ QQQ 分钟线数据已获取")
    else:
        print(f"✗ QQQ 分钟线数据获取失败")

    # 阶段2：指标计算
    print("\n【指标计算阶段】\n")
    print("正在计算技术指标快照...")
    indicator_snapshot = build_indicator_snapshot(daily_data, intraday_data)
    print("✓ 技术指标快照计算完成\n")

    # 阶段3：评分计算
    print("【评分计算阶段】\n")

    print("计算 TQQQ 做多评分...")
    tqqq_result = calculate_tqqq_score(indicator_snapshot)
    tqqq_base = tqqq_result.get("base_score", 0)
    print(f"✓ TQQQ 基础评分：{tqqq_base:.0f} 分\n")

    print("计算 SQQQ 做空评分...")
    sqqq_result = calculate_sqqq_score(indicator_snapshot)
    sqqq_base = sqqq_result.get("base_score", 0)
    print(f"✓ SQQQ 基础评分：{sqqq_base:.0f} 分\n")

    # 阶段4：风险评估
    print("【风险评估阶段】\n")

    print("检查风险事件与计算风险扣分...")
    risk_result = get_risk_deduction(today, indicator_snapshot)
    risk_deduction = risk_result.get("deduction", 0)
    risk_events = risk_result.get("events", [])

    if risk_events:
        print(f"✓ 检测到风险事件：{', '.join(risk_events)}")
    else:
        print(f"✓ 当天无预定义风险事件")
    print(f"✓ 风险扣分：{risk_deduction:.0f} 分\n")

    # 阶段5：最终评分
    print("【最终评分阶段】\n")

    tqqq_final = calculate_final_score(tqqq_base, risk_deduction)
    sqqq_final = calculate_final_score(sqqq_base, risk_deduction)

    print(f"TQQQ 基础评分：{tqqq_base:.0f} 分")
    print(f"减去风险扣分：{risk_deduction:.0f} 分")
    print(f"TQQQ 最终评分：{tqqq_final:.0f} 分\n")

    print(f"SQQQ 基础评分：{sqqq_base:.0f} 分")
    print(f"减去风险扣分：{risk_deduction:.0f} 分")
    print(f"SQQQ 最终评分：{sqqq_final:.0f} 分\n")

    # 阶段6：市场总结
    print("【市场总结与建议】\n")

    final_scores = {
        "tqqq": tqqq_final,
        "sqqq": sqqq_final
    }

    summary = generate_market_summary(tqqq_result, sqqq_result, risk_result, final_scores)
    print(summary)

    # 输出信息完整性说明
    print("\n【数据完整性说明】")
    if indicator_snapshot.get("qqq"):
        print("✓ QQQ 指标完整")
    else:
        print("⚠ QQQ 指标缺失")

    if daily_data.get("SPY") and daily_data.get("QQQE"):
        print("✓ 相对强弱指标完整")
    else:
        print("⚠ SPY/QQQE 数据缺失，相对强弱计算受影响")

    tech_count = sum(1 for symbol in MEGA_CAP_TECH_SYMBOLS if symbol in daily_data)
    print(f"权重科技股数据：{tech_count}/8 个获取成功")

    if intraday_data.get("QQQ"):
        print("✓ 分钟线数据完整")
    else:
        print("⚠ 缺少分钟线数据（VWAP/开盘结构等指标受影响）")

    # 阶段7：数据库操作
    print("\n====== 数据库测试 ======\n")

    print("正在初始化数据库...")
    try:
        init_database()
        print("✓ 数据库初始化完成\n")
    except Exception as e:
        print(f"✗ 数据库初始化失败：{e}\n")
        return

    # 保存 QQQ 日线数据
    if "QQQ" in daily_data:
        print("正在保存 QQQ 日线行情...")
        count = save_daily_prices("QQQ", daily_data["QQQ"])
        print(f"✓ 写入 {count} 条\n")

    # 保存指标数据
    if "QQQ" in daily_data:
        print("正在计算并保存 QQQ 指标...")
        indicator_df = build_indicator_dataframe("QQQ", daily_data["QQQ"])
        if not indicator_df.empty:
            count = save_indicator_daily("QQQ", indicator_df)
            print(f"✓ 写入 {count} 条\n")
        else:
            print("⚠ QQQ 指标数据为空\n")

    # 保存评分结果
    print("正在保存市场评分...")
    market_state = classify_overall_market_state(tqqq_final, sqqq_final)
    score_record = {
        "datetime": datetime.now().isoformat(),
        "tqqq_base_score": tqqq_base,
        "sqqq_base_score": sqqq_base,
        "risk_deduction": risk_deduction,
        "tqqq_final_score": tqqq_final,
        "sqqq_final_score": sqqq_final,
        "market_state": market_state,
        "summary": summary,
    }
    score_id = save_market_score(score_record)
    if score_id > 0:
        print(f"✓ 评分记录保存成功\n")
    else:
        print(f"✗ 评分记录保存失败\n")

    # 读取最近评分记录
    print("最近评分记录：")
    recent_scores = load_recent_market_scores(limit=5)
    if not recent_scores.empty:
        print(recent_scores[["datetime", "tqqq_final_score", "sqqq_final_score", "market_state"]].to_string())
    else:
        print("无评分记录")

    print("\n✓ 数据库测试完成\n")

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
