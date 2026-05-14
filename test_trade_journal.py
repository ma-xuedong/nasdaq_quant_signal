"""Unit tests for trade journal module."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch
import pandas as pd

from src.database import get_connection, init_database
from src.trade_journal import (
    add_trade_record,
    calculate_trade_journal_stats,
    load_trade_records,
    update_trade_record,
)


def _sample_record(symbol: str = "TQQQ") -> dict:
    return {
        "datetime": "2026-05-14T09:35:00",
        "symbol": symbol,
        "signal_type": "BUY_TQQQ" if symbol == "TQQQ" else "BUY_SQQQ",
        "system_tqqq_score": 82,
        "system_sqqq_score": 35,
        "market_state": "只观察 TQQQ",
        "actual_action": "手动买入",
        "entry_price": 100.0,
        "exit_price": 105.0,
        "position_size": 0.3,
        "return_pct": 0.05,
        "followed_signal": True,
        "mistake_type": "",
        "notes": "test",
    }


def test_add_update_load_and_stats() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = str(Path(temp_dir) / "journal.db")
        with patch("src.trade_journal.get_connection", side_effect=lambda: get_connection(db_path)), patch(
            "src.trade_journal.init_database", side_effect=lambda: init_database(db_path)
        ):

            record_id = add_trade_record(_sample_record())
            assert record_id > 0

            updated = update_trade_record(record_id, {"return_pct": 0.08, "mistake_type": "追高"})
            assert updated is True

            add_trade_record(_sample_record(symbol="SQQQ") | {"followed_signal": False, "return_pct": -0.02, "mistake_type": "逆势交易"})

            records_df = load_trade_records()
            assert len(records_df) == 2

            filtered_df = load_trade_records(symbol="SQQQ")
            assert len(filtered_df) == 1
            assert filtered_df.iloc[0]["symbol"] == "SQQQ"

            stats = calculate_trade_journal_stats(records_df)
            assert stats["total_trades"] == 2
            assert stats["win_rate"] == 0.5
            assert stats["followed_signal_ratio"] == 0.5
            assert stats["mistake_type_counts"].get("追高") == 1


def test_empty_stats_do_not_crash() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = str(Path(temp_dir) / "journal.db")
        with patch("src.trade_journal.get_connection", side_effect=lambda: get_connection(db_path)), patch(
            "src.trade_journal.init_database", side_effect=lambda: init_database(db_path)
        ):
            stats = calculate_trade_journal_stats(load_trade_records(symbol="NO_SUCH_SYMBOL"))

    assert stats["total_trades"] == 0
    assert stats["mistake_type_counts"] == {}


def main() -> None:
    test_add_update_load_and_stats()
    test_empty_stats_do_not_crash()
    print("test_trade_journal passed")


if __name__ == "__main__":
    main()