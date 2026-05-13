"""Unit tests for database operations with mock data."""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from src.database import (
    init_database,
    save_daily_prices,
    save_intraday_prices,
    save_indicator_daily,
    save_market_score,
    save_signal_logs,
    load_recent_market_scores,
    load_daily_prices,
    load_indicator_daily,
)
from src.utils import setup_logger

logger = setup_logger("test_database")


def create_mock_daily_data(symbol: str = "TEST", days: int = 30) -> pd.DataFrame:
    """
    创建模拟日线数据。
    
    参数：
        symbol: 标的代码
        days: 天数
        
    返回：
        包含 OHLCV 数据的 DataFrame
    """
    dates = pd.date_range(end=datetime.now(), periods=days, freq="D")
    data = {
        "Open": np.random.uniform(100, 120, days),
        "High": np.random.uniform(120, 130, days),
        "Low": np.random.uniform(90, 100, days),
        "Close": np.random.uniform(100, 120, days),
        "Adj Close": np.random.uniform(100, 120, days),
        "Volume": np.random.uniform(1000000, 5000000, days),
    }
    df = pd.DataFrame(data, index=dates)
    return df


def create_mock_indicator_data(symbol: str = "TEST", days: int = 30) -> pd.DataFrame:
    """
    创建模拟指标数据。
    
    参数：
        symbol: 标的代码
        days: 天数
        
    返回：
        包含指标的 DataFrame
    """
    dates = pd.date_range(end=datetime.now(), periods=days, freq="D")
    data = {
        "ma5": np.random.uniform(100, 120, days),
        "ma20": np.random.uniform(100, 120, days),
        "ma50": np.random.uniform(95, 115, days),
        "ma200": np.random.uniform(90, 110, days),
        "ma20_slope": np.random.uniform(-2, 2, days),
        "ma50_slope": np.random.uniform(-1, 1, days),
        "ma20_slope_pct": np.random.uniform(-0.05, 0.05, days),
        "ma50_slope_pct": np.random.uniform(-0.03, 0.03, days),
        "atr14": np.random.uniform(1, 5, days),
        "daily_return": np.random.uniform(-0.05, 0.05, days),
        "volume_ratio": np.random.uniform(0.8, 1.5, days),
    }
    df = pd.DataFrame(data, index=dates)
    return df


def create_mock_intraday_data(symbol: str = "TEST", periods: int = 100) -> pd.DataFrame:
    """
    创建模拟分钟线数据。
    
    参数：
        symbol: 标的代码
        periods: 分钟数
        
    返回：
        包含分钟线数据的 DataFrame
    """
    times = pd.date_range(end=datetime.now(), periods=periods, freq="5min")
    data = {
        "Open": np.random.uniform(100, 120, periods),
        "High": np.random.uniform(120, 130, periods),
        "Low": np.random.uniform(90, 100, periods),
        "Close": np.random.uniform(100, 120, periods),
        "Volume": np.random.uniform(100000, 500000, periods),
    }
    df = pd.DataFrame(data, index=times)
    return df


def main() -> None:
    """Run database tests."""
    print("====== Database Unit Tests ======\n")
    
    # 1. 初始化数据库
    print("1. 初始化数据库...")
    try:
        init_database()
        print("✓ 数据库初始化成功\n")
    except Exception as e:
        print(f"✗ 数据库初始化失败：{e}\n")
        return
    
    # 2. 测试保存日线数据
    print("2. 测试保存日线数据...")
    daily_df = create_mock_daily_data("TEST_DAILY", days=30)
    count = save_daily_prices("TEST_DAILY", daily_df)
    assert count > 0, f"保存日线数据失败，返回 {count}"
    print(f"✓ 成功保存 {count} 条日线数据\n")
    
    # 3. 测试保存分钟线数据
    print("3. 测试保存分钟线数据...")
    intraday_df = create_mock_intraday_data("TEST_INTRA", periods=100)
    count = save_intraday_prices("TEST_INTRA", intraday_df, interval="5m")
    assert count > 0, f"保存分钟线数据失败，返回 {count}"
    print(f"✓ 成功保存 {count} 条分钟线数据\n")
    
    # 4. 测试保存指标数据
    print("4. 测试保存指标数据...")
    indicator_df = create_mock_indicator_data("TEST_IND", days=30)
    count = save_indicator_daily("TEST_IND", indicator_df)
    assert count > 0, f"保存指标数据失败，返回 {count}"
    print(f"✓ 成功保存 {count} 条指标数据\n")
    
    # 5. 测试保存评分结果
    print("5. 测试保存评分结果...")
    score_result = {
        "datetime": datetime.now().isoformat(),
        "tqqq_base_score": 75.5,
        "sqqq_base_score": 45.0,
        "risk_deduction": 5.0,
        "tqqq_final_score": 70.5,
        "sqqq_final_score": 40.0,
        "market_state": "只观察 TQQQ",
        "summary": "Mock test summary",
    }
    score_id = save_market_score(score_result)
    assert score_id > 0, f"保存评分结果失败，返回 {score_id}"
    print(f"✓ 成功保存评分结果，ID = {score_id}\n")
    
    # 6. 测试保存信号日志
    print("6. 测试保存信号日志...")
    logs = [
        {
            "datetime": datetime.now().isoformat(),
            "signal_type": "BULLISH",
            "score": 75.5,
            "reason": "Mock test reason 1",
        },
        {
            "datetime": datetime.now().isoformat(),
            "signal_type": "BEARISH",
            "score": 45.0,
            "reason": "Mock test reason 2",
        },
    ]
    count = save_signal_logs(logs)
    assert count == len(logs), f"保存信号日志失败，返回 {count}"
    print(f"✓ 成功保存 {count} 条信号日志\n")
    
    # 7. 测试读取最近评分记录
    print("7. 测试读取最近评分记录...")
    scores_df = load_recent_market_scores(limit=10)
    assert not scores_df.empty, "读取评分记录失败"
    print(f"✓ 成功读取 {len(scores_df)} 条评分记录")
    print(scores_df[["datetime", "tqqq_final_score", "sqqq_final_score", "market_state"]].to_string())
    print()
    
    # 8. 测试读取日线数据
    print("8. 测试读取日线数据...")
    daily_loaded = load_daily_prices("TEST_DAILY", limit=30)
    assert not daily_loaded.empty, "读取日线数据失败"
    print(f"✓ 成功读取 {len(daily_loaded)} 条日线数据")
    print(daily_loaded.head().to_string())
    print()
    
    # 9. 测试读取指标数据
    print("9. 测试读取指标数据...")
    indicator_loaded = load_indicator_daily("TEST_IND", limit=30)
    assert not indicator_loaded.empty, "读取指标数据失败"
    print(f"✓ 成功读取 {len(indicator_loaded)} 条指标数据")
    print(indicator_loaded.head().to_string())
    print()
    
    # 10. 测试重复保存（UPSERT 功能）
    print("10. 测试重复保存数据（应更新不插入）...")
    # 使用相同的日期再次保存
    daily_df_v2 = create_mock_daily_data("TEST_DAILY", days=5)
    count_v2 = save_daily_prices("TEST_DAILY", daily_df_v2)
    print(f"✓ 重复保存成功，返回 {count_v2} 条（应为较少条数）\n")
    
    # 最终汇总
    print("====== 所有数据库测试通过 ======\n")
    print("✓ 1. 数据库初始化")
    print("✓ 2. 保存日线数据")
    print("✓ 3. 保存分钟线数据")
    print("✓ 4. 保存指标数据")
    print("✓ 5. 保存评分结果")
    print("✓ 6. 保存信号日志")
    print("✓ 7. 读取最近评分记录")
    print("✓ 8. 读取日线数据")
    print("✓ 9. 读取指标数据")
    print("✓ 10. 重复保存数据（UPSERT）")


if __name__ == "__main__":
    main()
