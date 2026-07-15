"""Live self-check — run this on the machine that will host the server (in Iran).

It exercises the real TSETMC endpoints the server depends on and prints a clear
PASS / FAIL / BLOCKED report, including a sample parsed row so you can confirm the
field mapping is aligned with what TSETMC currently returns. This is the one check
that cannot be done from outside Iran (TSETMC geo-blocks foreign IPs), so it is
shipped as a command you run yourself:

    uv run tsetmc-mcp-selfcheck        # or: python -m tsetmc_mcp.selfcheck
"""

from __future__ import annotations

import asyncio
import sys

from .calendar_tsec import market_status
from .config import load_config
from .fetch import RawSource, TsetmcBlocked, TsetmcError

_PROBE_SYMBOL = "فولاد"  # a large, always-listed symbol


def _line(status: str, name: str, detail: str = "") -> None:
    mark = {"PASS": "✅", "FAIL": "❌", "BLOCKED": "🚫", "WARN": "⚠️"}.get(status, "•")
    print(f"{mark} {status:7} {name}" + (f" — {detail}" if detail else ""), file=sys.stderr)


async def _run() -> int:
    cfg = load_config()
    ok = True
    print("── tsetmc-mcp self-check ──", file=sys.stderr)
    st = market_status(cfg)
    _line(
        "PASS" if st["trading_day"] else "WARN",
        "calendar",
        f"open={st['open']} trading_day={st['trading_day']} ({st['now_tehran']})",
    )
    print(f"   source={cfg.source} cdn={cfg.cdn_base}", file=sys.stderr)

    src = RawSource(cfg)
    try:
        # 1) search
        try:
            hits = await src.search(_PROBE_SYMBOL)
            if hits:
                _line(
                    "PASS",
                    "search",
                    f"{_PROBE_SYMBOL} -> insCode {hits[0]['ins_code']} ({hits[0]['name']})",
                )
                ins = hits[0]["ins_code"]
            else:
                _line("FAIL", "search", "no results")
                ok = False
                ins = None
        except TsetmcBlocked as e:
            _line(
                "BLOCKED", "search", f"{e} — is this an Iranian IP? (foreign/VPN IPs are blocked)"
            )
            ok = False
            ins = None
        except TsetmcError as e:
            _line("FAIL", "search", str(e))
            ok = False
            ins = None

        # 2) market watch (the backbone)
        try:
            rows = await src.market_watch()
            if rows:
                traded = [r for r in rows if r.last is not None]
                sample = traded[0] if traded else next((r for r in rows if r.symbol), rows[0])
                _line(
                    "PASS",
                    "market_watch",
                    f"{len(rows)} instruments, {len(traded)} traded; sample: {sample.symbol} last={sample.last} vol={sample.volume}",
                )
                if not traded:
                    _line(
                        "WARN",
                        "market_watch",
                        "no instrument shows a last price — the market is likely closed / a non-trading "
                        "day (GetMarketWatch zeroes intraday fields off-session). Re-run during Tehran "
                        "market hours (Sat–Wed 09:00–12:30) to confirm the price mapping is live.",
                    )
            else:
                _line("FAIL", "market_watch", "0 rows")
                ok = False
        except TsetmcError as e:
            _line("BLOCKED" if isinstance(e, TsetmcBlocked) else "FAIL", "market_watch", str(e))
            ok = False

        # 3) per-symbol probes
        if ins:
            for name, coro in (
                ("order_book", src.order_book(ins)),
                ("client_type", src.client_type(ins)),
                ("price_history", src.price_history(ins, 5)),
            ):
                try:
                    res = await coro
                    n = len(res) if isinstance(res, list) else (0 if res is None else 1)
                    _line("PASS" if n else "WARN", name, f"{n} rows")
                except TsetmcError as e:
                    _line("FAIL", name, str(e))
                    ok = False

        # 4) overview
        try:
            ov = await src.market_overview()
            _line(
                "PASS" if ov and ov.index_value is not None else "WARN",
                "overview",
                f"TEDPIX={ov.index_value if ov else None}",
            )
        except TsetmcError as e:
            _line("FAIL", "overview", str(e))
            ok = False
    finally:
        await src.close()

    print(
        (
            "\n✅ self-check PASSED — the server should work here."
            if ok
            else "\n❌ self-check had failures — see above. If everything is BLOCKED, you are "
            "likely not on an Iranian IP (disable any foreign VPN for this process)."
        ),
        file=sys.stderr,
    )
    return 0 if ok else 1


def main() -> None:
    raise SystemExit(asyncio.run(_run()))


if __name__ == "__main__":
    main()
