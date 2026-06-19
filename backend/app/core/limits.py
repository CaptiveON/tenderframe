"""Abuse & cost controls (SECURITY_AUDIT F1, F2).

In-process, in-memory by design: this matches the single-instance free-tier
deployment and avoids a second datastore (no Redis, per the brief). For a
multi-instance deploy, swap the two stores for a shared backend (e.g. Redis)
without changing any call site.

- per-key sliding-window rate limit  -> RateLimited (429)
- global per-day answer counter (the LLM spend ceiling) -> DailyCapReached (429)
"""
import threading
import time
from collections import defaultdict, deque
from datetime import date, datetime, timezone

from fastapi import Request, status

from app.core.config import settings
from app.exceptions.base import AppException


class RateLimited(AppException):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    detail = "Too many requests. Please slow down and try again shortly."


class DailyCapReached(AppException):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    detail = "The demo's daily question limit has been reached. Please try again tomorrow."


def client_ip(request: Request) -> str:
    """Best-effort client IP, honouring a single proxy hop (X-Forwarded-For)."""
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class _SlidingWindow:
    def __init__(self) -> None:
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, limit: int, window_s: int) -> None:
        now = time.monotonic()
        with self._lock:
            dq = self._hits[key]
            while dq and dq[0] <= now - window_s:
                dq.popleft()
            if len(dq) >= limit:
                raise RateLimited()
            dq.append(now)


class _DailyCounter:
    def __init__(self) -> None:
        self._day = date.today()
        self.count = 0
        self._lock = threading.Lock()

    def consume(self, limit: int) -> None:
        with self._lock:
            today = date.today()
            if today != self._day:
                self._day, self.count = today, 0
            if self.count >= limit:
                raise DailyCapReached()
            self.count += 1


_rate = _SlidingWindow()
_daily = _DailyCounter()


def rate_limit(key: str, limit: int, window_s: int) -> None:
    """Raise RateLimited if `key` exceeds `limit` hits per `window_s` seconds."""
    _rate.check(key, limit, window_s)


def consume_answer_quota() -> None:
    """Count one model-calling answer against the global daily ceiling (F1)."""
    _daily.consume(settings.DAILY_ANSWER_CAP)


def usage_snapshot() -> dict:
    return {
        "answers_today": _daily.count,
        "daily_cap": settings.DAILY_ANSWER_CAP,
        "as_of": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
