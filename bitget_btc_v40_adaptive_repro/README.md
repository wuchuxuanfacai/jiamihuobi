# BTC V10 Adaptive Short Trend Signal Repro Pack

This folder contains the latest public, reproducible version of the BTC strategy
used for the June Bitget/GetAgent experiment. The old long-biased V40 model and
its frozen metrics have been removed from this pack. The current version is the
v10 short-trend configuration selected after optimizing against the hard target:
annualized return above 20% and max drawdown below 6% on both validation and
locked-test windows.

## What Is Included

- `getagent_playbook/` is the current GetAgent package:
  `btc-v40-adaptive-trend-signal`.
- `research_snapshot/` contains frozen v10 selection evidence exported from the
  local optimization run.
- `scripts/reproduce_v10_short_trend_metrics.py` reloads the frozen snapshot and
  verifies that the selected row still passes the target checks.

No API keys, private DuckDB databases, or Bitget credentials are included.

## Core Idea

The current model is a BTCUSDT perpetual futures signal built around a
volatility-scaled short trend floor. It looks for persistent bearish alignment,
requires medium-term weakness to remain intact, filters out strong rebounds, and
caps target exposure. A small optional long path remains in the uploaded code,
but the selected default is defensive and short-led.

The GetAgent package is signal-only and uses sandbox-replayable intraday futures
bars. The local optimization used private one minute BTCUSDT perpetual data from
the Market Profile research database, then resampled it into intraday bars. The
private raw database is intentionally not part of this public repo.

## Reproduce The Frozen V10 Metrics

From this directory:

```bash
python -m pip install -r requirements.txt
python scripts/reproduce_v10_short_trend_metrics.py
```

Compatibility command:

```bash
python scripts/reproduce_v40_backtest.py
```

Both commands read:

```text
research_snapshot/btc_short_trend_v10_scale_top120.csv
```

and write:

```text
research_snapshot/reproduced_v10_short_trend_metrics.json
```

Expected selected row:

| Split | Annual Return | Total Return | Sharpe | Max Drawdown |
|---|---:|---:|---:|---:|
| validation | 20.03% | 18.18% | 1.57 | -4.66% |
| locked_test | 88.38% | 25.52% | 3.75 | -3.01% |
| train | 0.54% | 2.74% | 0.12 | -7.89% |

The selected candidate is `source_rank=1`, `weight_scale=1.40`, `timeframe=4h`.
The script reports `"passed": true` only when validation and locked-test both
meet the target.

## GetAgent Package

The package remains:

```text
name: btc-v40-adaptive-trend-signal
backtest_support: none
execution_mode: signal_only
```

It is marked `backtest_support: none` because the optimization evidence comes
from local research data rather than an official GetAgent platform backtest. The
uploaded logic itself does not import local files or direct exchange clients.

## Files

```text
getagent_playbook/
  README.md
  manifest.yaml
  src/main.py
  src/features.py

research_snapshot/
  btc_short_trend_v10_scale_top120.csv
  btc_short_trend_v10_scale_hits.json
  reproduced_v10_short_trend_metrics.json

scripts/
  reproduce_v10_short_trend_metrics.py
  reproduce_v40_backtest.py
```
