"""Command-line entry point for research dataset analysis reports."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.research_analysis import build_research_analysis_report


DEFAULT_INPUT_PATH = Path("data") / "research_dataset.csv"
DEFAULT_OUTPUT_DIR = Path("data")


def write_analysis_outputs(
    report: dict[str, pd.DataFrame],
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
) -> dict[str, Path]:
    """Write analysis report tables to CSV files."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    module_effects = pd.concat(
        [
            report.get("futures_effect", pd.DataFrame()),
            report.get("breadth_effect", pd.DataFrame()),
            report.get("event_risk_effect", pd.DataFrame()),
        ],
        ignore_index=True,
    )

    outputs = {
        "score_buckets": output_path / "research_score_buckets.csv",
        "module_effects": output_path / "research_module_effects.csv",
        "quality_analysis": output_path / "research_quality_analysis.csv",
        "summary": output_path / "research_summary.csv",
    }
    report.get("score_buckets", pd.DataFrame()).to_csv(outputs["score_buckets"], index=False)
    module_effects.to_csv(outputs["module_effects"], index=False)
    report.get("data_quality_effect", pd.DataFrame()).to_csv(outputs["quality_analysis"], index=False)
    report.get("summary", pd.DataFrame()).to_csv(outputs["summary"], index=False)
    return outputs


def analyze_dataset_file(
    input_path: str | Path = DEFAULT_INPUT_PATH,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
) -> tuple[dict[str, pd.DataFrame], dict[str, Path]]:
    """Read a research dataset, build reports, and write CSV outputs."""
    dataset_path = Path(input_path)
    if not dataset_path.exists():
        raise FileNotFoundError(f"research dataset not found: {dataset_path}")

    dataset = pd.read_csv(dataset_path)
    report = build_research_analysis_report(dataset)
    outputs = write_analysis_outputs(report, output_dir=output_dir)
    return report, outputs


def print_summary(report: dict[str, pd.DataFrame], outputs: dict[str, Path]) -> None:
    summary = report.get("summary", pd.DataFrame())
    summary_map = {}
    if not summary.empty and {"metric", "value"}.issubset(summary.columns):
        summary_map = dict(zip(summary["metric"], summary["value"]))

    print(f"dataset rows: {summary_map.get('row_count', 0)}")
    print(f"date range: {summary_map.get('start_date', 'n/a')} -> {summary_map.get('end_date', 'n/a')}")
    print(f"score bucket rows: {len(report.get('score_buckets', pd.DataFrame()))}")
    print(f"module effect rows: {len(pd.read_csv(outputs['module_effects'])) if outputs.get('module_effects') else 0}")
    for name, path in outputs.items():
        print(f"{name}: {path}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze data/research_dataset.csv into calibration report CSVs.")
    parser.add_argument("--input", default=str(DEFAULT_INPUT_PATH), help="Research dataset CSV path.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Directory for report CSV outputs.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report, outputs = analyze_dataset_file(input_path=args.input, output_dir=args.output_dir)
    print_summary(report, outputs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
