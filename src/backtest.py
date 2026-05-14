"""Backtesting module for TQQQ/SQQQ strategy."""

from __future__ import annotations

from typing import Any

import pandas as pd

from config.settings import BACKTEST_PARAMS
from src.data_fetcher import fetch_daily_data
from src.data_quality import assess_data_quality
from src.market_state import classify_overall_market_state
from src.risk_filter import get_risk_deduction
from src.scoring import calculate_final_score, calculate_sqqq_score, calculate_tqqq_score
from src.utils import setup_logger

logger = setup_logger("backtest")


SUPPORTED_EXECUTION_MODES = {"close_to_next_open", "close_to_next_close"}
MIN_HISTORY_DAYS = 200
REQUIRED_DAILY_COLUMNS = ["date", "open", "close"]


def _normalize_price_frame(df: pd.DataFrame | None) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    working_df = df.copy()
    if "date" not in working_df.columns:
        return pd.DataFrame()

    working_df["date"] = pd.to_datetime(working_df["date"], errors="coerce")
    working_df = working_df.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
    return working_df


def _normalize_historical_data(historical_data: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    normalized: dict[str, pd.DataFrame] = {}
    for symbol, df in historical_data.items():
        normalized_df = _normalize_price_frame(df)
        if not normalized_df.empty:
            normalized[symbol] = normalized_df
    return normalized


def _build_backtest_cache_status(historical_slice: dict[str, pd.DataFrame]) -> dict[str, dict[str, Any]]:
    cache_status: dict[str, dict[str, Any]] = {}
    for symbol, df in historical_slice.items():
        available = bool(df is not None and not df.empty)
        cache_status[symbol] = {
            "source": "api" if available else "missing",
            "is_fresh": available,
            "is_fallback": False,
            "used_cache": False,
        }

    cache_status.setdefault(
        "QQQ_intraday_5m",
        {
            "source": "missing",
            "is_fresh": False,
            "is_fallback": False,
            "used_cache": False,
        },
    )
    return cache_status


def _build_indicator_snapshot(historical_slice: dict[str, pd.DataFrame]) -> dict[str, Any]:
    qqq_df = historical_slice.get("QQQ")
    spy_df = historical_slice.get("SPY")
    qqqe_df = historical_slice.get("QQQE")

    snapshot: dict[str, Any] = {
        "qqq": {},
        "relative_strength": {},
        "mega_cap_tech": {"status": "mixed", "strong_count": 0, "available_count": 0},
        "intraday": {},
    }

    if qqq_df is not None and not qqq_df.empty:
        qqq_close = float(qqq_df.iloc[-1]["close"])
        ma20 = float(qqq_df["close"].tail(20).mean()) if len(qqq_df) >= 20 else qqq_close
        ma50 = float(qqq_df["close"].tail(50).mean()) if len(qqq_df) >= 50 else qqq_close
        ma200 = float(qqq_df["close"].tail(200).mean()) if len(qqq_df) >= 200 else qqq_close
        prior_close = float(qqq_df.iloc[-2]["close"]) if len(qqq_df) >= 2 else qqq_close
        snapshot["qqq"] = {
            "price": round(qqq_close, 2),
            "ma20": round(ma20, 2),
            "ma50": round(ma50, 2),
            "ma200": round(ma200, 2),
            "atr14": round(max(qqq_close * 0.02, 1.0), 2),
            "daily_return": round((qqq_close - prior_close) / prior_close, 4) if prior_close else 0.0,
            "volume_ratio": 1.0,
        }

    if (
        qqq_df is not None
        and not qqq_df.empty
        and spy_df is not None
        and not spy_df.empty
        and len(qqq_df) >= 2
        and len(spy_df) >= 2
    ):
        qqq_return = (float(qqq_df.iloc[-1]["close"]) - float(qqq_df.iloc[-2]["close"])) / float(qqq_df.iloc[-2]["close"])
        spy_return = (float(spy_df.iloc[-1]["close"]) - float(spy_df.iloc[-2]["close"])) / float(spy_df.iloc[-2]["close"])
        snapshot["relative_strength"]["qqq_vs_spy"] = round(qqq_return - spy_return, 4)

    if (
        qqq_df is not None
        and not qqq_df.empty
        and qqqe_df is not None
        and not qqqe_df.empty
        and len(qqq_df) >= 2
        and len(qqqe_df) >= 2
    ):
        qqqe_return = (float(qqqe_df.iloc[-1]["close"]) - float(qqqe_df.iloc[-2]["close"])) / float(qqqe_df.iloc[-2]["close"])
        qqq_return = (float(qqq_df.iloc[-1]["close"]) - float(qqq_df.iloc[-2]["close"])) / float(qqq_df.iloc[-2]["close"])
        snapshot["relative_strength"]["qqqe_vs_qqq"] = round(qqqe_return - qqq_return, 4)

    tech_symbols = [
        symbol
        for symbol in ["NVDA", "MSFT", "AAPL", "AMZN", "META", "GOOGL", "AVGO", "TSLA"]
        if symbol in historical_slice
    ]
    strong_count = 0
    available_count = 0
    for symbol in tech_symbols:
        df = historical_slice.get(symbol)
        if df is None or df.empty or len(df) < 20:
            continue
        available_count += 1
        if float(df.iloc[-1]["close"]) >= float(df["close"].tail(20).mean()):
            strong_count += 1

    if available_count > 0:
        if strong_count / available_count >= 0.6:
            status = "strong"
        elif strong_count == 0:
            status = "weak"
        else:
            status = "mixed"
        snapshot["mega_cap_tech"] = {
            "status": status,
            "strong_count": strong_count,
            "available_count": available_count,
        }

    return snapshot


def _resolve_execution_mode(execution_mode: str) -> str:
    if execution_mode not in SUPPORTED_EXECUTION_MODES:
        raise ValueError(f"Unsupported execution_mode: {execution_mode}")
    return execution_mode


def _pick_entry_price(price_df: pd.DataFrame, entry_idx: int, execution_mode: str) -> float | None:
    column = "open" if execution_mode == "close_to_next_open" else "close"
    if column not in price_df.columns:
        return None
    return float(price_df.iloc[entry_idx][column])


def _signal_score_from_row(signal: str, row: pd.Series) -> float:
    if signal == "BUY_TQQQ":
        return float(row.get("tqqq_score", row.get("tqqq_final_score", 0)) or 0)
    if signal == "BUY_SQQQ":
        return float(row.get("sqqq_score", row.get("sqqq_final_score", 0)) or 0)
    return 0.0


def generate_score_history(
    historical_data: dict[str, pd.DataFrame],
    mode: str = "close_to_next_open",
) -> pd.DataFrame:
    """逐日生成历史评分，且每一天只能使用当天及之前数据。"""
    del mode

    normalized_data = _normalize_historical_data(historical_data)
    qqq_df = normalized_data.get("QQQ")
    if qqq_df is None or qqq_df.empty or len(qqq_df) < MIN_HISTORY_DAYS:
        logger.warning("历史数据不足，无法生成评分历史")
        return pd.DataFrame()

    results: list[dict[str, Any]] = []
    qqq_dates = qqq_df["date"].tolist()

    for current_date in qqq_dates:
        historical_slice = {
            symbol: df[df["date"] <= current_date].copy()
            for symbol, df in normalized_data.items()
        }

        if len(historical_slice.get("QQQ", pd.DataFrame())) < MIN_HISTORY_DAYS:
            continue

        indicator_snapshot = _build_indicator_snapshot(historical_slice)
        tqqq_result = calculate_tqqq_score(indicator_snapshot)
        sqqq_result = calculate_sqqq_score(indicator_snapshot)
        risk_result = get_risk_deduction(str(pd.to_datetime(current_date).date()), indicator_snapshot)
        cache_status = _build_backtest_cache_status(historical_slice)
        data_quality = assess_data_quality(historical_slice, cache_status)

        tqqq_base = float(tqqq_result.get("base_score", 0) or 0)
        sqqq_base = float(sqqq_result.get("base_score", 0) or 0)
        risk_score = float(risk_result.get("deduction", 0) or 0)
        tqqq_final = calculate_final_score(tqqq_base, risk_score)
        sqqq_final = calculate_final_score(sqqq_base, risk_score)
        market_state = classify_overall_market_state(tqqq_final, sqqq_final)

        results.append(
            {
                "date": pd.to_datetime(current_date),
                "tqqq_base_score": tqqq_base,
                "sqqq_base_score": sqqq_base,
                "risk_score": risk_score,
                "tqqq_score": tqqq_final,
                "sqqq_score": sqqq_final,
                "tqqq_final_score": tqqq_final,
                "sqqq_final_score": sqqq_final,
                "market_state": market_state,
                "data_quality_level": data_quality.get("quality_level", "poor"),
                "data_quality_score": data_quality.get("quality_score", 0),
                "risk_events": risk_result.get("events", []),
            }
        )

    return pd.DataFrame(results)


def generate_historical_scores(historical_data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Backward-compatible alias for the old API."""
    return generate_score_history(historical_data, mode="close_to_next_open")


def generate_trade_signals(score_df: pd.DataFrame) -> pd.DataFrame:
    """根据评分生成交易信号。"""
    if score_df is None or score_df.empty:
        return pd.DataFrame(
            columns=["date", "signal", "tqqq_score", "sqqq_score", "data_quality_level", "market_state"]
        )

    tqqq_threshold = float(BACKTEST_PARAMS.get("tqqq_entry_score", BACKTEST_PARAMS.get("tqqq_signal_threshold", 75)))
    sqqq_threshold = float(BACKTEST_PARAMS.get("sqqq_entry_score", BACKTEST_PARAMS.get("sqqq_signal_threshold", 85)))
    tqqq_block = float(BACKTEST_PARAMS.get("tqqq_sqqq_threshold", 65))
    sqqq_block = float(BACKTEST_PARAMS.get("sqqq_tqqq_threshold", 65))

    records: list[dict[str, Any]] = []
    for _, row in score_df.iterrows():
        tqqq_score = float(row.get("tqqq_score", row.get("tqqq_final_score", 0)) or 0)
        sqqq_score = float(row.get("sqqq_score", row.get("sqqq_final_score", 0)) or 0)

        if tqqq_score >= tqqq_threshold and sqqq_score < tqqq_block:
            signal = "BUY_TQQQ"
        elif sqqq_score >= sqqq_threshold and tqqq_score < sqqq_block:
            signal = "BUY_SQQQ"
        else:
            signal = "HOLD_CASH"

        records.append(
            {
                "date": pd.to_datetime(row["date"]),
                "signal": signal,
                "tqqq_score": tqqq_score,
                "sqqq_score": sqqq_score,
                "data_quality_level": row.get("data_quality_level", "poor"),
                "market_state": row.get("market_state", "未知"),
            }
        )

    return pd.DataFrame(records)


def simulate_trades(
    signals_df: pd.DataFrame,
    price_data: dict[str, pd.DataFrame],
    execution_mode: str = "close_to_next_open",
) -> pd.DataFrame:
    """模拟交易，严格使用下一根可交易日价格执行。"""
    execution_mode = _resolve_execution_mode(execution_mode)
    if signals_df is None or signals_df.empty:
        return pd.DataFrame(
            columns=[
                "signal_date",
                "entry_date",
                "exit_date",
                "symbol",
                "entry_price",
                "exit_price",
                "return_pct",
                "exit_reason",
                "holding_days",
                "signal_score",
                "data_quality_level",
                "execution_mode",
            ]
        )

    transaction_cost = float(BACKTEST_PARAMS.get("transaction_cost", 0.001) or 0.001)
    price_frames = {
        symbol: _normalize_price_frame(price_data.get(symbol))
        for symbol in ["TQQQ", "SQQQ"]
    }
    price_frames = {symbol: df for symbol, df in price_frames.items() if not df.empty}

    trades: list[dict[str, Any]] = []
    last_exit_date: pd.Timestamp | None = None

    for _, row in signals_df.iterrows():
        signal_date = pd.to_datetime(row.get("date"), errors="coerce")
        signal = row.get("signal")
        if pd.isna(signal_date) or signal not in {"BUY_TQQQ", "BUY_SQQQ"}:
            continue
        if last_exit_date is not None and signal_date <= last_exit_date:
            continue

        symbol = "TQQQ" if signal == "BUY_TQQQ" else "SQQQ"
        price_df = price_frames.get(symbol)
        if price_df is None or price_df.empty or not all(column in price_df.columns for column in REQUIRED_DAILY_COLUMNS):
            continue

        future_rows = price_df[price_df["date"] > signal_date].reset_index(drop=True)
        if future_rows.empty:
            continue

        entry_row = future_rows.iloc[0]
        entry_date = pd.to_datetime(entry_row["date"])
        entry_idx = int(price_df.index[price_df["date"] == entry_date][0])
        entry_price = _pick_entry_price(price_df, entry_idx, execution_mode)
        if entry_price in {None, 0}:
            continue

        if symbol == "TQQQ":
            take_profit = float(BACKTEST_PARAMS.get("tqqq_take_profit", 0.06))
            stop_loss = float(BACKTEST_PARAMS.get("tqqq_stop_loss", -0.03))
            max_holding_days = int(
                BACKTEST_PARAMS.get("max_holding_days_tqqq", BACKTEST_PARAMS.get("tqqq_max_holding_days", 3))
            )
        else:
            take_profit = float(BACKTEST_PARAMS.get("sqqq_take_profit", 0.05))
            stop_loss = float(BACKTEST_PARAMS.get("sqqq_stop_loss", -0.03))
            max_holding_days = int(
                BACKTEST_PARAMS.get("max_holding_days_sqqq", BACKTEST_PARAMS.get("sqqq_max_holding_days", 2))
            )

        exit_reason = "TimeOut"
        exit_idx = min(entry_idx + max_holding_days - 1, len(price_df) - 1)
        evaluation_start = entry_idx if execution_mode == "close_to_next_open" else entry_idx + 1

        for check_idx in range(evaluation_start, min(entry_idx + max_holding_days, len(price_df))):
            close_price = float(price_df.iloc[check_idx]["close"])
            raw_return = (close_price - entry_price) / entry_price
            if raw_return >= take_profit:
                exit_idx = check_idx
                exit_reason = "TakeProfit"
                break
            if raw_return <= stop_loss:
                exit_idx = check_idx
                exit_reason = "StopLoss"
                break

        exit_row = price_df.iloc[exit_idx]
        exit_date = pd.to_datetime(exit_row["date"])
        exit_price = float(exit_row["close"])
        holding_days = max(1, exit_idx - entry_idx + 1)
        raw_return = (exit_price - entry_price) / entry_price
        return_pct = raw_return - 2 * transaction_cost
        signal_score = _signal_score_from_row(signal, row)

        trades.append(
            {
                "signal_date": signal_date,
                "entry_date": entry_date,
                "exit_date": exit_date,
                "symbol": symbol,
                "entry_price": round(entry_price, 4),
                "exit_price": round(exit_price, 4),
                "return_pct": round(return_pct, 4),
                "exit_reason": exit_reason,
                "holding_days": holding_days,
                "signal_score": round(signal_score, 2),
                "data_quality_level": row.get("data_quality_level", "poor"),
                "execution_mode": execution_mode,
            }
        )
        last_exit_date = exit_date

    return pd.DataFrame(trades)


def _empty_metrics() -> dict[str, Any]:
    return {
        "total_trades": 0,
        "win_rate": 0.0,
        "avg_win": 0.0,
        "avg_loss": 0.0,
        "profit_factor": 0.0,
        "avg_return": 0.0,
        "max_drawdown": 0.0,
        "max_consecutive_losses": 0,
        "avg_holding_days": 0.0,
        "cash_days_ratio": 1.0,
        "signal_frequency": 0.0,
        "tqqq_trade_count": 0,
        "sqqq_trade_count": 0,
        "tqqq_avg_return": 0.0,
        "sqqq_avg_return": 0.0,
    }


def calculate_backtest_metrics(trades_df: pd.DataFrame) -> dict[str, Any]:
    """计算回测指标。"""
    if trades_df is None or trades_df.empty:
        return _empty_metrics()

    working_df = trades_df.sort_values("entry_date").reset_index(drop=True)
    wins = working_df[working_df["return_pct"] > 0]
    losses = working_df[working_df["return_pct"] <= 0]
    total_profit = float(wins["return_pct"].sum()) if not wins.empty else 0.0
    total_loss = abs(float(losses["return_pct"].sum())) if not losses.empty else 0.0
    cumulative = (1 + working_df["return_pct"]).cumprod()
    drawdown = cumulative / cumulative.cummax() - 1

    max_consecutive_losses = 0
    current_losses = 0
    for value in working_df["return_pct"]:
        if value <= 0:
            current_losses += 1
            max_consecutive_losses = max(max_consecutive_losses, current_losses)
        else:
            current_losses = 0

    covered_days = max(
        1,
        (pd.to_datetime(working_df["exit_date"].max()) - pd.to_datetime(working_df["entry_date"].min())).days + 1,
    )
    invested_days = int(working_df["holding_days"].sum())
    total_trades = len(working_df)
    tqqq_trades = working_df[working_df["symbol"] == "TQQQ"]
    sqqq_trades = working_df[working_df["symbol"] == "SQQQ"]

    return {
        "total_trades": total_trades,
        "win_rate": round(len(wins) / total_trades, 4),
        "avg_win": round(float(wins["return_pct"].mean()) if not wins.empty else 0.0, 4),
        "avg_loss": round(float(losses["return_pct"].mean()) if not losses.empty else 0.0, 4),
        "profit_factor": round(total_profit / total_loss, 4) if total_loss > 0 else round(float(total_profit > 0), 4),
        "avg_return": round(float(working_df["return_pct"].mean()), 4),
        "max_drawdown": round(float(drawdown.min()) if not drawdown.empty else 0.0, 4),
        "max_consecutive_losses": max_consecutive_losses,
        "avg_holding_days": round(float(working_df["holding_days"].mean()), 2),
        "cash_days_ratio": round(max(0.0, min(1.0, 1 - invested_days / covered_days)), 4),
        "signal_frequency": round(total_trades / covered_days, 4),
        "tqqq_trade_count": int(len(tqqq_trades)),
        "sqqq_trade_count": int(len(sqqq_trades)),
        "tqqq_avg_return": round(float(tqqq_trades["return_pct"].mean()) if not tqqq_trades.empty else 0.0, 4),
        "sqqq_avg_return": round(float(sqqq_trades["return_pct"].mean()) if not sqqq_trades.empty else 0.0, 4),
    }


def analyze_score_buckets(trades_df: pd.DataFrame) -> pd.DataFrame:
    """分析不同评分区间的交易表现。"""
    if trades_df is None or trades_df.empty:
        return pd.DataFrame(columns=["score_bucket", "trade_count", "win_rate", "avg_return"])

    working_df = trades_df.copy()
    bins = [0, 65, 75, 85, float("inf")]
    labels = ["<65", "65-75", "75-85", "85+"]
    working_df["score_bucket"] = pd.cut(working_df["signal_score"], bins=bins, labels=labels, right=False)

    return (
        working_df.groupby("score_bucket", observed=False)
        .agg(
            trade_count=("return_pct", "count"),
            win_rate=("return_pct", lambda values: round((values > 0).mean(), 4) if len(values) else 0.0),
            avg_return=("return_pct", "mean"),
        )
        .reset_index()
        .fillna({"avg_return": 0.0, "win_rate": 0.0})
    )


def analyze_quality_buckets(trades_df: pd.DataFrame) -> pd.DataFrame:
    """分析不同数据质量等级下的交易表现。"""
    if trades_df is None or trades_df.empty:
        return pd.DataFrame(columns=["data_quality_level", "trade_count", "win_rate", "avg_return"])

    return (
        trades_df.groupby("data_quality_level")
        .agg(
            trade_count=("return_pct", "count"),
            win_rate=("return_pct", lambda values: round((values > 0).mean(), 4) if len(values) else 0.0),
            avg_return=("return_pct", "mean"),
        )
        .reset_index()
        .fillna({"avg_return": 0.0, "win_rate": 0.0})
    )


def run_backtest(
    start_date: str | None = None,
    end_date: str | None = None,
    symbols: list[str] | None = None,
    execution_mode: str = "close_to_next_open",
) -> dict[str, Any]:
    """执行完整回测流程。"""
    execution_mode = _resolve_execution_mode(execution_mode)
    warnings: list[str] = []

    if symbols is None:
        symbols = ["QQQ", "SPY", "QQQE", "TQQQ", "SQQQ", "NVDA", "MSFT", "AAPL", "AMZN"]

    historical_data: dict[str, pd.DataFrame] = {}
    for symbol in symbols:
        df = fetch_daily_data(symbol, period="5y")
        normalized_df = _normalize_price_frame(df)
        if normalized_df.empty:
            warnings.append(f"{symbol} 历史数据缺失，已跳过。")
            continue
        if start_date:
            normalized_df = normalized_df[normalized_df["date"] >= pd.to_datetime(start_date)]
        if end_date:
            normalized_df = normalized_df[normalized_df["date"] <= pd.to_datetime(end_date)]
        if not normalized_df.empty:
            historical_data[symbol] = normalized_df.reset_index(drop=True)

    if not historical_data:
        return {
            "status": "error",
            "message": "无法获取任何历史数据",
            "metrics": _empty_metrics(),
            "trades": pd.DataFrame(),
            "score_bucket_analysis": pd.DataFrame(),
            "quality_bucket_analysis": pd.DataFrame(),
            "warnings": warnings,
        }

    score_history = generate_score_history(historical_data, mode=execution_mode)
    if score_history.empty:
        warnings.append("历史评分为空，可能是样本窗口不足。")
        return {
            "status": "error",
            "message": "无法生成历史评分",
            "metrics": _empty_metrics(),
            "trades": pd.DataFrame(),
            "score_bucket_analysis": pd.DataFrame(),
            "quality_bucket_analysis": pd.DataFrame(),
            "warnings": warnings,
        }

    signals_df = generate_trade_signals(score_history)
    trades_df = simulate_trades(signals_df, historical_data, execution_mode=execution_mode)
    if trades_df.empty:
        warnings.append("本次回测没有生成任何交易。")

    metrics = calculate_backtest_metrics(trades_df)
    score_bucket_df = analyze_score_buckets(trades_df)
    quality_bucket_df = analyze_quality_buckets(trades_df)

    return {
        "status": "success",
        "message": "回测完成",
        "metrics": metrics,
        "trades": trades_df,
        "score_bucket_analysis": score_bucket_df,
        "quality_bucket_analysis": quality_bucket_df,
        "warnings": warnings,
        "historical_scores": score_history,
        "trade_signals": signals_df,
        "execution_mode": execution_mode,
    }
