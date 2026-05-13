"""Central configuration for the TQQQ / SQQQ signal project."""

# Database configuration
DATABASE_PATH = "data/market_data.db"

ETF_SYMBOLS = ["QQQ", "TQQQ", "SQQQ", "SPY", "QQQE"]

MEGA_CAP_TECH_SYMBOLS = [
    "NVDA",
    "MSFT",
    "AAPL",
    "AMZN",
    "META",
    "GOOGL",
    "AVGO",
    "TSLA",
]

VOLATILITY_SYMBOLS = {
    "VIX": "^VIX",
    "VXN": "^VXN",
}

FUTURES_SYMBOLS = {
    "NQ": "NQ=F",
    "ES": "ES=F",
    "MNQ": "MNQ=F",
    "MES": "MES=F",
}

INDICATOR_PARAMS = {
    "ma_short": 5,
    "ma_20": 20,
    "ma_50": 50,
    "ma_200": 200,
    "atr_window": 14,
    "volume_window": 20,
    "slope_window": 5,
}

SCORE_THRESHOLDS = {
    "strong": 85,
    "watch": 75,
    "weak_watch": 65,
}

RISK_EVENTS = {
    # "2026-05-13": ["CPI"],
    # "2026-06-12": ["FOMC"],
}

RISK_DISCLOSURE = (
    "本系统仅用于个人量化研究和交易辅助，不构成任何投资建议。"
    "TQQQ/SQQQ 为三倍杠杆ETF，波动较大，不适合长期持有，请严格控制仓位和风险。"
)

# Backtest configuration
BACKTEST_PARAMS = {
    # TQQQ 交易规则
    "tqqq_signal_threshold": 75,
    "tqqq_sqqq_threshold": 65,
    "tqqq_take_profit": 0.06,  # 6%
    "tqqq_stop_loss": -0.03,  # -3%
    "tqqq_max_holding_days": 3,
    # SQQQ 交易规则
    "sqqq_signal_threshold": 85,
    "sqqq_tqqq_threshold": 65,
    "sqqq_take_profit": 0.05,  # 5%
    "sqqq_stop_loss": -0.03,  # -3%
    "sqqq_max_holding_days": 2,
    # 交易成本
    "transaction_cost": 0.001,  # 0.1%
}

BACKTEST_DISCLOSURE = (
    "回测结果仅用于策略研究，不代表未来表现。历史收益不构成投资建议。"
    "TQQQ/SQQQ 为高波动三倍杠杆ETF，请严格控制风险。"
)
