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
