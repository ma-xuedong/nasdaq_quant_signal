"""Unit tests for rate limiter and retry behavior."""

from unittest.mock import patch

from src.rate_limiter import retry_on_failure, sleep_between_requests


def test_retry_success_after_failures() -> None:
    state = {"count": 0}

    @retry_on_failure(max_retries=3, delay_seconds=0.01)
    def flaky() -> str:
        state["count"] += 1
        if state["count"] < 3:
            raise ValueError("temporary")
        return "ok"

    with patch("time.sleep", return_value=None):
        result = flaky()

    assert result == "ok"
    assert state["count"] == 3


def test_retry_exhausted_returns_none() -> None:
    @retry_on_failure(max_retries=2, delay_seconds=0.01)
    def always_fail():
        raise RuntimeError("boom")

    with patch("time.sleep", return_value=None):
        result = always_fail()

    assert result is None


def test_sleep_callable() -> None:
    with patch("time.sleep", return_value=None) as mocked_sleep:
        sleep_between_requests(0.8)
    mocked_sleep.assert_called_once()


def main() -> None:
    test_retry_success_after_failures()
    test_retry_exhausted_returns_none()
    test_sleep_callable()
    print("test_rate_limiter passed")


if __name__ == "__main__":
    main()
