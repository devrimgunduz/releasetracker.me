"""A small in-memory sliding-window rate limiter.

Used to throttle login attempts by IP so the app has *some* protection out
of the box, independent of whether the operator has set up the optional
external fail2ban jail (deploy/fail2ban-*) described in the README.

Deliberately simple and in-process: this is correct for the deployment this
project ships (a single `uvicorn` worker process — see
deploy/release-radar-web.service). If the web service is ever scaled to
multiple worker processes, each process gets its own counters, which weakens
(but doesn't remove — each process still limits its own share of traffic)
the guarantee; at that point a shared store (e.g. the existing Postgres
database, or Redis) would be needed for a single global limit.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque


class SlidingWindowRateLimiter:
    def __init__(self, max_attempts: int, window_seconds: float):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._attempts: dict[str, deque[float]] = defaultdict(deque)

    def _prune(self, key: str, now: float) -> deque[float]:
        dq = self._attempts[key]
        while dq and now - dq[0] > self.window_seconds:
            dq.popleft()
        if not dq:
            self._attempts.pop(key, None)
            dq = self._attempts[key]
        return dq

    def allow(self, key: str) -> bool:
        """Record an attempt for `key` and return whether it's under the
        limit. Call once per attempt (e.g. once per login POST)."""
        now = time.monotonic()
        dq = self._prune(key, now)
        if len(dq) >= self.max_attempts:
            return False
        dq.append(now)
        return True

    def reset(self, key: str) -> None:
        """Clear a key's history — call on a successful login so a genuine
        user isn't penalized by earlier typos."""
        self._attempts.pop(key, None)
