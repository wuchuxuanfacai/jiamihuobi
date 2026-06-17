# BTC Adaptive Trend Range Signal Repro Pack

This folder contains a public BTCUSDT perpetual futures strategy package for
GetAgent. The current package is a composite target-position strategy. It
combines a trend-long model, a trend-short model, and a range mean-reversion
model, then clips the summed target weight.

## What Is Included

- `getagent_playbook/` is the GetAgent package with deterministic Cloud
  backtest support and managed follow-trade compatibility.
- `research_snapshot/` contains frozen local candidate-selection evidence from
  an earlier research run.
- `scripts/reproduce_metrics.py` verifies that the frozen research snapshot is
  still reproducible.

No API keys, private DuckDB databases, local raw data, or Bitget credentials are
included.

## Current Strategy

The uploaded package uses replayable intraday futures bars. Its trend-long
component can hold a long base and add a dynamic long weight during acceleration
or constructive pullback conditions. Its trend-short component can hold a short
base and add dynamic short weight during breakdown or rebound-failure
conditions. Its range component is only active when neither side has a dominant
trend; it fades channel extremes with smaller flexible weights and adjusts the
long/short bias for gently rising or falling channels.

The Cloud path trades target-position adjustments rather than isolated fixed
entry signals. It fetches pre-roll history before the declared trading window so
trend, channel, and volatility features are already formed at the first traded
bar.

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

Expected frozen selected row:

| Split | Annual Return | Total Return | Sharpe | Max Drawdown |
|---|---:|---:|---:|---:|
| validation | 20.03% | 18.18% | 1.57 | -4.66% |
| locked_test | 88.38% | 25.52% | 3.75 | -3.01% |
| train | 0.54% | 2.74% | 0.12 | -7.89% |

The selected frozen candidate is `source_rank=1`, `weight_scale=1.40`,
`timeframe=4h`. This snapshot is local research evidence, not official GetAgent
Cloud proof for the current composite package.

## GetAgent Package

```text
name: btc-adaptive-short-trend-signal
display_name: BTC Adaptive Trend Range Signal
backtest_support: full
execution_mode: follow_trade
```

The package includes `backtest.yaml` and a Nautilus strategy class so GetAgent
Cloud can run historical validation. Cloud results may differ from local
research because they use the platform K-line provider, the platform replay
engine, venue assumptions, and minimum-lot rounding.

## Files

```text
getagent_playbook/
  README.md
  manifest.yaml
  backtest.yaml
  src/main.py
  src/features.py
  src/strategy.py
  src/decision_logic.py

research_snapshot/
  selected_candidate_grid.csv
  candidate_hits.json
  reproduced_metrics.json

scripts/
  reproduce_metrics.py
```
