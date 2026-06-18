# BTC Selective Trend Re-Entry Signal

## Strategy / 策略

This Playbook trades BTCUSDT perpetual futures with a selective target-position
model. The design focuses on low average exposure, trend-first entries,
volatility-scaled sizing, and strict rebound filters. It avoids forcing trades
during every quiet market period.

The strategy is mainly a trend re-entry system. It waits for a directional
structure to become clear, then uses a controlled target weight instead of
repeated fixed-size entries. The short side is the primary research edge. The
long side is intentionally small and defensive, used only when upside alignment
is clean enough to avoid fighting a developing recovery.

## Entry / 开仓

The short model can open exposure when downside alignment, weak medium-term
momentum, price location below trend references, and rebound rejection are all
present. Position size is scaled down when realized volatility is high, so the
strategy does not simply use maximum exposure every time a bearish condition
appears.

The long model can open only a small recovery position when upside alignment is
healthy, price is above trend references, and volatility remains acceptable.
This long path is not intended to chase every bounce. It exists to avoid being
structurally short-only when BTC moves into a clean recovery phase.

The range component is constrained. It may fade channel extremes only when both
directional reads are quiet and volatility is low. It is not allowed to fill
every flat period.

## Exit / 平仓

The strategy exits by reducing the target weight. Short exposure is removed
when bearish alignment fades, rebound pressure invalidates the setup, or price
leaves the lower-risk zone. Long exposure is removed when upside alignment
weakens or volatility-adjusted sizing no longer supports the position. Range
exposure closes when price leaves the channel extreme or a clearer trend takes
over.

Orders in the replay are target-position adjustments, not independent signal
rows. Small target changes are ignored unless they are large enough to justify a
rebalance. This keeps turnover controlled.

## Parameters

Subscribers can tune leverage, margin budget, timeframe, aggressiveness, weight
scale, maximum effective exposure, maximum signal weight, maximum short weight,
maximum long weight, trend lookbacks, exposure caps, and volatility filters.

Higher leverage amplifies both gains and drawdowns without improving signal
quality. Margin budget controls the capital base used by the platform for
sizing and return interpretation. Higher weight scale and exposure caps allow
larger positions in confirmed regimes, while lower values make the strategy
more defensive. Tighter volatility filters reduce trade frequency and may miss
some strong moves, but they can help avoid unstable chop.

## Reading Returns

The strategy card's total return is the portfolio result on the declared
strategy margin budget after replayed fills and fees. Individual trade rows can
show a different percentage because each row reflects the price movement of one
position, not the whole strategy equity curve. The package declares maker and
taker fees in `backtest.yaml`; live execution can also include spread, slippage,
funding-rate effects, latency, partial fills, liquidation constraints, and
differences between platform bars and venue execution.

## Local Research Context

The frozen `research_snapshot/` files are local research evidence, not official
GetAgent Cloud metrics. The selected candidate is reproducible with
`scripts/reproduce_metrics.py` and is used only as a local selection baseline.
Cloud results must be read from the GetAgent strategy card after each run.

## Risk / 风险

The main risks are sharp BTC reversals, choppy markets with repeated false
breakdowns, strong upside recoveries after short entries, news gaps, unstable
liquidity, high funding dislocation, and live execution costs larger than the
replay assumptions. Historical results do not guarantee live profitability.
