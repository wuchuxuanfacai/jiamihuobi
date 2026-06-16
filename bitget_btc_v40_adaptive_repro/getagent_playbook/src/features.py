from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from getagent import data


@dataclass
class Decision:
    action: str
    confidence: float
    target_weight: float
    metrics: dict[str, Any]
    meta: dict[str, Any]


def _as_float(value: Any, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if not np.isfinite(parsed):
        return default
    return parsed


def load_daily_bars(symbol: str, days: int = 90) -> pd.DataFrame:
    bars = data.crypto.futures.kline(
        symbol=symbol,
        interval="1d",
        exchange="bitget",
        days=days,
        limit=1000,
    )
    frame = data.to_dataframe(bars)
    if frame.empty:
        return frame
    if "date" in frame.columns:
        frame.index = pd.to_datetime(frame["date"], utc=True, errors="coerce")
    elif "time" in frame.columns:
        frame.index = pd.to_datetime(frame["time"], utc=True, errors="coerce")
    frame = frame.loc[frame.index.notna()].copy()
    frame = frame.sort_index()
    for col in ["open", "high", "low", "close", "volume"]:
        if col in frame.columns:
            frame[col] = pd.to_numeric(frame[col], errors="coerce")
    return frame.dropna(subset=["close"])


def build_decision(frame: pd.DataFrame, config: dict[str, Any]) -> Decision:
    if len(frame) < 65:
        return Decision(
            action="watch",
            confidence=0.0,
            target_weight=0.0,
            metrics={"rows": int(len(frame)), "reason_code": 1},
            meta={"reason": "not enough daily bars for V40-style regime checks"},
        )

    close = frame["close"].astype(float)
    ret = close.pct_change().fillna(0.0)
    last_close = float(close.iloc[-1])

    sma20 = close.rolling(20).mean()
    sma50 = close.rolling(50).mean()
    sma63 = close.rolling(63).mean()
    ret20 = close.pct_change(20)
    ret63 = close.pct_change(63)
    realized_vol = ret.rolling(20).std() * np.sqrt(365)

    trend_strength = (
        (close > sma20).astype(float)
        + (close > sma50).astype(float)
        + (sma20 > sma50).astype(float)
        + (ret20 > 0).astype(float)
        + (ret63 > 0).astype(float)
    ) / 5.0
    bear_strength = (
        (close < sma20).astype(float)
        + (close < sma50).astype(float)
        + (sma20 < sma50).astype(float)
        + (ret20 < 0).astype(float)
        + (ret63 < 0).astype(float)
    ) / 5.0

    aggr = _as_float(config.get("aggressiveness"), 1.0)
    max_signal_weight = min(max(_as_float(config.get("max_signal_weight"), 0.05), 0.01), 0.15)
    vol = max(_as_float(realized_vol.iloc[-1], 0.20), 0.08)

    bull_threshold = 0.70 / aggr
    bear_threshold = 0.70 / aggr
    latest_trend = _as_float(trend_strength.iloc[-1], 0.0)
    latest_bear = _as_float(bear_strength.iloc[-1], 0.0)
    latest_ret20 = _as_float(ret20.iloc[-1], 0.0)
    latest_ret63 = _as_float(ret63.iloc[-1], 0.0)
    latest_sma63 = _as_float(sma63.iloc[-1], last_close)

    long_ok = (
        latest_trend >= bull_threshold
        and latest_ret63 > 0.0
        and last_close > latest_sma63
    )
    short_ok = (
        latest_bear >= bear_threshold
        and latest_ret63 < 0.0
        and last_close < latest_sma63
    )

    vol_scaled_weight = min(max_signal_weight, max_signal_weight * min(1.0, 0.20 / vol))
    if long_ok and not short_ok:
        action = "long"
        confidence = min(0.95, 0.50 + 0.45 * latest_trend)
        target_weight = vol_scaled_weight
        regime = "trend_floor"
    elif short_ok and not long_ok:
        action = "short"
        confidence = min(0.95, 0.50 + 0.45 * latest_bear)
        target_weight = -vol_scaled_weight
        regime = "short_trend_floor"
    else:
        action = "hold"
        confidence = 0.50
        target_weight = 0.0
        regime = "neutral"

    metrics = {
        "rows": int(len(frame)),
        "last_close": last_close,
        "trend_strength": latest_trend,
        "bear_strength": latest_bear,
        "ret20": latest_ret20,
        "ret63": latest_ret63,
        "realized_vol_20d_ann": vol,
        "target_weight": target_weight,
    }
    meta = {
        "regime": regime,
        "source": "v40-adapted-price-structure",
        "latest_bar_time": str(frame.index[-1]),
        "notes": "Signal-only adaptation of the local V40 model using sandbox-replayable BTC daily futures bars.",
    }
    return Decision(
        action=action,
        confidence=float(confidence),
        target_weight=float(target_weight),
        metrics=metrics,
        meta=meta,
    )
