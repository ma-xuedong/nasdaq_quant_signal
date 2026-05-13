"""Rate limiting and retry helpers for external API calls."""

from __future__ import annotations

import time
from collections.abc import Callable
from functools import wraps
from typing import Any

from src.utils import setup_logger

logger = setup_logger("rate_limiter")


def sleep_between_requests(seconds: float = 0.8) -> None:
    """每个请求之间等待一段时间，降低限流风险。"""
    if seconds <= 0:
        return
    time.sleep(seconds)


def retry_on_failure(max_retries: int = 3, delay_seconds: float = 2.0):
    """简单重试装饰器（指数退避）。"""

    def decorator(func: Callable[..., Any]):
        @wraps(func)
        def wrapper(*args, **kwargs):
            attempt = 0
            while True:
                try:
                    result = func(*args, **kwargs)
                    if result is not None:
                        return result
                    raise ValueError("empty result")
                except Exception as exc:
                    attempt += 1
                    if attempt > max_retries:
                        logger.warning(
                            "重试失败：%s，函数=%s", str(exc), func.__name__
                        )
                        return None
                    wait_seconds = delay_seconds * (2 ** (attempt - 1))
                    logger.warning(
                        "请求失败，第 %s/%s 次重试，%s 秒后重试，函数=%s，错误=%s",
                        attempt,
                        max_retries,
                        wait_seconds,
                        func.__name__,
                        str(exc),
                    )
                    time.sleep(wait_seconds)

        return wrapper

    return decorator
