"""
Backtesting module for TQQQ/SQQQ strategy.

This module implements historical simulation of the TQQQ/SQQQ signal system.
Key principle: NO FUTURE FUNCTIONS - signals are generated using only data
available at the end of each trading day.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd

from src.data_fetcher import fetch_daily_data
from src.indicators import build_indicator_snapshot
from src.risk_filter import get_risk_deduction
from src.scoring import calculate_tqqq_score, calculate_sqqq_score
from src.utils import setup_logger

logger = setup_logger("backtest")


def generate_historical_scores(
    historical_data: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    """
    逐日生成 TQQQ / SQQQ 评分。

    原理：
    - 逐日滚动，每日仅使用当日及之前的数据
    - 无未来函数
    - 每一行代表某日收盘后可生成的信号

    参数：
        historical_data: {'QQQ': df, 'SPY': df, ...} 包含所有必要数据

    返回：
        DataFrame with columns:
            date
            tqqq_base_score
            sqqq_base_score
            risk_score
            tqqq_final_score
            sqqq_final_score
            market_state
            reasons (dict)
    """
    logger.info("开始生成历史评分...")

    # 找出共同日期范围（统一使用 date 列，不假设 index 是日期）
    all_dates = set()
    normalized_data: dict[str, pd.DataFrame] = {}
    for symbol, df in historical_data.items():
        if df is None or df.empty:
            continue
        working_df = df.copy()
        if "date" not in working_df.columns:
            continue
        working_df["date"] = pd.to_datetime(working_df["date"], errors="coerce")
        working_df = working_df.dropna(subset=["date"]).sort_values("date")
        normalized_data[symbol] = working_df
        all_dates.update(working_df["date"].tolist())
    all_dates = sorted(all_dates)

    if len(all_dates) < 200:
        logger.warning(f"历史数据不足：仅有 {len(all_dates)} 天数据")
        return pd.DataFrame()

    # 初始化结果
    results = []

    # 逐日计算（从第200个交易日开始，确保有足够回溯数据）
    for i, current_date in enumerate(all_dates):
        if i < 200:  # 至少需要200天的历史数据进行指标计算
            continue

        # 获取截至当前日期的所有历史数据（不包含未来）
        historical_slice = {}
        for symbol, df in normalized_data.items():
            historical_slice[symbol] = df[df["date"] <= current_date].copy()

        try:
            # 构建指标快照
            indicator_snapshot = build_indicator_snapshot(historical_slice)

            # 计算 TQQQ 评分
            tqqq_result = calculate_tqqq_score(indicator_snapshot)
            tqqq_base = tqqq_result.get("base_score", 50)

            # 计算 SQQQ 评分
            sqqq_result = calculate_sqqq_score(indicator_snapshot)
            sqqq_base = sqqq_result.get("base_score", 50)

            # 计算风险扣分
            risk_result = get_risk_deduction(str(pd.to_datetime(current_date).date()), indicator_snapshot)
            risk_score = risk_result.get("deduction", 0)

            # 计算最终评分（扣除风险）
            tqqq_final = max(0, tqqq_base - risk_score)
            sqqq_final = max(0, sqqq_base - risk_score)

            # 市场状态判断
            if tqqq_final >= 75 and sqqq_final < 65:
                market_state = "BUY_TQQQ_SIGNAL"
            elif sqqq_final >= 85 and tqqq_final < 65:
                market_state = "BUY_SQQQ_SIGNAL"
            elif tqqq_final >= 65:
                market_state = "BULLISH"
            elif sqqq_final >= 65:
                market_state = "BEARISH"
            else:
                market_state = "HOLD_CASH"

            results.append(
                {
                    "date": current_date,
                    "tqqq_base_score": tqqq_base,
                    "sqqq_base_score": sqqq_base,
                    "risk_score": risk_score,
                    "tqqq_final_score": tqqq_final,
                    "sqqq_final_score": sqqq_final,
                    "market_state": market_state,
                    "tqqq_reasons": tqqq_result.get("reasons", []),
                    "sqqq_reasons": sqqq_result.get("reasons", []),
                }
            )

        except Exception as e:
            logger.warning(f"日期 {current_date} 评分计算失败: {e}")
            continue

    df_scores = pd.DataFrame(results)
    logger.info(f"生成了 {len(df_scores)} 条历史评分记录")
    return df_scores


def generate_trade_signals(score_df: pd.DataFrame) -> pd.DataFrame:
    """
    根据历史评分生成交易信号。

    规则：
    - TQQQ 信号：TQQQ >= 75 AND SQQQ < 65 → BUY_TQQQ
    - SQQQ 信号：SQQQ >= 85 AND TQQQ < 65 → BUY_SQQQ
    - 其他：HOLD_CASH

    返回：
        DataFrame with columns:
            date
            signal
            tqqq_final_score
            sqqq_final_score
            market_state
    """
    logger.info("生成交易信号...")

    signals = []
    for _, row in score_df.iterrows():
        tqqq_score = row["tqqq_final_score"]
        sqqq_score = row["sqqq_final_score"]

        # TQQQ 信号规则
        if tqqq_score >= 75 and sqqq_score < 65:
            signal = "BUY_TQQQ"
        # SQQQ 信号规则
        elif sqqq_score >= 85 and tqqq_score < 65:
            signal = "BUY_SQQQ"
        # 默认
        else:
            signal = "HOLD_CASH"

        signals.append(
            {
                "date": row["date"],
                "signal": signal,
                "tqqq_final_score": tqqq_score,
                "sqqq_final_score": sqqq_score,
                "market_state": row["market_state"],
            }
        )

    df_signals = pd.DataFrame(signals)
    logger.info(f"生成了 {len(df_signals)} 条交易信号")
    logger.info(
        f"  - BUY_TQQQ: {(df_signals['signal'] == 'BUY_TQQQ').sum()}")
    logger.info(
        f"  - BUY_SQQQ: {(df_signals['signal'] == 'BUY_SQQQ').sum()}")
    logger.info(
        f"  - HOLD_CASH: {(df_signals['signal'] == 'HOLD_CASH').sum()}")

    return df_signals


def simulate_trades(
    signals_df: pd.DataFrame,
    price_data: dict[str, pd.DataFrame],
    tqqq_take_profit: float = 0.06,
    tqqq_stop_loss: float = -0.03,
    sqqq_take_profit: float = 0.05,
    sqqq_stop_loss: float = -0.03,
    transaction_cost: float = 0.001,
) -> pd.DataFrame:
    """
    根据交易信号模拟交易。

    规则：
    - TQQQ: 最多持有3个交易日，止盈6%，止损-3%
    - SQQQ: 最多持有2个交易日，止盈5%，止损-3%
    - 交易成本：每笔0.1%

    参数：
        signals_df: 信号 DataFrame（带 date 和 signal）
        price_data: {'TQQQ': df, 'SQQQ': df, ...} 包含价格数据
        tqqq_take_profit: TQQQ 止盈比例（默认0.06 = 6%）
        tqqq_stop_loss: TQQQ 止损比例（默认-0.03 = -3%）
        sqqq_take_profit: SQQQ 止盈比例（默认0.05 = 5%）
        sqqq_stop_loss: SQQQ 止损比例（默认-0.03 = -3%）
        transaction_cost: 交易成本（默认0.001 = 0.1%）

    返回：
        DataFrame with columns:
            entry_date
            exit_date
            symbol
            entry_price
            exit_price
            return_pct
            exit_reason
            holding_days
    """
    logger.info("模拟交易...")

    trades = []

    price_frames: dict[str, pd.DataFrame] = {}
    for symbol in ["TQQQ", "SQQQ"]:
        if symbol not in price_data or price_data[symbol] is None or price_data[symbol].empty:
            continue
        df_symbol = price_data[symbol].copy()
        if "date" not in df_symbol.columns:
            continue
        df_symbol["date"] = pd.to_datetime(df_symbol["date"], errors="coerce")
        df_symbol = df_symbol.dropna(subset=["date"]).sort_values("date")
        price_frames[symbol] = df_symbol.set_index("date", drop=False)

    if "TQQQ" not in price_frames:
        return pd.DataFrame()

    dates_list = price_frames["TQQQ"]["date"].tolist()

    for _, row in signals_df.iterrows():
        signal_date = pd.to_datetime(row["date"], errors="coerce")
        if pd.isna(signal_date):
            continue
        signal = row["signal"]

        # 找到信号日期在价格数据中的位置
        if signal_date not in dates_list:
            continue

        signal_idx = dates_list.index(signal_date)

        # 次日开盘买入
        entry_idx = signal_idx + 1
        if entry_idx >= len(dates_list):
            continue

        entry_date = dates_list[entry_idx]

        if signal == "BUY_TQQQ":
            symbol = "TQQQ"
            take_profit = tqqq_take_profit
            stop_loss = tqqq_stop_loss
            max_holding_days = 3

        elif signal == "BUY_SQQQ":
            symbol = "SQQQ"
            take_profit = sqqq_take_profit
            stop_loss = sqqq_stop_loss
            max_holding_days = 2

        else:  # HOLD_CASH
            continue

        # 获取入场价格（次日开盘 = 当日收盘价的近似）
        try:
            entry_price = price_frames[symbol].loc[entry_date, "open"]
        except KeyError:
            continue

        # 模拟持有期间的交易
        exit_idx = entry_idx
        exit_date = entry_date
        exit_price = entry_price
        exit_reason = "Unknown"
        holding_days = 0

        for hold_day in range(1, max_holding_days + 1):
            check_idx = entry_idx + hold_day
            if check_idx >= len(dates_list):
                # 超出数据范围，按最后数据卖出
                exit_idx = len(dates_list) - 1
                exit_date = dates_list[exit_idx]
                exit_price = price_frames[symbol].iloc[exit_idx]["close"]
                exit_reason = "DataEnd"
                holding_days = hold_day
                break

            check_date = dates_list[check_idx]
            check_price = price_frames[symbol].loc[check_date, "close"]

            # 计算收益率（考虑交易成本）
            raw_return = (check_price - entry_price) / entry_price
            net_return = (
                raw_return - transaction_cost
            )  # 入场和出场各扣除成本

            # 检查止盈
            if raw_return >= take_profit:
                exit_idx = check_idx
                exit_date = check_date
                exit_price = check_price
                exit_reason = "TakeProfit"
                holding_days = hold_day
                break

            # 检查止损
            if raw_return <= stop_loss:
                exit_idx = check_idx
                exit_date = check_date
                exit_price = check_price
                exit_reason = "StopLoss"
                holding_days = hold_day
                break

        # 如果未触发止盈/止损，按最后日期卖出
        if exit_reason == "Unknown":
            exit_date = dates_list[exit_idx]
            exit_price = price_frames[symbol].loc[exit_date, "close"]
            exit_reason = "TimeOut"
            holding_days = max_holding_days

        # 计算最终收益率（扣除往返交易成本）
        raw_return = (exit_price - entry_price) / entry_price
        return_pct = raw_return - 2 * transaction_cost  # 入场和出场各扣除成本

        trades.append(
            {
                "entry_date": entry_date,
                "exit_date": exit_date,
                "symbol": symbol,
                "entry_price": round(entry_price, 2),
                "exit_price": round(exit_price, 2),
                "return_pct": round(return_pct, 4),
                "exit_reason": exit_reason,
                "holding_days": holding_days,
            }
        )

    df_trades = pd.DataFrame(trades)
    logger.info(f"生成了 {len(df_trades)} 笔交易记录")

    return df_trades


def calculate_backtest_metrics(trades_df: pd.DataFrame) -> dict:
    """
    计算回测指标。

    指标包括：
    - total_trades: 总交易笔数
    - win_rate: 胜率
    - avg_win: 平均盈利
    - avg_loss: 平均亏损
    - profit_factor: 盈亏比
    - avg_return: 平均收益率
    - max_drawdown: 最大回撤
    - consecutive_losses: 连续亏损次数
    - avg_holding_days: 平均持仓天数
    - cumulative_return: 累计收益率
    """
    if trades_df.empty:
        logger.warning("交易数据为空，无法计算回测指标")
        return {}

    total_trades = len(trades_df)
    winning_trades = trades_df[trades_df["return_pct"] > 0]
    losing_trades = trades_df[trades_df["return_pct"] <= 0]

    win_count = len(winning_trades)
    loss_count = len(losing_trades)

    win_rate = win_count / total_trades if total_trades > 0 else 0.0
    avg_win = winning_trades["return_pct"].mean() if len(winning_trades) > 0 else 0.0
    avg_loss = (
        losing_trades["return_pct"].mean() if len(losing_trades) > 0 else 0.0
    )

    # 盈亏比 = 总盈利 / 总亏损（绝对值）
    total_profit = winning_trades["return_pct"].sum()
    total_loss = abs(losing_trades["return_pct"].sum())
    profit_factor = (
        total_profit / total_loss if total_loss > 0 else (1.0 if total_profit > 0 else 0.0)
    )

    avg_return = trades_df["return_pct"].mean()
    avg_holding_days = trades_df["holding_days"].mean()

    # 最大回撤：从最高点开始下跌的最大幅度
    cumulative_returns = (1 + trades_df["return_pct"]).cumprod()
    running_max = cumulative_returns.expanding().max()
    drawdown = (cumulative_returns - running_max) / running_max
    max_drawdown = drawdown.min()

    # 连续亏损次数
    consecutive_losses = 0
    current_consecutive = 0
    for ret in trades_df["return_pct"]:
        if ret <= 0:
            current_consecutive += 1
            consecutive_losses = max(consecutive_losses, current_consecutive)
        else:
            current_consecutive = 0

    # 累计收益率
    cumulative_return = (cumulative_returns.iloc[-1] - 1) if not cumulative_returns.empty else 0.0

    metrics = {
        "total_trades": total_trades,
        "win_count": win_count,
        "loss_count": loss_count,
        "win_rate": round(win_rate, 4),
        "avg_win": round(avg_win, 4),
        "avg_loss": round(avg_loss, 4),
        "profit_factor": round(profit_factor, 4),
        "avg_return": round(avg_return, 4),
        "max_drawdown": round(max_drawdown, 4),
        "consecutive_losses": consecutive_losses,
        "avg_holding_days": round(avg_holding_days, 2),
        "cumulative_return": round(cumulative_return, 4),
    }

    logger.info("回测指标计算完成：")
    logger.info(f"  - 总交易数: {metrics['total_trades']}")
    logger.info(f"  - 胜率: {metrics['win_rate'] * 100:.2f}%")
    logger.info(f"  - 平均盈利: {metrics['avg_win'] * 100:.2f}%")
    logger.info(f"  - 平均亏损: {metrics['avg_loss'] * 100:.2f}%")
    logger.info(f"  - 盈亏比: {metrics['profit_factor']:.2f}")
    logger.info(f"  - 累计收益: {metrics['cumulative_return'] * 100:.2f}%")
    logger.info(f"  - 最大回撤: {metrics['max_drawdown'] * 100:.2f}%")

    return metrics


def run_backtest(
    start_date: str | None = None,
    end_date: str | None = None,
    symbols: list[str] | None = None,
) -> dict:
    """
    执行完整回测流程。

    参数：
        start_date: 回测开始日期（格式: 'YYYY-MM-DD'），默认None表示最早数据
        end_date: 回测结束日期（格式: 'YYYY-MM-DD'），默认None表示最新数据
        symbols: 要回测的符号列表，默认['QQQ', 'SPY', 'QQQE', 'TQQQ', 'SQQQ', ...]

    返回：
        {
            'status': 'success' | 'error',
            'message': str,
            'historical_scores': DataFrame,
            'trade_signals': DataFrame,
            'trades': DataFrame,
            'metrics': dict,
            'start_date': str,
            'end_date': str,
        }
    """
    if symbols is None:
        symbols = ["QQQ", "SPY", "QQQE", "TQQQ", "SQQQ", "NVDA", "MSFT"]

    logger.info("开始执行回测流程...")
    logger.info(f"回测符号: {symbols}")
    logger.info(f"回测时间段: {start_date} to {end_date}")

    try:
        # 1. 获取历史数据
        logger.info("Step 1: 抓取历史数据...")
        historical_data = {}

        for symbol in symbols:
            logger.info(f"  抓取 {symbol} 数据...")
            df = fetch_daily_data(symbol, period="5y")

            if df.empty:
                logger.warning(f"  {symbol} 数据获取失败，跳过")
                continue

            if "date" not in df.columns:
                logger.warning(f"  {symbol} 缺少 date 列，跳过")
                continue

            df["date"] = pd.to_datetime(df["date"], errors="coerce")
            df = df.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)

            # 按日期范围筛选
            if start_date:
                df = df[df["date"] >= pd.to_datetime(start_date)]
            if end_date:
                df = df[df["date"] <= pd.to_datetime(end_date)]

            historical_data[symbol] = df

        if not historical_data:
            return {
                "status": "error",
                "message": "无法获取任何历史数据",
                "historical_scores": pd.DataFrame(),
                "trade_signals": pd.DataFrame(),
                "trades": pd.DataFrame(),
                "metrics": {},
            }

        # 2. 生成历史评分
        logger.info("Step 2: 生成历史评分...")
        df_scores = generate_historical_scores(historical_data)

        if df_scores.empty:
            return {
                "status": "error",
                "message": "无法生成历史评分，历史数据不足",
                "historical_scores": df_scores,
                "trade_signals": pd.DataFrame(),
                "trades": pd.DataFrame(),
                "metrics": {},
            }

        # 3. 生成交易信号
        logger.info("Step 3: 生成交易信号...")
        df_signals = generate_trade_signals(df_scores)

        # 4. 模拟交易
        logger.info("Step 4: 模拟交易...")
        df_trades = simulate_trades(df_signals, historical_data)

        # 5. 计算回测指标
        logger.info("Step 5: 计算回测指标...")
        metrics = calculate_backtest_metrics(df_trades)

        # 获取实际的日期范围
        actual_start = df_scores["date"].min()
        actual_end = df_scores["date"].max()

        logger.info("回测流程完成！")

        return {
            "status": "success",
            "message": "回测完成",
            "historical_scores": df_scores,
            "trade_signals": df_signals,
            "trades": df_trades,
            "metrics": metrics,
            "start_date": str(actual_start),
            "end_date": str(actual_end),
        }

    except Exception as e:
        logger.error(f"回测过程中出错: {e}", exc_info=True)
        return {
            "status": "error",
            "message": f"回测失败: {str(e)}",
            "historical_scores": pd.DataFrame(),
            "trade_signals": pd.DataFrame(),
            "trades": pd.DataFrame(),
            "metrics": {},
        }
