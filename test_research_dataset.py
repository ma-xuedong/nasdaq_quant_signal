"""Tests for research dataset construction."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pandas as pd

from src.research_dataset import build_research_dataset, export_research_dataset, research_dataset_columns


def _price_frame(symbol: str, start: str = "2025-01-01", periods: int = 215, slope: float = 1.0) -> pd.DataFrame:
    dates = pd.date_range(start, periods=periods, freq="D")
    closes = [100 + slope * idx for idx in range(periods)]
    return pd.DataFrame(
        {
            "date": dates,
            "open": [value - 0.2 for value in closes],
            "high": [value + 0.8 for value in closes],
            "low": [value - 0.8 for value in closes],
            "close": closes,
            "adj_close": closes,
            "volume": [1_000_000 + idx for idx in range(periods)],
            "symbol": [symbol] * periods,
        }
    )


def _historical_data() -> dict[str, pd.DataFrame]:
    return {
        "QQQ": _price_frame("QQQ", slope=1.0),
        "SPY": _price_frame("SPY", slope=0.8),
        "QQQE": _price_frame("QQQE", slope=1.1),
        "TQQQ": _price_frame("TQQQ", slope=2.0),
        "SQQQ": _price_frame("SQQQ", slope=-0.25),
        "NQ=F": _price_frame("NQ=F", slope=1.2),
        "ES=F": _price_frame("ES=F", slope=0.7),
        "MNQ=F": _price_frame("MNQ=F", slope=1.2),
        "MES=F": _price_frame("MES=F", slope=0.7),
        "^VIX": _price_frame("^VIX", slope=0.05),
        "^VXN": _price_frame("^VXN", slope=0.07),
        "NVDA": _price_frame("NVDA", slope=1.5),
        "MSFT": _price_frame("MSFT", slope=0.9),
        "AAPL": _price_frame("AAPL", slope=0.8),
        "AMZN": _price_frame("AMZN", slope=1.0),
        "META": _price_frame("META", slope=1.0),
        "GOOGL": _price_frame("GOOGL", slope=0.9),
        "AVGO": _price_frame("AVGO", slope=1.1),
        "TSLA": _price_frame("TSLA", slope=1.3),
    }


def test_research_dataset_generates_rows() -> None:
    dataset = build_research_dataset(_historical_data(), min_history_days=200)

    assert not dataset.empty
    assert len(dataset) == 16


def test_research_dataset_has_complete_fields() -> None:
    dataset = build_research_dataset(_historical_data(), min_history_days=200)

    assert list(dataset.columns) == research_dataset_columns()
    assert set(research_dataset_columns()).issubset(dataset.columns)


def test_future_return_labels_are_correct() -> None:
    historical_data = _historical_data()
    dataset = build_research_dataset(historical_data, min_history_days=200)

    row = dataset.iloc[0]
    row_date = pd.to_datetime(row["date"])
    tqqq_df = historical_data["TQQQ"].sort_values("date").reset_index(drop=True)
    sqqq_df = historical_data["SQQQ"].sort_values("date").reset_index(drop=True)
    row_idx = int(tqqq_df.index[tqqq_df["date"] == row_date][0])

    expected_tqqq_3d = (tqqq_df.iloc[row_idx + 3]["close"] / tqqq_df.iloc[row_idx]["close"]) - 1
    expected_sqqq_5d = (sqqq_df.iloc[row_idx + 5]["close"] / sqqq_df.iloc[row_idx]["close"]) - 1

    assert row["next_3d_tqqq_return"] == expected_tqqq_3d
    assert row["next_5d_sqqq_return"] == expected_sqqq_5d


def test_research_dataset_features_do_not_use_future_data() -> None:
    observed_max_dates: list[pd.Timestamp] = []

    def fake_build_snapshot(market_data: dict, current_date=None, mode: str = "research") -> dict:
        del mode
        observed_max_dates.append(market_data["daily_data"]["QQQ"]["date"].max())
        from src.snapshot_builder import build_scoring_snapshot

        return build_scoring_snapshot(market_data, current_date=current_date, mode="research")

    with patch("src.research_dataset.build_scoring_snapshot", side_effect=fake_build_snapshot):
        dataset = build_research_dataset(_historical_data(), min_history_days=200)

    assert not dataset.empty
    for row_date, observed_date in zip(dataset["date"], observed_max_dates):
        assert observed_date <= row_date


def test_research_dataset_empty_data_does_not_crash() -> None:
    dataset = build_research_dataset({}, min_history_days=200)

    assert dataset.empty
    assert list(dataset.columns) == research_dataset_columns()


def test_export_research_dataset_writes_csv(tmp_path: Path) -> None:
    output_path = tmp_path / "research_dataset.csv"

    dataset = export_research_dataset(_historical_data(), output_path=output_path, min_history_days=200)

    assert output_path.exists()
    loaded = pd.read_csv(output_path)
    assert len(loaded) == len(dataset)


def main() -> None:
    test_research_dataset_generates_rows()
    test_research_dataset_has_complete_fields()
    test_future_return_labels_are_correct()
    test_research_dataset_features_do_not_use_future_data()
    test_research_dataset_empty_data_does_not_crash()
    print("test_research_dataset passed")


if __name__ == "__main__":
    main()
