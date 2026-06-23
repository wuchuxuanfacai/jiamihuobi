from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass
class OverlayState:
    target_weight: float
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


def _rsi(values: np.ndarray, period: int) -> float:
    if len(values) < period + 2:
        return 50.0
    diffs = np.diff(values[-(period + 1) :])
    gains = np.clip(diffs, 0.0, None)
    losses = np.clip(-diffs, 0.0, None)
    avg_gain = float(np.mean(gains))
    avg_loss = float(np.mean(losses))
    if avg_loss <= 1e-12:
        return 100.0 if avg_gain > 0.0 else 50.0
    rs = avg_gain / avg_loss
    return float(100.0 - 100.0 / (1.0 + rs))


def _atr_pct(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int) -> float:
    if len(closes) < period + 2:
        return 0.0
    h = highs[-period:]
    l = lows[-period:]
    c = closes[-period:]
    prev = closes[-(period + 1) : -1]
    tr = np.maximum.reduce([h - l, np.abs(h - prev), np.abs(l - prev)])
    return float(np.mean(tr) / max(float(closes[-1]), 1e-9))


def compute_overlay_state(
    opens: Any,
    highs: Any,
    lows: Any,
    closes: Any,
    volumes: Any,
    quote_volumes: Any,
    taker_buy_volumes: Any,
    config: dict[str, Any],
    base_weight: float,
) -> OverlayState:
    o = np.asarray(opens, dtype=float)
    h = np.asarray(highs, dtype=float)
    l = np.asarray(lows, dtype=float)
    c = np.asarray(closes, dtype=float)
    v = np.asarray(volumes, dtype=float)
    qv = np.asarray(quote_volumes, dtype=float)
    tbv = np.asarray(taker_buy_volumes, dtype=float)
    vwap_window = _as_int(config.get("overlay_vwap_window"), 48)
    atr_window = _as_int(config.get("overlay_atr_window"), 24)
    rsi_window = _as_int(config.get("overlay_rsi_window"), 7)
    flow_window = _as_int(config.get("overlay_flow_window"), 4)
    vol_window = _as_int(config.get("overlay_vol_window"), 16)
    rank_window = _as_int(config.get("overlay_rank_window"), 192)
    required = max(vwap_window, atr_window + 1, rsi_window + 1, flow_window, vol_window, rank_window // 2) + 2
    if len(c) < required:
        return OverlayState(0.0, "overlay_warmup", {"overlay_rows": int(len(c)), "overlay_required": int(required)})

    latest = float(c[-1])
    vol_slice = v[-vwap_window:]
    quote_slice = qv[-vwap_window:]
    vwap = float(np.sum(quote_slice) / max(np.sum(vol_slice), 1e-9))
    atr = max(_atr_pct(h, l, c, atr_window), 1e-9)
    vwap_z = (latest / max(vwap, 1e-9) - 1.0) / atr
    rsi_value = _rsi(c, rsi_window)
    flow_base = v[-flow_window:]
    flow = float(np.mean(tbv[-flow_window:] / np.maximum(flow_base, 1e-9) - 0.5))
    returns = np.diff(c) / np.maximum(c[:-1], 1e-9)
    current_vol = float(np.std(returns[-vol_window:])) if len(returns) >= vol_window else 0.0
    vol_hist = np.array(
        [float(np.std(returns[max(0, i - vol_window) : i])) for i in range(max(vol_window, len(returns) - rank_window), len(returns) + 1)]
    )
    vol_rank = float(np.mean(vol_hist <= current_vol)) if len(vol_hist) else 0.5

    base_gate = _as_float(config.get("overlay_base_gate"), 0.04)
    cap = _as_float(config.get("overlay_cap"), 0.025)
    z_entry = _as_float(config.get("overlay_z_entry"), 0.70)
    rsi_low = _as_float(config.get("overlay_rsi_low"), 44.0)
    rsi_high = _as_float(config.get("overlay_rsi_high"), 52.0)
    flow_gate = _as_float(config.get("overlay_flow_gate"), 0.03)
    vol_rank_max = _as_float(config.get("overlay_vol_rank_max"), 0.85)
    target = 0.0
    regime = "overlay_neutral"
    flat_base = abs(base_weight) <= base_gate
    calm = vol_rank <= vol_rank_max
    if flat_base and calm and vwap_z <= -z_entry and rsi_value <= rsi_low and flow >= -flow_gate:
        target = cap
        regime = "overlay_vwap_long"
    elif flat_base and calm and vwap_z >= z_entry and rsi_value >= rsi_high and flow <= flow_gate:
        target = -cap
        regime = "overlay_vwap_short"

    return OverlayState(
        target_weight=float(target),
        regime=regime,
        metrics={
            "overlay_rows": int(len(c)),
            "overlay_vwap": vwap,
            "overlay_atr_pct": atr,
            "overlay_vwap_z": float(vwap_z),
            "overlay_rsi": float(rsi_value),
            "overlay_flow": flow,
            "overlay_vol_rank": vol_rank,
            "overlay_base_weight": float(base_weight),
            "overlay_target_weight": float(target),
            "overlay_flat_base": bool(flat_base),
            "overlay_calm": bool(calm),
        },
    )
