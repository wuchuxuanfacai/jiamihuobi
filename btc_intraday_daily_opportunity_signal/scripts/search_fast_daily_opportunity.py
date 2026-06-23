from __future__ import annotations

import json
import math
import random
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from search_daily_opportunity import load_1m, resample, simulate


@dataclass
class Hit:
    family: str
    timeframe: str
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


def ema(s: pd.Series, span: int) -> pd.Series:
    return s.ewm(span=span, adjust=False, min_periods=max(3, span // 4)).mean()


def rsi(close: pd.Series, n: int) -> pd.Series:
    diff = close.diff()
    up = diff.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    down = (-diff.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    rs = up / down.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50.0)


def atr_pct(bars: pd.DataFrame, n: int) -> pd.Series:
    prev = bars["close"].shift(1)
    tr = pd.concat(
        [(bars["high"] - bars["low"]), (bars["high"] - prev).abs(), (bars["low"] - prev).abs()],
        axis=1,
    ).max(axis=1)
    return (tr.ewm(span=n, adjust=False, min_periods=max(3, n // 4)).mean() / bars["close"]).fillna(0.0)


def feature_bank(bars: pd.DataFrame) -> dict[str, pd.Series]:
    close = bars["close"]
    bank: dict[str, pd.Series] = {
        "ret1": close.pct_change().fillna(0.0),
        "flow4": (bars["taker_buy_ratio"] - 0.5).rolling(4, min_periods=2).mean().fillna(0.0),
        "flow12": (bars["taker_buy_ratio"] - 0.5).rolling(12, min_periods=3).mean().fillna(0.0),
    }
    for n in [8, 12, 16, 24, 32, 48, 64, 96, 128, 192, 288, 384]:
        bank[f"ema{n}"] = ema(close, n)
    for n in [7, 10, 14, 21]:
        bank[f"rsi{n}"] = rsi(close, n)
    for n in [16, 24, 32, 48, 64, 96]:
        vwap = (bars["quote_volume"].rolling(n, min_periods=max(3, n // 4)).sum() / bars["volume"].rolling(n, min_periods=max(3, n // 4)).sum()).ffill()
        bank[f"vwap_z{n}"] = ((close / vwap - 1.0) / atr_pct(bars, max(16, n // 2)).replace(0, np.nan)).fillna(0.0).clip(-8, 8)
    for n in [16, 32, 48, 64, 96]:
        ret = close.pct_change()
        vol = ret.rolling(n, min_periods=max(5, n // 4)).std().fillna(0.0)
        bank[f"vol{n}"] = vol
        bank[f"volrank{n}"] = vol.rolling(192, min_periods=40).rank(pct=True).fillna(0.5)
    for n in [12, 16, 24, 32, 48, 64]:
        bank[f"hi{n}"] = close.shift(1).rolling(n, min_periods=max(4, n // 4)).max()
        bank[f"lo{n}"] = close.shift(1).rolling(n, min_periods=max(4, n // 4)).min()
    return bank


def choose(rng: random.Random, xs: list):
    return xs[rng.randrange(len(xs))]


def make_signal(bars: pd.DataFrame, f: dict[str, pd.Series], family: str, p: dict[str, float | int | str]) -> pd.Series:
    close = bars["close"]
    fast = f[f"ema{p['fast']}"]
    slow = f[f"ema{p['slow']}"]
    long = f[f"ema{p['long']}"]
    trend = (fast / slow - 1.0).fillna(0.0)
    macro = (slow / long - 1.0).fillna(0.0)
    r = f[f"rsi{p['rsi']}"]
    vz = f[f"vwap_z{p['vwap']}"]
    flow = f[f"flow{p['flow']}"]
    volrank = f[f"volrank{p['vol']}"]
    sig = pd.Series(0.0, index=bars.index)

    if family == "daily_vwap_rotation":
        calm = volrank <= float(p["volrank_max"])
        up_bias = macro > -float(p["macro_band"])
        down_bias = macro < float(p["macro_band"])
        sig[calm & up_bias & (vz <= -float(p["z"])) & (r <= float(p["rsi_low"])) & (flow >= -float(p["flow_gate"]))] = float(p["w"])
        sig[calm & down_bias & (vz >= float(p["z"])) & (r >= float(p["rsi_high"])) & (flow <= float(p["flow_gate"]))] = -float(p["w"])
    elif family == "trend_reentry_dense":
        up = (trend > float(p["trend"])) & (macro > -float(p["macro_band"]))
        down = (trend < -float(p["trend"])) & (macro < float(p["macro_band"]))
        sig[up & ((vz <= -float(p["z"])) | (r <= float(p["rsi_low"]))) & (flow > -float(p["flow_gate"]))] = float(p["w"])
        sig[down & ((vz >= float(p["z"])) | (r >= float(p["rsi_high"]))) & (flow < float(p["flow_gate"]))] = -float(p["w"])
    elif family == "flow_breakout":
        hi = f[f"hi{p['box']}"]
        lo = f[f"lo{p['box']}"]
        active = volrank >= float(p["volrank_min"])
        sig[active & (close > hi) & (trend > -float(p["trend"])) & (flow >= float(p["flow_gate"]))] = float(p["w"])
        sig[active & (close < lo) & (trend < float(p["trend"])) & (flow <= -float(p["flow_gate"]))] = -float(p["w"])
    else:
        raise ValueError(family)
    return sig.shift(1).fillna(0.0)


def rough_simulate(
    bars: pd.DataFrame,
    raw_pos: pd.Series,
    *,
    fee: float = 0.0005,
    trade_start: str = "2025-12-18",
    trade_end: str = "2026-06-01",
) -> dict[str, float | int]:
    position = raw_pos.reindex(bars.index).fillna(0.0).astype(float).clip(-1.0, 1.0)
    start = pd.Timestamp(trade_start, tz="UTC")
    end = pd.Timestamp(trade_end, tz="UTC")
    position = position.where((position.index >= start) & (position.index <= end), 0.0)
    returns = bars["close"].pct_change().fillna(0.0)
    turnover = position.diff().abs().fillna(position.abs())
    pnl = position.shift(1).fillna(0.0) * returns - turnover * fee
    equity = (1.0 + pnl).cumprod()
    drawdown = equity / equity.cummax() - 1.0
    entries = (position != 0.0) & (position.shift(1).fillna(0.0) == 0.0)
    entry_days = set(position.index[entries].date)
    total_days = max(len(pd.date_range(start, end, freq="D")), 1)
    years = max((end - start).days / 365.25, 1 / 365.25)
    total_return = float(equity.loc[:end].iloc[-1] - 1.0)
    return {
        "total_return": total_return,
        "annual_return": float((1.0 + total_return) ** (1.0 / years) - 1.0),
        "max_drawdown": float(drawdown.min()),
        "trades": int(entries.sum()),
        "avg_entries_per_day": float(entries.sum() / total_days),
        "active_day_ratio": float(len(entry_days) / total_days),
    }
    return sig.shift(1).fillna(0.0)


def sample_params(rng: random.Random, timeframe: str, family: str) -> dict[str, float | int | str]:
    base = {
        "fast": choose(rng, [8, 12, 16, 24]),
        "slow": choose(rng, [32, 48, 64, 96]),
        "long": choose(rng, [128, 192, 288, 384]),
        "rsi": choose(rng, [7, 10, 14, 21]),
        "vwap": choose(rng, [16, 24, 32, 48, 64, 96]),
        "flow": choose(rng, [4, 12]),
        "vol": choose(rng, [16, 32, 48, 64, 96]),
        "w": choose(rng, [0.20, 0.28, 0.36, 0.48, 0.64]),
        "max_hold": choose(rng, [8, 12, 16, 24, 32, 48] if timeframe == "15m" else [4, 6, 8, 12, 16, 24]),
    }
    if int(base["slow"]) <= int(base["fast"]):
        base["slow"] = 64
    if int(base["long"]) <= int(base["slow"]):
        base["long"] = 288
    if family == "daily_vwap_rotation":
        base.update(
            {
                "z": choose(rng, [0.35, 0.50, 0.70, 0.90, 1.10]),
                "rsi_low": choose(rng, [36, 40, 44, 48]),
                "rsi_high": choose(rng, [52, 56, 60, 64]),
                "macro_band": choose(rng, [0.004, 0.008, 0.014, 0.022, 0.035]),
                "volrank_max": choose(rng, [0.55, 0.70, 0.85, 0.95]),
                "flow_gate": choose(rng, [0.005, 0.015, 0.030, 0.050]),
            }
        )
    elif family == "trend_reentry_dense":
        base.update(
            {
                "trend": choose(rng, [0.0002, 0.0005, 0.0010, 0.0018, 0.0030]),
                "z": choose(rng, [0.25, 0.45, 0.65, 0.85, 1.10]),
                "rsi_low": choose(rng, [38, 42, 46, 50]),
                "rsi_high": choose(rng, [50, 54, 58, 62]),
                "macro_band": choose(rng, [0.004, 0.010, 0.018, 0.030]),
                "flow_gate": choose(rng, [0.005, 0.015, 0.030, 0.050]),
            }
        )
    else:
        base.update(
            {
                "box": choose(rng, [12, 16, 24, 32, 48, 64]),
                "trend": choose(rng, [0.0002, 0.0005, 0.0010, 0.0020]),
                "volrank_min": choose(rng, [0.45, 0.55, 0.65, 0.75]),
                "flow_gate": choose(rng, [0.005, 0.015, 0.025, 0.040]),
            }
        )
    return base


def run_one(timeframe: str, bars: pd.DataFrame, trials: int, seed: int) -> list[Hit]:
    rng = random.Random(seed)
    bank = feature_bank(bars)
    rough_hits: list[tuple[float, str, dict[str, float | int | str], pd.Series]] = []
    families = ["daily_vwap_rotation", "trend_reentry_dense", "flow_breakout"]
    for i in range(trials):
        family = choose(rng, families)
        params = sample_params(rng, timeframe, family)
        sig = make_signal(bars, bank, family, params)
        metrics = rough_simulate(bars, sig, fee=0.0005)
        if metrics["avg_entries_per_day"] < 0.90 or metrics["active_day_ratio"] < 0.58:
            continue
        if metrics["trades"] < 90:
            continue
        score = float(metrics["total_return"]) + 0.20 * max(float(metrics["max_drawdown"]), -0.20)
        rough_hits.append((score, family, params, sig))
        if i and i % 250 == 0:
            rough_hits.sort(key=lambda item: item[0], reverse=True)
            rough_hits = rough_hits[:120]
            print(timeframe, "trial", i, "rough_hits", len(rough_hits), "best_score", rough_hits[0][0] if rough_hits else None)
    rough_hits.sort(key=lambda item: item[0], reverse=True)
    hits: list[Hit] = []
    for _, family, params, sig in rough_hits[:160]:
        metrics, _, _ = simulate(
            bars,
            sig,
            fee=0.0005,
            max_hold=int(params["max_hold"]),
            cooldown=0,
            trade_start="2025-12-18",
            trade_end="2026-06-01",
        )
        if metrics["avg_entries_per_day"] < 0.90 or metrics["active_day_ratio"] < 0.58:
            continue
        hits.append(Hit(family=family, timeframe=timeframe, params=params, **metrics))
    hits.sort(key=lambda h: (h.max_drawdown >= -0.10, h.total_return, h.profit_factor, h.active_day_ratio), reverse=True)
    return hits[:50]


def main() -> int:
    raw = load_1m("2025-12-01", "2026-06-01")
    out: dict[str, list[dict[str, object]]] = {}
    for timeframe, rule, trials in [("1h", "1h", 1600), ("15m", "15min", 900)]:
        bars = resample(raw, rule)
        hits = run_one(timeframe, bars, trials=trials, seed=20260623 + (0 if timeframe == "15m" else 1))
        out[timeframe] = [asdict(h) for h in hits]
        print("==", timeframe, "==")
        for h in hits[:12]:
            print(
                json.dumps(
                    {
                        "family": h.family,
                        "ret": round(h.total_return, 4),
                        "ann": round(h.annual_return, 4),
                        "dd": round(h.max_drawdown, 4),
                        "pf": round(h.profit_factor, 3),
                        "trades": h.trades,
                        "per_day": round(h.avg_entries_per_day, 2),
                        "active": round(h.active_day_ratio, 2),
                        "params": h.params,
                    },
                    ensure_ascii=False,
                )
            )
    path = Path("btc_intraday_daily_opportunity_signal/research_snapshot/fast_search_results.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
