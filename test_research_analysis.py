"""Tests for research analysis reports."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pandas as pd

from scripts.analyze_research_dataset import analyze_dataset_file
from src.research_analysis import (
    analyze_breadth_effect,
    analyze_data_quality_effect,
    analyze_event_risk_effect,
    analyze_futures_effect,
    analyze_score_buckets,
    build_research_analysis_report,
)


def _mock_research_dataset() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "date": "2025-01-01",
                "tqqq_score": 45,
                "sqqq_score": 92,
                "nq_vs_es": -0.01,
                "breadth_status": "weak",
                "event_risk_level": "high",
                "event_risk_score": 30,
                "data_quality_level": "poor",
                "next_1d_tqqq_return": -0.03,
                "next_3d_tqqq_return": -0.05,
                "next_5d_tqqq_return": -0.08,
                "next_1d_sqqq_return": 0.04,
                "next_3d_sqqq_return": 0.07,
                "next_5d_sqqq_return": 0.08,
            },
            {
                "date": "2025-01-02",
                "tqqq_score": 55,
                "sqqq_score": 82,
                "nq_vs_es": -0.02,
                "breadth_status": "mixed",
                "event_risk_level": "medium",
                "event_risk_score": 10,
                "data_quality_level": "low",
                "next_1d_tqqq_return": -0.01,
                "next_3d_tqqq_return": 0.01,
                "next_5d_tqqq_return": -0.02,
                "next_1d_sqqq_return": 0.01,
                "next_3d_sqqq_return": 0.02,
                "next_5d_sqqq_return": 0.03,
            },
            {
                "date": "2025-01-03",
                "tqqq_score": 75,
                "sqqq_score": 62,
                "nq_vs_es": 0.01,
                "breadth_status": "strong",
                "event_risk_level": "low",
                "event_risk_score": 0,
                "data_quality_level": "high",
                "next_1d_tqqq_return": 0.02,
                "next_3d_tqqq_return": 0.05,
                "next_5d_tqqq_return": 0.06,
                "next_1d_sqqq_return": -0.02,
                "next_3d_sqqq_return": -0.04,
                "next_5d_sqqq_return": -0.05,
            },
            {
                "date": "2025-01-04",
                "tqqq_score": 95,
                "sqqq_score": 42,
                "nq_vs_es": 0.02,
                "breadth_status": "strong",
                "event_risk_level": "low",
                "event_risk_score": 0,
                "data_quality_level": "medium",
                "next_1d_tqqq_return": 0.03,
                "next_3d_tqqq_return": 0.06,
                "next_5d_tqqq_return": 0.07,
                "next_1d_sqqq_return": -0.03,
                "next_3d_sqqq_return": -0.05,
                "next_5d_sqqq_return": -0.06,
            },
        ]
    )


def test_score_bucket_groups_are_correct() -> None:
    result = analyze_score_buckets(_mock_research_dataset(), "tqqq_score", ["next_1d_tqqq_return"])

    populated = result[result["count"] > 0]
    assert set(populated["group"]) == {"<50", "50-60", "70-80", "90+"}


def test_score_bucket_win_rate_is_correct() -> None:
    result = analyze_score_buckets(_mock_research_dataset(), "tqqq_score", ["next_1d_tqqq_return"])
    bucket_70_80 = result[(result["group"] == "70-80") & (result["return_col"] == "next_1d_tqqq_return")]

    assert float(bucket_70_80.iloc[0]["win_rate"]) == 1.0


def test_module_effect_analyses_do_not_crash() -> None:
    dataset = _mock_research_dataset()

    assert not analyze_futures_effect(dataset).empty
    assert not analyze_breadth_effect(dataset).empty
    assert not analyze_event_risk_effect(dataset).empty
    assert not analyze_data_quality_effect(dataset).empty


def test_empty_dataframe_returns_empty_analysis_results() -> None:
    report = build_research_analysis_report(pd.DataFrame())

    assert set(report) == {
        "score_buckets",
        "futures_effect",
        "breadth_effect",
        "event_risk_effect",
        "data_quality_effect",
        "summary",
    }
    for table in report.values():
        assert table.empty


def test_analyze_research_dataset_script_outputs_csv() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        input_path = temp_path / "research_dataset.csv"
        _mock_research_dataset().to_csv(input_path, index=False)

        report, outputs = analyze_dataset_file(input_path=input_path, output_dir=temp_path)

        assert not report["score_buckets"].empty
        for output_path in outputs.values():
            assert output_path.exists()
            assert pd.read_csv(output_path) is not None


def main() -> None:
    test_score_bucket_groups_are_correct()
    test_score_bucket_win_rate_is_correct()
    test_module_effect_analyses_do_not_crash()
    test_empty_dataframe_returns_empty_analysis_results()
    test_analyze_research_dataset_script_outputs_csv()
    print("test_research_analysis passed")


if __name__ == "__main__":
    main()
