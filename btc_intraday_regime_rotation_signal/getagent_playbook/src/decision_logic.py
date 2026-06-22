from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass
class SignalState:
    target_weight: float
    action: str
    confidence: float
    regime: str
    metrics: dict[str, Any]


def _as_float(value: Any, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if not np.isfinite(parsed):
        return default
    return parsed


def _as_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _window(config: dict[str, Any], direct_key: str, days_key: str, bars_per_day: float, minimum: int) -> int:
    if direct_key in config:
        return max(minimum, _as_int(config.get(direct_key), minimum))
    return max(minimum, int(round(_as_float(config.get(days_key), minimum / max(bars_per_day, 1e-9)) * bars_per_day)))


def _clip(value: float, low: float, high: float) -> float:
    return float(min(high, max(low, value)))


def compute_signal_state(closes: Any, config: dict[str, Any], bars_per_day: float = 6.0) -> SignalState:
    values = np.asarray(closes, dtype=float)
    fast_window = _window(config, "fast_window", "fast_trend_days", bars_per_day, 3)
    mid_window = _window(config, "mid_window", "mid_trend_days", bars_per_day, 6)
    slow_window = _window(config, "slow_window", "slow_trend_days", bars_per_day, 12)
    long_window = _window(config, "long_window", "long_trend_days", bars_per_day, 24)
    vol_window = _window(config, "vol_window", "vol_days", bars_per_day, 6)
    required_rows = max(fast_window, mid_window, slow_window, vol_window) + 2
    if len(values) < required_rows:
        return SignalState(
            target_weight=0.0,
            action="watch",
            confidence=0.0,
            regime="warmup",
            metrics={"rows": int(len(values)), "required_rows": int(required_rows), "reason_code": 1},
        )

    latest = float(values[-1])
    long_rows_used = min(long_window, len(values))
    sma_fast = float(np.mean(values[-fast_window:]))
    sma_mid = float(np.mean(values[-mid_window:]))
    sma_slow = float(np.mean(values[-slow_window:]))
    sma_long = float(np.mean(values[-long_rows_used:]))
    ret_fast = latest / float(values[-fast_window]) - 1.0
    ret_mid = latest / float(values[-mid_window]) - 1.0
    ret_slow = latest / float(values[-slow_window]) - 1.0
    vol_slice = values[-(vol_window + 1) :]
    vol_returns = np.diff(vol_slice) / np.maximum(vol_slice[:-1], 1e-9)
    realized_vol = float(np.std(vol_returns) * np.sqrt(365.0 * bars_per_day)) if len(vol_returns) else 9.0

    price_std = float(np.std(values[-mid_window:]))
    channel_z = (latest - sma_mid) / max(price_std, latest * 1e-6)
    slope_window = min(_as_int(config.get("channel_slope_window"), max(6, mid_window // 2)), len(values) - mid_window - 1)
    if slope_window > 0:
        prev_mid = float(np.mean(values[-(mid_window + slope_window) : -slope_window]))
        channel_slope = sma_mid / max(prev_mid, 1e-9) - 1.0
    else:
        channel_slope = 0.0

    trend_strength = (
        float(latest > sma_fast)
        + float(latest > sma_mid)
        + float(latest > sma_slow)
        + float(sma_fast > sma_mid)
        + float(sma_mid > sma_slow)
        + float(ret_mid > 0.0)
        + float(ret_slow > 0.0)
    ) / 7.0
    bear_strength = (
        float(latest < sma_fast)
        + float(latest < sma_mid)
        + float(latest < sma_slow)
        + float(sma_fast < sma_mid)
        + float(sma_mid < sma_slow)
        + float(ret_mid < 0.0)
        + float(ret_slow < 0.0)
    ) / 7.0

    aggr = max(_as_float(config.get("aggressiveness"), 1.0), 0.1)
    weight_scale = _clip(_as_float(config.get("weight_scale"), 1.75), 0.1, 2.0)
    max_signal_weight = _clip(_as_float(config.get("max_signal_weight"), 1.0), 0.01, 3.0)
    max_short_weight = _clip(_as_float(config.get("max_short_weight"), 1.0), 0.0, max_signal_weight)
    max_long_weight = _clip(_as_float(config.get("max_long_weight"), 0.10), 0.0, max_signal_weight)
    safe_vol = max(realized_vol, _as_float(config.get("vol_floor_min"), 0.20))
    trend_invalidation_off = _as_float(config.get("trend_invalidation_off"), 0.30)

    weak_momentum = (
        ret_mid < _as_float(config.get("ret_mid_max"), -0.04)
        or ret_slow < _as_float(config.get("ret_slow_max"), -0.08)
        or latest < sma_mid * _as_float(config.get("mid_sma_mult"), 1.0)
    )
    rebound_blocked = (
        ret_fast > _as_float(config.get("rebound_ret_max"), 0.08)
        and latest > sma_fast * _as_float(config.get("rebound_sma_mult"), 1.005)
    )

    bear_on = _as_float(config.get("bear_on"), 0.56) / aggr
    short_ok = (
        max_short_weight > 0.0
        and bear_strength >= bear_on
        and weak_momentum
        and latest < sma_long * _as_float(config.get("short_sma_mult"), 0.98)
        and latest < sma_slow
        and not rebound_blocked
        and realized_vol <= _as_float(config.get("vol_ceiling"), 0.45)
    )
    bear_conf = _clip((bear_strength - bear_on) / max(1.0 - bear_on, 1e-9), 0.0, 1.0)
    trend_short_base = (
        -min(
            _as_float(config.get("short_floor_cap"), 1.0),
            (_as_float(config.get("short_target_vol"), 0.35) / safe_vol)
            * (_as_float(config.get("short_base"), 0.65) + _as_float(config.get("short_conf"), 0.55) * bear_conf),
        )
        if short_ok
        else 0.0
    )

    long_on = _as_float(config.get("long_on"), 0.68)
    long_ok = (
        max_long_weight > 0.0
        and trend_strength >= long_on
        and ret_mid > _as_float(config.get("long_ret_mid_min"), 0.0)
        and latest > sma_long * _as_float(config.get("long_sma_mult"), 1.02)
        and latest > sma_slow
        and realized_vol <= _as_float(config.get("long_vol_ceiling"), 0.45)
    )
    long_conf = _clip((trend_strength - long_on) / max(1.0 - long_on, 1e-9), 0.0, 1.0)
    trend_long_base = (
        min(_as_float(config.get("long_floor_cap"), 0.10), max_long_weight) * (0.5 + 0.5 * long_conf)
        if long_ok
        else 0.0
    )

    range_mean_reversion = 0.0
    trend_base_active = bool(trend_long_base or trend_short_base)
    range_ok = (
        not trend_base_active
        and trend_strength <= _as_float(config.get("range_trend_max"), 0.30)
        and bear_strength <= _as_float(config.get("range_bear_max"), 0.30)
        and realized_vol <= _as_float(config.get("range_vol_ceiling"), 0.28)
        and abs(channel_slope) <= _as_float(config.get("range_abs_slope_max"), 0.012)
        and abs(ret_slow) <= _as_float(config.get("range_ret_slow_abs_max"), 0.08)
    )
    if range_ok:
        range_entry = max(_as_float(config.get("range_z_entry"), 1.50), 0.1)
        range_cap = _as_float(config.get("range_mr_cap"), 0.02)
        if channel_z <= -range_entry:
            depth = _clip((abs(channel_z) - range_entry) / max(range_entry, 1e-9), 0.0, 1.0)
            range_mean_reversion = min(range_cap, range_cap * (0.35 + 0.65 * depth))
        elif channel_z >= range_entry:
            depth = _clip((abs(channel_z) - range_entry) / max(range_entry, 1e-9), 0.0, 1.0)
            range_mean_reversion = -min(range_cap, range_cap * (0.35 + 0.65 * depth))

    raw_sum = trend_long_base + trend_short_base + range_mean_reversion
    target_weight = _clip(raw_sum * weight_scale, -max_short_weight, max_long_weight)
    if target_weight > 0.0 and trend_strength < trend_invalidation_off:
        target_weight = 0.0
    elif target_weight < 0.0 and bear_strength < trend_invalidation_off:
        target_weight = 0.0
    if abs(target_weight) < _as_float(config.get("target_step_weight"), 0.06):
        target_weight = 0.0

    if target_weight > 0.0:
        action = "long"
        confidence = min(0.95, 0.50 + 0.45 * trend_strength)
    elif target_weight < 0.0:
        action = "short"
        confidence = min(0.95, 0.50 + 0.45 * bear_strength)
    else:
        action = "hold"
        confidence = 0.50

    active = []
    if trend_long_base:
        active.append("long_base")
    if trend_short_base:
        active.append("short_base")
    if range_mean_reversion:
        active.append("range_mr")
    regime = "+".join(active) if active else "neutral"

    return SignalState(
        target_weight=float(target_weight),
        action=action,
        confidence=float(confidence),
        regime=regime,
        metrics={
            "rows": int(len(values)),
            "last_close": latest,
            "trend_strength": trend_strength,
            "bear_strength": bear_strength,
            "ret_fast": ret_fast,
            "ret_mid": ret_mid,
            "ret_slow": ret_slow,
            "sma_fast": sma_fast,
            "sma_mid": sma_mid,
            "sma_slow": sma_slow,
            "sma_long": sma_long,
            "realized_vol_ann": realized_vol,
            "channel_z": channel_z,
            "channel_slope": channel_slope,
            "fast_window": int(fast_window),
            "mid_window": int(mid_window),
            "slow_window": int(slow_window),
            "long_window": int(long_window),
            "long_rows_used": int(long_rows_used),
            "vol_window": int(vol_window),
            "trend_long_base": trend_long_base,
            "trend_short_base": trend_short_base,
            "range_mean_reversion": range_mean_reversion,
            "raw_component_sum": raw_sum,
            "weight_scale": weight_scale,
            "target_weight": target_weight,
            "weak_momentum": bool(weak_momentum),
            "rebound_blocked": bool(rebound_blocked),
            "short_ok": bool(short_ok),
            "long_ok": bool(long_ok),
            "range_ok": bool(range_ok),
        },
    )
