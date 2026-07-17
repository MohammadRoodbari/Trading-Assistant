# TSETMC MCP Server

An MCP server that connects AI agents (Claude, ChatGPT, Cursor, and any other MCP client) directly to the Tehran Stock Exchange (TSETMC) — live quotes, order books, institutional money flow, market-wide screening, and price history, in Persian or English.

Based on [solitraderbusiness/tsetmc-mcp](https://github.com/solitraderbusiness/tsetmc-mcp).

## Features

| Tool | What it does |
|---|---|
| `search_symbol` | نماد (Persian symbol name) → instrument code |
| `get_quote` | live price, % change, volume/value, EPS/PE |
| `get_order_book` | 5-level صف خرید/فروش (bid/ask) |
| `get_money_flow` | حقیقی/حقوقی (retail/institutional) buy & sell, plus net institutional flow |
| `get_market_watch` | filtered, sorted view of the whole market (never dumps all ~700 rows at once) |
| `screen` | top gainers/losers, most active symbols, market breadth |
| `get_index_overview` | TEDPIX + equal-weight index at a glance |
| `get_price_history` | daily OHLCV; large pulls are saved to a CSV file instead of flooding the chat |
| `market_status` | whether the Tehran market is open right now |
| `describe_fields` | reference for field names and units |
| `run_filter` | run a custom filter — describe it in plain language, or paste a TSETMC filter |
| `run_saved_filter` | run a saved filter, or one of the built-in presets, by name |
| `filter_help` | filter variables, operators, and available presets |

All prices are in Rial. Every response carries a freshness stamp (`market_open`, `staleness_seconds`, `upstream_reachable`) so the model never mistakes stale data for live data.

## Usage — just talk to LLM

Ask in plain Persian or English; LLM picks the right tool automatically.

- «قیمت فولاد چنده؟» / "what's فولاد trading at?"
- «صف خرید خودرو چطوره؟» / "show خودرو's order book"
- «امروز کدوم نمادها +۳٪ با حجم بالان؟» / "stocks up >3% on high volume"
- «بیشترین رشد امروز» / "top gainers now"
- «حقیقی/حقوقی شستا؟» / "smart-money on شستا"
- «شاخص کل چنده؟» / "where's TEDPIX?"
- «تاریخچه ۶ ماه فولاد» / "pull فولاد's price history" (large pulls saved to CSV)

