import math
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd

from getagent import backtest, data, runtime

from .features import build_decision, load_intraday_bars


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


def _as_float(value: Any, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(parsed):
        return default
    return parsed


def _rolling_days(value: Any, bars_per_day: float, minimum: int) -> int:
    return max(minimum, int(round(_as_float(value, 1.0) * bars_per_day)))


def _fetch_replay_frame(
    symbol: str,
    interval: str,
    start: datetime | None,
    end: datetime | None,
    history_days: int,
) -> Any:
    frames = []
    if end is None:
        end = datetime.now(timezone.utc)
    if start is None:
        start = end - timedelta(days=history_days)
    cursor = start
    while cursor < end:
        chunk_end = min(cursor + timedelta(days=89), end)
        bars = data.crypto.futures.kline(
            symbol=symbol,
            interval=interval,
            exchange="bitget",
            start_time=_to_ms(cursor),
            end_time=_to_ms(chunk_end),
        )
        frame = backtest.prepare_frame(bars, datetime_index="date")
        if not frame.empty:
            frames.append(frame)
        cursor = chunk_end + timedelta(milliseconds=1)
    if not frames:
        return pd.DataFrame()
    merged = pd.concat(frames).sort_index()
    return merged.loc[~merged.index.duplicated(keep="last")]


def _effective_spec(config: dict[str, Any]) -> dict[str, Any]:
    spec = dict(runtime.backtest_spec)
    strategy_spec = dict(spec.get("strategy", {}) or {})
    strategy_config = dict(strategy_spec.get("config", {}) or {})
    interval = str(config.get("timeframe") or "4h")
    bars_per_day = 6.0 if interval == "4h" else 24.0 if interval == "1h" else 96.0
    mapped = {
        "margin_budget": str(config.get("margin_budget") or strategy_config.get("margin_budget") or "1000"),
        "min_trade_size": str(config.get("min_trade_size") or strategy_config.get("min_trade_size") or "0.001"),
        "target_step_weight": _as_float(config.get("target_step_weight"), strategy_config.get("target_step_weight", 0.02)),
        "fast_window": _rolling_days(config.get("fast_trend_days"), bars_per_day, 3),
        "mid_window": _rolling_days(config.get("mid_trend_days"), bars_per_day, 6),
        "slow_window": _rolling_days(config.get("slow_trend_days"), bars_per_day, 12),
        "long_window": _rolling_days(config.get("long_trend_days"), bars_per_day, 24),
        "vol_window": _rolling_days(config.get("vol_days"), bars_per_day, 6),
        "bear_on": _as_float(config.get("bear_on"), strategy_config.get("bear_on", 0.42)),
        "bear_off": _as_float(config.get("bear_off"), strategy_config.get("bear_off", 0.30)),
        "ret_slow_max": _as_float(config.get("ret_slow_max"), strategy_config.get("ret_slow_max", -0.04)),
        "ret_mid_max": _as_float(config.get("ret_mid_max"), strategy_config.get("ret_mid_max", 0.01)),
        "short_sma_mult": _as_float(config.get("short_sma_mult"), strategy_config.get("short_sma_mult", 1.03)),
        "mid_sma_mult": _as_float(config.get("mid_sma_mult"), strategy_config.get("mid_sma_mult", 1.0)),
        "rebound_ret_max": _as_float(config.get("rebound_ret_max"), strategy_config.get("rebound_ret_max", 0.04)),
        "rebound_sma_mult": _as_float(config.get("rebound_sma_mult"), strategy_config.get("rebound_sma_mult", 1.005)),
        "short_target_vol": _as_float(config.get("short_target_vol"), strategy_config.get("short_target_vol", 1.20)),
        "short_floor_cap": _as_float(config.get("short_floor_cap"), strategy_config.get("short_floor_cap", 1.6)),
        "max_short_weight": _as_float(config.get("max_short_weight"), strategy_config.get("max_short_weight", 1.6)),
        "short_base": _as_float(config.get("short_base"), strategy_config.get("short_base", 0.65)),
        "short_conf": _as_float(config.get("short_conf"), strategy_config.get("short_conf", 0.55)),
        "weight_scale": _as_float(config.get("weight_scale"), strategy_config.get("weight_scale", 1.2)),
        "vol_ceiling": _as_float(config.get("vol_ceiling"), strategy_config.get("vol_ceiling", 0.35)),
        "vol_floor_min": _as_float(config.get("vol_floor_min"), strategy_config.get("vol_floor_min", 0.20)),
        "high_vol_floor": _as_float(config.get("high_vol_floor"), strategy_config.get("high_vol_floor", 0.40)),
        "high_vol_ceiling": _as_float(config.get("high_vol_ceiling"), strategy_config.get("high_vol_ceiling", 0.55)),
        "high_vol_bear_on": _as_float(config.get("high_vol_bear_on"), strategy_config.get("high_vol_bear_on", 0.42)),
        "high_vol_sma_mult": _as_float(config.get("high_vol_sma_mult"), strategy_config.get("high_vol_sma_mult", 1.02)),
        "high_vol_target_vol": _as_float(config.get("high_vol_target_vol"), strategy_config.get("high_vol_target_vol", 0.50)),
        "high_vol_short_cap": _as_float(config.get("high_vol_short_cap"), strategy_config.get("high_vol_short_cap", 1.0)),
        "high_vol_short_base": _as_float(config.get("high_vol_short_base"), strategy_config.get("high_vol_short_base", 0.65)),
        "high_vol_short_conf": _as_float(config.get("high_vol_short_conf"), strategy_config.get("high_vol_short_conf", 0.0)),
    }
    strategy_config.update(mapped)
    trade_start = str(config.get("cloud_trade_start") or strategy_config.get("trade_start") or "")
    if trade_start:
        strategy_config["trade_start"] = trade_start
    strategy_spec["config"] = strategy_config
    spec["strategy"] = strategy_spec
    execution = dict(spec.get("execution", {}) or {})
    fetch_start = str(config.get("cloud_fetch_start") or execution.get("start") or "")
    fetch_end = str(config.get("cloud_fetch_end") or execution.get("end") or "")
    if fetch_start:
        execution["start"] = fetch_start
    if fetch_end:
        execution["end"] = fetch_end
    spec["execution"] = execution
    return spec


def _run_historical(config: dict[str, Any], symbol: str) -> None:
    interval = str(config.get("timeframe") or "4h")
    history_days = max(90, min(_as_int(config.get("history_days"), 150), 270))
    spec = _effective_spec(config)
    execution = spec.get("execution", {}) or {}
    start = _parse_iso(execution.get("start"))
    end = _parse_iso(execution.get("end"))
    replay_frame = _fetch_replay_frame(
        symbol=symbol,
        interval=interval,
        start=start,
        end=end,
        history_days=history_days,
    )
    if end is not None:
        replay_frame = replay_frame.loc[replay_frame.index <= end]
    if replay_frame.empty:
        runtime.emit_signal(
            action="watch",
            symbol=symbol,
            confidence=0.0,
            metrics={"rows": 0},
            meta={"reason": "no historical bars returned"},
        )
        return

    result = backtest.run(
        ohlcv_data={f"{symbol}.BINANCE": replay_frame},
        spec=spec,
    )
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
        action="short" if net_pnl > 0 else "watch",
        symbol=symbol,
        confidence=_clean(result.win_rate) or 0.0,
        metrics=metrics,
        meta={"chart_path": chart_path, "mode": "historical_backtest"},
    )


def _run_signal(config: dict[str, Any], symbol: str) -> None:
    timeframe = str(config.get("timeframe") or "4h")
    history_days = max(30, min(_as_int(config.get("history_days"), 90), 90))
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
