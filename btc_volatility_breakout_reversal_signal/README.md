# BTC Volatility Breakout Reversal Signal

This is a new GetAgent strategy branch, separate from the older HTF short-only
candidate. It tests a different idea:

- BTCUSDT perpetual futures.
- 15-minute execution and decision feed.
- Volatility-aware breakout entries.
- Pullback and rebound entries inside established regimes.
- Both long and short paths are allowed, but capped separately.
- No requests, ccxt, DuckDB, local database, API key, or private exchange SDK.

## Strategy Idea

BTC often alternates between compression, breakout, pullback, and continuation.
This strategy combines four components:

1. Long breakout after bullish structure and price confirmation.
2. Short breakdown after bearish structure and price confirmation.
3. Controlled long pullback inside a bullish regime.
4. Controlled short rebound inside a bearish regime.

Every target position is volatility scaled and clipped by max effective
exposure. The strategy recalculates a target position, then the Nautilus replay
strategy trades the difference from the current target.

## GetAgent Package

```text
getagent_playbook/
  README.md
  manifest.yaml
  backtest.yaml
  src/main.py
  src/features.py
  src/decision_logic.py
  src/strategy.py
```

Package contract:

```text
name: btc-volatility-breakout-reversal-signal
display_name: BTC Volatility Breakout Reversal Signal
backtest_support: full
execution_mode: follow_trade
symbol: BTCUSDT
timeframe: 15m
```

## Validation

```bash
python C:\Users\wuchuxuan\.codex\skills\getagent\scripts\validate.py btc_volatility_breakout_reversal_signal/getagent_playbook
```

Expected:

```text
Validation PASSED
```

Cloud metrics should be treated as the only official evidence. Local research
or failed Cloud runs are not final proof.

## Cloud Result

Accepted completed GetAgent Cloud run:

```text
run_id: pbrun-845a8c4e34f4
version_id: 84133fdb-a294-4c8f-b3c7-dad209c7a30e
status: completed
account_total_return_pct: +3.6795%
account_max_drawdown_pct: -3.8193%
fills: 17
positions: 8
win_rate: 87.5%
profit_factor: 9.1336
window: 2025-12-18 -> 2026-06-01
```

This did not beat the older short-trend strategy on total return, but it is a
different low-frequency overheat-reversal branch with much higher profit factor
and lower drawdown.
