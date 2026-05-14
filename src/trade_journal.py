"""Trade journal and manual review helpers."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any

import pandas as pd

from src.database import get_connection, init_database
from src.utils import setup_logger

logger = setup_logger("trade_journal")


MISTAKE_TYPES = [
    "追高",
    "恐慌卖出",
    "没有止损",
    "没有执行系统",
    "逆势交易",
    "事件日前重仓",
    "数据质量不足仍交易",
    "仓位过大",
    "其他",
]


def _to_float(value: Any) -> float | None:
    if value in {None, ""}:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int_bool(value: Any) -> int | None:
    if value in {None, ""}:
        return None
    return 1 if bool(value) else 0


def _normalize_record(record: dict[str, Any]) -> dict[str, Any]:
    now = datetime.now().isoformat()
    datetime_value = record.get("datetime") or now
    datetime_str = pd.to_datetime(datetime_value, errors="coerce")
    if pd.isna(datetime_str):
        datetime_str = pd.to_datetime(now)

    return {
        "datetime": datetime_str.isoformat(),
        "symbol": str(record.get("symbol") or "").strip().upper(),
        "signal_type": str(record.get("signal_type") or "").strip(),
        "system_tqqq_score": _to_float(record.get("system_tqqq_score")),
        "system_sqqq_score": _to_float(record.get("system_sqqq_score")),
        "market_state": str(record.get("market_state") or "").strip(),
        "actual_action": str(record.get("actual_action") or "").strip(),
        "entry_price": _to_float(record.get("entry_price")),
        "exit_price": _to_float(record.get("exit_price")),
        "position_size": _to_float(record.get("position_size")),
        "return_pct": _to_float(record.get("return_pct")),
        "followed_signal": _to_int_bool(record.get("followed_signal")),
        "mistake_type": str(record.get("mistake_type") or "").strip(),
        "notes": str(record.get("notes") or "").strip(),
        "created_at": str(record.get("created_at") or now),
        "updated_at": now,
    }


def add_trade_record(record: dict) -> int:
    """新增交易记录，返回记录 id。"""
    init_database()
    normalized = _normalize_record(record)
    if not normalized["symbol"]:
        return 0

    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO trade_journal (
                datetime, symbol, signal_type, system_tqqq_score, system_sqqq_score,
                market_state, actual_action, entry_price, exit_price, position_size,
                return_pct, followed_signal, mistake_type, notes, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                normalized["datetime"],
                normalized["symbol"],
                normalized["signal_type"],
                normalized["system_tqqq_score"],
                normalized["system_sqqq_score"],
                normalized["market_state"],
                normalized["actual_action"],
                normalized["entry_price"],
                normalized["exit_price"],
                normalized["position_size"],
                normalized["return_pct"],
                normalized["followed_signal"],
                normalized["mistake_type"],
                normalized["notes"],
                normalized["created_at"],
                normalized["updated_at"],
            ),
        )
        conn.commit()
        return int(cursor.lastrowid or 0)
    except sqlite3.Error as exc:
        logger.error("新增交易记录失败: %s", str(exc))
        return 0
    finally:
        if conn:
            conn.close()


def update_trade_record(record_id: int, updates: dict) -> bool:
    """更新交易记录。"""
    if not record_id or not updates:
        return False

    init_database()
    normalized = _normalize_record(updates)
    allowed_fields = [
        "datetime",
        "symbol",
        "signal_type",
        "system_tqqq_score",
        "system_sqqq_score",
        "market_state",
        "actual_action",
        "entry_price",
        "exit_price",
        "position_size",
        "return_pct",
        "followed_signal",
        "mistake_type",
        "notes",
    ]
    set_fields = []
    params: list[Any] = []
    for field in allowed_fields:
        if field in updates:
            set_fields.append(f"{field} = ?")
            params.append(normalized[field])

    if not set_fields:
        return False

    params.append(datetime.now().isoformat())
    params.append(record_id)

    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE trade_journal SET {', '.join(set_fields)}, updated_at = ? WHERE id = ?",
            tuple(params),
        )
        conn.commit()
        return cursor.rowcount > 0
    except sqlite3.Error as exc:
        logger.error("更新交易记录失败: %s", str(exc))
        return False
    finally:
        if conn:
            conn.close()


def load_trade_records(
    start_date: str | None = None,
    end_date: str | None = None,
    symbol: str | None = None,
) -> pd.DataFrame:
    """读取交易记录。"""
    init_database()
    clauses = []
    params: list[Any] = []

    if start_date:
        parsed_start = pd.to_datetime(start_date, errors="coerce")
        if not pd.isna(parsed_start):
            clauses.append("datetime >= ?")
            params.append(parsed_start.isoformat())
    if end_date:
        parsed_end = pd.to_datetime(end_date, errors="coerce")
        if not pd.isna(parsed_end):
            end_dt = parsed_end.replace(hour=23, minute=59, second=59)
            clauses.append("datetime <= ?")
            params.append(end_dt.isoformat())
    if symbol:
        clauses.append("symbol = ?")
        params.append(symbol.strip().upper())

    query = "SELECT * FROM trade_journal"
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY datetime DESC, id DESC"

    conn = None
    try:
        conn = get_connection()
        df = pd.read_sql_query(query, conn, params=tuple(params))
        return df
    except sqlite3.Error as exc:
        logger.error("读取交易记录失败: %s", str(exc))
        return pd.DataFrame()
    finally:
        if conn:
            conn.close()


def calculate_trade_journal_stats(records_df: pd.DataFrame) -> dict:
    """计算人工交易复盘统计。"""
    if records_df is None or records_df.empty:
        return {
            "total_trades": 0,
            "win_rate": 0.0,
            "avg_return": 0.0,
            "followed_signal_ratio": 0.0,
            "avg_return_when_followed": 0.0,
            "avg_return_when_not_followed": 0.0,
            "mistake_type_counts": {},
        }

    working_df = records_df.copy()
    numeric_returns = pd.to_numeric(working_df.get("return_pct"), errors="coerce")
    followed = pd.to_numeric(working_df.get("followed_signal"), errors="coerce").fillna(0)
    valid_returns = numeric_returns.dropna()

    followed_returns = numeric_returns[followed == 1].dropna()
    not_followed_returns = numeric_returns[followed == 0].dropna()
    wins = valid_returns[valid_returns > 0]
    if "mistake_type" in working_df.columns:
        mistake_series = working_df["mistake_type"].fillna("")
        mistake_counts = working_df[mistake_series != ""]["mistake_type"].value_counts().to_dict()
    else:
        mistake_counts = {}

    return {
        "total_trades": int(len(working_df)),
        "win_rate": round(float(len(wins) / len(valid_returns)) if len(valid_returns) else 0.0, 4),
        "avg_return": round(float(valid_returns.mean()) if len(valid_returns) else 0.0, 4),
        "followed_signal_ratio": round(float((followed == 1).mean()) if len(working_df) else 0.0, 4),
        "avg_return_when_followed": round(float(followed_returns.mean()) if len(followed_returns) else 0.0, 4),
        "avg_return_when_not_followed": round(float(not_followed_returns.mean()) if len(not_followed_returns) else 0.0, 4),
        "mistake_type_counts": mistake_counts,
    }