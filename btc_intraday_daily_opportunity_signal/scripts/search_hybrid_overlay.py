from __future__ import annotations

import itertools
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from search_daily_opportunity import load_1m, resample, simulate
from search_fast_daily_opportunity import atr_pct, rsi


REPO = Path(__file__).resolve().parents[2]
BASE_SRC = REPO / "btc_intraday_regime_rotation_signal" / "getagent_playbook" / "src"
sys.path.insert(0, str(BASE_SRC))
from decision_logic import compute_signal_state  # noqa: E402


BASE_CONFIG = {
    "weight_scale": 1.75,
    "max_effective_exposure": 2.36,
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
    "long_sma_mult": 1.02,
    "long_floor_cap": 0.00,
    "max_long_weight": 0.00,
    "long_on": 0.68,
    "long_ret_mid_min": 0.0,
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


@dataclass
class OverlayHit:
    params: dict[str, float | int | str]
    total_return: float
    annual_return: float
    max_drawdown: float
    sharpe: float
    win_rate: float
    profit_factor: float
    trades: int
    avg_entries_per_day: float
    active_day_ratio: float
    avg_hold_bars: float


def base_target(bars_15m: pd.DataFrame) -> pd.Series:
    htf = bars_15m["close"].resample("4h", label="right", closed="right").last().dropna()
    out = []
    idx = []
    values = htf.to_numpy(dtype=float)
    for i, ts in enumerate(htf.index):
        state = compute_signal_state(values[: i + 1], BASE_CONFIG, bars_per_day=6.0)
        out.append(state.target_weight)
        idx.append(ts)
    base = pd.Series(out, index=pd.DatetimeIndex(idx)).reindex(bars_15m.index, method="ffill").fillna(0.0)
    return base


def overlay_signal(bars: pd.DataFrame, base: pd.Series, p: dict[str, float | int]) -> pd.Series:
    close = bars["close"]
    vwap_n = int(p["vwap"])
    vwap = (bars["quote_volume"].rolling(vwap_n, min_periods=max(4, vwap_n // 4)).sum() / bars["volume"].rolling(vwap_n, min_periods=max(4, vwap_n // 4)).sum()).ffill()
    vz = ((close / vwap - 1.0) / atr_pct(bars, int(p["atr"])).replace(0, np.nan)).fillna(0.0).clip(-8, 8)
    rr = rsi(close, int(p["rsi"]))
    flow = (bars["taker_buy_ratio"] - 0.5).rolling(int(p["flow"]), min_periods=2).mean().fillna(0.0)
    vol = close.pct_change().rolling(int(p["vol"]), min_periods=8).std().fillna(0.0)
    vol_rank = vol.rolling(int(p["rank"]), min_periods=40).rank(pct=True).fillna(0.5)
    ema_fast = close.ewm(span=int(p["fast"]), adjust=False, min_periods=8).mean()
    ema_slow = close.ewm(span=int(p["slow"]), adjust=False, min_periods=16).mean()
    macro = (ema_fast / ema_slow - 1.0).fillna(0.0)

    flat = base.abs() <= float(p["base_gate"])
    calm = vol_rank <= float(p["vol_rank_max"])
    sig = pd.Series(0.0, index=bars.index)
    long_ok = flat & calm & (vz <= -float(p["z"])) & (rr <= float(p["rsi_low"])) & (flow >= -float(p["flow_gate"])) & (macro >= -float(p["macro_band"]))
    short_ok = flat & calm & (vz >= float(p["z"])) & (rr >= float(p["rsi_high"])) & (flow <= float(p["flow_gate"])) & (macro <= float(p["macro_band"]))
    sig[long_ok] = float(p["cap"])
    sig[short_ok] = -float(p["cap"])
    return sig.shift(1).fillna(0.0)


def main() -> int:
    raw = load_1m("2025-12-01", "2026-06-01")
    bars = resample(raw, "15min")
    base = base_target(bars)
    base_metrics, _, _ = simulate(bars, base, fee=0.0005, max_hold=10_000)
    print("base", json.dumps(base_metrics, ensure_ascii=False))

    hits: list[OverlayHit] = []
    grid = {
        "vwap": [24, 32, 48, 64, 96],
        "atr": [24, 32, 48],
        "rsi": [7, 10, 14],
        "flow": [4, 8, 12],
        "vol": [32, 48, 64],
        "rank": [192, 384],
        "fast": [48, 96],
        "slow": [192, 384],
        "z": [0.45, 0.65, 0.85, 1.05],
        "rsi_low": [38, 42, 46],
        "rsi_high": [54, 58, 62],
        "flow_gate": [0.005, 0.015, 0.03],
        "macro_band": [0.006, 0.012, 0.025],
        "vol_rank_max": [0.55, 0.70, 0.85],
        "base_gate": [0.01, 0.04, 0.08],
        "cap": [0.025, 0.04, 0.06, 0.08],
        "max_hold": [8, 12, 16, 24],
    }
    keys = list(grid)
    combos = itertools.product(*(grid[k] for k in keys))
    for i, vals in enumerate(combos):
        if i % 17 != 0:
            continue
        p = dict(zip(keys, vals))
        overlay = overlay_signal(bars, base, p)
        target = (base + overlay).clip(-1.0, 0.20)
        metrics, _, _ = simulate(bars, target, fee=0.0005, max_hold=int(p["max_hold"]))
        if metrics["avg_entries_per_day"] < 0.70 or metrics["active_day_ratio"] < 0.48:
            continue
        if metrics["max_drawdown"] < -0.09:
            continue
        hits.append(OverlayHit(params=p, **metrics))
        if i % 50000 == 0 and hits:
            hits.sort(key=lambda h: (h.total_return, h.profit_factor, h.active_day_ratio), reverse=True)
            print("scan", i, "hits", len(hits), "best", asdict(hits[0]))
            hits = hits[:100]
    hits.sort(key=lambda h: (h.total_return, h.max_drawdown, h.active_day_ratio), reverse=True)
    out = [asdict(h) for h in hits[:50]]
    path = Path("btc_intraday_daily_opportunity_signal/research_snapshot/hybrid_overlay_results.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"base": base_metrics, "hits": out}, indent=2, ensure_ascii=False), encoding="utf-8")
    for h in out[:20]:
        print(json.dumps(h, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
