# BTC Selective Trend Re-Entry Import Safe

This folder is a simplified single-file source for GetAgent GitHub source
import. Use it only when the normal full Playbook authoring flow fails before
artifact generation.

Primary file:

```text
btc_selective_trend_reentry_single.py
```

The file intentionally includes:

```python
positions = []
```

That guard is not part of the trading logic. It exists only to prevent a known
authoring runtime failure where generated intermediate code references that
name before a Playbook artifact is created.

The trading logic remains the same family as the full package:

- BTCUSDT perpetual futures
- 4h selective trend re-entry
- short trend re-entry as the main branch
- small defensive long branch
- volatility-scaled target weight
- rebound filter

For official package validation and Cloud backtest, prefer the complete
Playbook at:

```text
btc_selective_trend_reentry_signal/getagent_playbook/
```

