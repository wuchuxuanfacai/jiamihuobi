from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from getagent import data
try:
    from .decision_logic import compute_signal_state
except ImportError:
    from decision_logic import compute_signal_state


@dataclass
class Decision:
    action: str
    confidence: float
    target_weight: float
    metrics: dict[str, Any]
    meta: dict[str, Any]


def _as_float(value: Any, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if not np.isfinite(parsed):
        return default
    return parsed


def _rolling_days(value: Any, bars_per_day: float, minimum: int) -> int:
    return max(minimum, int(round(_as_float(value, 1.0) * bars_per_day)))


def load_intraday_bars(symbol: str, interval: str = "4h", days: int = 180) -> pd.DataFrame:
    bars = data.crypto.futures.kline(
        symbol=symbol,
        interval=interval,
        exchange="bitget",
        days=days,
    )
    frame = data.to_dataframe(bars)
    if frame.empty:
        return frame
    if "date" in frame.columns:
        frame.index = pd.to_datetime(frame["date"], utc=True, errors="coerce")
    elif "time" in frame.columns:
        frame.index = pd.to_datetime(frame["time"], utc=True, errors="coerce")
    frame = frame.loc[frame.index.notna()].copy()
    frame = frame.sort_index()
    for col in ["open", "high", "low", "close", "volume"]:
        if col in frame.columns:
            frame[col] = pd.to_numeric(frame[col], errors="coerce")
    return frame.dropna(subset=["close"])


def build_decision(frame: pd.DataFrame, config: dict[str, Any]) -> Decision:
    interval = str(config.get("timeframe") or "4h")
    bars_per_day = 6.0 if interval == "4h" else 24.0 if interval == "1h" else 96.0

    if frame.empty or "close" not in frame.columns:
        return Decision(
            action="watch",
            confidence=0.0,
            target_weight=0.0,
            metrics={"rows": int(len(frame)), "reason_code": 1},
            meta={"reason": "no usable intraday bars for adaptive regime checks"},
        )

    state = compute_signal_state(frame["close"].astype(float).to_numpy(), config, bars_per_day=bars_per_day)
    meta = {
        "regime": state.regime,
        "timeframe": interval,
        "source": "btc-adaptive-trend-range-composite",
        "latest_bar_time": str(frame.index[-1]),
        "notes": "BTC futures composite target-weight model: long trend, short trend, and range mean-reversion components are summed before clipping.",
    }
    return Decision(
        action=state.action,
        confidence=float(state.confidence),
        target_weight=state.target_weight,
        metrics=state.metrics,
        meta=meta,
    )
