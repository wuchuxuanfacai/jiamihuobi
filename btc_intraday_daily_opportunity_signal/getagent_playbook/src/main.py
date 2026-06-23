import math
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
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
    return parsed if math.isfinite(parsed) else default


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


def _prepare_frame_from_bars(bars: Any) -> pd.DataFrame:
    frame = backtest.prepare_frame(bars, datetime_index="date")
    if frame.empty:
        return frame
    return _sanitize_ohlcv_frame(frame.sort_index().copy())


def _sanitize_ohlcv_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    frame = frame.sort_index().copy()
    for col in ("open", "high", "low", "close", "volume"):
        if col in frame.columns:
            frame[col] = pd.to_numeric(frame[col], errors="coerce")
    frame = frame.dropna(subset=["open", "high", "low", "close"])
    refs = frame[["open", "high", "low", "close"]].astype(float)
    high_ref = refs.max(axis=1)
    low_ref = refs.min(axis=1)
    frame["open"] = refs["open"].clip(lower=low_ref, upper=high_ref).round(2)
    frame["close"] = refs["close"].clip(lower=low_ref, upper=high_ref).round(2)
    frame["high"] = pd.concat([frame["open"], frame["close"], high_ref], axis=1).max(axis=1).round(2)
    frame["low"] = pd.concat([frame["open"], frame["close"], low_ref], axis=1).min(axis=1).round(2)
    frame["high"] = pd.concat([frame["open"], frame["high"], frame["low"], frame["close"]], axis=1).max(axis=1)
    frame["low"] = pd.concat([frame["open"], frame["high"], frame["low"], frame["close"]], axis=1).min(axis=1)
    if "volume" in frame.columns:
        frame["volume"] = frame["volume"].clip(lower=0.0).fillna(0.0)
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
    while cursor < end:
        chunk_end = min(cursor + timedelta(days=10), end)
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
    keys = [
        "margin_budget",
        "leverage",
        "min_trade_size",
        "target_step_weight",
        "max_effective_exposure",
        "min_rebalance_qty_pct",
        "fast_window",
        "mid_window",
        "slow_window",
        "long_window",
        "vol_window",
        "bear_on",
        "ret_slow_max",
        "ret_mid_max",
        "short_sma_mult",
        "mid_sma_mult",
        "rebound_ret_max",
        "rebound_sma_mult",
        "short_target_vol",
        "short_floor_cap",
        "short_base",
        "short_conf",
        "max_signal_weight",
        "max_short_weight",
        "max_long_weight",
        "weight_scale",
        "vol_ceiling",
        "vol_floor_min",
        "long_on",
        "long_ret_mid_min",
        "long_sma_mult",
        "long_vol_ceiling",
        "long_floor_cap",
        "channel_slope_window",
        "range_z_entry",
        "range_mr_cap",
        "range_trend_max",
        "range_bear_max",
        "range_vol_ceiling",
        "range_abs_slope_max",
        "range_ret_slow_abs_max",
        "trend_invalidation_off",
        "overlay_cap",
        "overlay_z_entry",
        "overlay_base_gate",
        "overlay_max_hold_1h",
        "overlay_vwap_window",
        "overlay_atr_window",
        "overlay_rsi_window",
        "overlay_flow_window",
        "overlay_vol_window",
        "overlay_rank_window",
        "overlay_rsi_low",
        "overlay_rsi_high",
        "overlay_flow_gate",
        "overlay_vol_rank_max",
    ]
    for key in keys:
        if key in config:
            strategy_config[key] = config[key]
    strategy_config["trade_start"] = str(config.get("cloud_trade_start") or strategy_config.get("trade_start") or "")
    strategy_spec["config"] = strategy_config
    spec["strategy"] = strategy_spec
    if config.get("cloud_fetch_start"):
        execution["start"] = str(config.get("cloud_fetch_start"))
    if config.get("cloud_fetch_end"):
        execution["end"] = str(config.get("cloud_fetch_end"))
    spec["execution"] = execution
    instrument = dict(spec.get("instrument", {}) or {})
    instrument["bar_type"] = "BTCUSDT.BINANCE-15-MINUTE-LAST-EXTERNAL"
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
    if replay_frame.empty:
        runtime.emit_signal(action="watch", symbol=symbol, confidence=0.0, metrics={"rows": 0}, meta={"reason": "no historical bars returned"})
        return
    result = backtest.run(ohlcv_data={f"{symbol}.BINANCE": replay_frame}, spec=spec)
    chart_path = backtest.generate_chart(result)
    summary = result.summary or {}
    account_report = ((result.raw or {}).get("reports", {}) or {}).get("account", []) if isinstance(result.raw, dict) else []
    initial_capital = float(summary.get("starting_balance", 100000.0) or 100000.0)
    ending_total = float(summary.get("ending_balance", initial_capital) or initial_capital)
    equity_curve = []
    if isinstance(account_report, list) and account_report:
        first_total = None
        for row in account_report:
            try:
                total = float(row.get("total"))
            except (TypeError, ValueError, AttributeError):
                continue
            if first_total is None:
                first_total = total
            equity_curve.append(
                {
                    "timestamp": str(row.get("index") or row.get("timestamp") or ""),
                    "value": total,
                    "nav": total / max(first_total, 1e-9),
                }
            )
        if equity_curve:
            initial_capital = float(equity_curve[0]["value"])
            ending_total = float(equity_curve[-1]["value"])
    net_pnl = ending_total - initial_capital
    account_return_pct = net_pnl / max(initial_capital, 1e-9) * 100.0
    margin_budget = _as_float(config.get("margin_budget"), 50000.0)
    strategy_return_pct = net_pnl / max(margin_budget, 1e-9) * 100.0
    if isinstance(result.raw, dict):
        result.raw["net_pnl"] = round(net_pnl, 6)
        result.raw["total_return_pct"] = round(strategy_return_pct, 6)
        result.raw["account_total_return_pct"] = round(account_return_pct, 6)
        result.raw["starting_balance"] = initial_capital
        result.raw["metrics_basis"] = "strategy"
        result.raw["margin_budget"] = margin_budget
        raw_summary = dict(result.raw.get("summary", {}) or {})
        raw_summary["net_pnl"] = round(net_pnl, 6)
        raw_summary["total_return_pct"] = round(account_return_pct, 6)
        raw_summary["starting_balance"] = initial_capital
        result.raw["summary"] = raw_summary
    _write_backtest_outputs(result, equity_curve, initial_capital, net_pnl, strategy_return_pct, account_return_pct, margin_budget)
    metrics = _clean_mapping(
        {
            "total_return_pct": strategy_return_pct,
            "net_pnl": net_pnl,
            "starting_balance": initial_capital,
            "sharpe_ratio": result.sharpe_ratio,
            "max_drawdown_pct": result.max_drawdown_pct,
            "win_rate": result.win_rate,
            "total_trades": result.total_trades,
            "profit_factor": result.profit_factor,
            "rows": len(replay_frame),
            "cloud_fetch_start": execution.get("start"),
            "cloud_trade_start": (spec.get("strategy", {}) or {}).get("config", {}).get("trade_start"),
            "cloud_fetch_end": execution.get("end"),
            "account_total_return_pct": account_return_pct,
            "metrics_basis": "strategy",
            "margin_budget": margin_budget,
        }
    )
    runtime.emit_signal(
        action="long" if net_pnl > 0 else "watch",
        symbol=symbol,
        confidence=_clean(result.win_rate) or 0.0,
        metrics=metrics,
        meta={"chart_path": chart_path, "mode": "historical_backtest", "timeframe": interval},
    )


def _write_backtest_outputs(
    result: Any,
    equity_curve: list[dict[str, Any]],
    initial_capital: float,
    net_pnl: float,
    strategy_return_pct: float,
    account_return_pct: float,
    margin_budget: float,
) -> None:
    out_dir = Path("/workspace/output")
    out_dir.mkdir(parents=True, exist_ok=True)
    raw = dict(result.raw or {}) if isinstance(result.raw, dict) else {}
    summary = dict(raw.get("summary", {}) or {})
    summary["starting_balance"] = initial_capital
    summary["net_pnl"] = net_pnl
    summary["total_return_pct"] = account_return_pct
    raw["summary"] = summary
    raw["net_pnl"] = round(net_pnl, 6)
    raw["total_return_pct"] = round(strategy_return_pct, 6)
    raw["account_total_return_pct"] = round(account_return_pct, 6)
    raw["starting_balance"] = initial_capital
    raw["metrics_basis"] = "strategy"
    raw["margin_budget"] = margin_budget
    reports = dict(raw.get("reports", {}) or {})
    reports.pop("equity_curve", None)
    reports.pop("account", None)
    reports.pop("orders", None)
    reports.pop("fills", None)
    raw["reports"] = reports
    (out_dir / "backtest_report.json").write_text(json.dumps(raw, default=str), encoding="utf-8")
    if equity_curve:
        lines = ["timestamp,value,nav"]
        for point in equity_curve:
            lines.append(f"{point.get('timestamp','')},{point.get('value','')},{point.get('nav','')}")
        (out_dir / "equity_curve.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _run_signal(config: dict[str, Any], symbol: str) -> None:
    history_days = max(20, min(_as_int(config.get("history_days"), 45), 90))
    frame = load_intraday_bars(symbol=symbol, interval="15m", days=history_days)
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
