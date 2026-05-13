"""Caching utilities backed by SQLite price tables and cache metadata."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

from config.settings import DATABASE_PATH
from src.data_provider.provider_factory import get_data_provider
from src.database import get_connection, save_daily_prices, save_intraday_prices
from src.utils import setup_logger

logger = setup_logger("cache")


def _now_utc() -> datetime:
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


def _iso_utc(dt: datetime) -> str:
    """Serialize datetime to ISO format in UTC."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _parse_datetime(value: str | None) -> datetime | None:
    """Parse ISO datetime string safely."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def init_cache_metadata_table(db_path: str | None = None) -> None:
    """Create cache metadata table if not exists."""
    if db_path is None:
        db_path = DATABASE_PATH

    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS cache_metadata (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cache_key TEXT NOT NULL UNIQUE,
                symbol TEXT NOT NULL,
                data_type TEXT NOT NULL,
                interval TEXT,
                provider TEXT,
                last_updated TEXT,
                expires_at TEXT,
                row_count INTEGER,
                status TEXT,
                message TEXT
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def build_cache_key(
    symbol: str,
    data_type: str,
    period: str | None = None,
    interval: str | None = None,
) -> str:
    """Generate a unique cache key."""
    parts = [symbol, data_type]
    if interval:
        parts.append(interval)
    if period:
        parts.append(period)
    return "_".join(parts)


def get_cache_metadata(cache_key: str, db_path: str | None = None) -> dict:
    if db_path is None:
        db_path = DATABASE_PATH

    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT cache_key, symbol, data_type, interval, provider, last_updated,
                   expires_at, row_count, status, message
            FROM cache_metadata
            WHERE cache_key = ?
            """,
            (cache_key,),
        )
        row = cursor.fetchone()
        return dict(row) if row else {}
    finally:
        conn.close()


def is_cache_fresh(cache_key: str, db_path: str | None = None) -> bool:
    """Check whether cache key is still fresh."""
    metadata = get_cache_metadata(cache_key, db_path=db_path)
    if not metadata:
        return False

    expires_at = _parse_datetime(metadata.get("expires_at"))
    if expires_at is None:
        return False
    return _now_utc() < expires_at


def update_cache_metadata(
    cache_key: str,
    symbol: str,
    data_type: str,
    provider: str,
    row_count: int,
    expires_at: str,
    status: str,
    message: str = "",
    interval: str | None = None,
    db_path: str | None = None,
) -> None:
    """Upsert cache metadata row."""
    if db_path is None:
        db_path = DATABASE_PATH

    now = _iso_utc(_now_utc())

    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO cache_metadata
            (cache_key, symbol, data_type, interval, provider, last_updated,
             expires_at, row_count, status, message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                symbol = excluded.symbol,
                data_type = excluded.data_type,
                interval = excluded.interval,
                provider = excluded.provider,
                last_updated = excluded.last_updated,
                expires_at = excluded.expires_at,
                row_count = excluded.row_count,
                status = excluded.status,
                message = excluded.message
            """,
            (
                cache_key,
                symbol,
                data_type,
                interval,
                provider,
                now,
                expires_at,
                row_count,
                status,
                message,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_cached_daily_data(symbol: str, db_path: str | None = None) -> pd.DataFrame:
    """Read daily data cache from DB (no freshness judgement)."""
    if db_path is None:
        db_path = DATABASE_PATH

    conn = get_connection(db_path)
    try:
        query = """
            SELECT date, open, high, low, close, adj_close, volume, symbol
            FROM price_daily
            WHERE symbol = ?
            ORDER BY date ASC
        """
        df = pd.read_sql_query(query, conn, params=(symbol,))
        if not df.empty:
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
        return df
    finally:
        conn.close()


def get_latest_cached_daily_data(symbol: str, db_path: str | None = None) -> pd.DataFrame:
    """Read latest available daily cache regardless of freshness."""
    if db_path is None:
        db_path = DATABASE_PATH

    conn = get_connection(db_path)
    try:
        query = """
            SELECT date, open, high, low, close, adj_close, volume, symbol
            FROM price_daily
            WHERE symbol = ?
            ORDER BY date ASC
        """
        df = pd.read_sql_query(query, conn, params=(symbol,))
        if not df.empty:
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
        return df
    finally:
        conn.close()


def get_cached_intraday_data(
    symbol: str,
    interval: str = "5m",
    db_path: str | None = None,
) -> pd.DataFrame:
    """Read intraday data cache from DB (no freshness judgement)."""
    if db_path is None:
        db_path = DATABASE_PATH

    conn = get_connection(db_path)
    try:
        query = """
            SELECT datetime, open, high, low, close, volume, symbol
            FROM price_intraday
            WHERE symbol = ? AND interval = ?
            ORDER BY datetime ASC
        """
        df = pd.read_sql_query(query, conn, params=(symbol, interval))
        if not df.empty:
            df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
        return df
    finally:
        conn.close()


def get_latest_cached_intraday_data(
    symbol: str,
    interval: str = "5m",
    db_path: str | None = None,
) -> pd.DataFrame:
    """Read latest available intraday cache regardless of freshness."""
    if db_path is None:
        db_path = DATABASE_PATH

    conn = get_connection(db_path)
    try:
        query = """
            SELECT datetime, open, high, low, close, volume, symbol
            FROM price_intraday
            WHERE symbol = ? AND interval = ?
            ORDER BY datetime ASC
        """
        df = pd.read_sql_query(query, conn, params=(symbol, interval))
        if not df.empty:
            df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
        return df
    finally:
        conn.close()


def get_daily_data_with_cache(
    symbol: str,
    period: str = "1y",
    max_age_minutes: int = 30,
    provider=None,
    db_path: str | None = None,
) -> tuple[pd.DataFrame, dict]:
    """Get daily data with strict freshness check and fallback support."""
    if db_path is None:
        db_path = DATABASE_PATH

    init_cache_metadata_table(db_path)

    cache_key = build_cache_key(symbol=symbol, data_type="daily", period=period)
    provider = provider or get_data_provider()
    metadata = get_cache_metadata(cache_key=cache_key, db_path=db_path)

    # 1) Only use cache when metadata says it is still fresh.
    cached_df = pd.DataFrame()
    if is_cache_fresh(cache_key=cache_key, db_path=db_path):
        cached_df = get_cached_daily_data(symbol=symbol, db_path=db_path)

    if not cached_df.empty:
        meta = {
            "symbol": symbol,
            "source": "cache",
            "is_fresh": True,
            "is_fallback": False,
            "cache_key": cache_key,
            "message": "使用缓存数据",
            "provider": provider.get_provider_name(),
            "last_updated": metadata.get("last_updated", ""),
        }
        return cached_df, meta

    # 2) Cache is not fresh (or missing metadata), request API.
    api_df = pd.DataFrame()
    api_error = ""
    try:
        api_df = provider.get_daily_data(symbol=symbol, period=period)
    except Exception as exc:
        api_error = str(exc)

    if not api_df.empty:
        save_daily_prices(symbol=symbol, df=api_df, db_path=db_path)
        expires_at = _iso_utc(_now_utc() + timedelta(minutes=max_age_minutes))
        now_iso = _iso_utc(_now_utc())
        update_cache_metadata(
            cache_key=cache_key,
            symbol=symbol,
            data_type="daily",
            interval=None,
            provider=provider.get_provider_name(),
            row_count=len(api_df),
            expires_at=expires_at,
            status="fresh",
            message="使用最新 API 数据",
            db_path=db_path,
        )
        return api_df, {
            "symbol": symbol,
            "source": "api",
            "is_fresh": True,
            "is_fallback": False,
            "cache_key": cache_key,
            "message": "使用最新 API 数据",
            "provider": provider.get_provider_name(),
            "last_updated": now_iso,
        }

    # 3) API failed or returned empty, fallback to latest stored cache.
    fallback_df = get_latest_cached_daily_data(symbol=symbol, db_path=db_path)
    if not fallback_df.empty:
        now_iso = _iso_utc(_now_utc())
        fallback_msg = "API 失败，使用最近缓存"
        if api_error:
            fallback_msg = f"API 失败，使用最近缓存。错误：{api_error}"
        update_cache_metadata(
            cache_key=cache_key,
            symbol=symbol,
            data_type="daily",
            interval=None,
            provider=provider.get_provider_name(),
            row_count=len(fallback_df),
            expires_at=now_iso,
            status="fallback",
            message=fallback_msg,
            db_path=db_path,
        )
        return fallback_df, {
            "symbol": symbol,
            "source": "fallback_cache",
            "is_fresh": False,
            "is_fallback": True,
            "cache_key": cache_key,
            "message": fallback_msg,
            "provider": provider.get_provider_name(),
            "last_updated": metadata.get("last_updated", now_iso),
        }

    # 4) API failed and no fallback cache exists.
    now_iso = _iso_utc(_now_utc())
    missing_msg = "API 失败，且无可用缓存。"
    if api_error:
        missing_msg = f"API 失败，且无可用缓存。错误：{api_error}"
    update_cache_metadata(
        cache_key=cache_key,
        symbol=symbol,
        data_type="daily",
        interval=None,
        provider=provider.get_provider_name(),
        row_count=0,
        expires_at=now_iso,
        status="failed",
        message=missing_msg,
        db_path=db_path,
    )
    return pd.DataFrame(), {
        "symbol": symbol,
        "source": "missing",
        "is_fresh": False,
        "is_fallback": False,
        "cache_key": cache_key,
        "message": missing_msg,
        "provider": provider.get_provider_name(),
        "last_updated": "",
    }


def get_intraday_data_with_cache(
    symbol: str,
    interval: str = "5m",
    period: str = "5d",
    max_age_minutes: int = 5,
    db_path: str | None = None,
) -> tuple[pd.DataFrame, dict]:
    """Get intraday data with cache-first strategy and fallback support."""
    if db_path is None:
        db_path = DATABASE_PATH

    init_cache_metadata_table(db_path)

    cache_key = build_cache_key(
        symbol=symbol,
        data_type="intraday",
        period=period,
        interval=interval,
    )
    provider = get_data_provider()
    metadata = get_cache_metadata(cache_key=cache_key, db_path=db_path)

    if is_cache_fresh(cache_key=cache_key, db_path=db_path):
        cached_df = get_cached_intraday_data(
            symbol=symbol,
            interval=interval,
            db_path=db_path,
        )
    else:
        cached_df = pd.DataFrame()

    if not cached_df.empty:
        return cached_df, {
            "symbol": symbol,
            "source": "cache",
            "is_fresh": True,
            "is_fallback": False,
            "message": "使用缓存数据",
            "provider": provider.get_provider_name(),
            "last_updated": metadata.get("last_updated", ""),
        }

    api_df = provider.get_intraday_data(symbol=symbol, interval=interval, period=period)
    if not api_df.empty:
        save_intraday_prices(symbol=symbol, df=api_df, interval=interval, db_path=db_path)
        expires_at = _iso_utc(_now_utc() + timedelta(minutes=max_age_minutes))
        now_iso = _iso_utc(_now_utc())
        update_cache_metadata(
            cache_key=cache_key,
            symbol=symbol,
            data_type="intraday",
            interval=interval,
            provider=provider.get_provider_name(),
            row_count=len(api_df),
            expires_at=expires_at,
            status="fresh",
            message="使用最新 API 数据",
            db_path=db_path,
        )
        return api_df, {
            "symbol": symbol,
            "source": "api",
            "is_fresh": True,
            "is_fallback": False,
            "message": "使用最新 API 数据",
            "provider": provider.get_provider_name(),
            "last_updated": now_iso,
        }

    fallback_df = get_latest_cached_intraday_data(symbol=symbol, interval=interval, db_path=db_path)
    if not fallback_df.empty:
        now_iso = _iso_utc(_now_utc())
        update_cache_metadata(
            cache_key=cache_key,
            symbol=symbol,
            data_type="intraday",
            interval=interval,
            provider=provider.get_provider_name(),
            row_count=len(fallback_df),
            expires_at=now_iso,
            status="fallback",
            message="API 失败，使用最近缓存",
            db_path=db_path,
        )
        return fallback_df, {
            "symbol": symbol,
            "source": "fallback_cache",
            "is_fresh": False,
            "is_fallback": True,
            "message": "API 失败，使用最近缓存",
            "provider": provider.get_provider_name(),
            "last_updated": metadata.get("last_updated", now_iso),
        }

    now_iso = _iso_utc(_now_utc())
    update_cache_metadata(
        cache_key=cache_key,
        symbol=symbol,
        data_type="intraday",
        interval=interval,
        provider=provider.get_provider_name(),
        row_count=0,
        expires_at=now_iso,
        status="failed",
        message="无可用数据",
        db_path=db_path,
    )
    return pd.DataFrame(), {
        "symbol": symbol,
        "source": "none",
        "is_fresh": False,
        "is_fallback": False,
        "message": "无可用数据",
        "provider": provider.get_provider_name(),
        "last_updated": "",
    }
