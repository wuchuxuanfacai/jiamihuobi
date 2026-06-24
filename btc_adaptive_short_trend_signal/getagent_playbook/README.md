# BTC Adaptive Short Trend Signal

## Strategy / 策略

This Playbook trades BTCUSDT perpetual futures as a short-or-flat target
position strategy on four-hour bars. It does not run a long path and it does
not use a fixed `trade_size` loop. Each decision recalculates the target short
weight, converts that weight into BTC quantity from margin budget, leverage,
BTC price, and minimum lot size, then rebalances only when the target change is
large enough to matter.

The core idea is that BTC bearish regimes behave differently depending on
volatility. In cleaner low-volatility downtrends, the strategy can carry a
larger short target. In high-volatility bearish markets, it can still
participate with a smaller short target instead of staying fully flat, while
avoiding the drawdown risk of full-size exposure.

## Entry / 开仓

The strategy opens or increases short exposure when bearish alignment, weak
medium-term momentum, price location below longer references, rebound filtering,
and realized volatility confirm the setup. The low-volatility branch is the
main branch and can use the larger target. The high-volatility branch is a
reduced-size branch that only participates when bearish structure is still
valid.

## Exit / 平仓

The strategy exits by reducing the target short quantity. Short exposure is
reduced or closed when bearish alignment fades, the rebound filter invalidates
the setup, volatility leaves the intended regime, or the target weight falls
below the useful rebalance threshold. In backtest and follow-trade execution,
orders are target-position adjustments rather than isolated fixed-size entries.

## Parameters

Subscribers can tune leverage, margin budget, timeframe, aggressiveness,
weight scale, maximum signal weight, maximum effective exposure, maximum short
weight, trend lookbacks, short floor cap, volatility ceiling, and high-volatility
branch parameters. Higher leverage and exposure caps amplify both gains and
drawdowns. Lower caps make the strategy more defensive but may miss profitable
downside moves.

## Costs And Slippage

The package declares maker and taker fees in `backtest.yaml`, so GetAgent Cloud
can include exchange trading fees in replay. Live trading can also be affected
by bid-ask spread, slippage, funding rates, latency, partial fills, liquidation
constraints, and differences between replay candles and real execution.

## Risk / 风险

The main risks are sharp BTC rebounds, news gaps, choppy markets that briefly
look bearish and then reverse, high funding dislocation, and live execution
costs above the replay assumptions. Historical Cloud performance does not
guarantee live profitability.
