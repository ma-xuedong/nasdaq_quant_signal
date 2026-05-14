# nasdaq_quant_signal

TQQQ / SQQQ 纳指量化信号辅助系统。

## 项目状态

当前项目已完成第三期功能开发，现处于 coding review / P1 收口阶段。

本项目用于个人量化研究与交易辅助，核心目标是辅助判断当前市场环境更适合观察 TQQQ、SQQQ，还是保持空仓。它不是自动交易系统，也不构成任何投资建议。

## 当前模块

- 数据源与 provider 抽象：统一处理真实行情源与测试源
- 缓存与回退机制：区分 `api`、`cache`、`fallback_cache`、`mock`、`missing`
- 统一信号流程：命令行与页面统一复用 `run_signal_pipeline()` 输出
- 数据质量控制：基于 freshness、fallback、mock、分钟线可用性约束强交易结论
- 期货确认模块：辅助判断盘前成长风格强弱
- 市场宽度模块：辅助判断 Nasdaq-100 内部结构强弱
- 事件风险模块：统一处理事件日历与风险扣分
- 回测模块：支持 `python main.py --backtest` 输出历史回测摘要
- 交易日志模块：记录人工交易与复盘统计
- SQLite 持久化：保存评分、回测、交易日志与缓存元数据

## 评分系统

当前评分与约束结构基于第三期后的多模块体系，主要包括：

- `trend`
- `futures`
- `breadth`
- `volatility`
- `mega cap tech`
- `intraday/reversal`
- `event risk`
- `data quality`

其中，评分结果不是单一基础分数的直接映射，还会叠加事件风险扣分与数据质量约束。`mock`、`fallback_cache`、实时性不足或数据质量较低时，系统会主动抑制强交易结论。

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

默认执行统一信号流程并输出当前评分、数据质量和摘要信息。

### 运行历史回测

```bash
python main.py --backtest
```

该命令执行 `run_backtest()` 并输出回测摘要。回测结果仅用于策略研究与行为比较，不代表未来表现。

### 运行可视化面板

```bash
streamlit run app.py
```

## 风险说明

本系统仅用于个人量化研究和交易辅助，不构成任何投资建议。TQQQ/SQQQ 为三倍杠杆 ETF，波动较大，不适合长期持有，请严格控制仓位和风险。

回测结果仅用于策略研究，不代表未来表现。历史收益不构成投资建议，也不代表系统具备稳定盈利能力。
