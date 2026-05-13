"""SQLite database module for storing market data, indicators, and scores."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd

from config.settings import DATABASE_PATH
from src.utils import setup_logger

logger = setup_logger("database")


def get_connection(db_path: str | None = None):
    """
    Get SQLite database connection.
    
    If db_path is None, use DATABASE_PATH from settings.py.
    
    Args:
        db_path: Database file path, default None
        
    Returns:
        sqlite3.Connection object
    """
    if db_path is None:
        db_path = DATABASE_PATH
    
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        logger.error(f"Database connection failed: {str(e)}")
        raise


def init_database(db_path: str | None = None) -> None:
    """
    Initialize database with required tables.
    """
    if db_path is None:
        db_path = DATABASE_PATH
    
    # Ensure data directory exists
    db_dir = Path(db_path).parent
    db_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        conn = get_connection(db_path)
        cursor = conn.cursor()
        
        # price_daily table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS price_daily (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                date TEXT NOT NULL,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                adj_close REAL,
                volume REAL,
                created_at TEXT,
                updated_at TEXT,
                UNIQUE(symbol, date)
            )
        """)
        
        # price_intraday table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS price_intraday (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                datetime TEXT NOT NULL,
                interval TEXT NOT NULL,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume REAL,
                created_at TEXT,
                UNIQUE(symbol, datetime, interval)
            )
        """)
        
        # indicator_daily table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS indicator_daily (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                date TEXT NOT NULL,
                ma5 REAL,
                ma20 REAL,
                ma50 REAL,
                ma200 REAL,
                ma20_slope REAL,
                ma50_slope REAL,
                ma20_slope_pct REAL,
                ma50_slope_pct REAL,
                atr14 REAL,
                daily_return REAL,
                volume_ratio REAL,
                created_at TEXT,
                UNIQUE(symbol, date)
            )
        """)
        
        # market_score table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS market_score (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                datetime TEXT NOT NULL,
                tqqq_base_score REAL,
                sqqq_base_score REAL,
                risk_deduction REAL,
                tqqq_final_score REAL,
                sqqq_final_score REAL,
                market_state TEXT,
                summary TEXT,
                created_at TEXT
            )
        """)
        
        # signal_log table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS signal_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                datetime TEXT NOT NULL,
                signal_type TEXT,
                score REAL,
                reason TEXT,
                created_at TEXT
            )
        """)
        
        conn.commit()
        logger.info(f"Database initialized: {db_path}")
        
    except sqlite3.Error as e:
        logger.error(f"Failed to initialize database: {str(e)}")
        raise
    finally:
        if conn:
            conn.close()


def save_daily_prices(symbol: str, df: pd.DataFrame, db_path: str | None = None) -> int:
    """Save daily prices to database."""
    if df is None or df.empty:
        logger.warning(f"{symbol} daily price data is empty")
        return 0
    
    if db_path is None:
        db_path = DATABASE_PATH
    
    try:
        conn = get_connection(db_path)
        cursor = conn.cursor()
        
        now = datetime.now().isoformat()
        count = 0
        
        for idx, row in df.iterrows():
            date_str = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)
            
            cursor.execute("""
                INSERT OR REPLACE INTO price_daily 
                (symbol, date, open, high, low, close, adj_close, volume, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                symbol,
                date_str,
                float(row.get("Open", 0)) if "Open" in row else None,
                float(row.get("High", 0)) if "High" in row else None,
                float(row.get("Low", 0)) if "Low" in row else None,
                float(row.get("Close", 0)) if "Close" in row else None,
                float(row.get("Adj Close", 0)) if "Adj Close" in row else None,
                float(row.get("Volume", 0)) if "Volume" in row else None,
                now,
                now
            ))
            count += 1
        
        conn.commit()
        logger.info(f"{symbol} daily prices saved: {count} records")
        return count
        
    except sqlite3.Error as e:
        logger.error(f"Failed to save {symbol} daily prices: {str(e)}")
        return 0
    finally:
        if conn:
            conn.close()


def save_intraday_prices(
    symbol: str,
    df: pd.DataFrame,
    interval: str = "5m",
    db_path: str | None = None
) -> int:
    """Save intraday prices to database."""
    if df is None or df.empty:
        logger.warning(f"{symbol} {interval} intraday data is empty")
        return 0
    
    if db_path is None:
        db_path = DATABASE_PATH
    
    try:
        conn = get_connection(db_path)
        cursor = conn.cursor()
        
        now = datetime.now().isoformat()
        count = 0
        
        for idx, row in df.iterrows():
            datetime_str = idx.strftime("%Y-%m-%d %H:%M:%S") if hasattr(idx, "strftime") else str(idx)
            
            cursor.execute("""
                INSERT OR REPLACE INTO price_intraday
                (symbol, datetime, interval, open, high, low, close, volume, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                symbol,
                datetime_str,
                interval,
                float(row.get("Open", 0)) if "Open" in row else None,
                float(row.get("High", 0)) if "High" in row else None,
                float(row.get("Low", 0)) if "Low" in row else None,
                float(row.get("Close", 0)) if "Close" in row else None,
                float(row.get("Volume", 0)) if "Volume" in row else None,
                now
            ))
            count += 1
        
        conn.commit()
        logger.info(f"{symbol} {interval} intraday saved: {count} records")
        return count
        
    except sqlite3.Error as e:
        logger.error(f"Failed to save {symbol} intraday: {str(e)}")
        return 0
    finally:
        if conn:
            conn.close()


def save_indicator_daily(
    symbol: str,
    df: pd.DataFrame,
    db_path: str | None = None
) -> int:
    """Save daily indicators to database."""
    if df is None or df.empty:
        logger.warning(f"{symbol} indicator data is empty")
        return 0
    
    if db_path is None:
        db_path = DATABASE_PATH
    
    try:
        conn = get_connection(db_path)
        cursor = conn.cursor()
        
        now = datetime.now().isoformat()
        count = 0
        
        for idx, row in df.iterrows():
            date_str = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)
            
            cursor.execute("""
                INSERT OR REPLACE INTO indicator_daily
                (symbol, date, ma5, ma20, ma50, ma200, ma20_slope, ma50_slope,
                 ma20_slope_pct, ma50_slope_pct, atr14, daily_return, volume_ratio, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                symbol,
                date_str,
                float(row.get("ma5", 0)) if "ma5" in row else None,
                float(row.get("ma20", 0)) if "ma20" in row else None,
                float(row.get("ma50", 0)) if "ma50" in row else None,
                float(row.get("ma200", 0)) if "ma200" in row else None,
                float(row.get("ma20_slope", 0)) if "ma20_slope" in row else None,
                float(row.get("ma50_slope", 0)) if "ma50_slope" in row else None,
                float(row.get("ma20_slope_pct", 0)) if "ma20_slope_pct" in row else None,
                float(row.get("ma50_slope_pct", 0)) if "ma50_slope_pct" in row else None,
                float(row.get("atr14", 0)) if "atr14" in row else None,
                float(row.get("daily_return", 0)) if "daily_return" in row else None,
                float(row.get("volume_ratio", 0)) if "volume_ratio" in row else None,
                now
            ))
            count += 1
        
        conn.commit()
        logger.info(f"{symbol} indicators saved: {count} records")
        return count
        
    except sqlite3.Error as e:
        logger.error(f"Failed to save {symbol} indicators: {str(e)}")
        return 0
    finally:
        if conn:
            conn.close()


def save_market_score(
    score_result: dict,
    db_path: str | None = None
) -> int:
    """Save market score to database."""
    if not score_result:
        logger.warning("Score result is empty")
        return 0
    
    if db_path is None:
        db_path = DATABASE_PATH
    
    try:
        conn = get_connection(db_path)
        cursor = conn.cursor()
        
        now = datetime.now().isoformat()
        
        cursor.execute("""
            INSERT INTO market_score
            (datetime, tqqq_base_score, sqqq_base_score, risk_deduction,
             tqqq_final_score, sqqq_final_score, market_state, summary, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            score_result.get("datetime", now),
            float(score_result.get("tqqq_base_score", 0)),
            float(score_result.get("sqqq_base_score", 0)),
            float(score_result.get("risk_deduction", 0)),
            float(score_result.get("tqqq_final_score", 0)),
            float(score_result.get("sqqq_final_score", 0)),
            score_result.get("market_state", ""),
            score_result.get("summary", ""),
            now
        ))
        
        conn.commit()
        logger.info("Market score saved")
        return 1
        
    except sqlite3.Error as e:
        logger.error(f"Failed to save market score: {str(e)}")
        return 0
    finally:
        if conn:
            conn.close()


def save_signal_logs(
    logs: list[dict],
    db_path: str | None = None
) -> int:
    """Save signal logs to database."""
    if not logs:
        logger.warning("Logs are empty")
        return 0
    
    if db_path is None:
        db_path = DATABASE_PATH
    
    try:
        conn = get_connection(db_path)
        cursor = conn.cursor()
        
        now = datetime.now().isoformat()
        count = 0
        
        for log in logs:
            cursor.execute("""
                INSERT INTO signal_log
                (datetime, signal_type, score, reason, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (
                log.get("datetime", now),
                log.get("signal_type", ""),
                float(log.get("score", 0)),
                log.get("reason", ""),
                now
            ))
            count += 1
        
        conn.commit()
        logger.info(f"Signal logs saved: {count} records")
        return count
        
    except sqlite3.Error as e:
        logger.error(f"Failed to save signal logs: {str(e)}")
        return 0
    finally:
        if conn:
            conn.close()


def load_recent_market_scores(limit: int = 100, db_path: str | None = None) -> pd.DataFrame:
    """Load recent market scores from database."""
    if db_path is None:
        db_path = DATABASE_PATH
    
    try:
        conn = get_connection(db_path)
        
        query = """
            SELECT 
                datetime,
                tqqq_base_score,
                sqqq_base_score,
                risk_deduction,
                tqqq_final_score,
                sqqq_final_score,
                market_state,
                summary,
                created_at
            FROM market_score
            ORDER BY datetime DESC
            LIMIT ?
        """
        
        df = pd.read_sql_query(query, conn, params=(limit,))
        logger.info(f"Loaded {len(df)} market score records")
        return df
        
    except sqlite3.Error as e:
        logger.error(f"Failed to load market scores: {str(e)}")
        return pd.DataFrame()
    finally:
        if conn:
            conn.close()


def load_daily_prices(
    symbol: str,
    limit: int = 300,
    db_path: str | None = None
) -> pd.DataFrame:
    """Load daily prices from database."""
    if db_path is None:
        db_path = DATABASE_PATH
    
    try:
        conn = get_connection(db_path)
        
        query = """
            SELECT 
                date,
                open,
                high,
                low,
                close,
                adj_close,
                volume
            FROM price_daily
            WHERE symbol = ?
            ORDER BY date DESC
            LIMIT ?
        """
        
        df = pd.read_sql_query(query, conn, params=(symbol, limit))
        logger.info(f"Loaded {len(df)} {symbol} daily price records")
        return df
        
    except sqlite3.Error as e:
        logger.error(f"Failed to load {symbol} daily prices: {str(e)}")
        return pd.DataFrame()
    finally:
        if conn:
            conn.close()


def load_indicator_daily(
    symbol: str,
    limit: int = 300,
    db_path: str | None = None
) -> pd.DataFrame:
    """Load daily indicators from database."""
    if db_path is None:
        db_path = DATABASE_PATH
    
    try:
        conn = get_connection(db_path)
        
        query = """
            SELECT 
                date,
                ma5,
                ma20,
                ma50,
                ma200,
                ma20_slope,
                ma50_slope,
                atr14,
                daily_return,
                volume_ratio
            FROM indicator_daily
            WHERE symbol = ?
            ORDER BY date DESC
            LIMIT ?
        """
        
        df = pd.read_sql_query(query, conn, params=(symbol, limit))
        logger.info(f"Loaded {len(df)} {symbol} indicator records")
        return df
        
    except sqlite3.Error as e:
        logger.error(f"Failed to load {symbol} indicators: {str(e)}")
        return pd.DataFrame()
    finally:
        if conn:
            conn.close()


def init_backtest_tables(db_path: str | None = None) -> None:
    """Initialize backtest tables."""
    if db_path is None:
        db_path = DATABASE_PATH
    
    try:
        conn = get_connection(db_path)
        cursor = conn.cursor()
        
        # Backtest scores table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS backtest_scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                tqqq_base_score REAL,
                sqqq_base_score REAL,
                risk_score REAL,
                tqqq_final_score REAL,
                sqqq_final_score REAL,
                market_state TEXT,
                created_at TEXT,
                UNIQUE(date)
            )
        """)
        
        # Backtest signals table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS backtest_signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                signal TEXT,
                tqqq_final_score REAL,
                sqqq_final_score REAL,
                market_state TEXT,
                created_at TEXT,
                UNIQUE(date)
            )
        """)
        
        # Backtest trades table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS backtest_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entry_date TEXT NOT NULL,
                exit_date TEXT NOT NULL,
                symbol TEXT NOT NULL,
                entry_price REAL,
                exit_price REAL,
                return_pct REAL,
                exit_reason TEXT,
                holding_days INTEGER,
                created_at TEXT
            )
        """)
        
        # Backtest metrics table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS backtest_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                backtest_date TEXT NOT NULL,
                start_date TEXT,
                end_date TEXT,
                total_trades INTEGER,
                win_count INTEGER,
                loss_count INTEGER,
                win_rate REAL,
                avg_win REAL,
                avg_loss REAL,
                profit_factor REAL,
                avg_return REAL,
                max_drawdown REAL,
                consecutive_losses INTEGER,
                avg_holding_days REAL,
                cumulative_return REAL,
                created_at TEXT,
                UNIQUE(backtest_date)
            )
        """)
        
        conn.commit()
        logger.info("Backtest tables initialized")
        
    except sqlite3.Error as e:
        logger.error(f"Failed to initialize backtest tables: {str(e)}")
    finally:
        if conn:
            conn.close()


def save_backtest_scores(
    df_scores: pd.DataFrame,
    db_path: str | None = None
) -> int:
    """Save backtest scores."""
    if df_scores is None or df_scores.empty:
        logger.warning("Scores data is empty")
        return 0
    
    if db_path is None:
        db_path = DATABASE_PATH
    
    try:
        conn = get_connection(db_path)
        cursor = conn.cursor()
        
        now = datetime.now().isoformat()
        count = 0
        
        for _, row in df_scores.iterrows():
            cursor.execute("""
                INSERT OR REPLACE INTO backtest_scores
                (date, tqqq_base_score, sqqq_base_score, risk_score, 
                 tqqq_final_score, sqqq_final_score, market_state, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                str(row.get("date", "")),
                float(row.get("tqqq_base_score", 0)),
                float(row.get("sqqq_base_score", 0)),
                float(row.get("risk_score", 0)),
                float(row.get("tqqq_final_score", 0)),
                float(row.get("sqqq_final_score", 0)),
                str(row.get("market_state", "")),
                now
            ))
            count += 1
        
        conn.commit()
        logger.info(f"Saved {count} backtest score records")
        return count
        
    except sqlite3.Error as e:
        logger.error(f"Failed to save backtest scores: {str(e)}")
        return 0
    finally:
        if conn:
            conn.close()


def save_backtest_signals(
    df_signals: pd.DataFrame,
    db_path: str | None = None
) -> int:
    """Save backtest signals."""
    if df_signals is None or df_signals.empty:
        logger.warning("Signals data is empty")
        return 0
    
    if db_path is None:
        db_path = DATABASE_PATH
    
    try:
        conn = get_connection(db_path)
        cursor = conn.cursor()
        
        now = datetime.now().isoformat()
        count = 0
        
        for _, row in df_signals.iterrows():
            cursor.execute("""
                INSERT OR REPLACE INTO backtest_signals
                (date, signal, tqqq_final_score, sqqq_final_score, market_state, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                str(row.get("date", "")),
                str(row.get("signal", "")),
                float(row.get("tqqq_final_score", 0)),
                float(row.get("sqqq_final_score", 0)),
                str(row.get("market_state", "")),
                now
            ))
            count += 1
        
        conn.commit()
        logger.info(f"Saved {count} backtest signal records")
        return count
        
    except sqlite3.Error as e:
        logger.error(f"Failed to save backtest signals: {str(e)}")
        return 0
    finally:
        if conn:
            conn.close()


def save_backtest_trades(
    df_trades: pd.DataFrame,
    db_path: str | None = None
) -> int:
    """Save backtest trades."""
    if df_trades is None or df_trades.empty:
        logger.warning("Trades data is empty")
        return 0
    
    if db_path is None:
        db_path = DATABASE_PATH
    
    try:
        conn = get_connection(db_path)
        cursor = conn.cursor()
        
        now = datetime.now().isoformat()
        count = 0
        
        for _, row in df_trades.iterrows():
            cursor.execute("""
                INSERT INTO backtest_trades
                (entry_date, exit_date, symbol, entry_price, exit_price, 
                 return_pct, exit_reason, holding_days, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                str(row.get("entry_date", "")),
                str(row.get("exit_date", "")),
                str(row.get("symbol", "")),
                float(row.get("entry_price", 0)),
                float(row.get("exit_price", 0)),
                float(row.get("return_pct", 0)),
                str(row.get("exit_reason", "")),
                int(row.get("holding_days", 0)),
                now
            ))
            count += 1
        
        conn.commit()
        logger.info(f"Saved {count} backtest trade records")
        return count
        
    except sqlite3.Error as e:
        logger.error(f"Failed to save backtest trades: {str(e)}")
        return 0
    finally:
        if conn:
            conn.close()


def save_backtest_metrics(
    metrics: dict,
    start_date: str | None = None,
    end_date: str | None = None,
    db_path: str | None = None
) -> bool:
    """Save backtest metrics."""
    if not metrics:
        logger.warning("Metrics data is empty")
        return False
    
    if db_path is None:
        db_path = DATABASE_PATH
    
    try:
        conn = get_connection(db_path)
        cursor = conn.cursor()
        
        now = datetime.now().isoformat()
        backtest_date = now.split("T")[0]
        
        cursor.execute("""
            INSERT OR REPLACE INTO backtest_metrics
            (backtest_date, start_date, end_date, total_trades, win_count, loss_count,
             win_rate, avg_win, avg_loss, profit_factor, avg_return, max_drawdown,
             consecutive_losses, avg_holding_days, cumulative_return, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            backtest_date,
            start_date,
            end_date,
            metrics.get("total_trades", 0),
            metrics.get("win_count", 0),
            metrics.get("loss_count", 0),
            metrics.get("win_rate", 0),
            metrics.get("avg_win", 0),
            metrics.get("avg_loss", 0),
            metrics.get("profit_factor", 0),
            metrics.get("avg_return", 0),
            metrics.get("max_drawdown", 0),
            metrics.get("consecutive_losses", 0),
            metrics.get("avg_holding_days", 0),
            metrics.get("cumulative_return", 0),
            now
        ))
        
        conn.commit()
        logger.info("Saved backtest metrics")
        return True
        
    except sqlite3.Error as e:
        logger.error(f"Failed to save backtest metrics: {str(e)}")
        return False
    finally:
        if conn:
            conn.close()


def load_latest_backtest_metrics(db_path: str | None = None) -> dict:
    """Load latest backtest metrics."""
    if db_path is None:
        db_path = DATABASE_PATH
    
    try:
        conn = get_connection(db_path)
        
        query = """
            SELECT 
                backtest_date,
                start_date,
                end_date,
                total_trades,
                win_count,
                loss_count,
                win_rate,
                avg_win,
                avg_loss,
                profit_factor,
                avg_return,
                max_drawdown,
                consecutive_losses,
                avg_holding_days,
                cumulative_return,
                created_at
            FROM backtest_metrics
            ORDER BY created_at DESC
            LIMIT 1
        """
        
        cursor = conn.cursor()
        cursor.execute(query)
        row = cursor.fetchone()
        
        if row:
            return dict(row)
        return {}
        
    except sqlite3.Error as e:
        logger.error(f"Failed to load backtest metrics: {str(e)}")
        return {}
    finally:
        if conn:
            conn.close()


def load_backtest_trades(
    limit: int = 100,
    db_path: str | None = None
) -> pd.DataFrame:
    """Load recent backtest trades."""
    if db_path is None:
        db_path = DATABASE_PATH
    
    try:
        conn = get_connection(db_path)
        
        query = """
            SELECT 
                entry_date,
                exit_date,
                symbol,
                entry_price,
                exit_price,
                return_pct,
                exit_reason,
                holding_days,
                created_at
            FROM backtest_trades
            ORDER BY entry_date DESC
            LIMIT ?
        """
        
        df = pd.read_sql_query(query, conn, params=(limit,))
        logger.info(f"Loaded {len(df)} backtest trade records")
        return df
        
    except sqlite3.Error as e:
        logger.error(f"Failed to load backtest trades: {str(e)}")
        return pd.DataFrame()
    finally:
        if conn:
            conn.close()
