# jiamihuobi

Public reproducible crypto strategy materials.

Current package:

- `btc_adaptive_short_trend_signal/` - BTC adaptive short-trend GetAgent signal package and frozen local research snapshot.

The BTC package is built around a volatility-scaled short trend floor, rebound filtering, and hard exposure caps. The frozen snapshot verifies the target checks used during selection: annualized return above 20% and max drawdown below 6% on both validation and locked-test windows.
