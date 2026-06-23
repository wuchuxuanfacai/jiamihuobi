from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from search_daily_opportunity import load_1m, resample, simulate
from search_fast_daily_opportunity import atr_pct, rsi


REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "btc_intraday_regime_rotation_signal" / "getagent_playbook" / "src"))
from decision_logic import compute_signal_state  # noqa: E402


BASE_CONFIG = {
    "weight_scale": 1.75,
    "fast_window": 18,
    "mid_window": 60,
    "slow_window": 180,
    "long_window": 540,
    "vol_window": 60,
    "bear_on": 0.56,
    "ret_slow_max": -0.08,
    "ret_mid_max": -0.04,
    "short_sma_mult": 0.98,
    "mid_sma_mult": 1.0,
    "rebound_ret_max": 0.08,
    "rebound_sma_mult": 1.005,
    "short_target_vol": 0.35,
    "short_floor_cap": 1.00,
    "short_base": 0.65,
    "short_conf": 0.55,
    "max_short_weight": 1.00,
    "max_signal_weight": 1.00,
    "long_floor_cap": 0.00,
    "max_long_weight": 0.00,
    "long_on": 0.68,
    "long_sma_mult": 1.02,
    "long_vol_ceiling": 0.45,
    "range_mr_cap": 0.02,
    "range_z_entry": 1.50,
    "range_trend_max": 0.30,
    "range_bear_max": 0.30,
    "range_vol_ceiling": 0.28,
    "range_abs_slope_max": 0.012,
    "range_ret_slow_abs_max": 0.08,
    "vol_ceiling": 0.45,
    "vol_floor_min": 0.20,
    "target_step_weight": 0.06,
    "trend_invalidation_off": 0.30,
}


def base_target(bars: pd.DataFrame) -> pd.Series:
    htf = bars["close"].resample("4h", label="right", closed="right").last().dropna()
    values = htf.to_numpy(float)
    targets = []
    for i in range(len(values)):
        targets.append(compute_signal_state(values[: i + 1], BASE_CONFIG, bars_per_day=6.0).target_weight)
    return pd.Series(targets, index=htf.index).reindex(bars.index, method="ffill").fillna(0.0)


def vwap_overlay(bars: pd.DataFrame, base: pd.Series, cap: float, z_entry: float, base_gate: float, max_overlay_hold: int) -> pd.Series:
    close = bars["close"]
    vwap = (bars["quote_volume"].rolling(48, min_periods=12).sum() / bars["volume"].rolling(48, min_periods=12).sum()).ffill()
    vz = ((close / vwap - 1.0) / atr_pct(bars, 24).replace(0, np.nan)).fillna(0.0).clip(-8, 8)
    rr = rsi(close, 7)
    flow = (bars["taker_buy_ratio"] - 0.5).rolling(4, min_periods=2).mean().fillna(0.0)
    vol = close.pct_change().rolling(16, min_periods=6).std().fillna(0.0)
    vol_rank = vol.rolling(192, min_periods=40).rank(pct=True).fillna(0.5)
    sig = pd.Series(0.0, index=bars.index)
    flat = base.abs() <= base_gate
    calm = vol_rank <= 0.85
    sig[flat & calm & (vz <= -z_entry) & (rr <= 44) & (flow >= -0.03)] = cap
    sig[flat & calm & (vz >= z_entry) & (rr >= 52) & (flow <= 0.03)] = -cap
    sig = sig.shift(1).fillna(0.0)
    # Avoid overlay lingering forever; main simulate max_hold applies to whole target,
    # so we keep overlay pulses short before adding them to the base.
    out = np.zeros(len(sig))
    hold = 0
    active = 0.0
    for i, val in enumerate(sig.to_numpy()):
        if active == 0.0 and val != 0.0:
            active = val
            hold = 0
        elif active != 0.0:
            hold += 1
            if hold >= max_overlay_hold or val == -active:
                active = 0.0
                hold = 0
        out[i] = active
    return pd.Series(out, index=bars.index)


def main() -> int:
    raw = load_1m("2025-12-01", "2026-06-01")
    bars15 = resample(raw, "15min")
    bars1h = resample(raw, "1h")
    base15 = base_target(bars15)
    results = []
    for base_scale in [1.0, 1.05, 1.10, 1.20]:
        scaled_base = (base15 * base_scale).clip(-1.0, 0.2)
        m, _, _ = simulate(bars15, scaled_base, fee=0.0005, max_hold=10_000)
        results.append({"kind": "base", "base_scale": base_scale, **m})
    # Use 1h overlay and forward-fill to 15m to reduce fee churn.
    base1h = base15.resample("1h").last().reindex(bars1h.index, method="ffill").fillna(0.0)
    for cap in [0.025, 0.04, 0.06]:
        for z_entry in [0.35, 0.50, 0.70]:
            for gate in [0.04, 0.08, 0.12]:
                for hold in [2, 4]:
                    ov1h = vwap_overlay(bars1h, base1h, cap=cap, z_entry=z_entry, base_gate=gate, max_overlay_hold=hold)
                    ov15 = ov1h.reindex(bars15.index, method="ffill").fillna(0.0)
                    for base_scale in [1.0, 1.10]:
                        target = (base15 * base_scale + ov15).clip(-1.0, 0.2)
                        m, _, _ = simulate(bars15, target, fee=0.0005, max_hold=10_000)
                        if m["avg_entries_per_day"] < 0.45:
                            continue
                        results.append(
                            {
                                "kind": "hybrid_1h_overlay",
                                "base_scale": base_scale,
                                "cap": cap,
                                "z_entry": z_entry,
                                "base_gate": gate,
                                "overlay_hold": hold,
                                **m,
                            }
                        )
    results.sort(key=lambda r: (r["max_drawdown"] >= -0.065, r["total_return"], r["active_day_ratio"]), reverse=True)
    path = Path("btc_intraday_daily_opportunity_signal/research_snapshot/quick_hybrid_results.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(results[:100], indent=2, ensure_ascii=False), encoding="utf-8")
    for row in results[:30]:
        print(json.dumps(row, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
