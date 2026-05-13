"""Streamlit web dashboard for TQQQ/SQQQ trading signals."""

from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config.settings import (
    RISK_DISCLOSURE,
    MEGA_CAP_TECH_SYMBOLS,
)
from src.data_fetcher import (
    fetch_daily_data,
    fetch_intraday_data,
)
from src.pipeline import run_signal_pipeline
from src.indicators import (
    build_indicator_snapshot,
    calculate_moving_averages,
    calculate_ma_slope,
    calculate_atr,
    calculate_volume_ratio,
    calculate_daily_return,
)
from src.scoring import calculate_tqqq_score, calculate_sqqq_score, calculate_final_score
from src.risk_filter import get_risk_deduction
from src.market_state import (
    generate_market_summary,
    classify_overall_market_state,
)
from src.database import (
    init_database,
    save_market_score,
    load_recent_market_scores,
    load_daily_prices,
)
from src.utils import setup_logger

logger = setup_logger("streamlit_app")


# 页面配置
st.set_page_config(
    page_title="TQQQ / SQQQ 纳指量化信号面板",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# 自定义样式
st.markdown("""
    <style>
        .metric-box {
            padding: 20px;
            border-radius: 10px;
            background-color: #f0f2f6;
            margin-bottom: 10px;
        }
        .success-box {
            padding: 15px;
            border-radius: 8px;
            background-color: #d4edda;
            border-left: 4px solid #28a745;
            margin-bottom: 10px;
        }
        .warning-box {
            padding: 15px;
            border-radius: 8px;
            background-color: #fff3cd;
            border-left: 4px solid #ffc107;
            margin-bottom: 10px;
        }
        .error-box {
            padding: 15px;
            border-radius: 8px;
            background-color: #f8d7da;
            border-left: 4px solid #dc3545;
            margin-bottom: 10px;
        }
    </style>
    """, unsafe_allow_html=True)


@st.cache_resource
def init_db():
    """初始化数据库（仅运行一次）。"""
    try:
        init_database()
    except Exception as e:
        logger.error(f"数据库初始化失败：{e}")


@st.cache_data(ttl=3600)
def load_historical_data():
    """从数据库加载最近的评分记录。"""
    try:
        return load_recent_market_scores(limit=100)
    except Exception as e:
        logger.error(f"加载历史数据失败：{e}")
        return pd.DataFrame()


def fetch_and_calculate():
    """
    获取数据、计算指标、评分并保存到数据库。
    
    返回：
        包含所有计算结果的字典，或 None（失败时）
    """
    try:
        with st.spinner("正在执行统一信号流程（含缓存与容错）..."):
            result = run_signal_pipeline(save_to_db=True, use_cache=True)

        if not result.get("success", False):
            st.error(f"❌ 处理失败：{result.get('message', '未知错误')}")
            for warning in result.get("warnings", []):
                st.warning(warning)
            return None

        return result

    except Exception as e:
        logger.error(f"数据获取和计算失败：{e}")
        st.error(f"❌ 处理失败：{str(e)}")
        return None


def display_data_status(result: dict) -> None:
    """显示数据来源状态与数据质量。"""
    st.subheader("🧭 数据状态与可信度")

    data_quality = result.get("data_quality", {})
    cache_status = result.get("cache_status", {})

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("数据质量分", data_quality.get("quality_score", 0))
    with col2:
        st.metric("质量等级", data_quality.get("quality_level", "unknown"))
    with col3:
        fallback_count = data_quality.get("cache_fallback_count", 0)
        st.metric("缓存回退次数", fallback_count)

    records = []
    for symbol, meta in cache_status.items():
        if symbol == "QQQ_intraday_5m":
            name = "QQQ(5m)"
        else:
            name = symbol
        records.append(
            {
                "数据": name,
                "来源": meta.get("source", "none"),
                "状态": "新鲜" if meta.get("is_fresh", False) else "可能滞后",
                "说明": meta.get("message", ""),
            }
        )

    if records:
        st.dataframe(pd.DataFrame(records), use_container_width=True, hide_index=True)

    missing_symbols = data_quality.get("missing_symbols", [])
    if missing_symbols:
        st.warning(f"缺失数据：{', '.join(missing_symbols)}")
    for warning in data_quality.get("warnings", []):
        st.info(warning)


def display_market_status(result: dict) -> None:
    """显示当前市场状态。"""
    st.subheader("📊 当前市场状态")
    
    tqqq_final = result["tqqq_final"]
    sqqq_final = result["sqqq_final"]
    market_state = result["market_state"]
    
    # 显示市场状态和分数
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("TQQQ 最终评分", f"{tqqq_final:.0f}", delta=None)
    
    with col2:
        st.metric("SQQQ 最终评分", f"{sqqq_final:.0f}", delta=None)
    
    with col3:
        st.metric("风险扣分", f"{result['risk_deduction']:.0f}", delta=None)
    
    with col4:
        st.metric("市场状态", market_state, delta=None)
    
    # 颜色提示
    st.markdown("---")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("TQQQ 做多信号")
        if tqqq_final >= 85:
            st.success(f"🟢 强多环境 ({tqqq_final:.0f})")
        elif tqqq_final >= 75:
            st.success(f"🟢 偏多环境 ({tqqq_final:.0f})")
        elif tqqq_final >= 65:
            st.warning(f"🟡 弱多观察 ({tqqq_final:.0f})")
        else:
            st.info(f"⚪ 不适合做多 ({tqqq_final:.0f})")
    
    with col2:
        st.subheader("SQQQ 做空信号")
        if sqqq_final >= 85:
            st.error(f"🔴 强空环境 ({sqqq_final:.0f})")
        elif sqqq_final >= 75:
            st.warning(f"🟠 偏空环境 ({sqqq_final:.0f})")
        elif sqqq_final >= 65:
            st.warning(f"🟡 弱空观察 ({sqqq_final:.0f})")
        else:
            st.info(f"⚪ 不适合做空 ({sqqq_final:.0f})")
    
    # 混乱信号警告
    if tqqq_final >= 65 and sqqq_final >= 65:
        st.warning(
            "⚠️ TQQQ 与 SQQQ 分数同时偏高，说明市场信号混乱，方向不确定，建议观望。"
        )


def display_qqq_indicators(result: dict) -> None:
    """显示 QQQ 趋势指标表。"""
    st.subheader("📈 QQQ 趋势指标")
    
    try:
        snapshot = result["indicator_snapshot"]
        qqq_data = snapshot.get("qqq", {})
        
        if not qqq_data:
            st.info("⚠️ QQQ 指标数据不可用")
            return
        
        indicators_df = pd.DataFrame({
            "指标": [
                "当前价格",
                "MA5",
                "MA20",
                "MA50",
                "MA200",
                "MA20 斜率",
                "MA50 斜率",
                "ATR14",
                "成交量比例",
            ],
            "数值": [
                f"{qqq_data.get('price', 0):.2f}",
                f"{qqq_data.get('ma5', 0):.2f}",
                f"{qqq_data.get('ma20', 0):.2f}",
                f"{qqq_data.get('ma50', 0):.2f}",
                f"{qqq_data.get('ma200', 0):.2f}",
                f"{qqq_data.get('ma20_slope', 0):.4f}",
                f"{qqq_data.get('ma50_slope', 0):.4f}",
                f"{qqq_data.get('atr14', 0):.2f}",
                f"{qqq_data.get('volume_ratio', 0):.2f}x",
            ],
            "解释": [
                "最新收盘价",
                "5日简单移动平均",
                "20日简单移动平均",
                "50日简单移动平均",
                "200日简单移动平均",
                "MA20 变化率",
                "MA50 变化率",
                "14日平均真实波幅",
                "当日成交量相对平均比例",
            ],
        })
        
        st.dataframe(indicators_df, use_container_width=True, hide_index=True)
        
    except Exception as e:
        logger.error(f"显示 QQQ 指标失败：{e}")
        st.warning("⚠️ QQQ 指标显示失败")


def display_tech_stocks(result: dict) -> None:
    """显示科技权重股涨跌表。"""
    st.subheader("💻 科技权重股强弱")
    
    try:
        daily_data = result["daily_data"]
        snapshot = result["indicator_snapshot"]
        
        tech_stats = []
        up_count = 0
        down_count = 0
        total_return = 0
        
        for symbol in MEGA_CAP_TECH_SYMBOLS:
            if symbol not in daily_data or daily_data[symbol].empty:
                tech_stats.append({
                    "股票": symbol,
                    "最新涨跌幅": "数据缺失",
                    "状态": "⚠️ 缺失",
                })
                continue
            
            df = daily_data[symbol]
            if len(df) > 1:
                latest = df.iloc[-1]["close"]
                prev = df.iloc[-2]["close"]
                change_pct = (latest - prev) / prev * 100
            else:
                change_pct = 0
            
            if change_pct > 0.1:
                status = "🟢 上涨"
                up_count += 1
            elif change_pct < -0.1:
                status = "🔴 下跌"
                down_count += 1
            else:
                status = "⚪ 持平"
            
            total_return += change_pct
            
            tech_stats.append({
                "股票": symbol,
                "最新涨跌幅": f"{change_pct:.2f}%",
                "状态": status,
            })
        
        tech_df = pd.DataFrame(tech_stats)
        st.dataframe(tech_df, use_container_width=True, hide_index=True)
        
        # 统计信息
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("上涨数量", f"{up_count}/8")
        with col2:
            st.metric("下跌数量", f"{down_count}/8")
        with col3:
            st.metric("平均涨跌幅", f"{total_return/8:.2f}%")
        with col4:
            if up_count > down_count:
                st.metric("综合状态", "🟢 强势")
            elif down_count > up_count:
                st.metric("综合状态", "🔴 弱势")
            else:
                st.metric("综合状态", "⚪ 混合")
        
    except Exception as e:
        logger.error(f"显示科技股信息失败：{e}")
        st.warning("⚠️ 科技权重股数据显示失败")


def display_relative_strength(result: dict) -> None:
    """显示相对强弱指标。"""
    st.subheader("⚖️ 相对强弱指标")
    
    try:
        snapshot = result["indicator_snapshot"]
        relative_strength = snapshot.get("relative_strength", {})
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**QQQ 相对 SPY 强弱**")
            qqq_spy_ratio = relative_strength.get("qqq_vs_spy", 0)
            if qqq_spy_ratio > 0.01:
                st.success(f"🟢 纳指相对强势 ({qqq_spy_ratio:.4f})")
                st.caption("说明纳指科技方向强于大盘")
            elif qqq_spy_ratio < -0.01:
                st.error(f"🔴 纳指相对弱势 ({qqq_spy_ratio:.4f})")
                st.caption("说明纳指科技方向弱于大盘")
            else:
                st.info(f"⚪ 强弱相当 ({qqq_spy_ratio:.4f})")
        
        with col2:
            st.markdown("**QQQE 相对 QQQ 强弱**")
            qqqe_qqq_ratio = relative_strength.get("qqqe_vs_qqq", 0)
            if qqqe_qqq_ratio > -0.02:
                st.success(f"🟢 广度健康 ({qqqe_qqq_ratio:.4f})")
                st.caption("说明上涨更健康，不完全依赖少数权重股")
            else:
                st.warning(f"🟡 权重效应 ({qqqe_qqq_ratio:.4f})")
                st.caption("说明可能是少数大权重硬拉")
        
    except Exception as e:
        logger.error(f"显示相对强弱指标失败：{e}")
        st.warning("⚠️ 相对强弱指标显示失败")


def display_volatility(result: dict) -> None:
    """显示波动率指标。"""
    st.subheader("📊 波动率指标")
    
    try:
        snapshot = result["indicator_snapshot"]
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            vix = snapshot.get("vix", 0)
            st.metric("VIX", f"{vix:.2f}")
            if vix > 25:
                st.caption("⚠️ 市场波动率较高")
            elif vix < 15:
                st.caption("✓ 市场波动率较低")
            else:
                st.caption("中等波动率")
        
        with col2:
            vxn = snapshot.get("vxn", 0)
            if vxn > 0:
                st.metric("VXN", f"{vxn:.2f}")
                st.caption("纳指特定波动率")
            else:
                st.metric("VXN", "数据缺失")
                st.warning("VXN 数据缺失，评分使用 VIX 替代")
        
        with col3:
            st.metric("波动率趋势", "实时")
            st.caption("用于风险扣分计算")
        
    except Exception as e:
        logger.error(f"显示波动率指标失败：{e}")
        st.warning("⚠️ 波动率指标显示失败")


def display_scoring_reasons(result: dict) -> None:
    """显示评分原因（可展开）。"""
    st.subheader("💡 评分原因与解释")
    
    with st.expander("点击查看详细评分原因", expanded=False):
        try:
            tqqq_result = result["tqqq_result"]
            sqqq_result = result["sqqq_result"]
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("**TQQQ 做多评分原因：**")
                tqqq_reasons = tqqq_result.get("reasons", [])
                if tqqq_reasons:
                    for reason in tqqq_reasons:
                        st.caption(f"• {reason}")
                else:
                    st.caption("暂无详细原因")
            
            with col2:
                st.markdown("**SQQQ 做空评分原因：**")
                sqqq_reasons = sqqq_result.get("reasons", [])
                if sqqq_reasons:
                    for reason in sqqq_reasons:
                        st.caption(f"• {reason}")
                else:
                    st.caption("暂无详细原因")
            
            st.markdown("---")
            
            st.markdown("**综合结论：**")
            st.write(result["summary"])
            
            st.markdown("---")
            
            st.markdown("**风险因素：**")
            risk_result = result["risk_result"]
            risk_events = risk_result.get("events", [])
            if risk_events:
                for event in risk_events:
                    st.caption(f"⚠️ {event}")
            else:
                st.caption("✓ 当前无预定义风险事件")
        
        except Exception as e:
            logger.error(f"显示评分原因失败：{e}")
            st.warning("⚠️ 评分原因显示失败")


def display_qqq_chart(result: dict) -> None:
    """显示 QQQ 价格走势图。"""
    st.subheader("📉 QQQ 趋势结构")
    
    try:
        daily_data = result["daily_data"]
        
        if "QQQ" not in daily_data or daily_data["QQQ"].empty:
            st.info("⚠️ QQQ 数据不可用，无法绘制图表")
            return
        
        df = daily_data["QQQ"].copy()
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df.dropna(subset=["date"]).sort_values("date")
        
        # 计算 MA
        ma_df = calculate_moving_averages(df)
        
        fig = go.Figure()
        
        # 添加收盘价
        fig.add_trace(go.Scatter(
            x=df["date"],
            y=df["close"],
            name="QQQ Close",
            line=dict(color="#1f77b4", width=2),
        ))
        
        # 添加移动平均线
        if "ma20" in ma_df.columns:
            fig.add_trace(go.Scatter(
                x=ma_df["date"],
                y=ma_df["ma20"],
                name="MA20",
                line=dict(color="#ff7f0e", width=1, dash="dash"),
            ))
        
        if "ma50" in ma_df.columns:
            fig.add_trace(go.Scatter(
                x=ma_df["date"],
                y=ma_df["ma50"],
                name="MA50",
                line=dict(color="#2ca02c", width=1, dash="dash"),
            ))
        
        if "ma200" in ma_df.columns:
            fig.add_trace(go.Scatter(
                x=ma_df["date"],
                y=ma_df["ma200"],
                name="MA200",
                line=dict(color="#d62728", width=1, dash="dash"),
            ))
        
        fig.update_layout(
            title="QQQ 趋势结构（最近 1 年）",
            xaxis_title="日期",
            yaxis_title="价格 ($)",
            hovermode="x unified",
            height=500,
            template="plotly_white",
        )
        
        st.plotly_chart(fig, use_container_width=True)
        
    except Exception as e:
        logger.error(f"绘制 QQQ 图表失败：{e}")
        st.warning("⚠️ QQQ 走势图绘制失败")


def display_historical_scores() -> None:
    """显示历史评分变化图。"""
    st.subheader("📊 历史评分变化")
    
    try:
        # 清除缓存重新加载
        st.cache_data.clear()
        scores_df = load_recent_market_scores(limit=100)
        
        if scores_df.empty:
            st.info("⚠️ 暂无历史评分记录")
            return
        
        # 按时间倒序排列（最早在前，最新在后）
        scores_df = scores_df.iloc[::-1].reset_index(drop=True)
        scores_df["datetime"] = pd.to_datetime(scores_df["datetime"])
        
        fig = go.Figure()
        
        # 添加 TQQQ 最终评分
        fig.add_trace(go.Scatter(
            x=scores_df["datetime"],
            y=scores_df["tqqq_final_score"],
            name="TQQQ 最终评分",
            line=dict(color="#2ca02c", width=2),
            fill="tozeroy",
        ))
        
        # 添加 SQQQ 最终评分
        fig.add_trace(go.Scatter(
            x=scores_df["datetime"],
            y=scores_df["sqqq_final_score"],
            name="SQQQ 最终评分",
            line=dict(color="#d62728", width=2),
            fill="tozeroy",
        ))
        
        fig.update_layout(
            title="历史评分变化（最近 100 条）",
            xaxis_title="时间",
            yaxis_title="评分",
            hovermode="x unified",
            height=400,
            template="plotly_white",
        )
        
        st.plotly_chart(fig, use_container_width=True)
        
        # 显示统计信息
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("TQQQ 平均分", f"{scores_df['tqqq_final_score'].mean():.1f}")
        with col2:
            st.metric("SQQQ 平均分", f"{scores_df['sqqq_final_score'].mean():.1f}")
        with col3:
            st.metric("最高 TQQQ", f"{scores_df['tqqq_final_score'].max():.1f}")
        with col4:
            st.metric("最高 SQQQ", f"{scores_df['sqqq_final_score'].max():.1f}")
        
    except Exception as e:
        logger.error(f"显示历史评分失败：{e}")
        st.warning("⚠️ 历史评分图表显示失败")


def display_backtest_metrics(metrics: dict) -> None:
    """
    显示回测指标。
    """
    if not metrics:
        st.warning("⚠️ 无回测指标数据")
        return
    
    try:
        # 显示关键指标
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("总交易次数", metrics.get("total_trades", 0))
        with col2:
            win_rate = metrics.get("win_rate", 0) * 100
            st.metric("胜率", f"{win_rate:.1f}%")
        with col3:
            profit_factor = metrics.get("profit_factor", 0)
            st.metric("盈亏比", f"{profit_factor:.2f}")
        with col4:
            cumulative_return = metrics.get("cumulative_return", 0) * 100
            st.metric("累计收益", f"{cumulative_return:.2f}%")
        
        st.markdown("---")
        
        # 显示详细指标
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("平均盈利", f"{metrics.get('avg_win', 0) * 100:.2f}%")
            st.metric("平均亏损", f"{metrics.get('avg_loss', 0) * 100:.2f}%")
        
        with col2:
            st.metric("平均收益率", f"{metrics.get('avg_return', 0) * 100:.2f}%")
            st.metric("最大回撤", f"{metrics.get('max_drawdown', 0) * 100:.2f}%")
        
        with col3:
            st.metric("平均持仓天数", f"{metrics.get('avg_holding_days', 0):.1f}")
            st.metric("连续亏损", f"{metrics.get('consecutive_losses', 0)} 笔")
        
    except Exception as e:
        logger.error(f"显示回测指标失败：{e}")
        st.warning("⚠️ 回测指标显示失败")


def display_backtest_trades(df_trades: pd.DataFrame) -> None:
    """
    显示回测交易明细。
    """
    if df_trades is None or df_trades.empty:
        st.info("📊 暂无交易记录")
        return
    
    try:
        st.subheader("交易明细")
        
        # 显示最近的交易
        display_df = df_trades.tail(20)[
            ["entry_date", "exit_date", "symbol", "entry_price", "exit_price", "return_pct", "exit_reason"]
        ].copy()
        
        # 重命名列
        display_df.columns = ["进场日期", "出场日期", "标的", "进场价", "出场价", "收益%", "出场原因"]
        
        st.dataframe(display_df, use_container_width=True, hide_index=True)
        
    except Exception as e:
        logger.error(f"显示交易明细失败：{e}")
        st.warning("⚠️ 交易明细显示失败")


def display_backtest_analysis() -> None:
    """
    显示回测分析页面。
    """
    from src.backtest import run_backtest
    from src.database import (
        init_backtest_tables,
        save_backtest_scores,
        save_backtest_signals,
        save_backtest_trades,
        save_backtest_metrics,
        load_latest_backtest_metrics,
        load_backtest_trades,
    )
    
    st.markdown("---")
    st.subheader("📈 回测分析")
    st.markdown("基于历史数据的策略回测，评估信号系统的有效性")
    
    # 回测控制按钮
    col1, col2 = st.columns([2, 1])
    
    with col2:
        if st.button("▶️ 执行回测", use_container_width=True):
            st.session_state.run_backtest = True
    
    # 执行回测
    if st.session_state.get("run_backtest", False):
        with st.spinner("⏳ 正在执行回测（可能需要数分钟）..."):
            try:
                # 初始化表
                init_db()
                init_backtest_tables()
                
                # 执行回测
                backtest_result = run_backtest()
                
                if backtest_result["status"] == "success":
                    # 保存结果
                    save_backtest_scores(backtest_result["historical_scores"])
                    save_backtest_signals(backtest_result["trade_signals"])
                    save_backtest_trades(backtest_result["trades"])
                    save_backtest_metrics(
                        backtest_result["metrics"],
                        backtest_result["start_date"],
                        backtest_result["end_date"],
                    )
                    
                    st.session_state.last_backtest = backtest_result
                    st.session_state.run_backtest = False
                    st.success("✅ 回测完成")
                    st.rerun()
                else:
                    st.error(f"❌ 回测失败：{backtest_result['message']}")
                    st.session_state.run_backtest = False
                    
            except Exception as e:
                logger.error(f"回测执行失败：{e}", exc_info=True)
                st.error(f"❌ 回测异常：{str(e)}")
                st.session_state.run_backtest = False
    
    # 显示回测结果
    if "last_backtest" in st.session_state:
        backtest_result = st.session_state.last_backtest
        
        # 显示时间范围
        st.info(f"📅 回测时间段：{backtest_result['start_date']} 至 {backtest_result['end_date']}")
        
        # 显示回测指标
        display_backtest_metrics(backtest_result["metrics"])
        
        # 显示交易明细
        display_backtest_trades(backtest_result["trades"])
        
        # 显示信号分布
        st.markdown("---")
        st.subheader("信号分布")
        
        signals_df = backtest_result["trade_signals"]
        if not signals_df.empty:
            signal_counts = signals_df["signal"].value_counts()
            col1, col2, col3 = st.columns(3)
            
            with col1:
                tqqq_count = signal_counts.get("BUY_TQQQ", 0)
                st.metric("BUY_TQQQ 信号", tqqq_count)
            with col2:
                sqqq_count = signal_counts.get("BUY_SQQQ", 0)
                st.metric("BUY_SQQQ 信号", sqqq_count)
            with col3:
                hold_count = signal_counts.get("HOLD_CASH", 0)
                st.metric("HOLD_CASH 信号", hold_count)
    else:
        st.info("💡 点击「执行回测」开始历史回测分析")
    
    # 风险提示
    st.markdown("---")
    from config.settings import BACKTEST_DISCLOSURE
    st.warning("⚠️ **回测风险提示**\n\n" + BACKTEST_DISCLOSURE)


def main() -> None:
    """Main Streamlit app."""
    # 初始化数据库
    init_db()
    
    # 页面标题
    st.title("🚀 TQQQ / SQQQ 纳指量化信号面板")
    st.markdown("*个人量化研究与交易辅助系统，不构成投资建议*")
    
    st.markdown("---")
    
    # 创建选项卡
    tab1, tab2 = st.tabs(["📊 实时分析", "📈 回测分析"])
    
    # 选项卡 1：实时分析
    with tab1:
        # 数据刷新按钮
        col1, col2, col3 = st.columns([2, 1, 1])
        
        with col2:
            if st.button("🔄 刷新数据并重新评分", use_container_width=True):
                st.session_state.force_refresh = True
        
        with col3:
            if st.button("📊 查看最近记录", use_container_width=True):
                st.session_state.show_recent = True
        
        # 获取数据
        result = None
        
        if st.session_state.get("force_refresh", False):
            result = fetch_and_calculate()
            if result:
                st.session_state.last_result = result
                st.session_state.force_refresh = False
                st.rerun()
        else:
            # 尝试从 session state 恢复
            if "last_result" not in st.session_state:
                st.info("💡 点击「刷新数据并重新评分」开始分析")
                result = None
            else:
                result = st.session_state.last_result
        
        # 如果有结果，显示所有信息
        if result is not None:
            display_data_status(result)
            st.markdown("---")

            # 显示市场状态
            display_market_status(result)
            st.markdown("---")
            
            # 显示各个模块
            display_qqq_indicators(result)
            st.markdown("---")
            
            display_tech_stocks(result)
            st.markdown("---")
            
            display_relative_strength(result)
            st.markdown("---")
            
            display_volatility(result)
            st.markdown("---")
            
            display_scoring_reasons(result)
            st.markdown("---")
            
            display_qqq_chart(result)
            st.markdown("---")
            
            display_historical_scores()
        
        # 页面底部信息
        st.markdown("---")
        
        # 数据质量说明
        with st.expander("📋 数据质量说明", expanded=False):
            st.markdown("""
            **数据源：** yfinance
            
            **当前版本：** MVP（最小可行产品）
            
            **数据处理：**
            - 期货数据：若无法获取真实 NQ / ES，则使用 QQQ / SPY 替代逻辑
            - VXN：若缺失，则使用 VIX 部分替代
            - 分钟线：可选，用于 VWAP 和开盘结构分析
            
            **网络限制：**
            - 如果环境中存在代理/防火墙，可能无法正常获取实时数据
            - 建议在网络正常的环境中使用本系统
            """)
        
        # 风险提示
        st.markdown("---")
        st.warning(
            "⚠️ **重要风险提示** ⚠️\n\n"
            + RISK_DISCLOSURE
        )
    
    # 选项卡 2：回测分析
    with tab2:
        display_backtest_analysis()


if __name__ == "__main__":
    main()
