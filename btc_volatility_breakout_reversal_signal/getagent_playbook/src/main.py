import math
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd

from getagent import backtest, data, runtime

from .features import build_decision, load_intraday_bars


positions: list[Any] = []


def _clean(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _clean_mapping(values: dict[str, Any]) -> dict[str, Any]:
    return {key: _clean(value) for key, value in values.items()}


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value: Any, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(parsed):
        return default
    return parsed


def _parse_iso(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _to_ms(value: datetime) -> int:
    return int(value.timestamp() * 1000)


def _chunk_days(interval: str) -> int:
    if interval == "15m":
        return 10
    if interval == "1h":
        return 40
    return 89


def _prepare_frame_from_bars(bars: Any) -> pd.DataFrame:
    frame = backtest.prepare_frame(bars, datetime_index="date")
    if frame.empty:
        return frame
    frame = frame.sort_index().copy()
    return _sanitize_ohlcv_frame(frame)


def _sanitize_ohlcv_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    frame = frame.sort_index().copy()
    for col in ("open", "high", "low", "close", "volume"):
        if col in frame.columns:
            frame[col] = pd.to_numeric(frame[col], errors="coerce")
    frame = frame.dropna(subset=["open", "high", "low", "close"])
    frame = frame.loc[
        frame[["open", "high", "low", "close"]].apply(lambda row: all(math.isfinite(float(x)) for x in row), axis=1)
    ].copy()
    # Defensive OHLC normalization for dirty upstream bars before Nautilus replay.
    refs = frame[["open", "high", "low", "close"]].astype(float)
    high_ref = refs.max(axis=1)
    low_ref = refs.min(axis=1)
    frame["high"] = high_ref
    frame["low"] = low_ref
    frame["open"] = frame["open"].clip(lower=frame["low"], upper=frame["high"])
    frame["close"] = frame["close"].clip(lower=frame["low"], upper=frame["high"])
    # Match the instrument precision so tiny float artifacts cannot invert OHLC after conversion.
    frame["open"] = frame["open"].round(2)
    frame["high"] = frame[["open", "high", "close"]].max(axis=1).round(2)
    frame["low"] = frame[["open", "low", "close"]].min(axis=1).round(2)
    frame["close"] = frame["close"].round(2)
    frame["high"] = frame[["open", "high", "low", "close"]].max(axis=1)
    frame["low"] = frame[["open", "high", "low", "close"]].min(axis=1)
    if "volume" in frame.columns:
        frame["volume"] = frame["volume"].clip(lower=0.0).fillna(0.0)
    frame = _force_ohlc_invariants(frame)
    return frame


def _force_ohlc_invariants(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    frame = frame.copy()
    for col in ("open", "high", "low", "close", "volume"):
        if col in frame.columns:
            frame[col] = pd.to_numeric(frame[col], errors="coerce")
    frame = frame.dropna(subset=["open", "high", "low", "close"]).copy()
    refs = frame[["open", "high", "low", "close"]].astype(float).round(2)
    row_high = refs.max(axis=1)
    row_low = refs.min(axis=1)
    frame["open"] = refs["open"]
    frame["close"] = refs["close"]
    frame["high"] = pd.concat([refs["open"], refs["close"], row_high], axis=1).max(axis=1).round(2)
    frame["low"] = pd.concat([refs["open"], refs["close"], row_low], axis=1).min(axis=1).round(2)
    frame["high"] = pd.concat([frame["open"], frame["close"], frame["high"]], axis=1).max(axis=1).round(2)
    frame["low"] = pd.concat([frame["open"], frame["close"], frame["low"]], axis=1).min(axis=1).round(2)
    if "volume" in frame.columns:
        frame["volume"] = frame["volume"].clip(lower=0.0).fillna(0.0)
    keep = ["open", "high", "low", "close"] + (["volume"] if "volume" in frame.columns else [])
    frame = frame[keep]
    ok = (frame["high"] >= frame["open"]) & (frame["high"] >= frame["close"]) & (frame["low"] <= frame["open"]) & (frame["low"] <= frame["close"])
    frame = frame.loc[ok].copy()
    return frame


def _fetch_replay_frame(symbol: str, interval: str, start: datetime | None, end: datetime | None, history_days: int) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    if end is None:
        end = datetime.now(timezone.utc)
    if start is None:
        start = end - timedelta(days=history_days)
    cursor = start
    step_days = _chunk_days(interval)
    while cursor < end:
        chunk_end = min(cursor + timedelta(days=step_days), end)
        bars = data.crypto.futures.kline(
            symbol=symbol,
            interval=interval,
            exchange="bitget",
            limit=1000,
            start_time=_to_ms(cursor),
            end_time=_to_ms(chunk_end),
        )
        frame = _prepare_frame_from_bars(bars)
        if not frame.empty:
            frames.append(frame)
        cursor = chunk_end + timedelta(milliseconds=1)
    if not frames:
        return pd.DataFrame()
    merged = pd.concat(frames).sort_index()
    merged = merged.loc[~merged.index.duplicated(keep="last")]
    return _sanitize_ohlcv_frame(merged)


def _effective_spec(config: dict[str, Any]) -> dict[str, Any]:
    spec = dict(runtime.backtest_spec)
    strategy_spec = dict(spec.get("strategy", {}) or {})
    strategy_config = dict(strategy_spec.get("config", {}) or {})
    execution = dict(spec.get("execution", {}) or {})
    interval = str(config.get("timeframe") or "15m")

    mapped = {
        "margin_budget": str(config.get("margin_budget") or strategy_config.get("margin_budget") or "50000"),
        "leverage": _as_int(config.get("leverage"), _as_int(strategy_config.get("leverage"), 3)),
        "min_trade_size": str(config.get("min_trade_size") or strategy_config.get("min_trade_size") or "0.001"),
        "decision_interval_minutes": _as_int(config.get("decision_interval_minutes"), _as_int(strategy_config.get("decision_interval_minutes"), 240)),
        "target_step_weight": _as_float(config.get("target_step_weight"), strategy_config.get("target_step_weight", 0.05)),
        "max_effective_exposure": _as_float(config.get("max_effective_exposure"), strategy_config.get("max_effective_exposure", 3.20)),
        "min_rebalance_qty_pct": _as_float(config.get("min_rebalance_qty_pct"), strategy_config.get("min_rebalance_qty_pct", 0.25)),
        "squeeze_window": _as_int(config.get("squeeze_window"), _as_int(strategy_config.get("squeeze_window"), 96)),
        "stretch_window": _as_int(config.get("stretch_window"), _as_int(strategy_config.get("stretch_window"), 32)),
        "trend_window": _as_int(config.get("trend_window"), _as_int(strategy_config.get("trend_window"), 384)),
        "vol_window": _as_int(config.get("vol_window"), _as_int(strategy_config.get("vol_window"), 96)),
        "overheat_z": _as_float(config.get("overheat_z"), strategy_config.get("overheat_z", 1.65)),
        "overheat_ret_min": _as_float(config.get("overheat_ret_min"), strategy_config.get("overheat_ret_min", 0.035)),
        "near_high_mult": _as_float(config.get("near_high_mult"), strategy_config.get("near_high_mult", 0.995)),
        "vol_ceiling": _as_float(config.get("vol_ceiling"), strategy_config.get("vol_ceiling", 0.95)),
        "turn_fast_ret_max": _as_float(config.get("turn_fast_ret_max"), strategy_config.get("turn_fast_ret_max", -0.004)),
        "fade_from_high_mult": _as_float(config.get("fade_from_high_mult"), strategy_config.get("fade_from_high_mult", 0.985)),
        "vol_expansion_min": _as_float(config.get("vol_expansion_min"), strategy_config.get("vol_expansion_min", 1.08)),
        "trend_block_ret": _as_float(config.get("trend_block_ret"), strategy_config.get("trend_block_ret", 0.22)),
        "washout_z": _as_float(config.get("washout_z"), strategy_config.get("washout_z", 1.85)),
        "washout_ret_max": _as_float(config.get("washout_ret_max"), strategy_config.get("washout_ret_max", 0.045)),
        "near_low_mult": _as_float(config.get("near_low_mult"), strategy_config.get("near_low_mult", 1.005)),
        "long_vol_ceiling": _as_float(config.get("long_vol_ceiling"), strategy_config.get("long_vol_ceiling", 0.90)),
        "turn_fast_ret_min": _as_float(config.get("turn_fast_ret_min"), strategy_config.get("turn_fast_ret_min", 0.004)),
        "bounce_from_low_mult": _as_float(config.get("bounce_from_low_mult"), strategy_config.get("bounce_from_low_mult", 1.015)),
        "short_target_vol": _as_float(config.get("short_target_vol"), strategy_config.get("short_target_vol", 0.42)),        "long_target_vol": _as_float(config.get("long_target_vol"), strategy_config.get("long_target_vol", 0.18)),        "rebalance_cooldown_bars": _as_int(config.get("rebalance_cooldown_bars"), _as_int(strategy_config.get("rebalance_cooldown_bars"), 2)),
        "min_hold_bars": _as_int(config.get("min_hold_bars"), _as_int(strategy_config.get("min_hold_bars"), 4)),
        "reversal_min_weight": _as_float(config.get("reversal_min_weight"), strategy_config.get("reversal_min_weight", 0.10)),
        "trade_start": str(config.get("cloud_trade_start") or strategy_config.get("trade_start") or ""),
    }
    strategy_config.update(mapped)
    strategy_spec["config"] = strategy_config
    spec["strategy"] = strategy_spec

    fetch_start = str(config.get("cloud_fetch_start") or execution.get("start") or "")
    fetch_end = str(config.get("cloud_fetch_end") or execution.get("end") or "")
    if fetch_start:
        execution["start"] = fetch_start
    if fetch_end:
        execution["end"] = fetch_end
    spec["execution"] = execution

    instrument = dict(spec.get("instrument", {}) or {})
    instrument["bar_type"] = f"{symbol}.BINANCE-15-MINUTE-LAST-EXTERNAL" if (symbol := "BTCUSDT") else instrument.get("bar_type")
    spec["instrument"] = instrument
    return spec


def _run_historical(config: dict[str, Any], symbol: str) -> None:
    interval = str(config.get("timeframe") or "15m")
    spec = _effective_spec(config)
    execution = spec.get("execution", {}) or {}
    start = _parse_iso(execution.get("start"))
    end = _parse_iso(execution.get("end"))
    history_days = max(60, _as_int(config.get("history_days"), 180))
    replay_frame = _fetch_replay_frame(symbol=symbol, interval=interval, start=start, end=end, history_days=history_days)
    if end is not None:
        replay_frame = replay_frame.loc[replay_frame.index <= end]
    replay_frame = _force_ohlc_invariants(replay_frame)
    replay_frame = _force_ohlc_invariants(replay_frame)
    if replay_frame.empty:
        runtime.emit_signal(
            action="watch",
            symbol=symbol,
            confidence=0.0,
            metrics={"rows": 0},
            meta={"reason": "no historical bars returned"},
        )
        return

    result = backtest.run(ohlcv_data={f"{symbol}.BINANCE": replay_frame}, spec=spec)
    chart_path = backtest.generate_chart(result)
    summary = result.summary or {}
    net_pnl = float(summary.get("net_pnl", 0) or 0)
    metrics = _clean_mapping(
        {
            "total_return_pct": result.total_return_pct,
            "net_pnl": net_pnl,
            "starting_balance": summary.get("starting_balance"),
            "sharpe_ratio": result.sharpe_ratio,
            "max_drawdown_pct": result.max_drawdown_pct,
            "win_rate": result.win_rate,
            "total_trades": result.total_trades,
            "profit_factor": result.profit_factor,
            "rows": len(replay_frame),
            "cloud_fetch_start": execution.get("start"),
            "cloud_trade_start": (spec.get("strategy", {}) or {}).get("config", {}).get("trade_start"),
            "cloud_fetch_end": execution.get("end"),
        }
    )
    runtime.emit_signal(
        action="long" if net_pnl > 0 else "watch",
        symbol=symbol,
        confidence=_clean(result.win_rate) or 0.0,
        metrics=metrics,
        meta={"chart_path": chart_path, "mode": "historical_backtest", "timeframe": interval},
    )


def _run_signal(config: dict[str, Any], symbol: str) -> None:
    timeframe = str(config.get("timeframe") or "15m")
    history_days = max(20, min(_as_int(config.get("history_days"), 45), 90))
    frame = load_intraday_bars(symbol=symbol, interval=timeframe, days=history_days)
    decision = build_decision(frame, config)
    runtime.emit_signal(
        action=decision.action,
        symbol=symbol,
        confidence=_clean(decision.confidence) or 0.0,
        metrics=_clean_mapping(decision.metrics),
        meta=decision.meta,
    )


def run() -> None:
    config = runtime.manifest.get("strategy_config", {}) or {}
    symbols = config.get("trading_symbols") or runtime.manifest.get("trading_symbols", ["BTCUSDT"])
    symbol = symbols[0]
    if getattr(runtime, "evaluation_mode", "") == "historical":
        _run_historical(config, symbol)
    else:
        _run_signal(config, symbol)


if __name__ == "__main__":
    run()
