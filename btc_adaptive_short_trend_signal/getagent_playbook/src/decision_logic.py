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


def compute_signal_state(
    closes: Any,
    config: dict[str, Any],
    bars_per_day: float = 6.0,
) -> SignalState:
    values = np.asarray(closes, dtype=float)
    fast_window = _window(config, "fast_window", "fast_trend_days", bars_per_day, 3)
    mid_window = _window(config, "mid_window", "mid_trend_days", bars_per_day, 6)
    slow_window = _window(config, "slow_window", "slow_trend_days", bars_per_day, 12)
    long_window = _window(config, "long_window", "long_trend_days", bars_per_day, 24)
    vol_window = _window(config, "vol_window", "vol_days", bars_per_day, 6)
    required_rows = max(fast_window, mid_window, slow_window, long_window, vol_window) + 2
    if len(values) < required_rows:
        return SignalState(
            target_weight=0.0,
            action="watch",
            confidence=0.0,
            regime="warmup",
            metrics={
                "rows": int(len(values)),
                "required_rows": int(required_rows),
                "reason_code": 1,
            },
        )

    latest = float(values[-1])
    sma_fast = float(np.mean(values[-fast_window:]))
    sma_mid = float(np.mean(values[-mid_window:]))
    sma_slow = float(np.mean(values[-slow_window:]))
    sma_long = float(np.mean(values[-long_window:]))
    ret_fast = latest / float(values[-fast_window]) - 1.0
    ret_mid = latest / float(values[-mid_window]) - 1.0
    ret_slow = latest / float(values[-slow_window]) - 1.0
    vol_slice = values[-(vol_window + 1) :]
    vol_returns = np.diff(vol_slice) / vol_slice[:-1]
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
    weight_scale = _clip(_as_float(config.get("weight_scale"), 1.2), 0.1, 2.0)
    max_signal_weight = _clip(_as_float(config.get("max_signal_weight"), 1.6), 0.01, 3.0)
    max_short_weight = _clip(_as_float(config.get("max_short_weight"), 1.6), 0.0, max_signal_weight)
    max_long_weight = _clip(_as_float(config.get("max_long_weight"), 0.50), 0.0, max_signal_weight)
    safe_vol = max(realized_vol, _as_float(config.get("vol_floor_min"), 0.20))

    weak_momentum = (
        ret_mid < _as_float(config.get("ret_mid_max"), 0.01)
        or ret_slow < _as_float(config.get("ret_slow_max"), -0.04)
        or latest < sma_mid * _as_float(config.get("mid_sma_mult"), 1.0)
    )
    rebound_blocked = (
        ret_fast > _as_float(config.get("rebound_ret_max"), 0.04)
        and latest > sma_fast * _as_float(config.get("rebound_sma_mult"), 1.005)
    )

    bear_on = _as_float(config.get("bear_on"), 0.42) / aggr
    short_ok = (
        max_short_weight > 0.0
        and bear_strength >= bear_on
        and weak_momentum
        and latest < sma_long * _as_float(config.get("short_sma_mult"), 1.03)
        and not rebound_blocked
        and realized_vol <= _as_float(config.get("vol_ceiling"), 0.35)
    )
    bear_conf = _clip((bear_strength - bear_on) / max(1.0 - bear_on, 1e-9), 0.0, 1.0)
    trend_short_base = (
        -min(
            _as_float(config.get("short_floor_cap"), 1.6),
            (_as_float(config.get("short_target_vol"), 1.20) / safe_vol)
            * (_as_float(config.get("short_base"), 0.65) + _as_float(config.get("short_conf"), 0.55) * bear_conf),
        )
        if short_ok
        else 0.0
    )

    high_vol_bear_on = _as_float(config.get("high_vol_bear_on"), 0.42)
    high_vol_short_ok = (
        max_short_weight > 0.0
        and realized_vol > _as_float(config.get("high_vol_floor"), 0.40)
        and realized_vol <= _as_float(config.get("high_vol_ceiling"), 0.55)
        and bear_strength >= high_vol_bear_on
        and weak_momentum
        and latest < sma_long * _as_float(config.get("high_vol_sma_mult"), 1.02)
        and not rebound_blocked
    )
    breakdown_ok = (
        bear_strength >= _as_float(config.get("dynamic_short_bear_on"), 0.56)
        and ret_fast < _as_float(config.get("short_accel_ret_max"), -0.015)
        and latest < sma_fast
    )
    upthrust_ok = (
        bear_strength >= _as_float(config.get("dynamic_short_bear_on"), 0.56)
        and channel_z >= _as_float(config.get("short_rebound_z"), 0.70)
        and latest < sma_long * _as_float(config.get("dynamic_short_sma_mult"), 1.02)
    )
    high_vol_conf = _clip((bear_strength - high_vol_bear_on) / max(1.0 - high_vol_bear_on, 1e-9), 0.0, 1.0)
    trend_short_dynamic = 0.0
    if high_vol_short_ok or breakdown_ok or upthrust_ok:
        dynamic_cap = _as_float(config.get("dynamic_short_cap"), 0.45)
        high_vol_cap = _as_float(config.get("high_vol_short_cap"), 1.0) if high_vol_short_ok else dynamic_cap
        dynamic_target_vol = _as_float(config.get("high_vol_target_vol"), 0.50) if high_vol_short_ok else _as_float(config.get("dynamic_short_target_vol"), 0.65)
        dynamic_base = _as_float(config.get("high_vol_short_base"), 0.65) if high_vol_short_ok else _as_float(config.get("dynamic_short_base"), 0.25)
        dynamic_conf = _as_float(config.get("high_vol_short_conf"), 0.0) if high_vol_short_ok else _as_float(config.get("dynamic_short_conf"), 0.35)
        trend_short_dynamic = -min(
            high_vol_cap,
            (dynamic_target_vol / safe_vol) * (dynamic_base + dynamic_conf * max(high_vol_conf, bear_conf)),
        )

    long_on = _as_float(config.get("long_on"), 0.50)
    long_ok = (
        max_long_weight > 0.0
        and trend_strength >= long_on
        and ret_mid > _as_float(config.get("long_ret_mid_min"), 0.01)
        and latest > sma_long * _as_float(config.get("long_sma_mult"), 1.0)
        and realized_vol <= _as_float(config.get("long_vol_ceiling"), 0.45)
    )
    long_conf = _clip((trend_strength - long_on) / max(1.0 - long_on, 1e-9), 0.0, 1.0)
    trend_long_base = (
        min(_as_float(config.get("long_floor_cap"), 0.50), max_long_weight) * (0.5 + 0.5 * long_conf)
        if long_ok
        else 0.0
    )

    long_trend_ok = (
        max_long_weight > 0.0
        and trend_strength >= _as_float(config.get("dynamic_long_trend_on"), 0.58)
        and latest > sma_long * _as_float(config.get("dynamic_long_sma_mult"), 0.995)
        and realized_vol <= _as_float(config.get("dynamic_long_vol_ceiling"), 0.55)
    )
    accel_long_ok = long_trend_ok and ret_fast > _as_float(config.get("long_accel_ret_min"), 0.015) and latest > sma_fast
    pullback_long_ok = (
        long_trend_ok
        and channel_z <= _as_float(config.get("long_pullback_z"), -0.80)
        and ret_mid > _as_float(config.get("long_pullback_ret_mid_min"), -0.015)
        and latest > sma_slow * _as_float(config.get("long_pullback_slow_mult"), 0.97)
    )
    trend_long_dynamic = 0.0
    if accel_long_ok or pullback_long_ok:
        dyn_conf = max(long_conf, _clip((trend_strength - 0.5) / 0.5, 0.0, 1.0))
        trend_long_dynamic = min(
            _as_float(config.get("dynamic_long_cap"), 0.35),
            (_as_float(config.get("dynamic_long_target_vol"), 0.55) / safe_vol)
            * (_as_float(config.get("dynamic_long_base"), 0.18) + _as_float(config.get("dynamic_long_conf"), 0.32) * dyn_conf),
        )

    range_mean_reversion = 0.0
    range_ok = (
        trend_strength <= _as_float(config.get("range_trend_max"), 0.62)
        and bear_strength <= _as_float(config.get("range_bear_max"), 0.62)
        and realized_vol <= _as_float(config.get("range_vol_ceiling"), 0.50)
    )
    if range_ok:
        range_entry = max(_as_float(config.get("range_z_entry"), 0.85), 0.1)
        slope_deadband = _as_float(config.get("channel_slope_deadband"), 0.01)
        bias_strength = _clip(_as_float(config.get("range_bias_strength"), 0.25), 0.0, 0.75)
        long_entry = range_entry * (1.0 - bias_strength if channel_slope > slope_deadband else 1.0)
        short_entry = range_entry * (1.0 - bias_strength if channel_slope < -slope_deadband else 1.0)
        long_size_mult = 1.0 + bias_strength if channel_slope > slope_deadband else 1.0
        short_size_mult = 1.0 + bias_strength if channel_slope < -slope_deadband else 1.0
        range_cap = _as_float(config.get("range_mr_cap"), 0.25)
        if channel_z <= -long_entry:
            depth = _clip((abs(channel_z) - long_entry) / max(range_entry, 1e-9), 0.0, 1.0)
            range_mean_reversion = min(range_cap * long_size_mult, range_cap * (0.35 + 0.65 * depth) * long_size_mult)
        elif channel_z >= short_entry:
            depth = _clip((abs(channel_z) - short_entry) / max(range_entry, 1e-9), 0.0, 1.0)
            range_mean_reversion = -min(range_cap * short_size_mult, range_cap * (0.35 + 0.65 * depth) * short_size_mult)

    raw_sum = trend_long_base + trend_long_dynamic + trend_short_base + trend_short_dynamic + range_mean_reversion
    target_weight = _clip(raw_sum * weight_scale, -max_short_weight, max_long_weight)
    if abs(target_weight) < _as_float(config.get("target_step_weight"), 0.02):
        target_weight = 0.0

    if target_weight > 0.0:
        action = "long"
        confidence = min(0.95, 0.50 + 0.45 * max(trend_strength, abs(range_mean_reversion) / max(_as_float(config.get("range_mr_cap"), 0.25), 1e-9)))
    elif target_weight < 0.0:
        action = "short"
        confidence = min(0.95, 0.50 + 0.45 * max(bear_strength, abs(range_mean_reversion) / max(_as_float(config.get("range_mr_cap"), 0.25), 1e-9)))
    else:
        action = "hold"
        confidence = 0.50

    active = []
    if trend_long_base:
        active.append("long_base")
    if trend_long_dynamic:
        active.append("long_dynamic")
    if trend_short_base:
        active.append("short_base")
    if trend_short_dynamic:
        active.append("short_dynamic")
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
            "vol_window": int(vol_window),
            "trend_long_base": trend_long_base,
            "trend_long_dynamic": trend_long_dynamic,
            "trend_short_base": trend_short_base,
            "trend_short_dynamic": trend_short_dynamic,
            "range_mean_reversion": range_mean_reversion,
            "raw_component_sum": raw_sum,
            "weight_scale": weight_scale,
            "target_weight": target_weight,
            "weak_momentum": bool(weak_momentum),
            "rebound_blocked": bool(rebound_blocked),
            "short_ok": bool(short_ok),
            "high_vol_short_ok": bool(high_vol_short_ok),
            "long_ok": bool(long_ok),
            "accel_long_ok": bool(accel_long_ok),
            "pullback_long_ok": bool(pullback_long_ok),
            "breakdown_short_ok": bool(breakdown_ok),
            "upthrust_short_ok": bool(upthrust_ok),
            "range_ok": bool(range_ok),
        },
    )
