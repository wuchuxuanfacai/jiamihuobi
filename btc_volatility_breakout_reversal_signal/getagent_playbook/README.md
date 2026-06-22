# BTC Volatility Breakout Reversal Signal

This Playbook trades BTCUSDT perpetual futures with a deterministic volatility
breakout and pullback-reversal model. It uses intraday BTC futures bars as the
execution feed and recalculates a target position from price action, trend
alignment, recent channel position, momentum, and realized volatility.

## How It Enters

The strategy can open long when the market is already in an upward regime and
price confirms a breakout above its recent range. It can also open a smaller
long when a bullish regime pulls back in a controlled way. On the short side,
it can open after a bearish breakdown or after a controlled rebound inside a
falling regime.

## How It Exits

The Playbook does not use a single fixed take-profit label. It continuously
computes a target position. When the breakout weakens, the trend regime fades,
volatility becomes unattractive, or a pullback no longer has the right shape,
the target position shrinks or returns to flat. The follow-trade runtime then
adjusts the simulated position toward that target.

## Parameters

`leverage` changes notional exposure and amplifies both gains and drawdowns.
`margin_budget` is the capital base used for sizing and return interpretation.
`max_effective_exposure` limits leverage-adjusted notional exposure.
`max_long_weight` and `max_short_weight` cap directional exposure. `weight_scale`
changes overall aggressiveness. Trend, breakout, pullback, and volatility
parameters control how early or late the model reacts to market structure.

## Risk

The strategy can lose money during false breakouts, fast news reversals,
sideways markets with repeated failed triggers, or conditions where execution
costs exceed replay assumptions. Historical backtest results are not a
guarantee of future profitability.

## 中文摘要

本策略用于 BTCUSDT 永续合约，核心是用 15m K 线识别波动突破、趋势回撤和反弹后的继续走势。
开仓时，策略会同时检查趋势方向、近期通道、动量和波动率；当上涨结构确认时做多，当下跌结构确认时做空。
平仓时，策略不是固定止盈止损，而是根据目标仓位变化逐步减仓或回到空仓。
主要风险包括假突破、重大消息导致的急速反转、震荡区间反复打脸、手续费和滑点高于回测假设。
