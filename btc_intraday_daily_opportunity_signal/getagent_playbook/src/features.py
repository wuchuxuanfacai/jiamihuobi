from dataclasses import dataclass
from typing import Any

import pandas as pd

from getagent import data

try:
    from .decision_logic import compute_signal_state
    from .overlay_logic import compute_overlay_state
except ImportError:
    from decision_logic import compute_signal_state
    from overlay_logic import compute_overlay_state


positions: list[object] = []


@dataclass
class Decision:
    action: str
    confidence: float
    target_weight: float
    metrics: dict[str, Any]
    meta: dict[str, Any]


def load_intraday_bars(symbol: str, interval: str = "15m", days: int = 45) -> pd.DataFrame:
    bars = data.crypto.futures.kline(symbol=symbol, interval=interval, exchange="bitget", days=days)
    frame = data.to_dataframe(bars)
    if frame.empty:
        return frame
    if "date" in frame.columns:
        frame.index = pd.to_datetime(frame["date"], utc=True, errors="coerce")
    elif "time" in frame.columns:
        frame.index = pd.to_datetime(frame["time"], utc=True, errors="coerce")
    frame = frame.loc[frame.index.notna()].copy().sort_index()
    for col in ["open", "high", "low", "close", "volume", "quote_volume", "taker_buy_volume"]:
        if col in frame.columns:
            frame[col] = pd.to_numeric(frame[col], errors="coerce")
    if "quote_volume" not in frame.columns:
        frame["quote_volume"] = frame["volume"] * frame["close"]
    if "taker_buy_volume" not in frame.columns:
        frame["taker_buy_volume"] = frame["volume"] * 0.5
    return frame.dropna(subset=["open", "high", "low", "close"])


def _resample_1h(frame: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(
        {
            "open": frame["open"].resample("1h").first(),
            "high": frame["high"].resample("1h").max(),
            "low": frame["low"].resample("1h").min(),
            "close": frame["close"].resample("1h").last(),
            "volume": frame["volume"].resample("1h").sum(),
            "quote_volume": frame["quote_volume"].resample("1h").sum(),
            "taker_buy_volume": frame["taker_buy_volume"].resample("1h").sum(),
        }
    )
    return out.dropna(subset=["open", "high", "low", "close"])


def build_decision(frame: pd.DataFrame, config: dict[str, Any]) -> Decision:
    if frame.empty or "close" not in frame.columns:
        return Decision("watch", 0.0, 0.0, {"rows": int(len(frame))}, {"reason": "no usable intraday bars"})
    htf = frame[["close"]].resample("4h", label="right", closed="right").last().dropna()
    base = compute_signal_state(htf["close"].astype(float).to_numpy(), config, bars_per_day=6.0)
    hourly = _resample_1h(frame)
    overlay = compute_overlay_state(
        hourly["open"].to_numpy(),
        hourly["high"].to_numpy(),
        hourly["low"].to_numpy(),
        hourly["close"].to_numpy(),
        hourly["volume"].to_numpy(),
        hourly["quote_volume"].to_numpy(),
        hourly["taker_buy_volume"].to_numpy(),
        config,
        base.target_weight,
    )
    target = max(-float(config.get("max_short_weight", 1.0)), min(float(config.get("max_long_weight", 0.20)), base.target_weight + overlay.target_weight))
    action = "long" if target > 0 else "short" if target < 0 else "hold"
    confidence = 0.55 + min(abs(target), 1.0) * 0.35
    metrics = dict(base.metrics)
    metrics.update(overlay.metrics)
    metrics["base_target_weight"] = base.target_weight
    metrics["overlay_target_weight"] = overlay.target_weight
    metrics["target_weight"] = target
    return Decision(
        action=action,
        confidence=float(min(0.95, confidence)),
        target_weight=float(target),
        metrics=metrics,
        meta={
            "regime": base.regime + "+" + overlay.regime,
            "timeframe": "15m",
            "decision_timeframes": "4h base trend plus 1h overlay",
            "latest_bar_time": str(frame.index[-1]),
            "source": "btc-intraday-daily-opportunity",
        },
    )
