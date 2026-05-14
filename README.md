# nasdaq_quant_signal

TQQQ / SQQQ 纳指量化信号辅助系统。

## 项目状态

第三期功能已完成，进入 coding review / P1 收口阶段。

本项目用于个人量化研究与交易辅助，核心目标是辅助判断当前市场环境更适合观察 TQQQ、SQQQ，还是保持空仓。它不是自动交易系统，也不构成任何投资建议。

## 当前模块

- `data_provider`：统一封装不同数据源的获取接口
- `cache`：管理缓存、fallback 与数据来源标记
- `rate_limiter`：控制请求节奏与重试
- `pipeline`：统一信号流程入口，供命令行与页面复用
- `data_quality`：根据 freshness、fallback、mock 与分钟线可用性约束强交易结论
- `futures`：辅助判断盘前成长风格强弱
- `breadth`：辅助判断 Nasdaq-100 内部结构强弱
- `event_calendar`：处理事件日历与事件风险快照
- `backtest`：执行历史回测并输出摘要结果
- `trade_journal`：记录人工交易与复盘统计

## 运行方式

### 配置环境变量

可参考 `.env.example` 创建 `.env`：

```env
DATA_PROVIDER=yfinance
DATABASE_PATH=data/market_data.db
FINNHUB_API_KEY=
TIINGO_API_KEY=
POLYGON_API_KEY=
ALPHA_VANTAGE_API_KEY=
```

说明：

- 正式运行应优先使用真实行情源
- `mock` 仅用于开发测试，不可用于真实交易判断
- `DATABASE_PATH` 默认值为 `data/market_data.db`，可通过环境变量覆盖

### 运行命令行信号流程

```bash
python main.py
```

### 运行历史回测

```bash
python main.py --backtest
```

### 运行可视化面板

```bash
streamlit run app.py
```

## 风险说明

本系统仅用于个人量化研究和交易辅助，不构成任何投资建议。TQQQ/SQQQ 为三倍杠杆 ETF，波动较大，不适合长期持有，请严格控制仓位和风险。

回测结果仅用于策略研究，不代表未来表现。历史收益不构成投资建议，也不代表系统具备稳定盈利能力。
