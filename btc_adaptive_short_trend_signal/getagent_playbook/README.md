# BTC Adaptive Short Trend Signal

## Strategy 策略

This Playbook is a BTCUSDT perpetual futures signal. Its core engine is a
volatility-scaled short trend floor: when BTC is in a confirmed weak regime, the
strategy keeps a controlled short signal instead of waiting for repeated fresh
breakdowns.

The strategy uses only replayable intraday futures bars in the uploaded code
path. Private research files, local databases, and raw optimization inputs are
not included in the upload package.

## Entry 开仓

The Playbook opens a short signal when bearish trend alignment, medium-term
momentum, broader trend position, rebound filtering, and volatility checks
agree. The short trend floor is the base position. A small optional long path
exists for healthy recovery regimes, but the default configuration is defensive
and short-led.

If the bearish regime is not confirmed, the strategy emits hold. It does not
short every dip, and it avoids entries when the rebound filter suggests the
market has already recovered enough to invalidate the short setup.

## Exit 平仓

A short signal closes when bearish alignment fades, momentum no longer confirms
the move, price recovers into the broader trend reference, or
volatility-adjusted sizing no longer supports exposure. A long signal closes
when upside confirmation disappears.

This package emits signals and also includes a simplified deterministic
historical replay path for GetAgent Cloud validation. It does not place fixed
take-profit or stop-loss orders on the exchange in signal mode. Risk control
comes from regime withdrawal, volatility-aware sizing, and hard caps on target
exposure.

## Parameters 参数

Subscribers can tune leverage, margin budget, timeframe, aggressiveness, weight
scale, maximum signal weight, max short weight, max long weight, trend
lookbacks, short floor cap, short target volatility, long floor cap, and
volatility ceiling.

Higher leverage amplifies both gains and drawdowns. Margin budget controls the
capital base used by the platform for sizing and return interpretation. Higher
aggressiveness makes the model act earlier. Higher weight scale and exposure
caps allow larger signals in confirmed regimes. Lower volatility ceiling makes
the model more selective during unstable periods.

## Local Research Context 回测指标如何读

The selected local candidate is a 4h short trend floor configuration with a
conservative weight scale. It was selected because it passed the hard filter on
local splits: annualized return above 20% and max drawdown below 6% on both
validation and locked-test windows.

Local result for selected candidate `source_rank=1`, `weight_scale=1.40`:

- validation: annual return about 20.03%, total return about 18.18%, max drawdown about -4.66%, Sharpe about 1.57
- locked_test: annual return about 88.38%, total return about 25.52%, max drawdown about -3.01%, Sharpe about 3.75
- train: annual return about 0.54%, max drawdown about -7.89%

These are local research results with a 6 bps turnover cost assumption. The
GetAgent package also contains a Cloud backtest path under `backtest_support:
full`; Cloud results may differ because they use the platform K-line provider,
the shorter platform replay window, and Nautilus execution assumptions.

## Risk 风险

The main risk is a sharp BTC rebound after a short signal. The strategy can also
underperform in choppy ranges, news-driven gaps, exchange slippage, funding
stress, and regimes where downside momentum decays before the model exits.
Because the default is short-led, persistent bull markets can produce long
periods of holding or losing short attempts. Past local performance is not a
guarantee of live profitability.
