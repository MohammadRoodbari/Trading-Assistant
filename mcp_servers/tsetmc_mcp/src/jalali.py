"""Jalali (شمسی) <-> Gregorian conversion and TSETMC date/time integer helpers.

TSETMC speaks two integer forms:
  * DEven : Gregorian date as an 8-digit int  YYYYMMDD   (e.g. 20240115)
  * HEven : time of day as an int             HHMMSS     (e.g. 93012, may be <6 digits)
Users think in Jalali dates, so every outgoing timestamp is stamped with both.
"""

from __future__ import annotations

from datetime import date, datetime

import jdatetime

from .normalize import to_number


def deven_to_date(deven) -> date | None:
    """8-digit Gregorian YYYYMMDD int/str -> date. None on junk."""
    n = to_number(deven)
    if n is None:
        return None
    s = str(int(n))
    if len(s) != 8:
        return None
    try:
        return date(int(s[0:4]), int(s[4:6]), int(s[6:8]))
    except ValueError:
        return None


def date_to_deven(d: date) -> int:
    return d.year * 10000 + d.month * 100 + d.day


def heven_to_hms(heven) -> str | None:
    """HHMMSS int/str (possibly short) -> 'HH:MM:SS'. None on junk."""
    n = to_number(heven)
    if n is None:
        return None
    s = str(int(n)).zfill(6)
    if len(s) != 6:
        return None
    return f"{s[0:2]}:{s[2:4]}:{s[4:6]}"


def to_jalali_str(d: date) -> str:
    """Gregorian date -> 'YYYY/MM/DD' Jalali string."""
    j = jdatetime.date.fromgregorian(date=d)
    return f"{j.year:04d}/{j.month:02d}/{j.day:02d}"


def jalali_to_gregorian(jy: int, jm: int, jd: int) -> date:
    return jdatetime.date(jy, jm, jd).togregorian()


def parse_jalali(text: str) -> date | None:
    """Parse a Jalali date written as 'YYYY/MM/DD' or 'YYYY-MM-DD' -> Gregorian date."""
    from .normalize import fold_digits

    if not text:
        return None
    parts = fold_digits(text).replace("-", "/").split("/")
    if len(parts) != 3:
        return None
    try:
        jy, jm, jd = (int(p) for p in parts)
        if not 1200 <= jy <= 1600:  # reject a 2-digit year -> ~624 AD junk date
            return None
        return jalali_to_gregorian(jy, jm, jd)
    except (ValueError, TypeError):
        return None


def stamp(d: date, t: datetime | None = None) -> dict:
    """Build the dual-calendar timestamp block attached to every payload."""
    return {
        "gregorian": d.isoformat(),
        "jalali": to_jalali_str(d),
        "deven": date_to_deven(d),
    }
