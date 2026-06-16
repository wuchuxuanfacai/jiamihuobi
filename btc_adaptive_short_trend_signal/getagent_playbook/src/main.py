import math
from typing import Any

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


def _run_historical(config: dict[str, Any], symbol: str) -> None:
    bars = data.crypto.futures.kline(
        symbol=symbol,
        interval=str(config.get("timeframe") or "4h"),
        exchange="bitget",
        days=max(30, min(_as_int(config.get("history_days"), 90), 90)),
        limit=1000,
    )
    replay_frame = backtest.prepare_frame(bars, datetime_index="date")
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
        spec=runtime.backtest_spec,
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
