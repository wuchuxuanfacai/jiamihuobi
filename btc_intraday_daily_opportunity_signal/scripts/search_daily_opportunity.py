from __future__ import annotations

import argparse
import itertools
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd


RAW_DIR = Path(r"D:\市场轮廓理论\data\raw\binance_um_futures\BTCUSDT\1m")


@dataclass
class Result:
    name: str
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


def _month_paths(start: str, end: str) -> list[Path]:
    idx = pd.date_range(pd.Timestamp(start).replace(day=1), pd.Timestamp(end), freq="MS", tz="UTC")
    paths: list[Path] = []
    for ts in idx:
        monthly = RAW_DIR / f"BTCUSDT-1m-{ts:%Y-%m}.csv"
        if monthly.exists():
            paths.append(monthly)
    daily = sorted(RAW_DIR.glob("BTCUSDT-1m-2026-06-*.csv"))
    paths.extend([p for p in daily if p not in paths])
    return paths


def load_1m(start: str, end: str) -> pd.DataFrame:
    frames = []
    usecols = [
        "open_time",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "quote_volume",
        "count",
        "taker_buy_volume",
        "taker_buy_quote_volume",
    ]
    for path in _month_paths(start, end):
        frame = pd.read_csv(path, usecols=usecols)
        frame["time"] = pd.to_datetime(frame["open_time"], unit="ms", utc=True)
        frames.append(frame)
    if not frames:
        raise FileNotFoundError("no raw csv files found")
    data = pd.concat(frames, ignore_index=True)
    data = data.set_index("time").sort_index()
    data = data.loc[pd.Timestamp(start, tz="UTC") : pd.Timestamp(end, tz="UTC")]
    return data


def resample(frame: pd.DataFrame, rule: str) -> pd.DataFrame:
    out = pd.DataFrame(
        {
            "open": frame["open"].resample(rule).first(),
            "high": frame["high"].resample(rule).max(),
            "low": frame["low"].resample(rule).min(),
            "close": frame["close"].resample(rule).last(),
            "volume": frame["volume"].resample(rule).sum(),
            "quote_volume": frame["quote_volume"].resample(rule).sum(),
            "trade_count": frame["count"].resample(rule).sum(),
            "taker_buy_volume": frame["taker_buy_volume"].resample(rule).sum(),
            "taker_buy_quote_volume": frame["taker_buy_quote_volume"].resample(rule).sum(),
        }
    )
    out = out.dropna(subset=["open", "high", "low", "close"])
    out["taker_buy_ratio"] = out["taker_buy_volume"] / out["volume"].replace(0, np.nan)
    out["taker_buy_ratio"] = out["taker_buy_ratio"].fillna(0.5).clip(0.0, 1.0)
    return out


def _ema(s: pd.Series, span: int) -> pd.Series:
    return s.ewm(span=span, adjust=False, min_periods=max(2, span // 3)).mean()


def _rsi(close: pd.Series, n: int) -> pd.Series:
    diff = close.diff()
    up = diff.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    down = (-diff.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    rs = up / down.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50)


def _zscore(s: pd.Series, n: int) -> pd.Series:
    mean = s.rolling(n, min_periods=max(5, n // 3)).mean()
    std = s.rolling(n, min_periods=max(5, n // 3)).std()
    return ((s - mean) / std.replace(0, np.nan)).fillna(0.0)


def _atr_pct(bars: pd.DataFrame, n: int) -> pd.Series:
    prev = bars["close"].shift(1)
    tr = pd.concat(
        [
            bars["high"] - bars["low"],
            (bars["high"] - prev).abs(),
            (bars["low"] - prev).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return (tr.ewm(span=n, adjust=False, min_periods=max(3, n // 3)).mean() / bars["close"]).fillna(0.0)


def simulate(
    bars: pd.DataFrame,
    raw_pos: pd.Series,
    *,
    fee: float = 0.0005,
    max_hold: int = 64,
    cooldown: int = 0,
    trade_start: str = "2025-12-18",
    trade_end: str = "2026-06-01",
) -> tuple[dict[str, float | int], pd.Series, list[dict[str, float | str]]]:
    idx = bars.index
    raw = raw_pos.reindex(idx).fillna(0.0).astype(float).clip(-1.0, 1.0)
    pos = np.zeros(len(raw))
    hold = 0
    cool = 0
    last = 0.0
    for i, desired in enumerate(raw.to_numpy()):
        if idx[i] < pd.Timestamp(trade_start, tz="UTC") or idx[i] > pd.Timestamp(trade_end, tz="UTC"):
            desired = 0.0
        if cool > 0:
            desired = last
            cool -= 1
        if last != 0.0:
            hold += 1
            if hold >= max_hold:
                desired = 0.0
        else:
            hold = 0
        if np.sign(desired) != np.sign(last) and last != 0.0 and desired != 0.0:
            desired = 0.0
        if desired != last and cooldown > 0:
            cool = cooldown
        if desired == 0.0:
            hold = 0
        pos[i] = desired
        last = desired

    position = pd.Series(pos, index=idx)
    ret = bars["close"].pct_change().fillna(0.0)
    turnover = position.diff().abs().fillna(position.abs())
    pnl = position.shift(1).fillna(0.0) * ret - turnover * fee
    equity = (1.0 + pnl).cumprod()
    dd = equity / equity.cummax() - 1.0

    trades = []
    current = 0.0
    entry_i = None
    entry_equity = 1.0
    for i, value in enumerate(position.to_numpy()):
        if current == 0.0 and value != 0.0:
            current = value
            entry_i = i
            entry_equity = float(equity.iloc[max(i - 1, 0)])
        elif current != 0.0 and (value == 0.0 or np.sign(value) != np.sign(current)):
            exit_equity = float(equity.iloc[i])
            trades.append(
                {
                    "entry_time": str(idx[entry_i]) if entry_i is not None else "",
                    "exit_time": str(idx[i]),
                    "side": "long" if current > 0 else "short",
                    "pnl": exit_equity / max(entry_equity, 1e-12) - 1.0,
                    "bars": float(i - (entry_i or i)),
                }
            )
            current = value if value != 0.0 else 0.0
            entry_i = i if value != 0.0 else None
            entry_equity = float(equity.iloc[i])
    if current != 0.0 and entry_i is not None:
        trades.append(
            {
                "entry_time": str(idx[entry_i]),
                "exit_time": str(idx[-1]),
                "side": "long" if current > 0 else "short",
                "pnl": float(equity.iloc[-1]) / max(entry_equity, 1e-12) - 1.0,
                "bars": float(len(idx) - 1 - entry_i),
            }
        )

    trade_pnls = np.asarray([t["pnl"] for t in trades], dtype=float)
    gross_profit = trade_pnls[trade_pnls > 0].sum()
    gross_loss = -trade_pnls[trade_pnls < 0].sum()
    entry_days = pd.Series(
        [pd.Timestamp(t["entry_time"]).date() for t in trades],
        dtype="object",
    )
    window_days = pd.date_range(pd.Timestamp(trade_start, tz="UTC"), pd.Timestamp(trade_end, tz="UTC"), freq="D")
    total_days = max(len(window_days), 1)
    active_days = entry_days.nunique() if len(entry_days) else 0
    years = max((pd.Timestamp(trade_end, tz="UTC") - pd.Timestamp(trade_start, tz="UTC")).days / 365.25, 1 / 365.25)
    total_return = float(equity.loc[: pd.Timestamp(trade_end, tz="UTC")].iloc[-1] - 1.0)
    metrics = {
        "total_return": total_return,
        "annual_return": float((1.0 + total_return) ** (1.0 / years) - 1.0),
        "max_drawdown": float(dd.min()),
        "sharpe": float(np.sqrt(365 * 24 * 4) * pnl.mean() / pnl.std()) if pnl.std() > 0 else 0.0,
        "win_rate": float((trade_pnls > 0).mean()) if len(trade_pnls) else 0.0,
        "profit_factor": float(gross_profit / gross_loss) if gross_loss > 0 else (99.0 if gross_profit > 0 else 0.0),
        "trades": int(len(trades)),
        "avg_entries_per_day": float(len(trades) / total_days),
        "active_day_ratio": float(active_days / total_days),
        "avg_hold_bars": float(np.mean([t["bars"] for t in trades])) if trades else 0.0,
    }
    return metrics, equity, trades


def build_candidate(bars: pd.DataFrame, family: str, p: dict[str, float | int]) -> pd.Series:
    close = bars["close"]
    ret1 = close.pct_change()
    ema_fast = _ema(close, int(p["fast"]))
    ema_slow = _ema(close, int(p["slow"]))
    ema_long = _ema(close, int(p["long"]))
    trend = (ema_fast / ema_slow - 1.0).fillna(0.0)
    long_trend = (ema_slow / ema_long - 1.0).fillna(0.0)
    rsi = _rsi(close, int(p["rsi"]))
    vol = ret1.rolling(int(p["vol"]), min_periods=max(5, int(p["vol"]) // 3)).std().fillna(0.0)
    vol_rank = vol.rolling(int(p["rank"]), min_periods=max(10, int(p["rank"]) // 3)).rank(pct=True).fillna(0.5)
    z = _zscore(close, int(p["zwin"]))
    vwap = (bars["quote_volume"].rolling(int(p["vwap"]), min_periods=5).sum() / bars["volume"].rolling(int(p["vwap"]), min_periods=5).sum()).ffill()
    vwap_z = ((close / vwap - 1.0) / _atr_pct(bars, int(p["atr"])).replace(0, np.nan)).fillna(0.0)
    taker = (bars["taker_buy_ratio"] - 0.5).rolling(int(p["flow"]), min_periods=3).mean().fillna(0.0)

    if family == "trend_pullback":
        raw = pd.Series(0.0, index=bars.index)
        up = (trend > p["trend_on"]) & (long_trend > -p["long_floor"])
        down = (trend < -p["trend_on"]) & (long_trend < p["long_floor"])
        raw[up & ((rsi < p["rsi_buy"]) | (vwap_z < -p["vz"])) & (taker > -p["flow_abs"])] = p["w"]
        raw[down & ((rsi > p["rsi_sell"]) | (vwap_z > p["vz"])) & (taker < p["flow_abs"])] = -p["w"]
        return raw
    if family == "vwap_revert":
        raw = pd.Series(0.0, index=bars.index)
        calm = vol_rank < p["vol_rank_max"]
        raw[calm & (vwap_z < -p["vz"]) & (rsi < p["rsi_buy"]) & (long_trend > -p["long_floor"])] = p["w"]
        raw[calm & (vwap_z > p["vz"]) & (rsi > p["rsi_sell"]) & (long_trend < p["long_floor"])] = -p["w"]
        return raw
    if family == "breakout_retest":
        raw = pd.Series(0.0, index=bars.index)
        high = close.shift(1).rolling(int(p["box"]), min_periods=5).max()
        low = close.shift(1).rolling(int(p["box"]), min_periods=5).min()
        expansion = vol_rank > p["vol_rank_min"]
        raw[expansion & (close > high) & (trend > -p["trend_on"]) & (taker > p["flow_abs"])] = p["w"]
        raw[expansion & (close < low) & (trend < p["trend_on"]) & (taker < -p["flow_abs"])] = -p["w"]
        return raw
    raise ValueError(f"unknown family {family}")


def search(bars: pd.DataFrame, timeframe: str) -> list[Result]:
    rows: list[Result] = []
    grids: list[tuple[str, dict[str, list[float | int]]]] = [
        (
            "trend_pullback",
            {
                "fast": [8, 12, 16],
                "slow": [32, 48, 64],
                "long": [128, 192],
                "rsi": [10, 14],
                "vol": [32],
                "rank": [192],
                "zwin": [64],
                "vwap": [32, 64],
                "atr": [32],
                "flow": [4, 8],
                "trend_on": [0.0006, 0.0010, 0.0016],
                "long_floor": [0.006, 0.012],
                "rsi_buy": [42, 48],
                "rsi_sell": [52, 58],
                "vz": [0.7, 1.0, 1.3],
                "flow_abs": [0.01, 0.02],
                "w": [0.25, 0.35, 0.50],
            },
        ),
        (
            "vwap_revert",
            {
                "fast": [8],
                "slow": [48],
                "long": [192],
                "rsi": [10, 14],
                "vol": [32],
                "rank": [192],
                "zwin": [64],
                "vwap": [32, 64, 96],
                "atr": [32],
                "flow": [4],
                "vol_rank_max": [0.55, 0.70, 0.85],
                "long_floor": [0.006, 0.012, 0.02],
                "rsi_buy": [35, 40, 45],
                "rsi_sell": [55, 60, 65],
                "vz": [0.8, 1.1, 1.4],
                "w": [0.18, 0.25, 0.35],
            },
        ),
        (
            "breakout_retest",
            {
                "fast": [8, 12],
                "slow": [32, 48],
                "long": [128, 192],
                "rsi": [14],
                "vol": [32],
                "rank": [192],
                "zwin": [64],
                "vwap": [64],
                "atr": [32],
                "flow": [4, 8],
                "box": [16, 32, 48],
                "trend_on": [0.0005, 0.0010],
                "vol_rank_min": [0.55, 0.70],
                "flow_abs": [0.005, 0.015, 0.025],
                "w": [0.20, 0.30, 0.45],
            },
        ),
    ]
    for family, grid in grids:
        keys = list(grid)
        for values in itertools.product(*(grid[k] for k in keys)):
            params = dict(zip(keys, values))
            raw = build_candidate(bars, family, params).shift(1).fillna(0.0)
            for max_hold in ([16, 32, 64] if timeframe == "15m" else [8, 16, 32]):
                metrics, _, _ = simulate(bars, raw, max_hold=max_hold)
                if metrics["avg_entries_per_day"] < 0.85 or metrics["active_day_ratio"] < 0.55:
                    continue
                if metrics["trades"] < 90:
                    continue
                p = dict(params)
                p["max_hold"] = max_hold
                rows.append(Result(name=family, timeframe=timeframe, params=p, **metrics))
    rows.sort(
        key=lambda r: (
            r.max_drawdown >= -0.10,
            r.total_return,
            r.active_day_ratio,
            -abs(r.max_drawdown),
        ),
        reverse=True,
    )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2025-12-01")
    parser.add_argument("--end", default="2026-06-01")
    parser.add_argument("--out", default="btc_intraday_daily_opportunity_signal/research_snapshot/search_results.json")
    args = parser.parse_args()

    one = load_1m(args.start, args.end)
    outputs: dict[str, list[dict[str, object]]] = {}
    for timeframe, rule in [("15m", "15min"), ("1h", "1h")]:
        bars = resample(one, rule)
        outputs[timeframe] = [asdict(x) for x in search(bars, timeframe)[:50]]
        print(timeframe, len(outputs[timeframe]))
        for row in outputs[timeframe][:10]:
            print(json.dumps(row, ensure_ascii=False))

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(outputs, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
