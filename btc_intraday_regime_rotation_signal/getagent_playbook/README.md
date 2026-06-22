# BTC HTF Direction 15m Execution Signal

## Strategy / 策略

This Playbook trades BTCUSDT perpetual futures with 15-minute replay bars, but
the trading decision is intentionally slower. The strategy samples the 15-minute
stream on real UTC 4-hour boundaries and builds a higher-timeframe trend state
from those closes. The goal is to keep the package compatible with a 15-minute
execution feed while avoiding the fee drag that came from letting every small
15-minute fluctuation change the target position.

The current Cloud-winning profile is selective and short-biased. It focuses on
BTC downside trend re-entry when bearish alignment, weak momentum, controlled
rebound pressure, and acceptable volatility appear together. The long branch is
disabled in the submitted profile because the Cloud window showed better
risk-adjusted behavior from the selective short structure.

## Entry / 开仓

The strategy can open a short position when price is below slower references,
medium and slow momentum are weak, the bearish alignment score is strong enough,
and rebound pressure is not excessive. The strategy checks these conditions only
at real 4-hour decision points derived from the 15-minute bars.

A very small range component is still present in the code, but it is tightly
capped and only allowed when both trend and bear readings are weak. It is not an
idle-pressure mechanism and it is not meant to force trades every day.

## Exit / 平仓

Exits happen through target-weight reduction. When bearish structure weakens,
when rebound pressure invalidates the setup, or when volatility makes the target
unattractive, the target moves back toward flat. Small target changes are ignored
through the rebalance threshold so the strategy does not churn on every minor
bar.

## Parameters

The main user-tunable parameters are leverage, margin budget, aggressiveness,
maximum effective exposure, short exposure cap, range cap, and volatility
ceiling. Higher leverage or effective exposure increases both return and
drawdown. Margin budget is the sizing denominator used by GetAgent. More
aggressive settings can increase activity, but can also create weaker entries.

## Costs

The replay declares maker and taker fees in `backtest.yaml`. Live trading may
also face spread, slippage, latency, funding payments, partial fills, mark-price
differences, and liquidity loss during fast candles. These costs can materially
change results.

## Risk / 风险

The main risks are sharp BTC rebounds after bearish entries, news gaps, market
regime changes, and choppy periods where downside signals fail to follow
through. Historical Cloud backtest evidence is not a guarantee of future live
profitability.
