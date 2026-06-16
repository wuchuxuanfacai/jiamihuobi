import math
from typing import Any

from getagent import runtime

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


def run() -> None:
    config = runtime.manifest.get("strategy_config", {}) or {}
    symbols = config.get("trading_symbols") or runtime.manifest.get("trading_symbols", ["BTCUSDT"])
    symbol = symbols[0]

    timeframe = str(config.get("timeframe") or "4h")
    history_days = max(30, min(_as_int(config.get("history_days"), 180), 365))
    frame = load_intraday_bars(symbol=symbol, interval=timeframe, days=history_days)
    decision = build_decision(frame, config)

    runtime.emit_signal(
        action=decision.action,
        symbol=symbol,
        confidence=_clean(decision.confidence) or 0.0,
        metrics=_clean_mapping(decision.metrics),
        meta=decision.meta,
    )


if __name__ == "__main__":
    run()
