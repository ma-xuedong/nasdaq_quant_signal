"""Streamlit dashboard for TQQQ / SQQQ signal system."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from config.settings import CORE_REALTIME_SYMBOLS, DATA_PROVIDER, RISK_DISCLOSURE
from src.backtest import analyze_quality_buckets, analyze_score_buckets
from src.database import load_backtest_trades, load_latest_backtest_metrics
from src.pipeline import run_signal_pipeline
from src.trade_journal import (
    MISTAKE_TYPES,
    add_trade_record,
    calculate_trade_journal_stats,
    load_trade_records,
)


st.set_page_config(
    page_title="TQQQ / SQQQ 纳指量化信号面板",
    layout="wide",
)

st.title("TQQQ / SQQQ 纳指量化信号面板")
st.caption("个人量化研究与交易辅助系统，不构成投资建议。")

PAGES = [
    "首页：当前信号",
    "期货确认",
    "市场宽度",
    "事件风险",
    "回测分析",
    "交易日志",
    "系统状态",
]

if "signal_result" not in st.session_state:
    st.session_state["signal_result"] = None


def derive_signal_type(result: dict | None) -> str:
    """Derive a simple signal type from the current pipeline result."""
    if not isinstance(result, dict) or not result.get("success", False):
        return "HOLD_CASH"

    final_scores = result.get("final_scores", {})
    tqqq_score = float(final_scores.get("tqqq_final_score", 0) or 0)
    sqqq_score = float(final_scores.get("sqqq_final_score", 0) or 0)

    if tqqq_score >= 75 and sqqq_score < 65:
        return "BUY_TQQQ"
    if sqqq_score >= 85 and tqqq_score < 65:
        return "BUY_SQQQ"
    return "HOLD_CASH"


def format_pct(value: float | int | None, digits: int = 2) -> str:
    """Format ratio as percentage string."""
    try:
        return f"{float(value or 0) * 100:.{digits}f}%"
    except (TypeError, ValueError):
        return f"{0:.{digits}f}%"


def render_warnings(warnings: list[str]) -> None:
    """Render warning list."""
    if not warnings:
        st.success("当前无额外 warnings。")
        return

    st.warning("当前存在以下提示：")
    for warning in warnings:
        st.write(f"- {warning}")


def render_runtime_banner(result: dict) -> None:
    """Render high-priority runtime status banners."""
    data_quality = result.get("data_quality", {})

    if result.get("is_test_mode", False):
        st.error("当前为测试数据，不可用于真实交易判断。")
    if not result.get("is_realtime_usable", False):
        st.warning("当前数据不满足实时判断要求，不建议交易。")

    quality_score = float(data_quality.get("quality_score", 0) or 0)
    if quality_score < 50:
        st.error("数据质量不足，不建议交易。")
    elif quality_score < 70:
        st.warning("数据质量一般，仅作弱参考，不建议重仓。")


def render_no_signal_state() -> None:
    """Render empty state for signal-driven pages."""
    st.info("点击侧边栏中的“刷新数据并重新评分”开始。")


def render_invalid_signal_state(result: dict | None) -> None:
    """Render invalid or failed signal state."""
    if isinstance(result, dict) and not result.get("success", False):
        st.error("信号流程执行失败。")
        render_runtime_banner(result)
        render_warnings(result.get("warnings", []))
    else:
        st.error("信号流程返回结果异常。")


def summarize_futures(snapshot: dict) -> str:
    """Build a short futures summary."""
    if not snapshot.get("available", False):
        return "NQ / ES 数据不足，期货确认模块当前降级。"

    direction = "强于" if snapshot.get("nq_stronger_than_es") else "弱于" if snapshot.get("nq_weaker_than_es") else "接近"
    trend = snapshot.get("nq_trend", {}).get("trend", "unknown")
    return (
        f"NQ {direction} ES，NQ-ES 为 {format_pct(snapshot.get('nq_vs_es'))}，"
        f"趋势状态为 {trend}。"
    )


def summarize_breadth(snapshot: dict) -> str:
    """Build a short breadth summary."""
    if not snapshot.get("available", False):
        return "市场宽度数据不足，当前仅可做降级观察。"

    return (
        f"上涨比例 {format_pct(snapshot.get('up_ratio'))}，"
        f"站上 MA20 比例 {format_pct(snapshot.get('above_ma20_ratio'))}，"
        f"宽度状态 {snapshot.get('breadth_status', 'unknown')}。"
    )


def summarize_event_risk(snapshot: dict) -> str:
    """Build a short event risk summary."""
    today_events = snapshot.get("today_events", [])
    if not today_events:
        return "今日无重大事件，当前本地事件日历未显示高风险事项。"

    labels = [event.get("label") or event.get("type") or "事件" for event in today_events]
    return (
        f"今日共 {len(today_events)} 项事件，风险等级 {snapshot.get('risk_level', 'low')}，"
        f"预计扣分 {snapshot.get('deduction', 0):.0f} 分。重点：{', '.join(labels[:3])}。"
    )


def render_home_page(result: dict | None) -> None:
    """Render homepage signal overview."""
    st.header("首页：当前信号")
    if result is None:
        render_no_signal_state()
        return
    if not isinstance(result, dict) or not result.get("success", False):
        render_invalid_signal_state(result)
        return

    render_runtime_banner(result)
    final_scores = result.get("final_scores", {})
    data_quality = result.get("data_quality", {})

    col1, col2, col3, col4, col5, col6 = st.columns(6)
    col1.metric("TQQQ 最终评分", f"{float(final_scores.get('tqqq_final_score', 0) or 0):.2f}")
    col2.metric("SQQQ 最终评分", f"{float(final_scores.get('sqqq_final_score', 0) or 0):.2f}")
    col3.metric("市场状态", result.get("market_state", "未知"))
    col4.metric("数据质量", f"{data_quality.get('quality_level', 'unknown')} ({float(data_quality.get('quality_score', 0) or 0):.0f})")
    col5.metric("实时可用", "是" if result.get("is_realtime_usable", False) else "否")
    col6.metric("测试模式", "是" if result.get("is_test_mode", False) else "否")

    st.subheader("第三期摘要")
    summary_col1, summary_col2, summary_col3 = st.columns(3)
    summary_col1.info(summarize_futures(result.get("futures_snapshot", {})))
    summary_col2.info(summarize_breadth(result.get("breadth_snapshot", {})))
    summary_col3.info(summarize_event_risk(result.get("event_risk_snapshot", {})))

    st.subheader("最终结论")
    st.write(result.get("summary", ""))

    st.subheader("Warnings")
    render_warnings(result.get("warnings", []))


def render_futures_page(result: dict | None) -> None:
    """Render futures confirmation page."""
    st.header("期货确认")
    if result is None:
        render_no_signal_state()
        return
    if not isinstance(result, dict) or not result.get("success", False):
        render_invalid_signal_state(result)
        return

    snapshot = result.get("futures_snapshot", {})
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("NQ 涨跌幅", format_pct(snapshot.get("nq_return")))
    col2.metric("ES 涨跌幅", format_pct(snapshot.get("es_return")))
    col3.metric("NQ - ES", format_pct(snapshot.get("nq_vs_es")))
    col4.metric("NQ 是否强于 ES", "是" if snapshot.get("nq_stronger_than_es") else "否")

    st.write(f"NQ 趋势状态：{snapshot.get('nq_trend', {}).get('trend', 'unknown')}")
    st.write(f"Gap / ATR：{float(snapshot.get('gap_vs_atr', 0) or 0):.2f}")

    with st.expander("数据来源", expanded=False):
        st.json(snapshot.get("source_status", {}))
    with st.expander("Warnings", expanded=False):
        st.json(snapshot.get("warnings", []))
    with st.expander("完整 futures_snapshot", expanded=False):
        st.json(snapshot)


def render_breadth_page(result: dict | None) -> None:
    """Render breadth page."""
    st.header("市场宽度")
    if result is None:
        render_no_signal_state()
        return
    if not isinstance(result, dict) or not result.get("success", False):
        render_invalid_signal_state(result)
        return

    snapshot = result.get("breadth_snapshot", {})
    missing_symbols = snapshot.get("missing_symbols", [])

    row1 = st.columns(4)
    row1[0].metric("可用成分股数量", int(snapshot.get("available_symbols", 0) or 0))
    row1[1].metric("缺失成分股数量", len(missing_symbols))
    row1[2].metric("上涨家数", int(snapshot.get("up_count", 0) or 0))
    row1[3].metric("下跌家数", int(snapshot.get("down_count", 0) or 0))

    row2 = st.columns(4)
    row2[0].metric("上涨比例", format_pct(snapshot.get("up_ratio")))
    row2[1].metric("站上 MA20 比例", format_pct(snapshot.get("above_ma20_ratio")))
    row2[2].metric("站上 MA50 比例", format_pct(snapshot.get("above_ma50_ratio")))
    row2[3].metric("站上 MA200 比例", format_pct(snapshot.get("above_ma200_ratio")))

    st.write(f"breadth_status：{snapshot.get('breadth_status', 'unknown')}")

    with st.expander("Warnings", expanded=False):
        st.json(snapshot.get("warnings", []))
    with st.expander("缺失成分股", expanded=False):
        st.json(missing_symbols)
    with st.expander("完整 breadth_snapshot", expanded=False):
        st.json(snapshot)


def render_event_risk_page(result: dict | None) -> None:
    """Render event risk page."""
    st.header("事件风险")
    if result is None:
        render_no_signal_state()
        return
    if not isinstance(result, dict) or not result.get("success", False):
        render_invalid_signal_state(result)
        return

    snapshot = result.get("event_risk_snapshot", {})
    col1, col2, col3 = st.columns(3)
    col1.metric("risk_score", f"{float(snapshot.get('deduction', 0) or 0):.0f}")
    col2.metric("risk_level", snapshot.get("risk_level", "low"))
    col3.metric("今日事件数", int(snapshot.get("today_event_count", 0) or 0))

    st.subheader("今日事件")
    today_events = snapshot.get("today_events", [])
    if today_events:
        st.dataframe(pd.DataFrame(today_events), use_container_width=True, hide_index=True)
    else:
        st.info("今日无事件。")

    st.subheader("未来 7 天事件")
    upcoming_events = snapshot.get("upcoming_events", [])
    if upcoming_events:
        st.dataframe(pd.DataFrame(upcoming_events), use_container_width=True, hide_index=True)
    else:
        st.info("未来 7 天暂无已配置事件。")

    with st.expander("reasons", expanded=False):
        st.json(snapshot.get("reasons", []))


def render_backtest_page() -> None:
    """Render backtest page from persisted results only."""
    st.header("回测分析")
    metrics = load_latest_backtest_metrics()
    trades_df = load_backtest_trades(limit=200)

    st.warning("回测结果不代表未来收益。")

    if not metrics or trades_df.empty:
        st.info("历史数据不足，暂无法进行可靠回测。")
        return

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("总交易数", int(metrics.get("total_trades", 0) or 0))
    col2.metric("胜率", format_pct(metrics.get("win_rate")))
    col3.metric("profit_factor", f"{float(metrics.get('profit_factor', 0) or 0):.2f}")
    col4.metric("max_drawdown", format_pct(metrics.get("max_drawdown")))

    col5, col6, col7 = st.columns(3)
    col5.metric("avg_return", format_pct(metrics.get("avg_return")))
    col6.metric("avg_holding_days", f"{float(metrics.get('avg_holding_days', 0) or 0):.2f}")
    col7.metric("回测日期", str(metrics.get("backtest_date", "-")))

    st.subheader("metrics")
    st.json(metrics)

    st.subheader("trades")
    st.dataframe(trades_df, use_container_width=True, hide_index=True)

    st.subheader("score_bucket_analysis")
    if "signal_score" in trades_df.columns:
        score_bucket_df = analyze_score_buckets(trades_df)
        st.dataframe(score_bucket_df, use_container_width=True, hide_index=True)
    else:
        st.info("当前数据库中的回测交易不含 signal_score，暂无法展示评分分桶分析。")

    st.subheader("quality_bucket_analysis")
    if "data_quality_level" in trades_df.columns:
        quality_bucket_df = analyze_quality_buckets(trades_df)
        st.dataframe(quality_bucket_df, use_container_width=True, hide_index=True)
    else:
        st.info("当前数据库中的回测交易不含 data_quality_level，暂无法展示质量分桶分析。")


def render_trade_journal_page(result: dict | None) -> None:
    """Render trade journal inputs, filters and stats."""
    st.header("交易日志")
    st.caption("仅用于人工记录与复盘，不会自动下单。")

    system_tqqq_score = 0.0
    system_sqqq_score = 0.0
    market_state = ""
    signal_type = "HOLD_CASH"

    if isinstance(result, dict) and result.get("success", False):
        final_scores = result.get("final_scores", {})
        system_tqqq_score = float(final_scores.get("tqqq_final_score", 0) or 0)
        system_sqqq_score = float(final_scores.get("sqqq_final_score", 0) or 0)
        market_state = result.get("market_state", "")
        signal_type = derive_signal_type(result)

    with st.form("trade_journal_form"):
        col1, col2, col3 = st.columns(3)
        trade_datetime = col1.text_input("交易时间", value=pd.Timestamp.now().isoformat(timespec="seconds"))
        symbol = col2.selectbox("标的", ["TQQQ", "SQQQ", "QQQ", "SPY", "其他"])
        actual_action = col3.selectbox("实际操作", ["手动买入", "手动卖出", "观望", "减仓", "加仓", "其他"])

        col4, col5, col6 = st.columns(3)
        entry_price = col4.number_input("入场价格", min_value=0.0, value=0.0, step=0.01)
        exit_price = col5.number_input("离场价格", min_value=0.0, value=0.0, step=0.01)
        position_size = col6.number_input("仓位", min_value=0.0, max_value=1.0, value=0.0, step=0.05)

        col7, col8, col9 = st.columns(3)
        followed_signal = col7.checkbox("是否遵守系统信号", value=True)
        mistake_type = col8.selectbox("mistake_type", [""] + MISTAKE_TYPES)
        manual_return_pct = col9.number_input("收益率(可手填)", value=0.0, step=0.01, format="%.4f")

        notes = st.text_area("复盘备注", placeholder="记录主观干预、情绪、执行问题等")
        submitted = st.form_submit_button("保存交易记录", type="primary")

        if submitted:
            computed_return = manual_return_pct
            if entry_price > 0 and exit_price > 0:
                computed_return = (exit_price - entry_price) / entry_price

            record_id = add_trade_record(
                {
                    "datetime": trade_datetime,
                    "symbol": symbol,
                    "signal_type": signal_type,
                    "system_tqqq_score": system_tqqq_score,
                    "system_sqqq_score": system_sqqq_score,
                    "market_state": market_state,
                    "actual_action": actual_action,
                    "entry_price": entry_price or None,
                    "exit_price": exit_price or None,
                    "position_size": position_size or None,
                    "return_pct": computed_return,
                    "followed_signal": followed_signal,
                    "mistake_type": mistake_type,
                    "notes": notes,
                }
            )

            if record_id > 0:
                st.success(f"交易记录已保存，ID={record_id}")
            else:
                st.error("交易记录保存失败。")

    st.markdown("---")
    filter_col1, filter_col2, filter_col3 = st.columns(3)
    filter_start = filter_col1.text_input("开始日期", value="")
    filter_end = filter_col2.text_input("结束日期", value="")
    filter_symbol = filter_col3.selectbox("筛选标的", ["全部", "TQQQ", "SQQQ", "QQQ", "SPY", "其他"], index=0)

    selected_symbol = None if filter_symbol == "全部" else filter_symbol
    records_df = load_trade_records(
        start_date=filter_start or None,
        end_date=filter_end or None,
        symbol=selected_symbol,
    )
    stats = calculate_trade_journal_stats(records_df)

    stat_col1, stat_col2, stat_col3, stat_col4 = st.columns(4)
    stat_col1.metric("总交易数", stats.get("total_trades", 0))
    stat_col2.metric("胜率", f"{stats.get('win_rate', 0.0) * 100:.1f}%")
    stat_col3.metric("平均收益", f"{stats.get('avg_return', 0.0) * 100:.2f}%")
    stat_col4.metric("遵守系统比例", f"{stats.get('followed_signal_ratio', 0.0) * 100:.1f}%")

    stat_col5, stat_col6 = st.columns(2)
    stat_col5.metric("遵守系统时平均收益", f"{stats.get('avg_return_when_followed', 0.0) * 100:.2f}%")
    stat_col6.metric("未遵守系统时平均收益", f"{stats.get('avg_return_when_not_followed', 0.0) * 100:.2f}%")

    with st.expander("mistake_type 分布", expanded=False):
        st.json(stats.get("mistake_type_counts", {}))

    st.subheader("历史交易记录")
    if records_df.empty:
        st.info("暂无交易日志记录。")
    else:
        st.dataframe(records_df, use_container_width=True, hide_index=True)


def render_system_status_page(result: dict | None) -> None:
    """Render system status page."""
    st.header("系统状态")
    st.metric("DATA_PROVIDER", DATA_PROVIDER)

    if result is None:
        render_no_signal_state()
        return
    if not isinstance(result, dict):
        render_invalid_signal_state(result)
        return

    if result.get("is_test_mode", False):
        st.error("当前为测试数据，不可用于真实交易判断。")
    if not result.get("is_realtime_usable", False):
        st.warning("当前数据不满足实时判断要求，不建议交易。")

    data_quality = result.get("data_quality", {})
    cache_status = result.get("cache_status", {})
    data_source_status = result.get("data_source_status", {})

    row = st.columns(4)
    row[0].metric("实时可用", "是" if result.get("is_realtime_usable", False) else "否")
    row[1].metric("测试模式", "是" if result.get("is_test_mode", False) else "否")
    row[2].metric("fallback_cache 数量", int(data_quality.get("cache_fallback_count", 0) or 0))
    row[3].metric("missing_symbols 数量", len(data_quality.get("missing_symbols", [])))

    st.subheader("data_quality")
    st.json(data_quality)

    st.subheader("missing_symbols")
    st.json(data_quality.get("missing_symbols", []))

    st.subheader("data_source_status")
    st.json(data_source_status)

    st.subheader("cache_status")
    st.json(cache_status)

    status_rows = []
    for key in CORE_REALTIME_SYMBOLS + ["QQQ_intraday_5m"]:
        meta = data_source_status.get(key, {})
        status_rows.append(
            {
                "symbol": key,
                "source": meta.get("source", "missing"),
                "fresh": meta.get("is_fresh", False),
                "fallback_cache": meta.get("is_fallback", False),
                "used_cache": meta.get("used_cache", False),
                "last_updated": meta.get("last_updated", ""),
                "message": meta.get("message", ""),
            }
        )

    st.subheader("核心标的数据来源")
    st.dataframe(pd.DataFrame(status_rows), use_container_width=True, hide_index=True)


with st.sidebar:
    st.header("页面导航")
    selected_page = st.radio("选择页面", PAGES)
    if st.button("刷新数据并重新评分", type="primary", use_container_width=True):
        with st.spinner("正在执行统一信号流程..."):
            st.session_state["signal_result"] = run_signal_pipeline(
                save_to_db=True,
                use_cache=True,
            )
    st.caption(f"当前数据提供方：{DATA_PROVIDER}")


result = st.session_state.get("signal_result")

if selected_page == "首页：当前信号":
    render_home_page(result)
elif selected_page == "期货确认":
    render_futures_page(result)
elif selected_page == "市场宽度":
    render_breadth_page(result)
elif selected_page == "事件风险":
    render_event_risk_page(result)
elif selected_page == "回测分析":
    render_backtest_page()
elif selected_page == "交易日志":
    render_trade_journal_page(result if isinstance(result, dict) else None)
else:
    render_system_status_page(result)

st.warning(RISK_DISCLOSURE)
