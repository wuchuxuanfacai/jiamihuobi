# Paper / Cloud Execution Log

Source: GetAgent Studio official strategy card  
Strategy: BTC Adaptive Short Trend Signal  
GetAgent Studio: https://getagent.studio/strategy/2f355b4e-42ae-48d0-8633-a7ccf8fb433d  
Track: Trading Agent  
Market: BTCUSDT perpetual futures  
Execution mode: `follow_trade`  
Backtest support: `full`  

## Official Cloud Summary

| Field | Value |
|---|---:|
| Evidence source | GetAgent Cloud backtest / Studio strategy card |
| Window | 2026-03-03 to 2026-06-01 |
| Pair | BTCUSDT |
| Strategy style | short-or-flat target-position model |
| Total return | +10.15% |
| Maximum drawdown | -5.88% |
| Sharpe ratio | 1.49 |
| Fills | 38 |
| Complete positions | 6 |

## Trading Record Format Required By The Competition

The public GetAgent Studio card is the canonical record for the timestamped
execution rows. It displays the strategy's Cloud replay records for BTCUSDT,
including side, entry/exit price, quantity, PnL, and holding period. This file
summarizes the same official evidence for reviewers and points to the public
card above for row-level inspection.

| Timestamp / Window | Pair | Side | Price | Size | Balance Change |
|---|---|---|---:|---:|---:|
| 2026-03-03 to 2026-06-01 | BTCUSDT perpetual | Short / close-short target adjustments | See GetAgent Studio execution rows | 38 fills, 6 complete positions | +10.15% total return, -5.88% max drawdown |

## Notes

- The strategy is not a fixed trade-size model. It recalculates a target short
  weight on each 4h bar and rebalances toward the target quantity after lot-size
  rounding.
- No local DuckDB, private raw data, API key, `requests`, `httpx`, `ccxt`, or
  private exchange SDK is used by the Playbook package.
- Local research results are not used as official evidence. The official result
  is the GetAgent Studio Cloud strategy card linked above.
