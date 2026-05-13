"""Unit tests for indicators module with mock data."""

import pandas as pd
import numpy as np
from src.indicators import (
    calculate_moving_averages,
    calculate_ma_slope,
    calculate_atr,
    calculate_volume_ratio,
    calculate_daily_return,
    calculate_relative_strength,
    calculate_vwap,
    analyze_opening_30min_structure,
    analyze_mega_cap_tech_strength,
    build_indicator_snapshot,
)


def create_sample_daily_data(days: int = 250, base_price: float = 100.0) -> pd.DataFrame:
    """Create sample daily OHLCV data."""
    dates = pd.date_range(end="2026-05-13", periods=days)
    
    # 生成价格数据（随机游走）
    returns = np.random.normal(0.0005, 0.02, days)
    prices = base_price * (1 + returns).cumprod()
    
    df = pd.DataFrame({
        "date": dates,
        "open": prices * (1 + np.random.uniform(-0.01, 0.01, days)),
        "high": prices * (1 + np.random.uniform(0, 0.02, days)),
        "low": prices * (1 - np.random.uniform(0, 0.02, days)),
        "close": prices,
        "adj_close": prices,
        "volume": np.random.uniform(50000000, 100000000, days),
        "symbol": "TEST"
    })
    
    return df.reset_index(drop=True)


def create_sample_intraday_data(bars: int = 100) -> pd.DataFrame:
    """Create sample intraday OHLCV data."""
    times = pd.date_range(end="2026-05-13 16:00", periods=bars, freq="5min")
    
    base_price = 150.0
    returns = np.random.normal(0, 0.001, bars)
    prices = base_price * (1 + returns).cumprod()
    
    df = pd.DataFrame({
        "datetime": times,
        "open": prices * (1 + np.random.uniform(-0.001, 0.001, bars)),
        "high": prices * (1 + np.random.uniform(0, 0.002, bars)),
        "low": prices * (1 - np.random.uniform(0, 0.002, bars)),
        "close": prices,
        "volume": np.random.uniform(1000000, 3000000, bars),
        "symbol": "QQQ"
    })
    
    return df.reset_index(drop=True)


def test_moving_averages():
    """Test moving average calculation."""
    print("Testing calculate_moving_averages...")
    df = create_sample_daily_data(250)
    df = calculate_moving_averages(df)
    
    assert "ma5" in df.columns, "ma5 column missing"
    assert "ma20" in df.columns, "ma20 column missing"
    assert "ma50" in df.columns, "ma50 column missing"
    assert "ma200" in df.columns, "ma200 column missing"
    
    # 最后一行不应该是 NaN
    assert not pd.isna(df["ma20"].iloc[-1]), "ma20 at last row is NaN"
    
    # MA5 应该比 MA200 反应更快
    recent_ma5 = df["ma5"].iloc[-1]
    recent_ma200 = df["ma200"].iloc[-1]
    assert abs(recent_ma5 - df["close"].iloc[-1]) < abs(recent_ma200 - df["close"].iloc[-1])
    
    print("✓ Moving averages test passed")


def test_ma_slope():
    """Test MA slope calculation."""
    print("Testing calculate_ma_slope...")
    df = create_sample_daily_data(250)
    df = calculate_moving_averages(df)
    df = calculate_ma_slope(df, "ma20", window=5)
    
    assert "ma20_slope" in df.columns, "ma20_slope column missing"
    assert "ma20_slope_pct" in df.columns, "ma20_slope_pct column missing"
    
    # 最后一行应该有值
    assert not pd.isna(df["ma20_slope"].iloc[-1]), "ma20_slope at last row is NaN"
    
    print("✓ MA slope test passed")


def test_atr():
    """Test ATR calculation."""
    print("Testing calculate_atr...")
    df = create_sample_daily_data(250)
    df = calculate_atr(df, window=14)
    
    assert "tr" in df.columns, "tr column missing"
    assert "atr14" in df.columns, "atr14 column missing"
    
    # ATR 应该是正数
    assert (df["atr14"] > 0).any(), "ATR should have positive values"
    
    print("✓ ATR test passed")


def test_volume_ratio():
    """Test volume ratio calculation."""
    print("Testing calculate_volume_ratio...")
    df = create_sample_daily_data(250)
    df = calculate_volume_ratio(df, window=20)
    
    assert "volume_ma20" in df.columns, "volume_ma20 column missing"
    assert "volume_ratio" in df.columns, "volume_ratio column missing"
    
    # 成交量比例应该在合理范围内
    assert (df["volume_ratio"] > 0).all(), "volume_ratio should be positive"
    
    print("✓ Volume ratio test passed")


def test_daily_return():
    """Test daily return calculation."""
    print("Testing calculate_daily_return...")
    df = create_sample_daily_data(250)
    
    ret = calculate_daily_return(df)
    
    # 返回值应该在 -1 到 1 之间
    assert -1 < ret < 1, f"Daily return {ret} out of reasonable range"
    
    print(f"✓ Daily return test passed (return: {ret:.4f})")


def test_relative_strength():
    """Test relative strength calculation."""
    print("Testing calculate_relative_strength...")
    df1 = create_sample_daily_data(250, base_price=100)
    df2 = create_sample_daily_data(250, base_price=100)
    
    rs = calculate_relative_strength(df1, df2)
    
    # 相对强弱应该在合理范围内
    assert -1 < rs < 1, f"Relative strength {rs} out of reasonable range"
    
    print(f"✓ Relative strength test passed (rs: {rs:.4f})")


def test_vwap():
    """Test VWAP calculation."""
    print("Testing calculate_vwap...")
    df = create_sample_intraday_data(100)
    df = calculate_vwap(df)
    
    assert "typical_price" in df.columns, "typical_price column missing"
    assert "vwap" in df.columns, "vwap column missing"
    
    # VWAP 应该有正数值
    assert (df["vwap"] > 0).all(), "VWAP should have positive values"
    
    # VWAP 应该大致在合理的价格范围内（close价格附近）
    avg_vwap = df["vwap"].mean()
    avg_close = df["close"].mean()
    assert abs(avg_vwap - avg_close) / avg_close < 0.1, "VWAP average should be close to close average"
    
    print("✓ VWAP test passed")


def test_opening_30min():
    """Test opening 30-minute structure analysis."""
    print("Testing analyze_opening_30min_structure...")
    df = create_sample_intraday_data(100)
    
    result = analyze_opening_30min_structure(df)
    
    assert "has_data" in result, "has_data missing in result"
    assert "description" in result, "description missing in result"
    
    if result["has_data"]:
        assert "open_price" in result, "open_price missing"
        assert "close_30m" in result, "close_30m missing"
        print(f"✓ Opening 30min structure test passed: {result['description']}")
    else:
        print("✓ Opening 30min structure test passed (no data)")


def test_mega_cap_tech_strength():
    """Test mega-cap tech strength analysis."""
    print("Testing analyze_mega_cap_tech_strength...")
    
    # 创建8只科技股的样本数据
    symbols_data = {}
    for symbol in ["NVDA", "MSFT", "AAPL", "AMZN", "META", "GOOGL", "AVGO", "TSLA"]:
        symbols_data[symbol] = create_sample_daily_data(250, base_price=100 + np.random.uniform(-20, 20))
    
    result = analyze_mega_cap_tech_strength(symbols_data)
    
    assert "up_count" in result, "up_count missing"
    assert "down_count" in result, "down_count missing"
    assert "status" in result, "status missing"
    
    # 总数应该等于8
    total = result["up_count"] + result["down_count"] + result.get("flat_count", 0)
    assert total == 8, f"Total count should be 8, got {total}"
    
    print(f"✓ Mega-cap tech strength test passed: {result['status']} (up: {result['up_count']}, down: {result['down_count']})")


def test_snapshot_with_empty_data():
    """Test snapshot building with empty data."""
    print("Testing build_indicator_snapshot with empty data...")
    
    snapshot = build_indicator_snapshot({})
    
    assert "qqq" in snapshot, "qqq missing in snapshot"
    assert "relative_strength" in snapshot, "relative_strength missing"
    
    print("✓ Snapshot with empty data test passed")


def test_snapshot_with_full_data():
    """Test snapshot building with complete data."""
    print("Testing build_indicator_snapshot with full data...")
    
    daily_data = {
        "QQQ": create_sample_daily_data(250, base_price=150),
        "SPY": create_sample_daily_data(250, base_price=450),
        "QQQE": create_sample_daily_data(250, base_price=75),
        "NVDA": create_sample_daily_data(250, base_price=900),
        "MSFT": create_sample_daily_data(250, base_price=420),
        "AAPL": create_sample_daily_data(250, base_price=190),
        "AMZN": create_sample_daily_data(250, base_price=190),
        "META": create_sample_daily_data(250, base_price=500),
        "GOOGL": create_sample_daily_data(250, base_price=140),
        "AVGO": create_sample_daily_data(250, base_price=120),
        "TSLA": create_sample_daily_data(250, base_price=250),
    }
    
    intraday_data = {
        "QQQ": create_sample_intraday_data(100)
    }
    
    snapshot = build_indicator_snapshot(daily_data, intraday_data)
    
    assert "qqq" in snapshot, "qqq missing in snapshot"
    assert snapshot["qqq"], "qqq should have data"
    
    print("✓ Snapshot with full data test passed")


def main():
    """Run all tests."""
    print("====== Indicators Module Tests ======\n")
    
    test_moving_averages()
    test_ma_slope()
    test_atr()
    test_volume_ratio()
    test_daily_return()
    test_relative_strength()
    test_vwap()
    test_opening_30min()
    test_mega_cap_tech_strength()
    test_snapshot_with_empty_data()
    test_snapshot_with_full_data()
    
    print("\n====== All Tests Passed ======\n")


if __name__ == "__main__":
    main()
