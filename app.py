"""Streamlit dashboard for TQQQ / SQQQ signal system."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from config.settings import CORE_REALTIME_SYMBOLS, RISK_DISCLOSURE
from src.pipeline import run_signal_pipeline


st.set_page_config(
    page_title="TQQQ / SQQQ 纳指量化信号面板",
    layout="wide",
)

st.title("TQQQ / SQQQ 纳指量化信号面板")
st.caption("个人量化研究与交易辅助系统，不构成投资建议。")


if "signal_result" not in st.session_state:
    st.session_state["signal_result"] = None


def render_warnings(warnings: list[str]) -> None:
    """Render warnings."""
    if not warnings:
        return

    st.warning("当前存在以下提示：")
    for warning in warnings:
        st.write(f"- {warning}")


def render_runtime_banner(result: dict) -> None:
    """Render high-priority runtime status banners."""
    data_quality = result.get("data_quality", {})

    if result.get("is_test_mode", False):
        st.error("测试数据，不可用于真实交易。")
    if not result.get("is_realtime_usable", False):
        st.warning("当前不满足实时/准实时判断条件，不能输出强交易建议。")

    quality_score = float(data_quality.get("quality_score", 0) or 0)
    if quality_score < 50:
        st.error("数据质量不足，不建议交易。")
    elif quality_score < 70:
        st.warning("数据质量一般，仅作弱参考，不建议重仓。")


def render_score_cards(result: dict) -> None:
    """Render top score cards."""
    final_scores = result.get("final_scores", {})
    data_quality = result.get("data_quality", {})

    col1, col2, col3, col4 = st.columns(4)

    col1.metric(
        "TQQQ最终评分",
        f"{float(final_scores.get('tqqq_final_score', 0) or 0):.2f}",
    )
    col2.metric(
        "SQQQ最终评分",
        f"{float(final_scores.get('sqqq_final_score', 0) or 0):.2f}",
    )
    col3.metric("市场状态", result.get("market_state", "未知"))
    col4.metric(
        "数据质量",
        f"{data_quality.get('quality_level', 'unknown')} "
        f"({float(data_quality.get('quality_score', 0) or 0):.0f})",
    )


def render_data_quality(result: dict) -> None:
    """Render data quality and cache status."""
    data_quality = result.get("data_quality", {})
    data_source_status = result.get("data_source_status", {})

    rows = []
    for key in CORE_REALTIME_SYMBOLS + ["QQQ_intraday_5m"]:
        meta = data_source_status.get(key, {})
        rows.append(
            {
                "symbol": key,
                "source": meta.get("source", "missing"),
                "fresh": meta.get("is_fresh", False),
                "fallback_cache": meta.get("is_fallback", False),
                "used_cache": meta.get("used_cache", False),
                "last_updated": meta.get("last_updated", ""),
                "data_timestamp": meta.get("data_timestamp", ""),
                "message": meta.get("message", ""),
            }
        )

    with st.expander("数据质量与缓存状态", expanded=False):
        st.subheader("运行状态")
        status_col1, status_col2, status_col3, status_col4 = st.columns(4)
        status_col1.metric("数据质量等级", data_quality.get("quality_level", "unknown"))
        status_col2.metric("质量分", f"{float(data_quality.get('quality_score', 0) or 0):.0f}")
        status_col3.metric("实时可用", "是" if result.get("is_realtime_usable", False) else "否")
        status_col4.metric("测试模式", "是" if result.get("is_test_mode", False) else "否")

        st.subheader("核心标的数据来源")
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        st.subheader("数据质量")
        st.json(data_quality)

        st.subheader("完整数据源状态")
        st.json(data_source_status)


def render_signal_details(result: dict) -> None:
    """Render signal details."""
    with st.expander("综合解释", expanded=True):
        st.write(result.get("summary", ""))

    with st.expander("TQQQ / SQQQ 评分细节", expanded=False):
        st.subheader("TQQQ")
        st.json(result.get("tqqq_result", {}))

        st.subheader("SQQQ")
        st.json(result.get("sqqq_result", {}))

        st.subheader("风险过滤")
        st.json(result.get("risk_result", {}))


def render_futures_breadth(result: dict) -> None:
    """Render futures and breadth snapshots from pipeline output."""
    futures_snapshot = result.get("futures_snapshot", {})
    breadth_snapshot = result.get("breadth_snapshot", {})

    col1, col2 = st.columns(2)
    with col1:
        with st.expander("期货确认", expanded=False):
            st.json(futures_snapshot)
    with col2:
        with st.expander("市场宽度", expanded=False):
            st.json(breadth_snapshot)


def render_indicator_snapshot(result: dict) -> None:
    """Render indicator snapshot if available."""
    snapshot = result.get("indicator_snapshot", {})
    if not snapshot:
        st.info("暂无指标快照。")
        return

    with st.expander("指标快照", expanded=False):
        st.json(snapshot)


if st.button("刷新数据并重新评分", type="primary"):
    with st.spinner("正在执行统一信号流程..."):
        st.session_state["signal_result"] = run_signal_pipeline(
            save_to_db=True,
            use_cache=True,
        )


result = st.session_state.get("signal_result")

if result is None:
    st.info("点击“刷新数据并重新评分”开始。")
    st.warning(RISK_DISCLOSURE)
    st.stop()


if not isinstance(result, dict):
    st.error("信号流程返回结果异常。")
    st.warning(RISK_DISCLOSURE)
    st.stop()


if not result.get("success", False):
    st.error("信号流程执行失败。")
    render_runtime_banner(result)
    render_warnings(result.get("warnings", []))
    st.warning(RISK_DISCLOSURE)
    st.stop()


render_runtime_banner(result)
render_score_cards(result)
render_warnings(result.get("warnings", []))
render_signal_details(result)
render_futures_breadth(result)
render_data_quality(result)
render_indicator_snapshot(result)

st.warning(RISK_DISCLOSURE)
