from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from getagent import data

try:
    from .decision_logic import compute_signal_state
except ImportError:
    from decision_logic import compute_signal_state


positions: list[object] = []


@dataclass
class Decision:
    action: str
    confidence: float
    target_weight: float
    metrics: dict[str, Any]
    meta: dict[str, Any]


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def load_intraday_bars(symbol: str, interval: str = "15m", days: int = 45) -> pd.DataFrame:
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
    interval = str(config.get("timeframe") or "15m")
    if frame.empty or "close" not in frame.columns:
        return Decision(
            action="watch",
            confidence=0.0,
            target_weight=0.0,
            metrics={"rows": int(len(frame)), "reason_code": 1},
            meta={"reason": "no usable intraday bars"},
        )

    decision_frame = frame
    bars_per_day = 96.0 if interval == "15m" else 24.0 if interval == "1h" else 6.0
    if interval == "15m":
        decision_frame = frame[["close"]].resample("4h", label="right", closed="right").last().dropna()
        bars_per_day = 6.0
    if decision_frame.empty or "close" not in decision_frame.columns:
        return Decision(
            action="watch",
            confidence=0.0,
            target_weight=0.0,
            metrics={"rows": int(len(frame)), "decision_rows": 0, "reason_code": 2},
            meta={"reason": "no usable higher-timeframe bars"},
        )

    idle_bars = _as_int(config.get("idle_bars"), 0)
    local_config = dict(config)
    local_config["idle_bars"] = idle_bars
    state = compute_signal_state(decision_frame["close"].astype(float).to_numpy(), local_config, bars_per_day=bars_per_day)
    return Decision(
        action=state.action,
        confidence=float(state.confidence),
        target_weight=state.target_weight,
        metrics=state.metrics,
        meta={
            "regime": state.regime,
            "timeframe": interval,
            "decision_timeframe": "4h_from_15m" if interval == "15m" else interval,
            "source": "btc-intraday-regime-rotation",
            "latest_bar_time": str(frame.index[-1]),
            "latest_decision_bar_time": str(decision_frame.index[-1]),
            "notes": "15m BTC execution feed with higher-timeframe selective short trend re-entry decisions.",
        },
    )
