# nasdaq_quant_signal

TQQQ / SQQQ 纳指量化信号辅助系统。

## 项目用途

本项目用于辅助判断当前纳指 100 市场环境更适合观察 TQQQ（三倍看多）、SQQQ（三倍看空），还是保持空仓。
它是一个个人量化研究与交易辅助面板，不是自动交易系统，也不构成投资建议。

## 项目特性

✓ **完整的数据处理管道**：从数据抓取、指标计算到评分生成
✓ **多模块评分系统**：覆盖趋势、期货确认、市场宽度、波动环境、权重科技股、日内结构 / 反弹失败、事件风险与数据质量约束
✓ **风险管理模块**：实时风险事件检测和动态扣分
✓ **完整的回测系统**：基于历史数据的策略验证和效果评估
✓ **可视化面板**：Streamlit 本地 Web 界面，实时展示市场状态和历史分析
✓ **持久化存储**：SQLite 数据库保存历史评分、市场数据和回测结果
✓ **完善的错误处理**：网络故障、数据缺失等场景的优雅降级
✓ **数据来源与实时性控制**：标记 api/cache/fallback_cache/mock/missing，并控制强信号输出

## 当前阶段

本项目当前已完成第三期功能开发，进入 coding review / P1 收口修复阶段。

- 第一期 MVP：已完成
- 第二期工程化改造：已完成
- 第三期功能：已完成
- 当前收口重点：
  - 文档 / 配置一致性修正
  - 数据库持久化与兼容性验证
  - 第三期模块回归测试
- 已接入模块：
  - 数据源抽象层
  - 本地缓存
  - 请求限流与重试
  - 统一信号流程
  - 数据质量评估
  - 期货确认
  - 市场宽度
  - 事件风险日历
  - 回测分析
  - 交易日志

## 快速开始

### 1. 安装依赖

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 2. 配置数据源

可直接参考 `.env.example` 创建 `.env`。例如：

```env
DATA_PROVIDER=yfinance
DATABASE_PATH=data/market_data.db
```

可切换值包括：`yfinance`、`mock`、`finnhub`、`tiingo`、`polygon`。

说明：
- 正式运行应优先使用真实行情源
- `mock` 仅用于开发测试，不可用于真实交易判断
- `DATABASE_PATH` 可通过环境变量覆盖，默认值为 `data/market_data.db`

### 3. 运行命令行版本

```bash
python main.py
```

默认执行统一信号流程 `run_signal_pipeline()`。

### 4. 运行 Streamlit 可视化面板

```bash
streamlit run app.py
```

然后在浏览器打开：**http://localhost:8501**

### 5. 执行历史回测

```bash
python main.py --backtest
```

该命令执行 `run_backtest()` 并输出回测摘要。回测结果仅用于策略研究，不代表未来表现。

## 项目结构

- `config/`：配置项与运行参数
- `src/data_provider/`：数据源抽象层与 provider 实现
- `src/cache.py`：缓存、fallback 与元信息标记
- `src/pipeline.py`：统一信号流程入口
- `src/data_quality.py`：数据质量与实时性判断
- `app.py`：Streamlit 页面入口
- `main.py`：命令行入口

### 1. 数据抓取（src/data_fetcher.py）

通过 provider 工厂调用数据源并保持兼容接口：
- `fetch_daily_data()` - 日线 OHLCV 数据
- `fetch_intraday_data()` - 分钟线数据
- `fetch_multiple_daily_data()` - 批量日线数据
- `fetch_multiple_intraday_data()` - 批量分钟线数据
- `fetch_latest_price()` - 最新价格
- `fetch_market_snapshot()` - 市场快照

### 1.1 数据源抽象（src/data_provider/）

用于隔离 yfinance、Finnhub、Tiingo、IBKR 等不同数据源差异：
- `base_provider.py`：统一抽象接口
- `yfinance_provider.py`：当前默认实现
- `provider_factory.py`：根据配置选择 provider

### 1.2 缓存与容错（src/cache.py）

缓存模块负责：
- 先通过 `cache_metadata.expires_at` 判断 freshness
- fresh cache 才直接返回
- cache 过期后请求 API
- API 失败时回退 fallback_cache
- 使用 `cache_metadata` 维护缓存状态
- 每个 symbol 返回 `source`、`last_updated`、`data_timestamp`、`is_fresh`
- `fallback_cache` 仅用于降级展示，不应作为强交易信号依据

### 1.3 限流与重试（src/rate_limiter.py）

用于降低免费 API 限流风险：
- 请求间隔控制
- 指数退避重试

### 1.4 统一流程（src/pipeline.py）

主流程统一由 pipeline 管理，供命令行与页面复用：
- 获取数据（API + cache + fallback）
- 构建指标
- 评分与风险扣分
- 数据质量评估
- 保存数据库并输出统一结构

### 1.5 数据质量评估（src/data_quality.py）

输出数据可信度信息：
- `quality_score`
- `quality_level`
- `confidence`
- `missing_symbols`
- `cache_fallback_count`
- `is_realtime_usable`
- `is_test_mode`

## 数据质量与实时性判断

正式运行以真实/准实时行情为核心，当前默认 provider 为 `yfinance`。系统会对每个 symbol 标记以下来源之一：

- `api`：本次成功从真实数据源获取
- `cache`：命中未过期缓存
- `fallback_cache`：API 失败后退回最近缓存，仅可观察
- `missing`：当前无可用数据
- `mock`：测试数据，仅用于开发测试

关键约束：

- `QQQ` 缺失时，统一信号流程返回 `success=False`
- `QQQ` 仅有 `fallback_cache` 时，可继续展示，但只能输出“观察/数据可能滞后”
- `QQQ` 不满足实时/准实时条件时，不允许输出强多/强空结论
- `quality_score < 50` 时，结论固定为“数据质量不足，不建议交易”
- `50 <= quality_score < 70` 时，仅作弱参考，不建议重仓
- `DATA_PROVIDER=mock` 时，系统进入测试模式，摘要会明确提示“不可用于真实交易判断”

说明：

- `yfinance` 适合原型与研究，但可能遇到限流、代理、网络失败等问题
- 后续可在 `src/data_provider/` 下扩展 Finnhub、Tiingo、Polygon、IBKR provider
- Mock provider 只用于开发测试，不参与正式交易判断

### 2. 技术指标（src/indicators.py）

计算 50+ 个技术指标：
- 移动平均线（MA5/20/50/200）和斜率
- ATR（平均真实波幅）
- 成交量比例
- 相对强弱度
- VWAP（成交量加权平均价）
- 开盘30分钟结构分析
- 权重科技股强弱分析

### 3. 评分系统（src/scoring.py）

第三期后的评分与约束结构包括：
- **趋势模块**：QQQ 相对均线位置、均线斜率、破位 / 走强结构
- **期货确认模块**：NQ / ES 强弱、趋势与缺口强度
- **市场宽度模块**：QQQE、Nasdaq-100 内部上涨比例、站上均线比例
- **波动环境模块**：VIX / VXN 缺失时降级，中性打分并给出 warning
- **权重科技股模块**：Mega Cap Tech 集体强弱
- **日内结构模块**：VWAP、开盘 30 分钟结构、反弹失败形态
- **事件风险模块**：通过 event risk snapshot 与 risk deduction 统一扣分
- **数据质量约束**：mock / fallback_cache / freshness / realtime usability 会限制强交易结论

说明：
- TQQQ 与 SQQQ 不是完全镜像的单一规则，而是分别按做多 / 做空场景组合多个评分模块
- 最终交易结论还会经过事件风险扣分与数据质量约束，不等于单纯基础分数高低

### 4. 风险管理（src/risk_filter.py）

风险评估和动态扣分：
- 检测预定义的风险事件（FOMC、CPI等）
- 根据 VIX/VXN 水平计算波动率扣分
- 返回 0-30 分的风险扣分

### 5. 数据库（src/database.py）

SQLite 数据持久化：
- `price_daily` - 日线行情
- `price_intraday` - 分钟线行情  
- `indicator_daily` - 日线指标
- `market_score` - 评分结果
- `signal_log` - 信号日志
- `backtest_scores` - 回测历史评分
- `backtest_signals` - 回测交易信号
- `backtest_trades` - 回测交易明细
- `backtest_metrics` - 回测统计指标

当前提供数据库初始化、主要写入接口以及历史查询接口，用于支撑信号、回测与交易日志模块。

### 6. 回测系统（src/backtest.py）

完整的历史回测实现：
- `generate_score_history()` - 逐日生成历史评分（避免未来函数）
- `generate_trade_signals()` - 根据评分生成交易信号
- `simulate_trades()` - 模拟交易执行（支持 close_to_next_open / close_to_next_close）
- `calculate_backtest_metrics()` - 计算胜率、盈亏比等指标
- `run_backtest()` - 完整的回测流程

**关键特性**：
- ✓ 无未来函数：每日信号仅使用当日及之前的数据
- ✓ 执行时点清晰：收盘信号只能在下一交易日开盘或收盘执行
- ✓ 保守估计：考虑 0.1% 的往返交易成本
- ✓ 完整的交易模拟：支持止盈、止损、时间到期三种退出方式
- ✓ 详细的统计指标：胜率、平均盈利/亏损、最大回撤等
- ✓ 数据持久化：回测结果保存到数据库

注意：回测结果仅用于研究和比较策略行为，不代表未来收益，也不构成稳定盈利承诺。

## 交易规则详解

### TQQQ 规则（做多）

**信号生成条件**：
- TQQQ 最终评分 ≥ 75 分
- SQQQ 最终评分 < 65 分

**执行方式**：
- 次日开盘买入 TQQQ
- 持有最多 3 个交易日
- 止盈：+6%
- 止损：-3%

### SQQQ 规则（做空）

**信号生成条件**：
- SQQQ 最终评分 ≥ 85 分
- TQQQ 最终评分 < 65 分

**执行方式**：
- 次日开盘买入 SQQQ
- 持有最多 2 个交易日
- 止盈：+5%
- 止损：-3%

## 评分示例

### 场景 1：强多信号
```
TQQQ 基础评分：85 分
- 趋势模块：15 分（MA20 > MA50 > MA200，正斜率）
- 动量模块：18 分（日涨幅 > 0，成交量充足）
- 广度模块：14 分（相对强弱良好）
- 波动性模块：15 分（ATR 上升）
- 结构模块：23 分（VWAP 支撑，权重股联动）

风险扣分：0 分（无风险事件，VIX 正常）
最终评分：85 分 → 强多环境
```

### 场景 2：空仓信号
```
TQQQ 基础评分：35 分
SQQQ 基础评分：40 分
风险扣分：8 分（CPI 数据发布日期）

TQQQ 最终评分：27 分
SQQQ 最终评分：32 分
综合判断：空仓等待
```

## 回测指标解释

### 胜率（Win Rate）
- 定义：盈利交易数 / 总交易数
- 意义：策略的成功率，但不是唯一评估标准
- 注意：高胜率+小止损可能导致亏损

### 盈亏比（Profit Factor）
- 定义：总盈利 / 总亏损的绝对值
- 目标：≥ 1.0 为盈利，≥ 1.5 为良好
- 意义：衡量平均盈利和亏损的比例关系

### 最大回撤（Max Drawdown）
- 定义：从最高点到最低点的百分比下降
- 意义：衡量策略的承受风险能力
- 目标：< -20% 为可接受

### 累计收益率（Cumulative Return）
- 定义：所有交易收益的总和
- 说明：不同时间周期结果差异大
- 使用：参考而非预测

## 数据源与质量

- **数据源**：Yahoo Finance（yfinance 库）
- **覆盖范围**：
  - 核心指数：QQQ、SPY
  - 相对强弱：QQQE（纳指等权）
  - 权重股：NVDA, MSFT, AAPL, AMZN, META, GOOGL, AVGO, TSLA
  - 波动率：VIX（S&P500）、VXN（纳指）
  - 期货：NQ、ES（若可用）
- **网络故障处理**：优雅降级，保留缓存数据
- **缺失数据处理**：使用默认/替代值，显示警告

## 系统要求

- Python 3.9+
- 1 GB 磁盘空间（包括历史数据）
- 互联网连接（数据抓取）
- 浏览器（Streamlit 面板）

## 测试与运行命令

```bash
python main.py
python main.py --backtest
streamlit run app.py
python test_indicators.py
python test_scoring.py
python test_database.py
python test_cache.py
python test_pipeline.py
python test_data_quality.py
python test_rate_limiter.py
```

## 依赖包

详见 `requirements.txt`，主要包括：
- pandas: 数据处理
- numpy: 数值计算
- yfinance: 数据获取
- streamlit: Web 面板
- plotly: 交互式图表
- python-dotenv: 环境配置

## 性能指标

- 单次数据刷新：~10-30 秒（取决于网络）
- 指标计算：~100ms
- 评分计算：~50ms
- 数据库写入：~10ms
- 历史数据读取：~20ms
- 图表渲染：~500ms
- 完整回测：5-30 分钟（取决于历史数据量）

## 扩展功能建议（后续开发）

- [ ] 添加更多权重股的分析
- [ ] 支持自定义评分权重
- [ ] 支持多时间框架分析
- [ ] 添加告警通知（邮件/短信）
- [ ] 接入真实期货数据（NQ、ES）
- [ ] 支持 Nasdaq-100 市场宽度分析
- [ ] 集成财经日历 API
- [ ] 支持国内 A 股行情对比
- [ ] 后端 FastAPI + PostgreSQL 服务化
- [ ] Docker 容器化部署

## 注意事项

⚠️ **重要提示**：
- 本系统仅作参考，不构成投资建议
- TQQQ/SQQQ 为 3 倍杠杆 ETF，日内波动剧烈
- 不适合作为长期持仓工具
- 请严格控制仓位和风险，设置好止损
- 历史回测表现不代表未来结果
- 回测结果仅用于策略研究，需要样本外验证
- 回测结果仅用于策略研究，不代表未来收益，不构成投资建议

## 免责声明

本系统仅用于个人量化研究和交易辅助，不构成任何投资建议。TQQQ/SQQQ 为三倍杠杆ETF，波动较大，不适合长期持有，请严格控制仓位和风险。使用者需自行承担所有交易风险。

## 许可证

个人研究项目，仅供学习参考。

---

## 更新日志

- **2026-05-13**: 阶段七完成 - 回测模块与后续扩展规划
  - 实现完整的历史回测系统
  - 添加 Streamlit 回测分析页面
  - 支持命令行回测报告
  - 添加数据库回测结果存储

- **2026-05-13**: 阶段六完成 - Streamlit 可视化面板
  - 实现 12 个可视化组件
  - 添加数据刷新功能
  - 支持历史评分查看

- **2026-05-13**: 阶段五完成 - SQLite 数据库
  - 实现 5 个数据表
  - 支持历史数据持久化

- **2026-05-13**: 阶段四完成 - 评分与风险管理
  - 实现 TQQQ/SQQQ 评分系统
  - 添加风险扣分机制

- **2026-05-13**: 阶段三完成 - 技术指标计算
  - 实现 10 个主要指标
  - 支持 50+ 个衍生指标

- **2026-05-13**: 阶段二完成 - 数据抓取模块
  - 集成 yfinance 数据源
  - 实现 6 个抓取函数

- **2026-05-13**: 阶段一完成 - 项目结构搭建
  - 初始化项目结构
  - 配置基础依赖


## 快速开始

### 1. 安装依赖

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 2. 运行命令行版本（完整演示）

```bash
python main.py
```

输出示例：
```
====== TQQQ / SQQQ Signal Report ======

【数据抓取阶段】
✓ QQQ 日线数据已获取
✓ SPY 日线数据已获取
...

【评分计算阶段】
✓ TQQQ 基础评分：75 分
✓ SQQQ 基础评分：30 分

【最终评分阶段】
TQQQ 最终评分：68 分
SQQQ 最终评分：20 分

【市场总结与建议】
综合判断：空仓等待
...
```

### 3. 运行 Streamlit 可视化面板

```bash
streamlit run app.py
```

然后在浏览器打开：**http://localhost:8501**

面板功能：
- 实时刷新数据并重新评分
- 显示 TQQQ/SQQQ 最终评分和市场状态
- 查看 QQQ 趋势指标（MA、ATR、成交量等）
- 科技权重股涨跌统计
- QQQ vs SPY、QQQE vs QQQ 相对强弱分析
- VIX/VXN 波动率指标
- 点击查看详细评分原因和中文解释
- QQQ 价格走势图（含MA20/MA50/MA200）
- 历史评分变化曲线（最近100条记录）

## 项目结构

```
nasdaq_quant_signal/
├── app.py                    # Streamlit 可视化面板（800+ 行）
├── main.py                   # 命令行完整演示脚本
├── config/
│   ├── settings.py          # 全局配置（标的代码、参数等）
│   └── __init__.py
├── src/
│   ├── data_fetcher.py       # 数据抓取（yfinance）
│   ├── indicators.py         # 技术指标计算（10 个指标）
│   ├── scoring.py            # 评分系统（5 个模块）
│   ├── risk_filter.py        # 风险管理和扣分
│   ├── market_state.py       # 市场状态分类和总结
│   ├── database.py           # SQLite 数据库操作
│   ├── utils.py              # 工具函数（日志等）
│   └── __init__.py
├── data/
│   ├── market_data.db        # SQLite 数据库文件
│   └── .gitkeep
├── test_*.py                 # 各阶段的单元测试脚本
├── PHASE*_ACCEPTANCE.md      # 各阶段验收报告
└── requirements.txt          # Python 依赖列表
```

## 核心模块说明

### 1. 数据抓取（src/data_fetcher.py）

从 Yahoo Finance 获取市场数据：
- `fetch_daily_data()` - 日线 OHLCV 数据
- `fetch_intraday_data()` - 分钟线数据
- `fetch_multiple_daily_data()` - 批量日线数据
- `fetch_multiple_intraday_data()` - 批量分钟线数据
- `fetch_latest_price()` - 最新价格
- `fetch_market_snapshot()` - 市场快照

### 2. 技术指标（src/indicators.py）

计算 50+ 个技术指标：
- 移动平均线（MA5/20/50/200）和斜率
- ATR（平均真实波幅）
- 成交量比例
- 相对强弱度
- VWAP（成交量加权平均价）
- 开盘30分钟结构分析
- 权重科技股强弱分析

### 3. 评分系统（src/scoring.py）

5 个模块共 100 分的评分体系：
- **趋势模块**（15分）：MA 位置、斜率、黄金交叉
- **动量模块**（20分）：日涨跌幅、成交量特征
- **广度模块**（15分）：相对强弱（QQQE vs QQQ、QQQ vs SPY）
- **波动性模块**（15分）：ATR 趋势强度
- **结构模块**（35分）：VWAP、开盘模式、日内动态

### 4. 风险管理（src/risk_filter.py）

风险评估和动态扣分：
- 检测预定义的风险事件（FOMC、CPI等）
- 根据 VIX/VXN 水平计算波动率扣分
- 返回 0-30 分的风险扣分

### 5. 数据库（src/database.py）

SQLite 数据持久化：
- `price_daily` - 日线行情
- `price_intraday` - 分钟线行情  
- `indicator_daily` - 日线指标
- `market_score` - 评分结果
- `signal_log` - 信号日志

支持完整的 CRUD 操作和历史数据查询。

## 评分示例

### 场景 1：强多信号
```
TQQQ 基础评分：85 分
- 趋势模块：15 分（MA20 > MA50 > MA200，正斜率）
- 动量模块：18 分（日涨幅 > 0，成交量充足）
- 广度模块：14 分（相对强弱良好）
- 波动性模块：15 分（ATR 上升）
- 结构模块：23 分（VWAP 支撑，权重股联动）

风险扣分：0 分（无风险事件，VIX 正常）
最终评分：85 分 → 强多环境
```

### 场景 2：空仓信号
```
TQQQ 基础评分：35 分
SQQQ 基础评分：40 分
风险扣分：8 分（CPI 数据发布日期）

TQQQ 最终评分：27 分
SQQQ 最终评分：32 分
综合判断：空仓等待
```

## 数据源与质量

- **数据源**：Yahoo Finance（yfinance 库）
- **覆盖范围**：
  - 核心指数：QQQ、SPY
  - 相对强弱：QQQE（纳指等权）
  - 权重股：NVDA, MSFT, AAPL, AMZN, META, GOOGL, AVGO, TSLA
  - 波动率：VIX（S&P500）、VXN（纳指）
  - 期货：NQ、ES（若可用）
- **网络故障处理**：优雅降级，保留缓存数据
- **缺失数据处理**：使用默认/替代值，显示警告

## 系统要求

- Python 3.9+
- 1 GB 磁盘空间（包括历史数据）
- 互联网连接（数据抓取）
- 浏览器（Streamlit 面板）

## 依赖包

详见 `requirements.txt`，主要包括：
- pandas: 数据处理
- numpy: 数值计算
- yfinance: 数据获取
- streamlit: Web 面板
- plotly: 交互式图表
- python-dotenv: 环境配置

## 性能指标

- 单次数据刷新：~10-30 秒（取决于网络）
- 指标计算：~100ms
- 评分计算：~50ms
- 数据库写入：~10ms
- 历史数据读取：~20ms
- 图表渲染：~500ms

## 扩展功能建议

- [ ] 添加更多权重股的分析
- [ ] 支持自定义评分权重
- [ ] 添加回测功能
- [ ] 支持多时间框架分析
- [ ] 添加告警通知（邮件/短信）
- [ ] 支持期货数据真实集成
- [ ] 添加技术面三买三卖点
- [ ] 支持国内 A 股行情对比

## 注意事项

⚠️ **重要提示**：
- 本系统仅作参考，不构成投资建议
- TQQQ/SQQQ 为 3 倍杠杆 ETF，日内波动剧烈
- 不适合作为长期持仓工具
- 请严格控制仓位和风险，设置好止损
- 历史表现不代表未来结果

## 免责声明

本系统仅用于个人量化研究和交易辅助，不构成任何投资建议。TQQQ/SQQQ 为三倍杠杆ETF，波动较大，不适合长期持有，请严格控制仓位和风险。使用者需自行承担所有交易风险。

## 许可证

个人研究项目，仅供学习参考。
