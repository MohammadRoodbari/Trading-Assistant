# TradingView MCP Server

An MCP server that gives AI agents (Claude, ChatGPT, Cursor, and any other MCP client) direct access to real-time market data, technical analysis, screeners, and strategy backtesting — for stocks, crypto, forex, and futures across global exchanges.

Built on top of / adapted from [atilaahmettaner/tradingview-mcp](https://github.com/atilaahmettaner/tradingview-mcp).

## What it does

30+ tools across four areas:

### 📊 Backtesting Engine
- `backtest_strategy` — backtest 1 of 9 strategies with institutional-grade metrics (Sharpe, Calmar, Expectancy, Profit Factor, Max Drawdown, vs Buy-and-Hold). Supports 1h/1d timeframes, with optional full trade log + equity curve.
- `compare_strategies` — run all 9 strategies on one symbol and rank them.
- `walk_forward_backtest_strategy` — train/test walk-forward validation with an overfitting verdict (ROBUST / MODERATE / WEAK / OVERFITTED).

**Strategies:** `rsi`, `bollinger`, `macd`, `ema_cross`, `supertrend`, `donchian`, `rsi_pullback`, `keltner_breakout`, `triple_ema`.
> The three newer trend-filtered strategies (`rsi_pullback`, `keltner_breakout`, `triple_ema`) need `period='1y'` or `'2y'` so the SMA200 warmup can complete.

### 💰 Real-Time Prices (Yahoo Finance)
- `yahoo_price` — live quote: price, % change, 52w high/low, market state.
- `market_snapshot` — global overview: S&P 500, NASDAQ, VIX, BTC, ETH, EUR/USD, SPY, GLD.

Covers stocks, crypto (`BTC-USD`), ETFs, indices (`^GSPC`, `^VIX`), FX (`EURUSD=X`), and Turkish equities (`THYAO.IS`).

### 🌍 Global Stock Screener
- `stock_screener` — common/preferred shares for any TradingView country market, ranked by market cap.
- `stock_prices` — direct lookup for specific `EXCHANGE:SYMBOL` tickers (e.g. `NASDAQ:NVDA`, `KRX:005930`).

### 📈 Technical Analysis Core
- `get_technical_analysis` — 23 indicators + RSI/MACD/Bollinger with a BUY/SELL/HOLD verdict.
- `get_multiple_analysis` — bulk TA across symbols.
- `get_bollinger_band_analysis` — proprietary ±3 BB rating.
- `get_stock_decision` — 3-layer decision engine (ranking + trade setup + quality score).
- `screen_stocks` — multi-exchange screener, 20+ filters.
- `scan_by_signal` — scan for oversold / trending / breakout setups.
- `get_candlestick_patterns` — 15-pattern detector.
- `get_multi_timeframe_analysis` — Weekly → Daily → 4H → 1H → 15m alignment.

**Exchanges:** Binance, KuCoin, Bybit (crypto), NASDAQ/NYSE (US equities), EGX (Egypt, with dedicated tools), and Turkish BIST via the TradingView screener.

## Example prompts

```
"Compare all 9 strategies on MSFT for 2 years"
"Backtest RSI strategy on BTC-USD for 2 years"
"Run walk-forward backtest on supertrend for SPY"
"Give me a full market snapshot right now"
"Analyze TSLA with all signals: technical + sentiment + news"
```
