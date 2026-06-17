# BTC Adaptive Short Trend Signal Repro Pack

This folder contains a public, reproducible BTCUSDT perpetual futures signal
package for GetAgent. The strategy is built around a volatility-scaled short
trend floor, rebound filtering, and capped exposure.

## What Is Included

- `getagent_playbook/` is the GetAgent package with signal output and a
  deterministic Cloud backtest path.
- `research_snapshot/` contains the frozen candidate-selection evidence.
- `scripts/reproduce_metrics.py` reloads the frozen snapshot and verifies that
  the selected row passes the target checks.

No API keys, private DuckDB databases, or Bitget credentials are included.

## Core Idea

The model looks for persistent bearish alignment in BTCUSDT perpetual futures.
It requires medium-term weakness to remain intact, filters out strong rebounds,
uses recent realized volatility to size the short floor, and caps target
exposure. A small optional long path remains in the uploaded code for recovery
regimes, but the selected default is defensive and short-led.

The GetAgent package uses sandbox-replayable intraday futures bars. The frozen
research snapshot was exported from a local optimization run. The private raw
market database is intentionally not part of this public repo.

## Reproduce The Frozen Metrics

From this directory:

```bash
python -m pip install -r requirements.txt
python scripts/reproduce_metrics.py
```

The script reads:

```text
research_snapshot/selected_candidate_grid.csv
```

and writes:

```text
research_snapshot/reproduced_metrics.json
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

```text
name: btc-adaptive-short-trend-signal
backtest_support: full
execution_mode: follow_trade
```

The package includes `backtest.yaml` and a Nautilus strategy class so GetAgent
Cloud can run historical validation. Cloud results may differ from the frozen
research snapshot because they use platform K-lines and the platform replay
window. The uploaded logic does not import local files or direct exchange
clients.

## Files

```text
getagent_playbook/
  README.md
  manifest.yaml
  backtest.yaml
  src/main.py
  src/features.py
  src/strategy.py

research_snapshot/
  selected_candidate_grid.csv
  candidate_hits.json
  reproduced_metrics.json

scripts/
  reproduce_metrics.py
```
