# nasdaq_quant_signal

TQQQ / SQQQ 纳指量化信号辅助系统。

本项目用于辅助判断当前纳指 100 市场环境更适合观察 TQQQ、SQQQ，还是保持空仓。

本系统不是自动交易系统，不接入券商下单接口，不构成任何投资建议。

---

## 当前状态

当前项目已完成第三期功能开发，进入 coding review / P1 收口阶段。

已完成主线：

- 第一期 MVP：完成；
- 第二期工程化改造：完成；
- 第三期功能开发：完成；
- 当前阶段：文档、配置、数据库测试与代码结构审查收口。

已接入模块：

- 数据源抽象层：`src/data_provider/`
- 本地缓存与 fallback：`src/cache.py`
- 请求限流与重试：`src/rate_limiter.py`
- 统一信号流程：`src/pipeline.py`
- 数据质量评估：`src/data_quality.py`
- 指数期货确认：`src/futures.py`
- Nasdaq-100 市场宽度：`src/breadth.py`
- 事件风险日历：`src/event_calendar.py`
- 回测分析：`src/backtest.py`
- 交易日志与人工复盘：`src/trade_journal.py`
- Streamlit 本地可视化面板：`app.py`

---

## 核心原则

本项目正式运行时必须优先使用真实或准实时行情数据。

Mock 数据只允许用于开发测试，不能用于真实交易判断。

fallback_cache 只允许作为降级展示，不应作为强交易信号依据。

如果核心数据 QQQ 缺失，系统应停止评分。

如果 QQQ 仅来自 fallback_cache，系统只能输出观察或数据滞后提示，不能输出强多或强空结论。

---

## 系统架构

系统主流程由 `src/pipeline.py` 统一调度。

```text
真实/准实时行情源
        ↓
data_provider / cache / rate_limiter
        ↓
pipeline.py
        ↓
indicators / futures / breadth / event_calendar
        ↓
scoring / risk_filter / data_quality
        ↓
database.py
        ↓
app.py / main.py
```

`main.py` 和 `app.py` 都应通过 `run_signal_pipeline()` 获取统一结果，不应绕过 pipeline 直接抓数据或直接评分。

---

## 数据来源状态

系统会为核心数据标记来源：

| 来源 | 含义 |
|---|---|
| `api` | 本次成功从真实数据源获取 |
| `cache` | 使用未过期缓存 |
| `fallback_cache` | API 失败后回退到旧缓存 |
| `missing` | 当前无可用数据 |
| `mock` | 测试数据，仅用于开发测试 |

数据质量由 `src/data_quality.py` 评估，主要输出：

- `quality_score`
- `quality_level`
- `confidence`
- `missing_symbols`
- `cache_fallback_count`
- `is_realtime_usable`
- `is_test_mode`

如果数据质量不足，系统不应输出强交易信号。

---

## 数据源配置

配置通过 `.env` 控制。

复制示例文件：

```bash
copy .env.example .env
```

macOS / Linux：

```bash
cp .env.example .env
```

`.env` 示例：

```env
DATA_PROVIDER=yfinance
DATABASE_PATH=data/market_data.db
FINNHUB_API_KEY=
TIINGO_API_KEY=
POLYGON_API_KEY=
ALPHA_VANTAGE_API_KEY=
```

当前默认正式数据源：

```text
yfinance
```

测试数据源：

```text
mock
```

未来可扩展数据源：

```text
finnhub
tiingo
polygon
ibkr
```

注意：

```text
DATA_PROVIDER=mock 仅用于开发测试。
mock 数据不能用于真实交易判断。
```

---

## 项目结构

```text
nasdaq_quant_signal/
├── app.py
├── main.py
├── config/
│   ├── settings.py
│   └── __init__.py
├── src/
│   ├── data_provider/
│   ├── data_fetcher.py
│   ├── cache.py
│   ├── rate_limiter.py
│   ├── pipeline.py
│   ├── data_quality.py
│   ├── indicators.py
│   ├── futures.py
│   ├── breadth.py
│   ├── event_calendar.py
│   ├── scoring.py
│   ├── risk_filter.py
│   ├── market_state.py
│   ├── database.py
│   ├── backtest.py
│   ├── trade_journal.py
│   ├── utils.py
│   └── __init__.py
├── data/
│   └── market_data.db
├── test_*.py
├── requirements.txt
├── .env.example
└── README.md
```

---

## 核心模块说明

### `src/pipeline.py`

统一信号流程入口。

负责：

- 获取行情数据；
- 使用缓存与 fallback；
- 构建技术指标；
- 构建期货快照；
- 构建市场宽度快照；
- 构建事件风险快照；
- 计算 TQQQ / SQQQ 评分；
- 计算风险扣分；
- 评估数据质量；
- 生成市场状态与中文解释；
- 保存数据库；
- 返回统一结果结构。

---

### `src/data_provider/`

数据源抽象层。

用于隔离不同数据源接口，避免业务代码直接依赖 yfinance。

当前默认实现：

```text
yfinance_provider.py
```

后续可扩展：

```text
finnhub_provider.py
tiingo_provider.py
polygon_provider.py
ibkr_provider.py
```

---

### `src/cache.py`

本地缓存与 fallback 逻辑。

日线数据读取顺序：

```text
fresh cache
→ API request
→ fallback_cache
→ missing
```

缓存是否新鲜必须基于 `cache_metadata.expires_at`。

不能仅因为数据库里有旧数据就将其视为 fresh cache。

---

### `src/rate_limiter.py`

请求限流与失败重试模块。

用于降低免费 API 的限流风险。

功能包括：

- 请求间隔；
- 指数退避；
- 失败重试；
- 防止单个 symbol 失败导致主流程崩溃。

---

### `src/data_quality.py`

数据质量与信号可信度评估模块。

用于判断当前数据是否足以支持实时/准实时交易辅助判断。

如果数据质量过低，系统应降低信号置信度或停止输出强交易结论。

---

### `src/futures.py`

指数期货确认模块。

主要用于分析：

- NQ 涨跌幅；
- ES 涨跌幅；
- NQ 相对 ES 强弱；
- NQ 趋势；
- NQ 缺口相对 QQQ ATR 的强度。

---

### `src/breadth.py`

Nasdaq-100 市场宽度模块。

主要用于分析：

- 上涨家数；
- 下跌家数；
- 上涨比例；
- 下跌比例；
- 站上 MA20 / MA50 / MA200 的比例；
- 市场宽度状态：strong / weak / mixed / insufficient。

---

### `src/event_calendar.py`

事件风险日历模块。

支持本地配置事件风险，包括：

- CPI；
- PPI；
- PCE；
- FOMC；
- 非农；
- 初请失业金；
- 期权到期日；
- 四巫日；
- 权重股财报。

事件风险会影响风险扣分和信号置信度，但不会单独生成交易方向。

---

### `src/scoring.py`

TQQQ / SQQQ 评分模块。

第三期后的评分结构包括：

- 趋势模块；
- 期货确认模块；
- 市场宽度模块；
- 波动环境模块；
- 权重科技股模块；
- 日内结构 / 反弹失败模块；
- 事件风险约束；
- 数据质量约束。

当前评分模型属于启发式规则评分，不是已经严格统计验证的量化因子模型。

---

### `src/backtest.py`

历史回测模块。

支持：

- 收盘信号，次日开盘执行；
- 收盘信号，次日收盘执行；
- TQQQ / SQQQ 交易表现区分；
- 不同评分区间表现分析；
- 不同数据质量等级表现分析；
- 胜率、盈亏比、最大回撤等指标。

回测结果仅用于策略研究，不代表未来收益。

---

### `src/trade_journal.py`

交易日志与人工复盘模块。

用于记录：

- 系统信号；
- 用户实际交易；
- 是否遵守系统；
- 交易收益；
- 错误类型；
- 备注。

本模块只用于人工复盘，不会自动下单。

---

### `src/database.py`

SQLite 数据持久化模块。

主要保存：

- 日线行情；
- 分钟线行情；
- 缓存元数据；
- 评分结果；
- 回测记录；
- 交易日志。

当前数据库是本地 SQLite 文件：

```text
data/market_data.db
```

它不是云数据库，也不是虚拟数据库。

---

## 前端界面

本项目的前端界面是 Streamlit 本地 Web 面板。

入口文件：

```text
app.py
```

运行后在浏览器中打开：

```text
http://localhost:8501
```

页面包括：

- 首页；
- 期货确认；
- 市场宽度；
- 事件风险；
- 回测分析；
- 交易日志；
- 系统状态。

---

## 运行方式

### 安装依赖

Windows：

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

如果 Windows 下 `python` 命令不可用，可以使用：

```bash
py -m venv .venv
.venv\Scripts\activate
py -m pip install -r requirements.txt
```

macOS / Linux：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

### 命令行运行

```bash
python main.py
```

或：

```bash
py main.py
```

---

### 回测运行

```bash
python main.py --backtest
```

或：

```bash
py main.py --backtest
```

---

### Streamlit 面板

```bash
streamlit run app.py
```

或：

```bash
py -m streamlit run app.py
```

---

## 测试命令

```bash
python test_indicators.py
python test_scoring.py
python test_database.py
python test_cache.py
python test_pipeline.py
python test_data_quality.py
python test_rate_limiter.py
python test_futures.py
python test_breadth.py
python test_event_calendar.py
python test_backtest.py
python test_trade_journal.py
```

Windows 如 `python` 不可用，可使用：

```bash
py test_indicators.py
py test_scoring.py
py test_database.py
py test_cache.py
py test_pipeline.py
py test_data_quality.py
py test_rate_limiter.py
py test_futures.py
py test_breadth.py
py test_event_calendar.py
py test_backtest.py
py test_trade_journal.py
```

---

## yfinance 说明

当前默认数据源为 yfinance。

yfinance 适合原型开发和个人研究，但可能遇到：

- Too Many Requests；
- 代理问题；
- SSL 连接失败；
- 数据延迟；
- 某些 symbol 暂时不可用。

因此系统加入了：

- 缓存；
- fallback_cache；
- 数据质量判断；
- 限流与重试；
- 数据来源提示。

正式交易决策不应只依赖单一免费数据源。

---

## 回测说明

回测结果仅用于策略研究。

回测结果不代表未来收益，不构成投资建议。

任何历史表现都需要结合：

- 样本外验证；
- 手续费与滑点；
- 数据质量；
- 最大回撤；
- 连续亏损；
- 策略容量；
- 实盘执行偏差。

---

## 风险提示

本系统仅用于个人量化研究和交易辅助，不构成任何投资建议。

TQQQ / SQQQ 为三倍杠杆 ETF，波动较大，不适合长期持有。

历史回测结果不代表未来收益。

任何交易决策和风险后果均由使用者自行承担。

---

## 后续开发方向

下一阶段不建议继续堆新功能，建议优先进行代码结构整理：

- 拆分 `app.py` 为页面模块；
- 拆分 `database.py` 为 repository 层；
- 拆分 `pipeline.py` 内部步骤；
- 抽象 `scoring.py` 中重复评分模式；
- 强化数据库持久化测试；
- 清理 README、settings 和 `.env.example` 的一致性；
- 后续再考虑更稳定的真实 NQ / ES 数据源和财经日历 API。