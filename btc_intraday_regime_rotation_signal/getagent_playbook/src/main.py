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
    refs = frame[["open", "high", "low", "close"]].astype(float)
    row_high = refs.max(axis=1)
    row_low = refs.min(axis=1)
    frame["open"] = refs["open"].clip(lower=row_low, upper=row_high).round(2)
    frame["close"] = refs["close"].clip(lower=row_low, upper=row_high).round(2)
    frame["high"] = pd.concat([frame["open"], frame["close"], row_high], axis=1).max(axis=1).round(2)
    frame["low"] = pd.concat([frame["open"], frame["close"], row_low], axis=1).min(axis=1).round(2)
    frame["high"] = pd.concat([frame["open"], frame["high"], frame["low"], frame["close"]], axis=1).max(axis=1)
    frame["low"] = pd.concat([frame["open"], frame["high"], frame["low"], frame["close"]], axis=1).min(axis=1)
    bad = (frame["low"] > frame["open"]) | (frame["low"] > frame["close"]) | (frame["high"] < frame["open"]) | (frame["high"] < frame["close"])
    if bool(bad.any()):
        refs = frame.loc[bad, ["open", "high", "low", "close"]].astype(float)
        frame.loc[bad, "high"] = refs.max(axis=1)
        frame.loc[bad, "low"] = refs.min(axis=1)
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
        "target_step_weight": _as_float(config.get("target_step_weight"), strategy_config.get("target_step_weight", 0.06)),
        "max_effective_exposure": _as_float(config.get("max_effective_exposure"), strategy_config.get("max_effective_exposure", 2.36)),
        "min_rebalance_qty_pct": _as_float(config.get("min_rebalance_qty_pct"), strategy_config.get("min_rebalance_qty_pct", 0.25)),
        "htf_bars_per_decision": _as_int(config.get("htf_bars_per_decision"), _as_int(strategy_config.get("htf_bars_per_decision"), 16)),
        "fast_window": _as_int(config.get("fast_window"), _as_int(strategy_config.get("fast_window"), 18)),
        "mid_window": _as_int(config.get("mid_window"), _as_int(strategy_config.get("mid_window"), 60)),
        "slow_window": _as_int(config.get("slow_window"), _as_int(strategy_config.get("slow_window"), 180)),
        "long_window": _as_int(config.get("long_window"), _as_int(strategy_config.get("long_window"), 540)),
        "vol_window": _as_int(config.get("vol_window"), _as_int(strategy_config.get("vol_window"), 60)),
        "bear_on": _as_float(config.get("bear_on"), strategy_config.get("bear_on", 0.56)),
        "bear_off": _as_float(config.get("bear_off"), strategy_config.get("bear_off", 0.50)),
        "ret_slow_max": _as_float(config.get("ret_slow_max"), strategy_config.get("ret_slow_max", -0.08)),
        "ret_mid_max": _as_float(config.get("ret_mid_max"), strategy_config.get("ret_mid_max", -0.04)),
        "short_sma_mult": _as_float(config.get("short_sma_mult"), strategy_config.get("short_sma_mult", 0.98)),
        "mid_sma_mult": _as_float(config.get("mid_sma_mult"), strategy_config.get("mid_sma_mult", 1.0)),
        "rebound_ret_max": _as_float(config.get("rebound_ret_max"), strategy_config.get("rebound_ret_max", 0.08)),
        "rebound_sma_mult": _as_float(config.get("rebound_sma_mult"), strategy_config.get("rebound_sma_mult", 1.005)),
        "short_target_vol": _as_float(config.get("short_target_vol"), strategy_config.get("short_target_vol", 0.35)),
        "short_floor_cap": _as_float(config.get("short_floor_cap"), strategy_config.get("short_floor_cap", 1.00)),
        "short_base": _as_float(config.get("short_base"), strategy_config.get("short_base", 0.65)),
        "short_conf": _as_float(config.get("short_conf"), strategy_config.get("short_conf", 0.55)),
        "max_signal_weight": _as_float(config.get("max_signal_weight"), strategy_config.get("max_signal_weight", 1.00)),
        "max_short_weight": _as_float(config.get("max_short_weight"), strategy_config.get("max_short_weight", 1.00)),
        "max_long_weight": _as_float(config.get("max_long_weight"), strategy_config.get("max_long_weight", 0.00)),
        "weight_scale": _as_float(config.get("weight_scale"), strategy_config.get("weight_scale", 1.75)),
        "vol_ceiling": _as_float(config.get("vol_ceiling"), strategy_config.get("vol_ceiling", 0.45)),
        "vol_floor_min": _as_float(config.get("vol_floor_min"), strategy_config.get("vol_floor_min", 0.20)),
        "long_on": _as_float(config.get("long_on"), strategy_config.get("long_on", 0.68)),
        "long_ret_mid_min": _as_float(config.get("long_ret_mid_min"), strategy_config.get("long_ret_mid_min", 0.0)),
        "long_sma_mult": _as_float(config.get("long_sma_mult"), strategy_config.get("long_sma_mult", 1.02)),
        "long_vol_ceiling": _as_float(config.get("long_vol_ceiling"), strategy_config.get("long_vol_ceiling", 0.45)),
        "long_floor_cap": _as_float(config.get("long_floor_cap"), strategy_config.get("long_floor_cap", 0.00)),
        "channel_slope_deadband": _as_float(config.get("channel_slope_deadband"), strategy_config.get("channel_slope_deadband", 0.00313)),
        "range_bias_strength": _as_float(config.get("range_bias_strength"), strategy_config.get("range_bias_strength", 0.54640)),
        "channel_slope_window": _as_int(config.get("channel_slope_window"), _as_int(strategy_config.get("channel_slope_window"), 45)),
        "range_mr_cap": _as_float(config.get("range_mr_cap"), strategy_config.get("range_mr_cap", 0.02)),
        "range_min_component": _as_float(config.get("range_min_component"), strategy_config.get("range_min_component", 0.0)),
        "range_z_entry": _as_float(config.get("range_z_entry"), strategy_config.get("range_z_entry", 1.50)),
        "range_trend_max": _as_float(config.get("range_trend_max"), strategy_config.get("range_trend_max", 0.30)),
        "range_bear_max": _as_float(config.get("range_bear_max"), strategy_config.get("range_bear_max", 0.30)),
        "range_vol_ceiling": _as_float(config.get("range_vol_ceiling"), strategy_config.get("range_vol_ceiling", 0.28)),
        "range_abs_slope_max": _as_float(config.get("range_abs_slope_max"), strategy_config.get("range_abs_slope_max", 0.012)),
        "range_ret_slow_abs_max": _as_float(config.get("range_ret_slow_abs_max"), strategy_config.get("range_ret_slow_abs_max", 0.08)),
        "trend_invalidation_off": _as_float(config.get("trend_invalidation_off"), strategy_config.get("trend_invalidation_off", 0.30)),
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
