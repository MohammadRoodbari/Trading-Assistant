"""Built-in named filters — the common shared TSETMC screens, in our syntax.

These double as ready-to-run filters (`run_saved_filter("buyer_power_2x")`) and as
worked examples so Claude writes valid filters.
"""

from __future__ import annotations

PRESETS: dict[str, dict] = {
    "up": {
        "expression": "last > yesterday",
        "description": "سبزها — last price above yesterday's close",
    },
    "up_liquid": {
        "expression": "change_pct > 0 and trade_count > 30 and volume >= base_volume",
        "description": "up on the day, ≥30 trades, volume reached base volume",
    },
    "net_individual_inflow": {
        "expression": "net_individual > 0 and change_pct > 0",
        "description": "ورود پول حقیقی — individuals net buyers while price rises",
    },
    "buyer_power_2x": {
        "expression": "buyer_power >= 2 and last >= close and change_pct > 0",
        "description": "پول داغ — per-capita individual buy ≥ 2× per-capita sell, positive",
    },
    "code_to_code": {
        "expression": "ct_buy_i_vol > 0.5*volume and ct_sell_n_vol > 0.5*volume and percap_buy > percap_sell",
        "description": "کد به کد حقوقی به حقیقی — institutions hand shares to strong retail",
    },
    "institutional_accumulation": {
        "expression": "ct_buy_n_vol >= 0.6*volume",
        "description": "خرید حقوقی — institutions absorbed ≥60% of the day's volume",
    },
    "volume_spike": {
        "expression": "volume > 3*base_volume and change_pct > 0",
        "description": "حجم مشکوک (proxy) — volume >3× base volume, price up",
    },
    "smart_money_lite": {
        "expression": "volume > 3*base_volume and buyer_power >= 1 and last >= close and change_pct > 0",
        "description": "ورود پول هوشمند (lite) — volume spike + individual buying dominant (no 30-day avg yet)",
    },
    "buy_queue": {
        "expression": "value > 0 and buy_queue()",
        "description": "صف خرید — locked in a buy queue (order-book enriched)",
    },
    "sell_queue": {
        "expression": "value > 0 and sell_queue()",
        "description": "صف فروش — locked in a sell queue (order-book enriched)",
    },
}
