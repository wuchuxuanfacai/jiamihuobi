from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import math

try:
    import numpy as np
except Exception:  # pragma: no cover - authoring runtimes may inspect only.
    np = None


# Compatibility guard for GetAgent authoring runtimes that inject a generated
# snippet referencing this name before constructing the final Playbook.
positions: list[Any] = []


@dataclass
class SignalResult:
    action: str
    target_weight: float
    confidence: float
    regime: str
    metrics: dict[str, Any]


DEFAULT_CONFIG: dict[str, Any] = {
    "timeframe": "4h",
    "weight_scale": 1.75,
    "max_short_weight": 1.00,
    "max_long_weight": 0.10,
    "max_signal_weight": 1.00,
    "fast_window": 18,
    "mid_window": 60,
    "slow_window": 180,
    "long_window": 540,
    "vol_window": 60,
    "bear_on": 0.56,
    "ret_mid_max": -0.04,
    "ret_slow_max": -0.08,
    "short_sma_mult": 0.98,
    "mid_sma_mult": 1.0,
    "rebound_ret_max": 0.08,
    "rebound_sma_mult": 1.005,
    "vol_ceiling": 0.45,
    "vol_floor_min": 0.20,
    "short_target_vol": 0.35,
    "short_floor_cap": 1.00,
    "short_base": 0.65,
    "short_conf": 0.55,
    "long_on": 0.68,
    "long_ret_mid_min": 0.0,
    "long_sma_mult": 1.02,
    "long_vol_ceiling": 0.45,
    "long_floor_cap": 0.10,
    "range_mr_cap": 0.02,
    "range_min_component": 0.00,
    "range_z_entry": 1.50,
    "range_trend_max": 0.30,
    "range_bear_max": 0.30,
    "range_vol_ceiling": 0.28,
    "range_abs_slope_max": 0.012,
    "range_ret_slow_abs_max": 0.08,
    "channel_slope_window": 45,
    "channel_slope_deadband": 0.00313,
    "range_bias_strength": 0.54640,
    "trend_invalidation_off": 0.30,
    "target_step_weight": 0.06,
}


def _float(value: Any, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if math.isfinite(parsed) else default


def _int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _clip(value: float, low: float, high: float) -> float:
    return float(min(high, max(low, value)))


def compute_signal(closes: list[float] | tuple[float, ...], config: dict[str, Any] | None = None) -> SignalResult:
    if np is None:
        return SignalResult("hold", 0.0, 0.0, "numpy_unavailable", {"reason_code": 99})

    cfg = dict(DEFAULT_CONFIG)
    if config:
        cfg.update(config)

    values = np.asarray(closes, dtype=float)
    values = values[np.isfinite(values)]
    if len(values) < 65:
        return SignalResult("hold", 0.0, 0.0, "warmup", {"rows": int(len(values)), "reason_code": 1})

    fast_window = min(_int(cfg.get("fast_window"), 18), len(values) - 2)
    mid_window = min(_int(cfg.get("mid_window"), 60), len(values) - 2)
    slow_window = min(_int(cfg.get("slow_window"), 180), len(values) - 2)
    long_window = min(_int(cfg.get("long_window"), 540), len(values))
    vol_window = min(_int(cfg.get("vol_window"), 60), len(values) - 2)

    latest = float(values[-1])
    sma_fast = float(np.mean(values[-fast_window:]))
    sma_mid = float(np.mean(values[-mid_window:]))
    sma_slow = float(np.mean(values[-slow_window:]))
    sma_long = float(np.mean(values[-long_window:]))
    ret_fast = latest / float(values[-fast_window]) - 1.0
    ret_mid = latest / float(values[-mid_window]) - 1.0
    ret_slow = latest / float(values[-slow_window]) - 1.0

    vol_slice = values[-(vol_window + 1):]
    vol_returns = np.diff(vol_slice) / vol_slice[:-1]
    realized_vol = float(np.std(vol_returns) * math.sqrt(365.0 * 6.0)) if len(vol_returns) else 9.0
    safe_vol = max(realized_vol, _float(cfg.get("vol_floor_min"), 0.20))

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

    weak_momentum = (
        ret_mid < _float(cfg.get("ret_mid_max"), -0.04)
        or ret_slow < _float(cfg.get("ret_slow_max"), -0.08)
        or latest < sma_mid * _float(cfg.get("mid_sma_mult"), 1.0)
    )
    rebound_blocked = (
        ret_fast > _float(cfg.get("rebound_ret_max"), 0.08)
        and latest > sma_fast * _float(cfg.get("rebound_sma_mult"), 1.005)
    )

    short_ok = (
        bear_strength >= _float(cfg.get("bear_on"), 0.56)
        and weak_momentum
        and latest < sma_long * _float(cfg.get("short_sma_mult"), 0.98)
        and latest < sma_slow
        and not rebound_blocked
        and realized_vol <= _float(cfg.get("vol_ceiling"), 0.45)
    )
    bear_conf = _clip((bear_strength - _float(cfg.get("bear_on"), 0.56)) / 0.44, 0.0, 1.0)
    short_weight = 0.0
    if short_ok:
        short_weight = -min(
            _float(cfg.get("short_floor_cap"), 1.00),
            (_float(cfg.get("short_target_vol"), 0.35) / safe_vol)
            * (_float(cfg.get("short_base"), 0.65) + _float(cfg.get("short_conf"), 0.55) * bear_conf),
        )

    long_ok = (
        trend_strength >= _float(cfg.get("long_on"), 0.68)
        and ret_mid > _float(cfg.get("long_ret_mid_min"), 0.0)
        and latest > sma_long * _float(cfg.get("long_sma_mult"), 1.02)
        and latest > sma_slow
        and realized_vol <= _float(cfg.get("long_vol_ceiling"), 0.45)
    )
    long_weight = 0.0
    if long_ok:
        long_conf = _clip((trend_strength - _float(cfg.get("long_on"), 0.68)) / 0.32, 0.0, 1.0)
        long_weight = min(_float(cfg.get("long_floor_cap"), 0.10), _float(cfg.get("max_long_weight"), 0.10)) * (0.5 + 0.5 * long_conf)

    raw_weight = (short_weight + long_weight) * _float(cfg.get("weight_scale"), 1.75)
    target_weight = _clip(raw_weight, -_float(cfg.get("max_short_weight"), 1.00), _float(cfg.get("max_long_weight"), 0.10))
    if target_weight > 0.0 and trend_strength < _float(cfg.get("trend_invalidation_off"), 0.30):
        target_weight = 0.0
    if target_weight < 0.0 and bear_strength < _float(cfg.get("trend_invalidation_off"), 0.30):
        target_weight = 0.0
    if abs(target_weight) < _float(cfg.get("target_step_weight"), 0.06):
        target_weight = 0.0

    action = "short" if target_weight < 0.0 else "long" if target_weight > 0.0 else "hold"
    confidence = 0.50 if target_weight == 0.0 else min(0.95, 0.50 + 0.45 * max(trend_strength, bear_strength))
    regime = "short_reentry" if target_weight < 0.0 else "defensive_long" if target_weight > 0.0 else "neutral"
    return SignalResult(
        action=action,
        target_weight=float(target_weight),
        confidence=float(confidence),
        regime=regime,
        metrics={
            "trend_strength": float(trend_strength),
            "bear_strength": float(bear_strength),
            "ret_fast": float(ret_fast),
            "ret_mid": float(ret_mid),
            "ret_slow": float(ret_slow),
            "realized_vol_ann": float(realized_vol),
            "last_close": float(latest),
            "short_ok": bool(short_ok),
            "long_ok": bool(long_ok),
            "rows": int(len(values)),
        },
    )


def run() -> None:
    from getagent import data, runtime

    config = runtime.manifest.get("strategy_config", {}) or {}
    symbols = config.get("trading_symbols") or runtime.manifest.get("trading_symbols", ["BTCUSDT"])
    symbol = symbols[0]
    bars = data.crypto.futures.kline(symbol=symbol, interval=str(config.get("timeframe") or "4h"), exchange="bitget", days=220)
    frame = data.to_dataframe(bars)
    closes = [float(x) for x in frame["close"].dropna().tolist()]
    signal = compute_signal(closes, config)
    runtime.emit_signal(
        action=signal.action,
        symbol=symbol,
        confidence=signal.confidence,
        metrics=signal.metrics | {"target_weight": signal.target_weight},
        meta={"regime": signal.regime, "source": "single_file_import_safe"},
    )


if __name__ == "__main__":
    run()
