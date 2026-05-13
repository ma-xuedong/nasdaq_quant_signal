"""Streamlit dashboard for TQQQ / SQQQ signal system."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from config.settings import RISK_DISCLOSURE
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
    cache_status = result.get("cache_status", {})

    with st.expander("数据质量与缓存状态", expanded=False):
        st.subheader("数据质量")
        st.json(data_quality)

        st.subheader("缓存状态")
        st.json(cache_status)


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


def render_indicator_snapshot(result: dict) -> None:
    """Render indicator snapshot if available."""
    snapshot = result.get("indicator_snapshot", {})
    if not snapshot:
        st.info("暂无指标快照。")
        return

    with st.expander("指标快照", expanded=False):
        st.json(snapshot)


def render_history_placeholder() -> None:
    """Render a placeholder for future historical charts."""
    st.info("历史评分图可在后续版本中从数据库读取并展示。")


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
    render_warnings(result.get("warnings", []))
    st.warning(RISK_DISCLOSURE)
    st.stop()


render_score_cards(result)
render_warnings(result.get("warnings", []))
render_signal_details(result)
render_data_quality(result)
render_indicator_snapshot(result)
render_history_placeholder()

st.warning(RISK_DISCLOSURE)
