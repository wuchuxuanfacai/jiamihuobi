# BTC Adaptive Short Trend Signal

This folder is the public submission package for the Bitget Trading Agent
track. It contains only the current BTC Adaptive Short Trend Signal materials:
the GetAgent Playbook source, the official GetAgent Studio strategy link, and a
public execution/backtest evidence summary.

## Submission Links

- GetAgent Studio strategy:
  https://getagent.studio/strategy/2f355b4e-42ae-48d0-8633-a7ccf8fb433d
- Strategy package:
  `getagent_playbook/`
- Paper / Cloud execution evidence:
  [`PAPER_TRADING_LOG.md`](./PAPER_TRADING_LOG.md)

## Idea

BTC Adaptive Short Trend Signal is a BTCUSDT perpetual futures Trading Agent
built for a short-or-flat regime. The strategy only uses flat or short target exposure and avoids repeated constant-size entries. Instead, every four-hour bar is
converted into a target short weight, then the target weight is translated into
BTC quantity from the configured margin budget, current BTC price, leverage,
and minimum order size.

The core thesis is that BTC downside moves have two different risk profiles.
In cleaner low-volatility bearish regimes, trend continuation can be traded
with a larger short target. In high-volatility bearish regimes, staying fully
flat can miss important selloffs, but full-size short exposure can create
unstable drawdown. The final version therefore uses two branches:

1. Low-volatility strong bearish branch: carries the main short exposure when
   downside structure, weak momentum, price location, rebound filtering, and
   realized volatility all confirm.
2. High-volatility small short branch: participates with reduced size when the
   market is volatile but bearish structure is still valid.

## Signals

The agent uses replayable BTCUSDT futures OHLCV data through GetAgent. The
decision logic combines:

- bearish regime alignment
- medium and short-term momentum
- long-cycle price position
- rebound filtering
- realized volatility regime

The output is a target position, not an isolated entry signal. The strategy
then adjusts toward that target using exchange lot-size rounding.

## Risk Management

Risk is controlled by keeping the system short-or-flat, capping maximum short
weight, shrinking exposure in high-volatility regimes, ignoring target changes
below the minimum useful rebalance size, and using GetAgent Cloud's declared
maker/taker fee assumptions. The strategy is still exposed to sharp BTC
rebounds, news gaps, funding-rate changes, slippage, and live execution
differences.

## Official Cloud Evidence

The official GetAgent Studio card reports:

| Metric | Value |
|---|---:|
| Total Return | +10.15% |
| Max Drawdown | -5.88% |
| Sharpe | 1.49 |
| Fills | 38 |
| Positions | 6 |
| Pair | BTCUSDT perpetual |
| Window | 2026-03-03 to 2026-06-01 |

These are platform Cloud results from GetAgent Studio. The GetAgent
Studio card is the primary source for the official execution history and
strategy card display.

## Contents

```text
getagent_playbook/
  README.md
  manifest.yaml
  backtest.yaml
  src/main.py
  src/features.py
  src/strategy.py
  src/decision_logic.py

PAPER_TRADING_LOG.md
```

This submission folder contains only the current GetAgent Playbook, public strategy documentation, and Cloud evidence summary.
