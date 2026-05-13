"""Data fetching module for yfinance data sources."""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd
import yfinance as yf

from src.utils import setup_logger

logger = setup_logger("data_fetcher")


def normalize_ohlcv_dataframe(
    df: pd.DataFrame,
    symbol: str,
    is_intraday: bool = False,
) -> pd.DataFrame:
    """标准化 yfinance 返回的 OHLCV 数据字段。"""
    if df is None or df.empty:
        return pd.DataFrame()

    normalized = df.copy()
    normalized = normalized.reset_index(drop=False)
    normalized.columns = [str(col).strip().lower().replace(" ", "_") for col in normalized.columns]

    if "adj_close" not in normalized.columns and "adjclose" in normalized.columns:
        normalized = normalized.rename(columns={"adjclose": "adj_close"})

    if is_intraday:
        if "datetime" not in normalized.columns:
            if "date" in normalized.columns:
                normalized = normalized.rename(columns={"date": "datetime"})
            elif "index" in normalized.columns:
                normalized = normalized.rename(columns={"index": "datetime"})
        if "datetime" in normalized.columns:
            normalized["datetime"] = pd.to_datetime(normalized["datetime"], errors="coerce")
    else:
        if "date" not in normalized.columns:
            if "datetime" in normalized.columns:
                normalized = normalized.rename(columns={"datetime": "date"})
            elif "index" in normalized.columns:
                normalized = normalized.rename(columns={"index": "date"})
        if "date" in normalized.columns:
            normalized["date"] = pd.to_datetime(normalized["date"], errors="coerce")

    normalized["symbol"] = symbol

    if is_intraday:
        required_columns = ["datetime", "open", "high", "low", "close", "volume", "symbol"]
    else:
        required_columns = ["date", "open", "high", "low", "close", "volume", "symbol"]

    for col in required_columns:
        if col not in normalized.columns:
            normalized[col] = pd.NA

    sort_col = "datetime" if is_intraday else "date"
    normalized = normalized.sort_values(sort_col).reset_index(drop=True)

    keep_cols = required_columns.copy()
    if not is_intraday and "adj_close" in normalized.columns:
        keep_cols.insert(5, "adj_close")

    return normalized[keep_cols]


def fetch_daily_data(symbol: str, period: str = "1y") -> pd.DataFrame:
    """
    使用 yfinance 抓取单个标的的日线数据。

    参数：
        symbol: 标的代码，例如 "QQQ"
        period: 历史周期，例如 "6mo", "1y", "2y"

    返回：
        pandas DataFrame，至少包含：
        date, open, high, low, close, adj_close, volume, symbol

    要求：
        1. 如果数据为空，返回空 DataFrame，不要抛出未处理异常；
        2. 捕获网络异常；
        3. 输出日志；
        4. 保证索引或字段中有日期信息；
        5. 统一字段名称，便于后续处理。
    """
    try:
        logger.info(f"正在抓取 {symbol} 日线数据（周期：{period}）...")
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period)

        if df.empty:
            logger.warning(f"{symbol} 返回空数据")
            return pd.DataFrame()

        df = normalize_ohlcv_dataframe(df, symbol=symbol, is_intraday=False)

        logger.info(f"{symbol} 日线数据获取成功，共 {len(df)} 条。")
        return df

    except Exception as e:
        logger.error(f"{symbol} 日线数据获取失败：{str(e)}")
        return pd.DataFrame()


def fetch_intraday_data(
    symbol: str,
    interval: str = "5m",
    period: str = "5d"
) -> pd.DataFrame:
    """
    使用 yfinance 抓取单个标的的分钟线数据。

    参数：
        symbol: 标的代码，例如 "QQQ"
        interval: 分钟周期，例如 "1m", "5m", "15m"
        period: 周期，例如 "1d", "5d", "1mo"

    返回：
        pandas DataFrame，至少包含：
        datetime, open, high, low, close, volume, symbol

    要求：
        1. 如果数据为空，返回空 DataFrame；
        2. 捕获异常；
        3. 输出日志；
        4. 注意 yfinance 对 1m 数据周期有限制；
        5. 统一字段名称。
    """
    try:
        logger.info(f"正在抓取 {symbol} 分钟线数据（间隔：{interval}, 周期：{period}）...")
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, interval=interval)

        if df.empty:
            logger.warning(f"{symbol} {interval} 数据返回空结果")
            return pd.DataFrame()

        df = normalize_ohlcv_dataframe(df, symbol=symbol, is_intraday=True)

        logger.info(f"{symbol} 分钟线数据获取成功，共 {len(df)} 条。")
        return df

    except Exception as e:
        logger.error(f"{symbol} 分钟线数据获取失败：{str(e)}")
        return pd.DataFrame()


def fetch_multiple_daily_data(
    symbols: list[str],
    period: str = "1y"
) -> dict[str, pd.DataFrame]:
    """
    批量抓取多个标的的日线数据。

    参数：
        symbols: 标的列表
        period: 历史周期

    返回：
        dict，key 为 symbol，value 为 DataFrame。
        如果某个标的失败，返回空 DataFrame。
    """
    result = {}
    for symbol in symbols:
        result[symbol] = fetch_daily_data(symbol, period=period)
    return result


def fetch_multiple_intraday_data(
    symbols: list[str],
    interval: str = "5m",
    period: str = "5d"
) -> dict[str, pd.DataFrame]:
    """
    批量抓取多个标的的分钟线数据。

    参数：
        symbols: 标的列表
        interval: 分钟周期
        period: 周期

    返回：
        dict，key 为 symbol，value 为 DataFrame。
        如果某个标的失败，返回空 DataFrame。
    """
    result = {}
    for symbol in symbols:
        result[symbol] = fetch_intraday_data(symbol, interval=interval, period=period)
    return result


def fetch_latest_price(symbol: str) -> dict[str, Any]:
    """
    抓取单个标的的最新价格信息。

    参数：
        symbol: 标的代码

    返回示例：
    {
        "symbol": "QQQ",
        "price": 450.12,
        "previous_close": 448.00,
        "change": 2.12,
        "change_pct": 0.0047,
        "source": "yfinance"
    }

    如果失败，返回：
    {
        "symbol": "QQQ",
        "price": None,
        "error": "..."
    }
    """
    try:
        logger.info(f"正在抓取 {symbol} 最新价格...")
        ticker = yf.Ticker(symbol)
        info = ticker.info

        price = info.get("currentPrice") or info.get("regularMarketPrice")
        previous_close = info.get("previousClose") or info.get("regularMarketPreviousClose")

        if price is None:
            logger.warning(f"{symbol} 无法获取最新价格")
            return {
                "symbol": symbol,
                "price": None,
                "error": "无法获取最新价格"
            }

        change = price - previous_close if previous_close else None
        change_pct = (change / previous_close) if previous_close and previous_close != 0 else None

        result = {
            "symbol": symbol,
            "price": price,
            "previous_close": previous_close,
            "change": change,
            "change_pct": change_pct,
            "source": "yfinance"
        }
        logger.info(f"{symbol} 获取成功，当前价格：{price}")
        return result

    except Exception as e:
        logger.error(f"{symbol} 价格抓取失败：{str(e)}")
        return {
            "symbol": symbol,
            "price": None,
            "error": str(e)
        }


def fetch_market_snapshot() -> dict[str, dict]:
    """
    抓取系统所需的核心市场快照。

    包括：
        ETF_SYMBOLS
        MEGA_CAP_TECH_SYMBOLS
        VOLATILITY_SYMBOLS
        FUTURES_SYMBOLS

    返回 dict：
    {
        "etfs": {...},
        "mega_cap_tech": {...},
        "volatility": {...},
        "futures": {...}
    }

    如果某些数据抓取失败，不影响其他数据。
    """
    from config.settings import (
        ETF_SYMBOLS,
        MEGA_CAP_TECH_SYMBOLS,
        VOLATILITY_SYMBOLS,
        FUTURES_SYMBOLS,
    )

    logger.info("正在抓取市场快照...")

    snapshot = {
        "etfs": {},
        "mega_cap_tech": {},
        "volatility": {},
        "futures": {}
    }

    # 抓取 ETF 数据
    for symbol in ETF_SYMBOLS:
        snapshot["etfs"][symbol] = fetch_latest_price(symbol)

    # 抓取权重科技股数据
    for symbol in MEGA_CAP_TECH_SYMBOLS:
        snapshot["mega_cap_tech"][symbol] = fetch_latest_price(symbol)

    # 抓取波动率指数数据
    for name, symbol in VOLATILITY_SYMBOLS.items():
        snapshot["volatility"][name] = fetch_latest_price(symbol)

    # 抓取期货数据
    for name, symbol in FUTURES_SYMBOLS.items():
        snapshot["futures"][name] = fetch_latest_price(symbol)

    logger.info("市场快照抓取完成。")
    return snapshot
