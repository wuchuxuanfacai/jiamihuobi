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


def _rolling_days(value: Any, bars_per_day: float, minimum: int) -> int:
    return max(minimum, int(round(_as_float(value, 1.0) * bars_per_day)))


def load_intraday_bars(symbol: str, interval: str = "4h", days: int = 180) -> pd.DataFrame:
    bars = data.crypto.futures.kline(
        symbol=symbol,
        interval=interval,
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
    interval = str(config.get("timeframe") or "4h")
    bars_per_day = 6.0 if interval == "4h" else 24.0 if interval == "1h" else 96.0
    fast_window = _rolling_days(config.get("fast_trend_days"), bars_per_day, 3)
    mid_window = _rolling_days(config.get("mid_trend_days"), bars_per_day, 6)
    slow_window = _rolling_days(config.get("slow_trend_days"), bars_per_day, 12)
    long_window = _rolling_days(config.get("long_trend_days"), bars_per_day, 24)
    vol_window = _rolling_days(config.get("vol_days"), bars_per_day, 6)
    min_rows = long_window + 5

    if len(frame) < min_rows:
        return Decision(
            action="watch",
            confidence=0.0,
            target_weight=0.0,
            metrics={"rows": int(len(frame)), "required_rows": int(min_rows), "reason_code": 1},
            meta={"reason": "not enough intraday bars for short-trend regime checks"},
        )

    close = frame["close"].astype(float)
    ret = close.pct_change().fillna(0.0)
    last_close = float(close.iloc[-1])

    sma_fast = close.rolling(fast_window).mean()
    sma_mid = close.rolling(mid_window).mean()
    sma_slow = close.rolling(slow_window).mean()
    sma_long = close.rolling(long_window).mean()
    ret_fast = close.pct_change(fast_window)
    ret_mid = close.pct_change(mid_window)
    ret_slow = close.pct_change(slow_window)
    realized_vol = ret.rolling(vol_window).std() * np.sqrt(365.0 * bars_per_day)

    trend_strength = (
        (close > sma_fast).astype(float)
        + (close > sma_mid).astype(float)
        + (close > sma_slow).astype(float)
        + (sma_fast > sma_mid).astype(float)
        + (sma_mid > sma_slow).astype(float)
        + (ret_mid > 0).astype(float)
        + (ret_slow > 0).astype(float)
    ) / 7.0
    bear_strength = (
        (close < sma_fast).astype(float)
        + (close < sma_mid).astype(float)
        + (close < sma_slow).astype(float)
        + (sma_fast < sma_mid).astype(float)
        + (sma_mid < sma_slow).astype(float)
        + (ret_mid < 0).astype(float)
        + (ret_slow < 0).astype(float)
    ) / 7.0

    aggr = max(_as_float(config.get("aggressiveness"), 1.0), 0.1)
    weight_scale = min(max(_as_float(config.get("weight_scale"), 1.4), 0.1), 2.0)
    max_signal_weight = min(max(_as_float(config.get("max_signal_weight"), 1.4), 0.01), 2.0)
    max_short_weight = min(max(_as_float(config.get("max_short_weight"), 1.4), 0.0), max_signal_weight)
    max_long_weight = min(max(_as_float(config.get("max_long_weight"), 0.14), 0.0), max_signal_weight)
    short_cap = min(max(_as_float(config.get("short_floor_cap"), 1.0), 0.0), max_short_weight)
    short_target_vol = min(max(_as_float(config.get("short_target_vol"), 0.35), 0.01), 1.20)
    long_cap = min(max(_as_float(config.get("long_floor_cap"), 0.10), 0.0), max_long_weight)
    long_target_vol = min(max(_as_float(config.get("long_target_vol"), 0.16), 0.0), 0.50)
    vol = max(_as_float(realized_vol.iloc[-1], 0.20), _as_float(config.get("vol_floor_min"), 0.20))

    latest_bear = _as_float(bear_strength.iloc[-1], 0.0)
    latest_trend = _as_float(trend_strength.iloc[-1], 0.0)
    latest_ret_fast = _as_float(ret_fast.iloc[-1], 0.0)
    latest_ret_mid = _as_float(ret_mid.iloc[-1], 0.0)
    latest_ret_slow = _as_float(ret_slow.iloc[-1], 0.0)
    latest_sma_fast = _as_float(sma_fast.iloc[-1], last_close)
    latest_sma_mid = _as_float(sma_mid.iloc[-1], last_close)
    latest_sma_long = _as_float(sma_long.iloc[-1], last_close)

    bear_threshold = _as_float(config.get("bear_on"), 0.56) / aggr
    short_ok = (
        max_short_weight > 0.0
        and latest_bear >= bear_threshold
        and latest_ret_slow < _as_float(config.get("ret_slow_max"), -0.08)
        and latest_ret_mid < _as_float(config.get("ret_mid_max"), -0.04)
        and last_close < latest_sma_long * _as_float(config.get("short_sma_mult"), 0.98)
        and last_close < latest_sma_fast * _as_float(config.get("fast_sma_mult"), 1.00)
        and latest_ret_fast < _as_float(config.get("rebound_ret_max"), 0.08)
        and vol <= _as_float(config.get("vol_ceiling"), 9.0)
    )
    trend_threshold = _as_float(config.get("trend_on"), 0.68) / aggr
    long_ok = (
        max_long_weight > 0.0
        and latest_trend >= trend_threshold
        and latest_ret_slow > _as_float(config.get("ret_slow_min"), 0.0)
        and latest_ret_mid > _as_float(config.get("ret_mid_min"), 0.0)
        and last_close > latest_sma_long * _as_float(config.get("long_sma_mult"), 1.02)
        and vol <= _as_float(config.get("vol_ceiling"), 9.0)
    )

    bear_conf = min(1.0, max(0.0, (latest_bear - bear_threshold) / max(1.0 - bear_threshold, 1e-9)))
    long_conf = min(1.0, max(0.0, (latest_trend - trend_threshold) / max(1.0 - trend_threshold, 1e-9)))
    short_base = _as_float(config.get("short_base"), 0.65)
    short_conf = _as_float(config.get("short_conf"), 0.55)
    short_floor = -min(short_cap, (short_target_vol / vol) * (short_base + short_conf * bear_conf)) if short_ok else 0.0
    long_floor = min(long_cap, (long_target_vol / vol) * (0.45 + 0.55 * long_conf)) if long_ok else 0.0

    raw_target = float(np.clip((short_floor + long_floor) * weight_scale, -max_short_weight, max_long_weight))
    if short_ok and not long_ok:
        action = "short"
        confidence = min(0.95, 0.50 + 0.45 * latest_bear)
        regime = "short_trend_floor"
    elif long_ok and not short_ok:
        action = "long"
        confidence = min(0.95, 0.50 + 0.45 * latest_trend)
        regime = "countertrend_long_filter"
    else:
        action = "hold"
        confidence = 0.50
        raw_target = 0.0
        regime = "neutral"

    metrics = {
        "rows": int(len(frame)),
        "last_close": last_close,
        "trend_strength": latest_trend,
        "bear_strength": latest_bear,
        "ret_fast": latest_ret_fast,
        "ret_mid": latest_ret_mid,
        "ret_slow": latest_ret_slow,
        "sma_fast": latest_sma_fast,
        "sma_mid": latest_sma_mid,
        "sma_long": latest_sma_long,
        "realized_vol_ann": vol,
        "fast_window": int(fast_window),
        "mid_window": int(mid_window),
        "slow_window": int(slow_window),
        "long_window": int(long_window),
        "short_trend_floor": short_floor,
        "long_trend_floor": long_floor,
        "weight_scale": weight_scale,
        "target_weight": raw_target,
    }
    meta = {
        "regime": regime,
        "timeframe": interval,
        "source": "btc-adaptive-short-trend-floor",
        "latest_bar_time": str(frame.index[-1]),
        "notes": "Signal-only BTC futures model. The default is a volatility-scaled short trend floor with rebound and trend-regime filters.",
    }
    return Decision(action=action, confidence=float(confidence), target_weight=raw_target, metrics=metrics, meta=meta)
