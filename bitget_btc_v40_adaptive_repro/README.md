# BTC V40 Adaptive Trend Signal Repro Pack

This folder contains the public, reproducible version of the BTC V40 adaptive
trend idea used for the June Bitget/GetAgent experiment.

It has two deliberately separate parts:

- `getagent_playbook/` is the GetAgent package that was uploaded and published
  as `btc-v40-adaptive-trend-signal` version `0.0.1`.
- `research_snapshot/` contains frozen CSV/JSON evidence from the local V40
  research run. The snapshot is included so anyone can reproduce the reported
  segment metrics without access to private D-drive databases, API keys, or
  live data providers.

## Core Idea

The original V40 model combines a long trend-following leg and a defensive
short regime leg. It uses a small capped target weight rather than full-account
directional exposure. The model favors BTC long exposure when price structure is
broadly bullish and adds a small short floor when the market is persistently
bearish. In unclear regimes, exposure is reduced or flat.

The full local research version used frozen model artifacts and private local
feature stores. Those dependencies are not included here because they would make
the result hard to reproduce and unsuitable for a public package. The GetAgent
Playbook therefore keeps only the sandbox-replayable price-structure core.

## Reproduce The Frozen V40 Metrics

From this directory:

```bash
python -m pip install -r requirements.txt
python scripts/reproduce_v40_backtest.py
```

The script reads `research_snapshot/v40_best_detail.csv`, recomputes segment
metrics, compares them with `research_snapshot/v40_summary.json`, and writes:

```text
research_snapshot/reproduced_v40_metrics.json
```

Expected headline metrics from the frozen snapshot:

| Segment | Dates | Total Return | Sharpe | Max Drawdown |
|---|---:|---:|---:|---:|
| inner_validation | 2023-07-01 to 2024-06-30 | 17.39% | 1.91 | -4.30% |
| outer_validation | 2024-07-01 to 2025-03-31 | 8.22% | 1.20 | -4.43% |
| outer_test | 2025-04-01 to 2026-05-13 | 12.81% | 1.41 | -3.80% |

The default tolerance is `1e-10`; a passing run should report
`"passed": true`.

## Published GetAgent Package

The published package is signal-only:

```text
name: btc-v40-adaptive-trend-signal
version: 0.0.1
status: published
playbook_id: edad9068-4af9-4814-93f4-70123ca818fe
strategy_id: b97dcdd8-e31f-4a4b-a092-3b554009245a
```

It is marked `backtest_support: none` because the original research result
depends on local datasets and frozen model artifacts. The Playbook should not
claim fake platform backtest evidence.

## Files

```text
getagent_playbook/
  README.md
  manifest.yaml
  src/main.py
  src/features.py

research_snapshot/
  v40_best_detail.csv
  v40_outer_test_detail.csv
  v40_summary.json
  latest_v40_v41_signal_summary.json

scripts/
  reproduce_v40_backtest.py
```

No API keys or private credentials are included.
