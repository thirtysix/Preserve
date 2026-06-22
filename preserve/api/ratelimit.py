"""In-memory rate limiting and daily token quotas, keyed by API key.

Scaffold-grade: state lives in this process. For multi-worker / multi-host
deployments, back this with Redis (same interface). Time is injected so the
limiter is deterministic in tests.
"""

from __future__ import annotations

import threading
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self, time_fn=None):
        import time as _time
        self._now = time_fn or _time.time
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._tokens: dict[str, list] = {}  # key -> [day_index, tokens_used]
        self._lock = threading.Lock()

    def check_request(self, key: str, rpm: int) -> None:
        """Raise RateLimitExceeded if the key is over its requests-per-minute."""
        if rpm <= 0:
            return
        now = self._now()
        with self._lock:
            q = self._requests[key]
            cutoff = now - 60.0
            while q and q[0] < cutoff:
                q.popleft()
            if len(q) >= rpm:
                retry = max(1, int(q[0] + 60.0 - now))
                raise RateLimitExceeded(f"Rate limit of {rpm} requests/min exceeded.", retry)
            q.append(now)

    def check_token_quota(self, key: str, daily_quota: int) -> None:
        """Raise RateLimitExceeded if the key has already met its daily token quota."""
        if daily_quota <= 0:
            return
        day = int(self._now() // 86400)
        with self._lock:
            rec = self._tokens.get(key)
            if rec is None or rec[0] != day:
                self._tokens[key] = [day, 0]
                rec = self._tokens[key]
            if rec[1] >= daily_quota:
                raise RateLimitExceeded(
                    f"Daily token quota of {daily_quota} reached.", self._secs_until_utc_midnight()
                )

    def add_tokens(self, key: str, tokens: int) -> int:
        """Record upstream token usage; returns the new daily total."""
        if tokens <= 0:
            return self._tokens.get(key, [0, 0])[1]
        day = int(self._now() // 86400)
        with self._lock:
            rec = self._tokens.get(key)
            if rec is None or rec[0] != day:
                self._tokens[key] = [day, 0]
                rec = self._tokens[key]
            rec[1] += tokens
            return rec[1]

    def _secs_until_utc_midnight(self) -> int:
        now = self._now()
        return max(1, int((int(now // 86400) + 1) * 86400 - now))


class RateLimitExceeded(Exception):
    def __init__(self, message: str, retry_after: int):
        super().__init__(message)
        self.retry_after = retry_after
