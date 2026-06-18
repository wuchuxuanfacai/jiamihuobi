# BTC Selective Trend Re-Entry Signal

This folder is an independent GetAgent candidate strategy built around the
strongest frozen low-turnover trend candidate currently available in this
repository.

## Core Idea

This candidate avoids forcing trades during long flat periods. The goal is to
improve the return/drawdown profile by waiting for higher-quality re-entry
conditions:

- Keep trend-first logic.
- Keep average exposure low.
- Use volatility-scaled target sizing.
- Use rebound filters before opening shorts.
- Keep the long path small and defensive.
- Treat range behavior as a strict filter and small context check, not as a
  reason to trade every quiet bar.

## Local Reproducible Baseline

Run from this directory:

```bash
python -m pip install -r requirements.txt
python scripts/reproduce_metrics.py
```

Expected output includes:

```json
"passed": true
```

Selected frozen candidate:

| Field | Value |
|---|---:|
| source_rank | 1 |
| weight_scale | 1.75 |
| timeframe | 4h |

Frozen local metrics:

| Split | Annual Return | Total Return | Max Drawdown | Sharpe |
|---|---:|---:|---:|---:|
| validation | 25.36% | 22.98% | -5.80% | 1.57 |
| locked_test | 119.69% | 32.64% | -3.76% | 3.75 |
| train | 0.62% | 3.13% | -9.79% | 0.12 |

These are local frozen research metrics. They are not GetAgent Cloud official
backtest evidence.

## GetAgent Package

```text
getagent_playbook/
  README.md
  manifest.yaml
  backtest.yaml
  src/main.py
  src/features.py
  src/strategy.py
  src/decision_logic.py
```

Package contract:

```text
name: btc-selective-trend-reentry-signal
display_name: BTC Selective Trend Re-Entry Signal
backtest_support: full
execution_mode: follow_trade
symbol: BTCUSDT
timeframe: 4h
```

The Cloud replay window is intentionally kept inside the practical 4h
bootstrap limit used by GetAgent Cloud:

```text
2025-12-18T00:00:00Z -> 2026-06-01T00:00:00Z
```

This keeps the Cloud test inside a stable platform data window and allows
direct comparison against the current acceptance threshold.

## Acceptance Threshold

The candidate should only be accepted if GetAgent Cloud produces:

```text
Total Return > +9.2%
Max Drawdown <= 6%
Complete trades not abnormally inflated
```

If Cloud return is below the threshold, drawdown is above the threshold, or the
trade count grows abnormally, this candidate should stay as research evidence
only and should not be published.

## Prompt

See:

```text
GETAGENT_PROMPT.md
```
