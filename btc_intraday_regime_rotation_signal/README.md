# BTC HTF Direction 15m Execution Signal

This folder contains the current 15-minute GetAgent candidate built after the
failed pure intraday experiments. The final structure is:

- BTCUSDT perpetual futures.
- 15-minute bars for replay and execution plumbing.
- Real UTC 4-hour boundaries for the actual decision layer.
- Selective short trend re-entry as the main return source.
- Long exposure disabled in the submitted Cloud-winning profile.
- Small range component retained but tightly capped.

## Why This Rebuild Exists

Earlier 15-minute versions traded too often and were eaten by fees. The fix was
not to add more idle-pressure trades. The fix was to raise the decision layer
back to a slower trend regime and let 15-minute bars act only as the execution
feed.

## Cloud Result

Current accepted completed GetAgent Cloud run:

```text
run_id: pbrun-f60c597831b0
version_id: e0c92319-8fb3-47f4-b21c-d9d43f03944f
status: completed
account_total_return_pct: +7.2109%
account_max_drawdown_pct: -5.9878%
fills: 20
positions: 10
win_rate: 50%
profit_factor: 2.228
window: 2025-12-18 -> 2026-06-01
```

The accepted profile uses `max_effective_exposure: 2.36`. Higher tests reached
slightly more return but crossed the 6% drawdown guardrail. Higher-frequency
15-minute and 2-hour direction variants increased trades but reduced quality
after fees, so they are not retained as the default.

GetAgent also reports strategy-basis fields using `margin_budget` as the
denominator. For comparing trading quality, use the account-level return,
account-level drawdown, fills, positions, win rate, and profit factor above.

## Local Research Snapshot

This folder keeps a frozen local research snapshot inherited from the selective
trend re-entry candidate. Run:

```bash
python -m pip install -r requirements.txt
python scripts/reproduce_metrics.py
```

Expected output includes:

```json
"passed": true
```

Frozen research metrics are local research evidence only. They are not GetAgent
Cloud official evidence.

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
name: btc-intraday-regime-rotation-signal
display_name: BTC HTF Direction 15m Execution Signal
backtest_support: full
execution_mode: follow_trade
symbol: BTCUSDT
execution feed: 15m
decision layer: 4h from 15m bars
```

## Validation

```bash
python C:\Users\wuchuxuan\.codex\skills\getagent\scripts\validate.py btc_intraday_regime_rotation_signal/getagent_playbook
```

Expected:

```text
Validation PASSED
```
