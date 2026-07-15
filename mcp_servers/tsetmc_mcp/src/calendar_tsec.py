"""Tehran trading-calendar gate.

Answers "is the market open right now?" so the poller can stop when closed and
every payload can be honestly labelled live vs. a frozen snapshot. The Tehran
Stock Exchange trades Saturday–Wednesday, roughly 09:00–12:30 local time; Thursday
and Friday are the weekend. Official Jalali holidays are numerous and shift yearly,
so they are read from a user-maintained file (config.holidays_file) rather than
hard-coded — an empty file simply means "weekends only", which never mislabels a
weekend as open but may optimistically treat a holiday as open (documented).
"""

from __future__ import annotations

from datetime import date, datetime, time
from functools import lru_cache
from zoneinfo import ZoneInfo

from .config import Config

# Python weekday(): Mon=0 .. Sun=6. Tehran weekend = Thursday(3), Friday(4).
_WEEKEND = {3, 4}


@lru_cache(maxsize=8)
def _load_holidays(path_str: str, mtime: float) -> frozenset:
    """Load Gregorian ISO dates from the holidays file. Cache keyed on mtime so
    edits are picked up without a restart."""
    from pathlib import Path

    out = set()
    p = Path(path_str)
    if not p.exists():
        return frozenset()
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            out.add(date.fromisoformat(line))
        except ValueError:
            continue
    return frozenset(out)


def _holidays(cfg: Config) -> frozenset:
    p = cfg.holidays_file
    mtime = p.stat().st_mtime if p.exists() else 0.0
    return _load_holidays(str(p), mtime)


def now_tehran(cfg: Config) -> datetime:
    return datetime.now(ZoneInfo(cfg.market_tz))


def is_trading_day(cfg: Config, d: date) -> bool:
    return d.weekday() not in _WEEKEND and d not in _holidays(cfg)


def is_market_open(cfg: Config, at: datetime | None = None) -> bool:
    at = at or now_tehran(cfg)
    if not is_trading_day(cfg, at.date()):
        return False
    open_t = time(cfg.open_hour, cfg.open_minute)
    close_t = time(cfg.close_hour, cfg.close_minute)
    return open_t <= at.time() <= close_t


def market_status(cfg: Config, at: datetime | None = None) -> dict:
    """A small human/machine readable status block."""
    at = at or now_tehran(cfg)
    return {
        "open": is_market_open(cfg, at),
        "trading_day": is_trading_day(cfg, at.date()),
        "now_tehran": at.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "session": f"{cfg.open_hour:02d}:{cfg.open_minute:02d}-{cfg.close_hour:02d}:{cfg.close_minute:02d} Asia/Tehran, Sat-Wed",
    }
