"""Background poller: keeps the Snapshot fresh, safely.

One asyncio task loops for the life of the server. During the Tehran session it
pulls the market-wide endpoints every `poll_interval_s`; when the market is closed
it idles (checking every minute) and leaves the last snapshot in place, flagged
stale by its metadata. A circuit breaker backs off on repeated upstream failures
(blocks / unreachability) instead of hammering TSETMC into a longer block.
"""

from __future__ import annotations

import asyncio
import logging

from .calendar_tsec import is_market_open
from .config import Config
from .fetch import MarketDataSource, TsetmcError
from .snapshot import Snapshot

log = logging.getLogger("tsetmc_mcp.poller")


class Poller:
    def __init__(self, cfg: Config, source: MarketDataSource, snapshot: Snapshot):
        self._cfg = cfg
        self._source = source
        self._snap = snapshot
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._consecutive_failures = 0

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="tsetmc-poller")
            self._task.add_done_callback(self._on_done)

    @staticmethod
    def _on_done(task: asyncio.Task) -> None:
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:  # should never happen now (_run swallows Exception)
            log.error("poller task exited unexpectedly: %r", exc)

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            except Exception as exc:  # noqa: BLE001 - don't let a dead task break shutdown
                log.warning("poller task ended with error: %s", exc)
            self._task = None

    async def poll_once(self) -> None:
        """One full refresh. Prices are critical; money-flow and overview are
        best-effort (a failure in either must not blank the price snapshot)."""
        rows = await self._source.market_watch()
        self._snap.update_prices(rows)
        for coro, apply in (
            (self._source.client_type_all(), self._snap.update_client_type),
            (self._source.market_overview(), self._snap.update_overview),
        ):
            try:
                apply(await coro)
            except TsetmcError as exc:
                log.warning("secondary poll failed: %s", exc)

    async def _run(self) -> None:
        # Warm up immediately so early tool calls have data — but only when the
        # market is open (off-session GetMarketWatch returns zeroed rows; leaving
        # the snapshot cold makes tools fall back to live per-symbol data instead).
        if is_market_open(self._cfg, None):
            try:
                await self.poll_once()
            except Exception as exc:  # noqa: BLE001 - keep the loop alive on any error
                self._snap.mark_error(str(exc))
                log.warning("initial poll failed: %s", exc)

        while not self._stop.is_set():
            if not is_market_open(self._cfg, None):
                await self._sleep(60)
                continue
            try:
                await self.poll_once()
                self._consecutive_failures = 0
                await self._sleep(self._cfg.poll_interval_s)
            except Exception as exc:  # noqa: BLE001 - a parse/network glitch must not kill the loop
                self._consecutive_failures += 1
                self._snap.mark_error(str(exc))
                backoff = min(self._cfg.poll_interval_s * (2**self._consecutive_failures), 120)
                log.warning(
                    "poll failed (%d in a row): %s; backing off %.0fs",
                    self._consecutive_failures,
                    exc,
                    backoff,
                )
                await self._sleep(backoff)

    async def _sleep(self, seconds: float) -> None:
        try:
            await asyncio.wait_for(self._stop.wait(), timeout=seconds)
        except TimeoutError:
            pass
