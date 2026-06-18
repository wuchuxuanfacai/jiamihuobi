# BTC Selective Trend Re-Entry Signal

## Strategy 策略

This Playbook trades BTCUSDT perpetual futures with one composite target
weight. It keeps the previously working GetAgent/Nautilus package structure,
but its defaults are tuned toward selective trend re-entry: short trend
re-entry is the main branch, the long branch is small and defensive, and range
mean reversion is only a constrained fallback.

The strategy uses replayable intraday futures OHLCV bars only. It does not use
local databases, API keys, private research files, direct exchange SDKs, or HTTP
clients.

## Entry 开仓

The short branch can open when bearish alignment, weak momentum, price location
below trend references, and rebound rejection are all present. Sizing is scaled
by realized volatility so that exposure falls when price action becomes too
unstable.

The long branch can open only when upside alignment is clean enough to support
a small defensive recovery exposure. It is intentionally capped below the short
side.

The range branch is active only when both trend reads are quiet, volatility is
low, and price is at a channel extreme. It should not fill every flat period.

## Exit 平仓

The strategy exits by reducing or removing the target weight. Short exposure
falls when bearish alignment fades, rebound pressure invalidates the setup, or
the market leaves the lower-risk volatility zone. Long exposure falls when
upside alignment weakens. Range exposure returns toward flat when price moves
away from the channel extreme or a clearer trend regime takes over.

The Cloud replay fetches pre-roll history before the trade window so trend and
volatility features are formed when trading begins. Orders in the backtest are
target adjustments rather than isolated fixed-size entries.

## Parameters

Subscribers can tune leverage, margin budget, timeframe, aggressiveness,
overall weight scale, maximum signal weight, maximum effective exposure,
maximum short weight, maximum long weight, trend lookbacks, caps, and
volatility filters.

Higher leverage amplifies both gains and drawdowns without making the signal
more selective. Margin budget controls the capital base used by the platform
for sizing and return interpretation. Higher weight scale and exposure caps
allow larger trades in confirmed regimes; lower values make the strategy more
defensive.

## Reading Returns

The strategy card's total return is the portfolio result on the declared
strategy margin budget after closed-trade PnL and fees. Individual trade rows
can show different percentages because each row is tied to one round trip, not
the full strategy equity curve.

## Risk 风险

The main risks are sharp BTC reversals, choppy ranges that repeatedly flip
regime, major news gaps, unstable liquidity, high funding dislocation, and live
execution costs that exceed replay assumptions. Historical results do not
guarantee live profitability.

