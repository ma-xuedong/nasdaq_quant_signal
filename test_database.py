"""Isolated database tests for schema creation and persistence helpers."""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

import pandas as pd

import src.database as database_module
from src.database import (
    _ensure_table_columns,
    get_connection,
    init_backtest_tables,
    init_database,
    load_backtest_trades,
    save_backtest_trades,
    save_daily_prices,
)


def _temp_db_path() -> str:
    temp_dir = tempfile.TemporaryDirectory()
    path = str(Path(temp_dir.name) / "test_market_data.db")
    return temp_dir, path


def _table_columns(db_path: str, table_name: str) -> set[str]:
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(f"PRAGMA table_info({table_name})")
        return {row[1] for row in cursor.fetchall()}
    finally:
        conn.close()


def test_init_database_creates_required_tables() -> None:
    temp_dir, db_path = _temp_db_path()
    try:
        init_database(db_path)
        conn = sqlite3.connect(db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            table_names = {row[0] for row in cursor.fetchall()}
        finally:
            conn.close()

        assert "trade_journal" in table_names
        assert "cache_metadata" in table_names
    finally:
        temp_dir.cleanup()


def test_backtest_trade_fields_roundtrip() -> None:
    temp_dir, db_path = _temp_db_path()
    try:
        trades_df = pd.DataFrame(
            [
                {
                    "entry_date": "2025-01-02",
                    "exit_date": "2025-01-03",
                    "symbol": "TQQQ",
                    "entry_price": 10.0,
                    "exit_price": 10.5,
                    "return_pct": 0.05,
                    "exit_reason": "TimeOut",
                    "holding_days": 2,
                    "signal_score": 88.0,
                    "data_quality_level": "high",
                    "execution_mode": "close_to_next_open",
                }
            ]
        )

        init_backtest_tables(db_path)
        saved = save_backtest_trades(trades_df, db_path=db_path)
        loaded = load_backtest_trades(limit=10, db_path=db_path)

        assert saved == 1
        assert not loaded.empty
        assert "signal_score" in loaded.columns
        assert "data_quality_level" in loaded.columns
        assert "execution_mode" in loaded.columns
        assert float(loaded.iloc[0]["signal_score"]) == 88.0
        assert loaded.iloc[0]["data_quality_level"] == "high"
        assert loaded.iloc[0]["execution_mode"] == "close_to_next_open"
    finally:
        temp_dir.cleanup()


def test_ensure_table_columns_migrates_legacy_backtest_table() -> None:
    temp_dir, db_path = _temp_db_path()
    try:
        conn = sqlite3.connect(db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE backtest_trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entry_date TEXT NOT NULL,
                    exit_date TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    created_at TEXT
                )
                """
            )
            _ensure_table_columns(
                cursor,
                "backtest_trades",
                {
                    "signal_score": "REAL",
                    "data_quality_level": "TEXT",
                    "execution_mode": "TEXT",
                },
            )
            conn.commit()
        finally:
            conn.close()

        columns = _table_columns(db_path, "backtest_trades")
        assert "signal_score" in columns
        assert "data_quality_level" in columns
        assert "execution_mode" in columns
    finally:
        temp_dir.cleanup()


def test_init_database_migrates_trade_journal_columns() -> None:
    temp_dir, db_path = _temp_db_path()
    try:
        conn = sqlite3.connect(db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE trade_journal (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    datetime TEXT NOT NULL,
                    symbol TEXT NOT NULL
                )
                """
            )
            conn.commit()
        finally:
            conn.close()

        init_database(db_path)
        columns = _table_columns(db_path, "trade_journal")
        assert "signal_type" in columns
        assert "actual_action" in columns
        assert "updated_at" in columns
    finally:
        temp_dir.cleanup()


def test_empty_dataframe_save_does_not_pollute_real_database() -> None:
    temp_dir, db_path = _temp_db_path()
    try:
        empty_df = pd.DataFrame()
        with patch.object(database_module, "DATABASE_PATH", db_path):
            result = save_daily_prices("TEST", empty_df)

        assert result == 0
        assert not Path(db_path).exists()
    finally:
        temp_dir.cleanup()


def test_isolated_database_is_repeatable() -> None:
    temp_dir, db_path = _temp_db_path()
    try:
        init_database(db_path)
        init_database(db_path)
        init_backtest_tables(db_path)
        init_backtest_tables(db_path)

        conn = get_connection(db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='cache_metadata'")
            assert cursor.fetchone() is not None
        finally:
            conn.close()
    finally:
        temp_dir.cleanup()


def main() -> None:
    test_init_database_creates_required_tables()
    test_backtest_trade_fields_roundtrip()
    test_ensure_table_columns_migrates_legacy_backtest_table()
    test_init_database_migrates_trade_journal_columns()
    test_empty_dataframe_save_does_not_pollute_real_database()
    test_isolated_database_is_repeatable()
    print("test_database passed")


if __name__ == "__main__":
    main()
