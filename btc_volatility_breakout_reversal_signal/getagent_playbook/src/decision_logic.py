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
    return parsed if np.isfinite(parsed) else default


def _as_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _clip(value: float, low: float, high: float) -> float:
    return float(min(high, max(low, value)))


def compute_signal_state(closes: Any, config: dict[str, Any], bars_per_day: float = 96.0) -> SignalState:
    values = np.asarray(closes, dtype=float)
    squeeze_window = _as_int(config.get("squeeze_window"), 96)
    stretch_window = _as_int(config.get("stretch_window"), 32)
    trend_window = _as_int(config.get("trend_window"), 384)
    vol_window = _as_int(config.get("vol_window"), 96)
    required = max(squeeze_window, stretch_window, trend_window, vol_window) + 3
    if len(values) < required:
        return SignalState(0.0, "watch", 0.0, "warmup", {"rows": int(len(values)), "required_rows": int(required)})

    latest = float(values[-1])
    slow_mean = float(np.mean(values[-trend_window:]))
    squeeze_mean = float(np.mean(values[-squeeze_window:]))
    squeeze_std = float(np.std(values[-squeeze_window:]))
    z = (latest - squeeze_mean) / max(squeeze_std, latest * 1e-6)
    ret_stretch = latest / max(float(values[-stretch_window]), 1e-9) - 1.0
    ret_trend = latest / max(float(values[-trend_window]), 1e-9) - 1.0
    fast_ret = latest / max(float(values[-8]), 1e-9) - 1.0
    prev = values[:-1]
    recent_high = float(np.max(prev[-stretch_window:]))
    recent_low = float(np.min(prev[-stretch_window:]))

    returns = np.diff(values[-(vol_window + 1) :]) / np.maximum(values[-(vol_window + 1) : -1], 1e-9)
    realized_vol = float(np.std(returns) * np.sqrt(365.0 * bars_per_day)) if len(returns) else 9.0
    short_returns = returns[-max(8, vol_window // 4) :]
    short_vol = float(np.std(short_returns) * np.sqrt(365.0 * bars_per_day)) if len(short_returns) else 9.0
    vol_ratio = short_vol / max(realized_vol, 1e-9)

    overheat = (
        z >= _as_float(config.get("overheat_z"), 1.65)
        and ret_stretch >= _as_float(config.get("overheat_ret_min"), 0.035)
        and latest >= recent_high * _as_float(config.get("near_high_mult"), 0.995)
        and realized_vol <= _as_float(config.get("vol_ceiling"), 0.95)
    )
    turn_down = (
        fast_ret <= _as_float(config.get("turn_fast_ret_max"), -0.004)
        or latest < recent_high * _as_float(config.get("fade_from_high_mult"), 0.985)
        or vol_ratio >= _as_float(config.get("vol_expansion_min"), 1.08)
    )
    trend_block = ret_trend > _as_float(config.get("trend_block_ret"), 0.22) and latest > slow_mean

    washout = (
        z <= -_as_float(config.get("washout_z"), 1.85)
        and ret_stretch <= -_as_float(config.get("washout_ret_max"), 0.045)
        and latest <= recent_low * _as_float(config.get("near_low_mult"), 1.005)
        and realized_vol <= _as_float(config.get("long_vol_ceiling"), 0.90)
    )
    turn_up = fast_ret >= _as_float(config.get("turn_fast_ret_min"), 0.004) or latest > recent_low * _as_float(config.get("bounce_from_low_mult"), 1.015)

    max_short = _as_float(config.get("max_short_weight"), 1.0)
    max_long = _as_float(config.get("max_long_weight"), 0.12)
    max_signal = _as_float(config.get("max_signal_weight"), 1.0)
    weight_scale = _as_float(config.get("weight_scale"), 2.0)
    safe_vol = max(realized_vol, _as_float(config.get("vol_floor_min"), 0.20))

    target = 0.0
    regime = "neutral"
    if overheat and turn_down and not trend_block:
        depth = _clip((z - _as_float(config.get("overheat_z"), 1.65)) / 1.25, 0.0, 1.0)
        target = -min(max_short, (_as_float(config.get("short_target_vol"), 0.42) / safe_vol) * (0.45 + 0.55 * depth))
        regime = "overheat_short"
    elif washout and turn_up:
        depth = _clip((abs(z) - _as_float(config.get("washout_z"), 1.85)) / 1.25, 0.0, 1.0)
        target = min(max_long, (_as_float(config.get("long_target_vol"), 0.18) / safe_vol) * (0.25 + 0.45 * depth))
        regime = "washout_long"

    target = _clip(target * weight_scale, -min(max_short, max_signal), min(max_long, max_signal))
    if abs(target) < _as_float(config.get("target_step_weight"), 0.05):
        target = 0.0
        regime = "neutral"

    action = "short" if target < 0 else "long" if target > 0 else "hold"
    confidence = 0.50 + 0.15 * min(abs(z), 3.0) / 3.0 + 0.20 * min(abs(ret_stretch), 0.10) / 0.10
    return SignalState(
        float(target),
        action,
        float(min(0.95, confidence)),
        regime,
        {
            "rows": int(len(values)),
            "last_close": latest,
            "slow_mean": slow_mean,
            "squeeze_mean": squeeze_mean,
            "z_score": z,
            "ret_stretch": ret_stretch,
            "ret_trend": ret_trend,
            "fast_ret": fast_ret,
            "realized_vol_ann": realized_vol,
            "vol_ratio": vol_ratio,
            "recent_high": recent_high,
            "recent_low": recent_low,
            "overheat": bool(overheat),
            "turn_down": bool(turn_down),
            "trend_block": bool(trend_block),
            "washout": bool(washout),
            "turn_up": bool(turn_up),
            "target_weight": float(target),
        },
    )