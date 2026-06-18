# BTC Selective Trend Re-Entry Signal

This folder is built by copying the previously working GetAgent package
structure from `btc_adaptive_short_trend_signal/` and applying only minimal
strategy-parameter changes for the selective trend re-entry candidate.

The goal is to keep the package shape that already passed GetAgent validation
and reached Cloud execution, while using the newer selective defaults:

- lower range fallback
- smaller defensive long branch
- stronger short-trend threshold
- higher `weight_scale`
- shorter Cloud comparison window

## Package

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

## Reproduce Research Snapshot

```bash
python -m pip install -r requirements.txt
python scripts/reproduce_metrics.py
```

Expected:

```json
"passed": true
```

Frozen local metrics:

```text
validation annual_return approximately 25.36%
validation max_drawdown approximately -5.80%
locked_test annual_return approximately 119.69%
locked_test max_drawdown approximately -3.76%
```

These are local research metrics, not GetAgent Cloud official evidence.

## Build Rule

Use this directory as a full package. Do not let authoring runtime rebuild the
strategy from scratch. Do not use single-file import. Validate and upload:

```bash
python <getagent_skill_path>/scripts/validate.py btc_selective_from_working_template/getagent_playbook
```

