"""Rate limiting and daily token quotas, keyed by API key.

Two backends with the same interface:
  - RateLimiter      — in-memory (single process; default; deterministic in tests)
  - RedisRateLimiter — shared across workers/hosts (set REDIS_URL)

get_rate_limiter() picks Redis when REDIS_URL is set and reachable, else falls
back to in-memory (logging a warning).
"""

from __future__ import annotations

import logging
import os
import threading
from collections import defaultdict, deque

logger = logging.getLogger("preserve.api")


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


class RedisRateLimiter:
    """Shared rate limiting backed by Redis, for multi-worker / multi-host deploys.

    Same interface as RateLimiter. Requests use a sliding-window log (sorted set);
    token quotas use a per-UTC-day counter that expires automatically.
    """

    def __init__(self, client):
        import time as _time
        self._now = _time.time
        self._r = client

    def check_request(self, key: str, rpm: int) -> None:
        if rpm <= 0:
            return
        now = self._now()
        zkey = f"preserve:rl:req:{key}"
        pipe = self._r.pipeline()
        pipe.zremrangebyscore(zkey, 0, now - 60.0)
        pipe.zcard(zkey)
        _, count = pipe.execute()
        if count >= rpm:
            oldest = self._r.zrange(zkey, 0, 0, withscores=True)
            retry = 1
            if oldest:
                retry = max(1, int(oldest[0][1] + 60.0 - now))
            raise RateLimitExceeded(f"Rate limit of {rpm} requests/min exceeded.", retry)
        pipe = self._r.pipeline()
        pipe.zadd(zkey, {f"{now}": now})
        pipe.expire(zkey, 60)
        pipe.execute()

    def check_token_quota(self, key: str, daily_quota: int) -> None:
        if daily_quota <= 0:
            return
        day = int(self._now() // 86400)
        used = self._r.get(f"preserve:rl:tok:{key}:{day}")
        if used is not None and int(used) >= daily_quota:
            raise RateLimitExceeded(
                f"Daily token quota of {daily_quota} reached.",
                self._secs_until_utc_midnight(),
            )

    def add_tokens(self, key: str, tokens: int) -> int:
        if tokens <= 0:
            return 0
        day = int(self._now() // 86400)
        tkey = f"preserve:rl:tok:{key}:{day}"
        pipe = self._r.pipeline()
        pipe.incrby(tkey, tokens)
        pipe.expire(tkey, self._secs_until_utc_midnight() + 60)
        total, _ = pipe.execute()
        return int(total)

    def _secs_until_utc_midnight(self) -> int:
        now = self._now()
        return max(1, int((int(now // 86400) + 1) * 86400 - now))


def get_rate_limiter():
    """Return a Redis-backed limiter if REDIS_URL is set and reachable, else in-memory."""
    url = os.environ.get("REDIS_URL")
    if url:
        try:
            import redis
            client = redis.Redis.from_url(url, decode_responses=True)
            client.ping()
            logger.info("Rate limiting backed by Redis at %s", url)
            return RedisRateLimiter(client)
        except Exception as e:
            logger.warning("Redis unavailable (%s); using in-memory rate limiting.", e)
    return RateLimiter()
