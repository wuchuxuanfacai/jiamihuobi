# BTC V40 Adaptive Trend Signal

## 策略

This Playbook is a BTC perpetual futures signal adapted from the local V40 multi-cycle research model. The original research model used private local databases, cross-asset features, derivatives context, and frozen model artifacts. This package keeps the part that can be reproduced honestly inside GetAgent: BTC price structure, trend alignment, bearish regime detection, realized volatility, and conservative target signal weight.

The strategy tries to capture two market behaviors. First, it can participate when BTC has a persistent upside trend and price structure confirms that the move is broad rather than a one-day bounce. Second, it can emit a small short signal when BTC remains in a defensive bearish regime. When the market is mixed, it stays flat or holds instead of forcing a trade.

## 开仓

The Playbook opens a long signal when the daily BTC structure shows bullish trend alignment, positive medium-term momentum, and price holding above its broader trend reference. It opens a short signal when the same structure turns defensive: price is below major trend references, medium-term return is negative, and the bearish score is high enough to justify a small defensive short floor.

The signal is intentionally capped. It is designed as a modest directional overlay, not an all-in leverage strategy. The emitted metadata includes the latest close, trend score, bear score, recent return, realized volatility, and target signal weight so the user can see why the signal was produced.

## 平仓

A long signal closes when upside confirmation fades or the market no longer satisfies the trend regime. A short signal closes when bearish confirmation fades or the market recovers into a healthier structure. The Playbook does not use fixed take profit or stop loss orders in this signal-only version. Its main risk control is regime withdrawal, volatility-aware sizing, and a hard cap on target exposure.

## 参数说明

Subscribers may tune leverage, margin budget, and signal aggressiveness. Leverage amplifies both gains and drawdowns equally; it does not make signals more accurate. Margin budget is the capital base used by the platform for strategy sizing and return interpretation. Aggressiveness controls how readily the strategy acts on regime evidence: raising it makes signals easier to trigger, while lowering it makes the model more selective.

## 回测指标如何读

This package is marked `backtest_support: none` because the original V40 research result depends on local datasets and frozen model artifacts that cannot be honestly replayed inside the current GetAgent sandbox. Local research context for V40 showed outer-test return of about 12.81%, Sharpe around 1.41, and maximum drawdown around 3.80% over the research window, but those numbers are not claimed as platform backtest evidence for this simplified package.

## 风险

The strategy can lose money in sharp V-shaped rebounds, news-driven gaps, sideways ranges, and sudden regime changes. The defensive short floor can remain active during relief rallies, while trend signals can be late after fast reversals. Past local research performance is not a guarantee of live profitability. Use conservative sizing, expect drawdown, and treat the signal as decision support rather than a promise of profit.
