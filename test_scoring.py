"""Unit tests for scoring and risk filter modules with mock data."""

from src.scoring import calculate_tqqq_score, calculate_sqqq_score, calculate_final_score
from src.risk_filter import check_risk_events, get_risk_deduction
from src.market_state import (
    classify_tqqq_state,
    classify_sqqq_state,
    classify_overall_market_state,
)


def create_bullish_snapshot() -> dict:
    """Create a bullish market snapshot for testing."""
    return {
        "qqq": {
            "price": 380.0,
            "ma5": 378.0,
            "ma20": 370.0,
            "ma50": 360.0,
            "ma200": 350.0,
            "ma20_slope": 3.5,
            "ma20_slope_pct": 0.0094,
            "ma50_slope": 4.0,
            "ma50_slope_pct": 0.0111,
            "atr14": 8.5,
            "daily_return": 0.015,  # +1.5%
            "volume_ratio": 1.2,
        },
        "relative_strength": {
            "qqq_vs_spy": 0.008,  # QQQ 强于 SPY
            "qqqe_vs_qqq": 0.005,  # QQQE 强于 QQQ
        },
        "mega_cap_tech": {
            "up_count": 7,
            "down_count": 1,
            "flat_count": 0,
            "avg_return": 0.012,
            "median_return": 0.010,
            "details": {
                "NVDA": 0.025,
                "MSFT": 0.012,
                "AAPL": 0.008,
                "AMZN": 0.015,
                "META": 0.020,
                "GOOGL": 0.010,
                "AVGO": 0.005,
                "TSLA": -0.003,
            },
            "status": "strong",
        },
        "intraday": {
            "vwap": 378.5,
            "opening_30min": {
                "has_data": True,
                "open_price": 376.0,
                "close_30m": 378.5,
                "is_strong_opening": True,
                "description": "强势开盘：预示向上",
            },
        },
        "futures_snapshot": {
            "available": True,
            "nq_return": 0.012,
            "es_return": 0.006,
            "nq_vs_es": 0.006,
            "nq_stronger_than_es": True,
            "nq_weaker_than_es": False,
            "nq_trend": {"trend": "up"},
            "gap_vs_atr": 0.9,
            "warnings": [],
        },
        "breadth_snapshot": {
            "available": True,
            "up_ratio": 0.72,
            "down_ratio": 0.20,
            "above_ma20_ratio": 0.68,
            "above_ma50_ratio": 0.61,
            "breadth_status": "strong",
            "warnings": [],
        },
    }


def create_bearish_snapshot() -> dict:
    """Create a bearish market snapshot for testing."""
    return {
        "qqq": {
            "price": 350.0,
            "ma5": 352.0,
            "ma20": 360.0,
            "ma50": 370.0,
            "ma200": 380.0,
            "ma20_slope": -3.5,
            "ma20_slope_pct": -0.0094,
            "ma50_slope": -4.0,
            "ma50_slope_pct": -0.0108,
            "atr14": 9.2,
            "daily_return": -0.025,  # -2.5%
            "volume_ratio": 1.5,
        },
        "relative_strength": {
            "qqq_vs_spy": -0.012,  # QQQ 弱于 SPY
            "qqqe_vs_qqq": -0.008,  # QQQE 弱于 QQQ
        },
        "mega_cap_tech": {
            "up_count": 2,
            "down_count": 6,
            "flat_count": 0,
            "avg_return": -0.018,
            "median_return": -0.015,
            "details": {
                "NVDA": -0.035,
                "MSFT": -0.020,
                "AAPL": -0.015,
                "AMZN": -0.010,
                "META": -0.025,
                "GOOGL": 0.005,
                "AVGO": -0.008,
                "TSLA": 0.010,
            },
            "status": "weak",
        },
        "intraday": {
            "vwap": 352.5,
            "opening_30min": {
                "has_data": True,
                "open_price": 355.0,
                "close_30m": 350.5,
                "is_weak_opening": True,
                "description": "弱势开盘：预示向下",
            },
        },
        "futures_snapshot": {
            "available": True,
            "nq_return": -0.018,
            "es_return": -0.005,
            "nq_vs_es": -0.013,
            "nq_stronger_than_es": False,
            "nq_weaker_than_es": True,
            "nq_trend": {"trend": "down"},
            "gap_vs_atr": 1.1,
            "warnings": [],
        },
        "breadth_snapshot": {
            "available": True,
            "up_ratio": 0.18,
            "down_ratio": 0.74,
            "above_ma20_ratio": 0.28,
            "above_ma50_ratio": 0.22,
            "breadth_status": "weak",
            "warnings": [],
        },
    }


def create_neutral_snapshot() -> dict:
    snapshot = create_bullish_snapshot()
    snapshot["futures_snapshot"] = {"available": False, "warnings": ["期货缺失"]}
    snapshot["breadth_snapshot"] = {"available": False, "warnings": ["宽度缺失"]}
    return snapshot


def test_tqqq_bullish():
    """Test TQQQ scoring with bullish data."""
    print("Testing TQQQ Bullish Scenario...")
    snapshot = create_bullish_snapshot()
    result = calculate_tqqq_score(snapshot)
    
    base_score = result.get("base_score", 0)
    assert base_score > 50, f"Expected high TQQQ score, got {base_score}"
    
    module_scores = result.get("module_scores", {})
    assert module_scores.get("trend", 0) >= 15, "Trend should score high in bullish"
    assert module_scores.get("mega_cap_tech", 0) == 10, "All tech stocks up"
    assert module_scores.get("futures", 0) >= 10, "Futures should add bullish confirmation"
    assert module_scores.get("breadth", 0) >= 10, "Breadth should add bullish confirmation"
    
    print(f"✓ TQQQ Bullish: {base_score:.0f} points")


def test_sqqq_bearish():
    """Test SQQQ scoring with bearish data."""
    print("Testing SQQQ Bearish Scenario...")
    snapshot = create_bearish_snapshot()
    result = calculate_sqqq_score(snapshot)
    
    base_score = result.get("base_score", 0)
    assert base_score > 40, f"Expected moderate SQQQ score, got {base_score}"
    
    module_scores = result.get("module_scores", {})
    assert module_scores.get("breakdown", 0) >= 15, "Breakdown should score high"
    assert module_scores.get("mega_cap_tech", 0) == 10, "Most tech stocks down"
    assert module_scores.get("weakness", 0) >= 12, "Futures weakness should score high"
    assert module_scores.get("breadth", 0) >= 10, "Breadth weakness should score high"
    
    print(f"✓ SQQQ Bearish: {base_score:.0f} points")


def test_final_score_calculation():
    """Test final score calculation with risk deduction."""
    print("Testing Final Score Calculation...")
    
    base_score = 80
    risk_deduction = 10
    final = calculate_final_score(base_score, risk_deduction)
    
    assert final == 70, f"Expected 70, got {final}"
    
    # Test with high deduction
    final2 = calculate_final_score(40, 50)
    assert final2 == 0, f"Expected 0 (floor), got {final2}"
    
    print(f"✓ Final Score: {base_score} - {risk_deduction} = {final}")


def test_risk_events():
    """Test risk event detection."""
    print("Testing Risk Event Detection...")
    
    # Test with the actual RISK_EVENTS configuration
    # Note: We test what's actually configured, not dynamic modification
    from src.risk_filter import check_risk_events
    
    # Since RISK_EVENTS is empty by default, test with empty result
    events = check_risk_events("2026-05-13")
    assert isinstance(events, list), f"Expected list, got {type(events)}"
    
    # Test that no events return empty list
    events_no_match = check_risk_events("2099-12-31")
    assert events_no_match == [], f"Expected [], got {events_no_match}"
    
    print("✓ Risk Events Detection")


def test_state_classification():
    """Test market state classification."""
    print("Testing State Classification...")
    
    # TQQQ states
    assert classify_tqqq_state(90) == "强多环境"
    assert classify_tqqq_state(80) == "偏多环境"
    assert classify_tqqq_state(70) == "弱多观察"
    assert classify_tqqq_state(50) == "不适合做多"
    
    # SQQQ states
    assert classify_sqqq_state(90) == "强空环境"
    assert classify_sqqq_state(80) == "偏空环境"
    assert classify_sqqq_state(70) == "弱空观察"
    assert classify_sqqq_state(50) == "不适合做空"
    
    print("✓ State Classification")


def test_overall_market_state():
    """Test overall market state classification."""
    print("Testing Overall Market State...")
    
    # TQQQ strong (>=75), SQQQ weak (<65) -> Only watch TQQQ
    state = classify_overall_market_state(80, 50)
    assert state == "只观察 TQQQ", f"Expected '只观察 TQQQ', got {state}"
    
    # SQQQ strong (>=75), TQQQ weak (<65) -> Only watch SQQQ
    state = classify_overall_market_state(50, 80)
    assert state == "只观察 SQQQ", f"Expected '只观察 SQQQ', got {state}"
    
    # Both weak (<65, <65) -> Wait for signal
    state = classify_overall_market_state(40, 30)
    assert state == "空仓等待", f"Expected '空仓等待', got {state}"
    
    # Both moderate/strong (>=65, >=65) but with clear difference (>= 5) -> Market confused
    state = classify_overall_market_state(85, 75)
    assert state == "市场混乱，不交易", f"Expected '市场混乱，不交易', got {state}"
    
    # Close scores (差值 < 5) -> Unclear direction
    state = classify_overall_market_state(72, 70)
    assert state == "方向不明确，不交易", f"Expected '方向不明确，不交易', got {state}"
    
    # Same scores (completely unclear)
    state = classify_overall_market_state(80, 80)
    assert state == "方向不明确，不交易", f"Expected '方向不明确，不交易', got {state}"
    
    print("✓ Overall Market State Classification")


def test_risk_deduction():
    """Test risk deduction calculation."""
    print("Testing Risk Deduction...")
    
    # Test with empty RISK_EVENTS (default)
    result = get_risk_deduction("2026-05-13")
    deduction = result.get("deduction", 0)
    events = result.get("events", [])
    
    assert isinstance(deduction, (int, float)), f"Expected numeric deduction, got {type(deduction)}"
    assert isinstance(events, list), f"Expected list of events, got {type(events)}"
    
    # Test with date that has no events
    result2 = get_risk_deduction("2026-05-14")
    assert result2.get("deduction", 0) == 0, "Should have 0 deduction with no events"
    
    print(f"✓ Risk Deduction: {deduction:.0f} points")


def test_bullish_vs_bearish():
    """Compare bullish and bearish scores."""
    print("Testing Bullish vs Bearish Comparison...")
    
    bullish = create_bullish_snapshot()
    bearish = create_bearish_snapshot()
    
    tqqq_bullish = calculate_tqqq_score(bullish).get("base_score", 0)
    tqqq_bearish = calculate_tqqq_score(bearish).get("base_score", 0)
    
    sqqq_bullish = calculate_sqqq_score(bullish).get("base_score", 0)
    sqqq_bearish = calculate_sqqq_score(bearish).get("base_score", 0)
    
    # In bullish market, TQQQ should score higher than SQQQ
    assert tqqq_bullish > sqqq_bullish, "TQQQ should score higher in bullish"
    
    # In bearish market, SQQQ should score higher than TQQQ
    assert sqqq_bearish > tqqq_bearish, "SQQQ should score higher in bearish"
    
    print(f"✓ Bullish: TQQQ {tqqq_bullish:.0f} > SQQQ {sqqq_bullish:.0f}")
    print(f"✓ Bearish: SQQQ {sqqq_bearish:.0f} > TQQQ {tqqq_bearish:.0f}")


def test_futures_and_breadth_increase_scores() -> None:
    print("Testing Futures and Breadth Impact...")
    bullish = create_bullish_snapshot()
    neutral = create_neutral_snapshot()
    bearish = create_bearish_snapshot()

    assert calculate_tqqq_score(bullish).get("base_score", 0) > calculate_tqqq_score(neutral).get("base_score", 0)
    assert calculate_sqqq_score(bearish).get("base_score", 0) > calculate_sqqq_score(neutral).get("base_score", 0)

    print("✓ Futures and breadth affect scores as expected")


def main():
    """Run all tests."""
    print("====== Scoring & Risk Filter Unit Tests ======\n")
    
    test_tqqq_bullish()
    test_sqqq_bearish()
    test_final_score_calculation()
    test_risk_events()
    test_state_classification()
    test_overall_market_state()
    test_risk_deduction()
    test_bullish_vs_bearish()
    test_futures_and_breadth_increase_scores()
    
    print("\n====== All Tests Passed ======\n")


if __name__ == "__main__":
    main()
