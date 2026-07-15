"""A polite, resilient HTTP session for TSETMC.

Encapsulates every anti-fragility rule the research surfaced:
  * a real browser User-Agent + header set (default python UA gets blocked),
  * a token-bucket rate limiter + concurrency cap (hammering triggers soft blocks),
  * retry-with-backoff on transient 5xx / network errors,
  * detection of TSETMC's Persian "security block" page and non-JSON error bodies,
    surfaced as typed exceptions so the poller's circuit breaker can react.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import aiohttp

from ..config import Config

# Blocked-response signatures (body is HTML/plain text, not JSON).
_BLOCK_MARKERS = (
    "مسدود",  # "...has been blocked..."
    "General Error Detected",
    "دسترسی شما",  # "your access..."
)

_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9,fa-IR;q=0.8,fa;q=0.7",
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "DNT": "1",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:100.0) Gecko/20100101 Firefox/100.0"
    ),
}


class TsetmcError(RuntimeError):
    """Base for all fetch failures."""


class TsetmcBlocked(TsetmcError):
    """TSETMC returned its security-block page or a non-JSON error body.
    Usually means we are being rate-limited or the IP is geo-blocked."""


class TsetmcUnreachable(TsetmcError):
    """Network/timeout/5xx failure after all retries."""


class _TokenBucket:
    """Simple async token bucket: at most `rate` requests per second, smoothed."""

    def __init__(self, rate_per_sec: float):
        self._min_interval = 1.0 / rate_per_sec if rate_per_sec > 0 else 0.0
        self._next_allowed = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        if self._min_interval <= 0:
            return
        async with self._lock:
            now = time.monotonic()
            wait = self._next_allowed - now
            if wait > 0:
                await asyncio.sleep(wait)
                now = time.monotonic()
            self._next_allowed = now + self._min_interval


def looks_blocked(body: str) -> bool:
    return any(m in body for m in _BLOCK_MARKERS)


class Session:
    def __init__(self, cfg: Config):
        self._cfg = cfg
        self._bucket = _TokenBucket(cfg.req_per_sec)
        self._sem = asyncio.Semaphore(max(1, cfg.max_concurrency))
        self._session: aiohttp.ClientSession | None = None

    async def _ensure(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self._cfg.timeout_s)
            self._session = aiohttp.ClientSession(headers=_HEADERS, timeout=timeout)
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def get_json(self, url: str) -> dict[str, Any]:
        """GET a cdn.tsetmc.com/api JSON endpoint, unwrap TSETMC quirks, raise
        TsetmcBlocked / TsetmcUnreachable on failure."""
        text = await self._get_text(url, expect_json=True)
        import json

        try:
            return json.loads(text)
        except (json.JSONDecodeError, ValueError) as exc:  # HTML block page etc.
            raise TsetmcBlocked(f"non-JSON body from {url!r}") from exc

    async def get_text(self, url: str) -> str:
        """GET a legacy text/CSV endpoint."""
        return await self._get_text(url, expect_json=False)

    async def _get_text(self, url: str, expect_json: bool) -> str:
        last_exc: Exception | None = None
        for attempt in range(self._cfg.retries + 1):
            await self._bucket.acquire()
            try:
                async with self._sem:
                    session = await self._ensure()
                    async with session.get(url) as resp:
                        if resp.status in (500, 502, 503, 504):
                            raise TsetmcUnreachable(f"HTTP {resp.status} from {url!r}")
                        if resp.status in (403, 429):  # IP block / rate limit — don't retry
                            raise TsetmcBlocked(f"HTTP {resp.status} from {url!r}")
                        resp.raise_for_status()
                        body = await resp.text()
                if looks_blocked(body):
                    raise TsetmcBlocked(f"block page from {url!r}")
                return body
            except (TimeoutError, TsetmcUnreachable, aiohttp.ClientError) as exc:
                last_exc = exc
                if attempt < self._cfg.retries:
                    await asyncio.sleep(min(2**attempt * 0.5, 8.0))
                    continue
                raise TsetmcUnreachable(str(exc)) from exc
            except TsetmcBlocked:
                raise
        # Unreachable, but keeps type-checkers happy.
        raise TsetmcUnreachable(str(last_exc) if last_exc else "unknown")
