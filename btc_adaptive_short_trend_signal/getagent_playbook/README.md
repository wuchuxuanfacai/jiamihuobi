# BTC Adaptive Trend Range Signal

## Strategy 策略

This Playbook trades BTCUSDT perpetual futures with one composite target
position. The target is built from three sub-models: a trend-long model, a
trend-short model, and a range mean-reversion model. Each sub-model produces a
signed weight, then the final target is the clipped sum of those weights.
The current default profile is deliberately trend-led: the short trend branch
and a smaller long trend branch are the only active base components, while
range exposure is a small fallback used only when both directional reads are
quiet, volatility is low, and price has moved to a channel extreme.

The uploaded package uses only replayable intraday futures OHLCV bars. It does
not read local databases, API keys, private research files, direct exchange
SDKs, or HTTP clients.

## Entry 开仓

The trend-long model can hold a long base when broader upside alignment is
healthy. Dynamic long add-ons are disabled in the default profile so the long
side stays simple and easier to audit.

The trend-short model can hold a short base when downside alignment, weak
momentum, and price location below trend references are clear. Dynamic short
add-ons are disabled in the default profile to keep turnover and exposure
controlled.

The range model is active only when neither trend side is dominant. It fades
channel extremes with smaller flexible weights: lower-channel weakness can
produce a long component, while upper-channel strength can produce a short
component. A gently rising channel makes range longs easier and slightly
larger; a gently falling channel does the same for range shorts. The fallback
also requires a flat enough channel and limited slow-period momentum so it does
not fight a developing trend.

## Exit 平仓

The strategy exits by reducing or removing the target weight. Long exposure
falls when upside alignment fades, the pullback setup stops being constructive,
or volatility-adjusted sizing no longer supports the position. Short exposure
falls when bearish alignment fades, rebound pressure invalidates the setup, or
price leaves the lower-risk short zone. Range positions close when price moves
away from the channel extreme or a clearer trend regime takes over.

The Cloud replay fetches pre-roll history before the trade window so moving
trend and volatility features are already formed when trading begins. Orders in
the backtest are target-position adjustments, not isolated fixed-size entries.
Small target changes are ignored unless they are large enough to justify a
rebalance, reducing churn and fee drag in sideways periods.
When trend confirmation falls below the invalidation threshold, the target is
forced back toward flat.

## Parameters

Subscribers can tune leverage, margin budget, timeframe, aggressiveness,
overall weight scale, maximum signal weight, maximum effective exposure,
maximum short weight, maximum long weight, trend lookbacks, short and long
exposure caps, and volatility filters.

Higher leverage amplifies both gains and drawdowns without making the signal
more selective, while maximum effective exposure caps the final notional size
after leverage is applied. Margin budget controls the capital base used by the
platform for sizing and return interpretation. Higher aggressiveness makes the
model act earlier; lower aggressiveness makes it wait for cleaner confirmation.
Higher exposure caps permit larger positions in confirmed regimes, while lower
caps make the strategy more defensive.

## Reading Returns

The strategy card's total return is the portfolio result on the declared
strategy margin budget after closed-trade PnL and fees. Individual trade rows
can show a much smaller percentage because that row is tied to the entry and
exit price movement of a single round trip, not the full strategy equity curve.
Very short price moves can display near zero percent while still producing
negative net PnL after taker fees. The replay sizes contract quantity from the
margin budget, leverage, target weight, current price, exchange lot size, and
the maximum effective exposure guardrail.

## Costs And Slippage

The package declares maker and taker fees in `backtest.yaml`, so GetAgent Cloud
can include exchange trading fees in the replay. Real trading losses are not
limited to fees. They can also include bid-ask spread, slippage, funding rates,
latency, order rejection or partial fill behavior, liquidation constraints,
and differences between platform K-lines and the venue where orders execute.
This version does not model those extra losses directly in package code.

## Local Research Context

The frozen `research_snapshot/` files are local research evidence, not official
GetAgent Cloud metrics. The selected frozen candidate remains reproducible with
`scripts/reproduce_metrics.py`, but the current Cloud package has been evolved
into a composite long/short/range model, so platform results should be read
from the GetAgent strategy card after each run.

Local approximate testing on the same Cloud-style window was used to select the
current default composite parameters. Those local checks are useful for
iteration, but they are not a substitute for Cloud replay evidence.

## Risk 风险

The main risks are sharp BTC reversals, choppy ranges that repeatedly flip
regime, major news gaps, unstable liquidity, high funding dislocation, and live
execution costs that are larger than the replay assumptions. Historical results
do not guarantee live profitability.
