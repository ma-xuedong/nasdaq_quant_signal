"""Technical indicators calculation module."""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd
import numpy as np

from src.utils import setup_logger

logger = setup_logger("indicators")


def calculate_moving_averages(df: pd.DataFrame) -> pd.DataFrame:
    """
    计算 MA5、MA20、MA50、MA200。

    MA（移动均线）是短期到长期的趋势指标：
        MA5: 短期趋势
        MA20: 短线趋势线
        MA50: 中短期强弱线
        MA200: 长期趋势参考

    输入：
        包含 close 字段的 DataFrame。

    输出：
        原 DataFrame 增加字段：
        ma5, ma20, ma50, ma200
    """
    try:
        if df.empty or "close" not in df.columns:
            logger.warning("calculate_moving_averages: 数据为空或缺少 close 字段")
            return df

        df = df.copy()
        df["ma5"] = df["close"].rolling(window=5, min_periods=1).mean()
        df["ma20"] = df["close"].rolling(window=20, min_periods=1).mean()
        df["ma50"] = df["close"].rolling(window=50, min_periods=1).mean()
        df["ma200"] = df["close"].rolling(window=200, min_periods=1).mean()

        logger.info("计算移动均线完成")
        return df

    except Exception as e:
        logger.error(f"计算移动均线失败：{str(e)}")
        return df


def calculate_ma_slope(
    df: pd.DataFrame,
    ma_col: str,
    window: int = 5
) -> pd.DataFrame:
    """
    计算指定均线的斜率。

    斜率用于判断趋势方向：
        正斜率：均线向上，趋势向上
        负斜率：均线向下，趋势向下
        绝对值大：趋势变化快

    slope = 当前 ma_col - window 个交易日前 ma_col
    slope_pct = (当前 ma_col / window 个交易日前 ma_col) - 1

    输出字段：
        {ma_col}_slope
        {ma_col}_slope_pct
    """
    try:
        if df.empty or ma_col not in df.columns:
            logger.warning(f"calculate_ma_slope: 数据为空或缺少 {ma_col} 字段")
            return df

        df = df.copy()
        slope_col = f"{ma_col}_slope"
        slope_pct_col = f"{ma_col}_slope_pct"

        # 计算斜率
        df[slope_col] = df[ma_col] - df[ma_col].shift(window)

        # 计算百分比斜率
        prev_ma = df[ma_col].shift(window)
        df[slope_pct_col] = np.where(
            prev_ma != 0,
            (df[ma_col] / prev_ma) - 1,
            0.0
        )

        logger.info(f"计算 {ma_col} 斜率完成")
        return df

    except Exception as e:
        logger.error(f"计算 {ma_col} 斜率失败：{str(e)}")
        return df


def calculate_atr(
    df: pd.DataFrame,
    window: int = 14
) -> pd.DataFrame:
    """
    计算 ATR（Average True Range）。

    ATR 衡量近期真实波动范围，用于判断波动性：
        高 ATR：波动大，机会多但风险大
        低 ATR：波动小，机会少但风险小

    True Range:
        tr = max(
            high - low,
            abs(high - previous_close),
            abs(low - previous_close)
        )

    输出字段：
        tr, atr14
    """
    try:
        if df.empty or not all(col in df.columns for col in ["high", "low", "close"]):
            logger.warning("calculate_atr: 数据为空或缺少 high/low/close 字段")
            return df

        df = df.copy()

        # 计算 True Range
        high_low = df["high"] - df["low"]
        high_close = abs(df["high"] - df["close"].shift(1))
        low_close = abs(df["low"] - df["close"].shift(1))

        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df["tr"] = tr

        # 计算 ATR
        df["atr14"] = tr.rolling(window=window, min_periods=1).mean()

        logger.info("计算 ATR 完成")
        return df

    except Exception as e:
        logger.error(f"计算 ATR 失败：{str(e)}")
        return df


def calculate_volume_ratio(
    df: pd.DataFrame,
    window: int = 20
) -> pd.DataFrame:
    """
    计算成交量比例。

    volume_ratio 用于判断是否放量：
        > 1.5：明显放量，有突破或拉升信号
        1.0-1.5：轻微放量
        < 1.0：缩量，可能继续下跌或整理

    volume_ma20 = 过去20日平均成交量
    volume_ratio = 当前成交量 / volume_ma20

    输出字段：
        volume_ma20, volume_ratio
    """
    try:
        if df.empty or "volume" not in df.columns:
            logger.warning("calculate_volume_ratio: 数据为空或缺少 volume 字段")
            return df

        df = df.copy()

        # 计算平均成交量
        df["volume_ma20"] = df["volume"].rolling(window=window, min_periods=1).mean()

        # 计算成交量比例
        df["volume_ratio"] = np.where(
            df["volume_ma20"] != 0,
            df["volume"] / df["volume_ma20"],
            1.0
        )

        logger.info("计算成交量比例完成")
        return df

    except Exception as e:
        logger.error(f"计算成交量比例失败：{str(e)}")
        return df


def calculate_daily_return(df: pd.DataFrame) -> float:
    """
    计算最新交易日涨跌幅。

    用于判断当日走势强弱。

    return = (当前 close / 前一交易日 close) - 1

    如果数据不足，返回 0.0。
    """
    try:
        if df.empty or "close" not in df.columns or len(df) < 2:
            logger.warning("calculate_daily_return: 数据不足")
            return 0.0

        latest_close = df["close"].iloc[-1]
        prev_close = df["close"].iloc[-2]

        if prev_close == 0:
            return 0.0

        return (latest_close / prev_close) - 1

    except Exception as e:
        logger.error(f"计算日涨跌幅失败：{str(e)}")
        return 0.0


def calculate_relative_strength(
    base_df: pd.DataFrame,
    benchmark_df: pd.DataFrame
) -> float:
    """
    计算 base 相对 benchmark 的强弱。

    用于判断相对强弱：
        正值：base 强于 benchmark
        负值：base 弱于 benchmark

    例如：
        QQQ 相对 SPY 强弱 = QQQ 当日涨跌幅 - SPY 当日涨跌幅
        QQQE 相对 QQQ 强弱 = QQQE 当日涨跌幅 - QQQ 当日涨跌幅

    返回值在 -2.0 到 2.0 之间。
    """
    try:
        base_return = calculate_daily_return(base_df)
        benchmark_return = calculate_daily_return(benchmark_df)

        return base_return - benchmark_return

    except Exception as e:
        logger.error(f"计算相对强弱失败：{str(e)}")
        return 0.0


def calculate_vwap(intraday_df: pd.DataFrame) -> pd.DataFrame:
    """
    基于分钟线计算 VWAP（成交量加权平均价格）。

    VWAP 表示按成交量加权的平均价格，用于判断当日走势的平衡点。

    typical_price = (high + low + close) / 3
    vwap = 累计(typical_price * volume) / 累计(volume)

    输出字段：
        typical_price, vwap
    """
    try:
        if intraday_df.empty or not all(col in intraday_df.columns for col in ["high", "low", "close", "volume"]):
            logger.warning("calculate_vwap: 数据为空或缺少必要字段")
            return intraday_df

        df = intraday_df.copy()

        # 计算 typical price
        df["typical_price"] = (df["high"] + df["low"] + df["close"]) / 3

        # 计算 VWAP（累计体积加权）
        df["pv"] = df["typical_price"] * df["volume"]
        df["vwap"] = df["pv"].cumsum() / df["volume"].cumsum()

        logger.info("计算 VWAP 完成")
        return df

    except Exception as e:
        logger.error(f"计算 VWAP 失败：{str(e)}")
        return intraday_df


def analyze_opening_30min_structure(intraday_df: pd.DataFrame) -> dict[str, Any]:
    """
    分析 QQQ 开盘30分钟走势。

    开盘30分钟结构用于判断当日强弱：
        强势开盘：收盘 > 开盘，预示向上
        弱势开盘：收盘 < 开盘，预示向下

    返回：
    {
        "has_data": True/False,
        "open_price": ...,
        "close_30m": ...,
        "high_30m": ...,
        "low_30m": ...,
        "is_strong_opening": True/False,
        "is_weak_opening": True/False,
        "description": "..."
    }
    """
    try:
        if intraday_df.empty or not all(col in intraday_df.columns for col in ["open", "close", "high", "low"]):
            logger.warning("analyze_opening_30min_structure: 数据为空或缺少必要字段")
            return {
                "has_data": False,
                "description": "无分钟线数据"
            }

        # 只取前 30 分钟的数据（假设是5分钟线，则取前6根）
        # 对于实际分钟线，需要按时间过滤
        first_30_min = intraday_df.head(6)  # 6 * 5分钟 = 30分钟

        if len(first_30_min) == 0:
            return {
                "has_data": False,
                "description": "开盘30分钟数据不足"
            }

        open_price = first_30_min["open"].iloc[0]
        close_30m = first_30_min["close"].iloc[-1]
        high_30m = first_30_min["high"].max()
        low_30m = first_30_min["low"].min()

        # 判断开盘强弱
        is_strong_opening = close_30m > open_price
        is_weak_opening = close_30m < open_price

        change_pct = ((close_30m - open_price) / open_price) * 100 if open_price != 0 else 0

        description = "强势开盘：预示向上" if is_strong_opening else "弱势开盘：预示向下" if is_weak_opening else "平盘开盘"

        return {
            "has_data": True,
            "open_price": round(open_price, 2),
            "close_30m": round(close_30m, 2),
            "high_30m": round(high_30m, 2),
            "low_30m": round(low_30m, 2),
            "is_strong_opening": is_strong_opening,
            "is_weak_opening": is_weak_opening,
            "change_pct": round(change_pct, 2),
            "description": description
        }

    except Exception as e:
        logger.error(f"分析开盘30分钟结构失败：{str(e)}")
        return {
            "has_data": False,
            "description": f"分析失败：{str(e)}"
        }


def analyze_mega_cap_tech_strength(
    symbol_data: dict[str, pd.DataFrame]
) -> dict[str, Any]:
    """
    分析 8 只科技权重股强弱。

    科技权重股包括：NVDA, MSFT, AAPL, AMZN, META, GOOGL, AVGO, TSLA

    用于判断大科技板块是否整体向上或向下。

    返回：
    {
        "up_count": 6,
        "down_count": 2,
        "flat_count": 0,
        "avg_return": 0.012,
        "median_return": 0.008,
        "details": {
            "NVDA": 0.02,
            "MSFT": -0.01
        },
        "status": "strong" / "weak" / "mixed"
    }

    判断规则：
        8只中6只及以上上涨：strong
        8只中6只及以上下跌：weak
        其他：mixed
    """
    try:
        if not symbol_data:
            logger.warning("analyze_mega_cap_tech_strength: 无数据")
            return {
                "up_count": 0,
                "down_count": 0,
                "flat_count": 0,
                "avg_return": 0.0,
                "median_return": 0.0,
                "details": {},
                "status": "unknown"
            }

        returns = {}
        up_count = 0
        down_count = 0
        flat_count = 0

        for symbol, df in symbol_data.items():
            if df.empty:
                logger.warning(f"analyze_mega_cap_tech_strength: {symbol} 数据为空")
                continue

            ret = calculate_daily_return(df)
            returns[symbol] = ret

            if ret > 0.0001:  # 上升（考虑浮点误差）
                up_count += 1
            elif ret < -0.0001:  # 下降
                down_count += 1
            else:  # 平盘
                flat_count += 1

        if not returns:
            return {
                "up_count": 0,
                "down_count": 0,
                "flat_count": 0,
                "avg_return": 0.0,
                "median_return": 0.0,
                "details": {},
                "status": "no_data"
            }

        return_values = list(returns.values())
        avg_return = sum(return_values) / len(return_values) if return_values else 0.0
        median_return = sorted(return_values)[len(return_values) // 2] if return_values else 0.0

        # 判断状态
        total = up_count + down_count + flat_count
        if up_count >= 6:
            status = "strong"
        elif down_count >= 6:
            status = "weak"
        else:
            status = "mixed"

        logger.info(f"科技权重股分析完成：{status}")

        return {
            "up_count": up_count,
            "down_count": down_count,
            "flat_count": flat_count,
            "avg_return": round(avg_return, 4),
            "median_return": round(median_return, 4),
            "details": {k: round(v, 4) for k, v in returns.items()},
            "status": status
        }

    except Exception as e:
        logger.error(f"分析科技权重股失败：{str(e)}")
        return {
            "up_count": 0,
            "down_count": 0,
            "flat_count": 0,
            "avg_return": 0.0,
            "median_return": 0.0,
            "details": {},
            "status": "error"
        }


def build_indicator_snapshot(
    daily_data: dict[str, pd.DataFrame],
    intraday_data: dict[str, pd.DataFrame] | None = None
) -> dict[str, Any]:
    """
    构建当前系统需要的指标快照。

    整合所有计算结果，形成统一的指标报告。

    返回：
    {
        "qqq": {
            "price": ...,
            "ma5": ...,
            "ma20": ...,
            "ma50": ...,
            "ma200": ...,
            "ma20_slope": ...,
            "ma50_slope": ...,
            "atr14": ...,
            "daily_return": ...,
            "volume_ratio": ...
        },
        "relative_strength": {
            "qqq_vs_spy": ...,
            "qqqe_vs_qqq": ...
        },
        "mega_cap_tech": {...},
        "intraday": {
            "vwap": ...,
            "opening_30min": {...}
        }
    }
    """
    try:
        snapshot = {
            "qqq": {},
            "relative_strength": {},
            "mega_cap_tech": {},
            "intraday": {}
        }

        # 处理 QQQ 数据
        if "QQQ" in daily_data and not daily_data["QQQ"].empty:
            qqq_df = daily_data["QQQ"].copy()
            qqq_df = calculate_moving_averages(qqq_df)
            qqq_df = calculate_ma_slope(qqq_df, "ma20", window=5)
            qqq_df = calculate_ma_slope(qqq_df, "ma50", window=5)
            qqq_df = calculate_atr(qqq_df, window=14)
            qqq_df = calculate_volume_ratio(qqq_df, window=20)

            last_row = qqq_df.iloc[-1]
            snapshot["qqq"] = {
                "price": round(last_row["close"], 2),
                "ma5": round(last_row.get("ma5", 0), 2),
                "ma20": round(last_row.get("ma20", 0), 2),
                "ma50": round(last_row.get("ma50", 0), 2),
                "ma200": round(last_row.get("ma200", 0), 2),
                "ma20_slope": round(last_row.get("ma20_slope", 0), 2),
                "ma20_slope_pct": round(last_row.get("ma20_slope_pct", 0), 4),
                "ma50_slope": round(last_row.get("ma50_slope", 0), 2),
                "ma50_slope_pct": round(last_row.get("ma50_slope_pct", 0), 4),
                "atr14": round(last_row.get("atr14", 0), 2),
                "daily_return": round(calculate_daily_return(qqq_df), 4),
                "volume_ratio": round(last_row.get("volume_ratio", 1.0), 2)
            }
        else:
            logger.warning("build_indicator_snapshot: QQQ 数据缺失")

        # 计算相对强弱
        qqq_df = daily_data.get("QQQ")
        spy_df = daily_data.get("SPY")
        qqqe_df = daily_data.get("QQQE")

        if qqq_df is not None and spy_df is not None:
            snapshot["relative_strength"]["qqq_vs_spy"] = round(
                calculate_relative_strength(qqq_df, spy_df), 4
            )
        else:
            logger.warning("build_indicator_snapshot: QQQ 或 SPY 数据缺失")

        if qqqe_df is not None and qqq_df is not None:
            snapshot["relative_strength"]["qqqe_vs_qqq"] = round(
                calculate_relative_strength(qqqe_df, qqq_df), 4
            )
        else:
            logger.warning("build_indicator_snapshot: QQQE 或 QQQ 数据缺失")

        # 科技权重股分析
        from config.settings import MEGA_CAP_TECH_SYMBOLS
        tech_symbols = {sym: daily_data.get(sym) for sym in MEGA_CAP_TECH_SYMBOLS if sym in daily_data}
        tech_symbols = {k: v for k, v in tech_symbols.items() if v is not None}

        if tech_symbols:
            snapshot["mega_cap_tech"] = analyze_mega_cap_tech_strength(tech_symbols)
        else:
            logger.warning("build_indicator_snapshot: 科技权重股数据缺失")

        # 分钟线分析
        if intraday_data and "QQQ" in intraday_data and not intraday_data["QQQ"].empty:
            qqq_intraday = intraday_data["QQQ"]
            qqq_intraday = calculate_vwap(qqq_intraday)

            last_row = qqq_intraday.iloc[-1]
            snapshot["intraday"]["vwap"] = round(last_row.get("vwap", 0), 2)
            snapshot["intraday"]["opening_30min"] = analyze_opening_30min_structure(qqq_intraday)
        else:
            logger.warning("build_indicator_snapshot: 分钟线数据缺失")

        logger.info("指标快照构建完成")
        return snapshot

    except Exception as e:
        logger.error(f"构建指标快照失败：{str(e)}")
        return {
            "qqq": {},
            "relative_strength": {},
            "mega_cap_tech": {},
            "intraday": {},
            "error": str(e)
        }
