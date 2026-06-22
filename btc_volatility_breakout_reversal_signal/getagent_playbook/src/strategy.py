from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

import numpy as np

from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.model.objects import Quantity
from nautilus_trader.trading.strategy import Strategy

try:
    from .decision_logic import compute_signal_state
except ImportError:
    from decision_logic import compute_signal_state


positions: list[object] = []


class VolatilityBreakoutReversalStrategyConfig(StrategyConfig):
    instrument_id: Optional[InstrumentId] = None
    bar_type: Optional[BarType] = None
    instrument_ids: tuple[InstrumentId, ...] = ()
    bar_types: tuple[BarType, ...] = ()
    order_id_tag: str = "001"
    margin_budget: str = "50000"
    leverage: int = 3
    min_trade_size: str = "0.001"
    decision_interval_minutes: int = 240
    target_step_weight: float = 0.05
    max_effective_exposure: float = 3.20
    min_rebalance_qty_pct: float = 0.25
    squeeze_window: int = 96
    stretch_window: int = 32
    trend_window: int = 384
    vol_window: int = 96
    overheat_z: float = 1.65
    overheat_ret_min: float = 0.035
    near_high_mult: float = 0.995
    vol_ceiling: float = 0.95
    turn_fast_ret_max: float = -0.004
    fade_from_high_mult: float = 0.985
    vol_expansion_min: float = 1.08
    trend_block_ret: float = 0.22
    washout_z: float = 1.85
    washout_ret_max: float = 0.045
    near_low_mult: float = 1.005
    long_vol_ceiling: float = 0.90
    turn_fast_ret_min: float = 0.004
    bounce_from_low_mult: float = 1.015
    short_target_vol: float = 0.42
    long_target_vol: float = 0.18
    max_signal_weight: float = 1.00
    max_short_weight: float = 1.00
    max_long_weight: float = 0.12
    weight_scale: float = 2.00
    vol_floor_min: float = 0.20
    rebalance_cooldown_bars: int = 2
    min_hold_bars: int = 4
    reversal_min_weight: float = 0.10
    trade_start: str = ""


class VolatilityBreakoutReversalStrategy(Strategy):
    def __init__(self, config: VolatilityBreakoutReversalStrategyConfig) -> None:
        super().__init__(config)
        self.cfg = config
        self._closes: list[float] = []
        self._instrument: Optional[Instrument] = None
        self._target_position_qty = 0.0
        self._bars_since_trade = 10_000
        self._holding_bars = 0
        self._trade_start_ns = self._parse_timestamp_ns(config.trade_start)

    def on_start(self) -> None:
        bar_type = self.cfg.bar_type or (self.cfg.bar_types[0] if self.cfg.bar_types else None)
        instrument_id = self.cfg.instrument_id or (self.cfg.instrument_ids[0] if self.cfg.instrument_ids else None)
        if bar_type is None or instrument_id is None:
            raise RuntimeError("bar_type and instrument_id must be set")
        self._instrument = self.cache.instrument(instrument_id)
        self.subscribe_bars(bar_type)

    def on_bar(self, bar: Bar) -> None:
        close = float(bar.close)
        self._closes.append(close)
        event_time = datetime.fromtimestamp(int(bar.ts_event) / 1_000_000_000, tz=timezone.utc)
        interval = max(int(self.cfg.decision_interval_minutes), 15)
        if event_time.minute % interval != 0:
            return

        min_ready = max(self.cfg.squeeze_window, self.cfg.stretch_window, self.cfg.trend_window, self.cfg.vol_window) + 3
        if len(self._closes) < min_ready:
            return
        instrument = self._instrument
        if instrument is None:
            return
        if self._trade_start_ns and int(bar.ts_event) < self._trade_start_ns:
            return

        self._bars_since_trade += 1
        config = self._config_dict()
        target_weight = compute_signal_state(np.asarray(self._closes, dtype=float), config, bars_per_day=96.0).target_weight
        target_qty = self._clip_target_qty(self._target_qty(target_weight, close), close)
        current_qty = self._target_position_qty
        delta_qty = target_qty - current_qty
        min_qty = float(self.cfg.min_trade_size)

        if abs(current_qty) >= min_qty:
            self._holding_bars += 1
        else:
            self._holding_bars = 0
        if abs(delta_qty) < min_qty:
            return
        if current_qty and abs(delta_qty) < abs(current_qty) * float(self.cfg.min_rebalance_qty_pct):
            return
        if self._bars_since_trade < int(self.cfg.rebalance_cooldown_bars):
            if np.sign(target_qty) == np.sign(current_qty) or abs(target_qty) < abs(current_qty):
                return
        if abs(current_qty) >= min_qty and self._holding_bars < int(self.cfg.min_hold_bars):
            current_sign = float(np.sign(current_qty))
            target_sign = float(np.sign(target_qty))
            if target_sign == 0.0 or target_sign == current_sign:
                return
            if abs(target_weight) < float(self.cfg.reversal_min_weight):
                return

        rounded_delta = self._round_qty(abs(delta_qty), min_qty)
        if rounded_delta < min_qty:
            return
        qty = Quantity(Decimal(str(rounded_delta)), instrument.size_precision)
        side = OrderSide.SELL if delta_qty < 0.0 else OrderSide.BUY
        order = self.order_factory.market(
            instrument_id=instrument.id,
            order_side=side,
            quantity=qty,
            time_in_force=TimeInForce.GTC,
        )
        self.submit_order(order)
        self._target_position_qty += -rounded_delta if side == OrderSide.SELL else rounded_delta
        self._bars_since_trade = 0

    def _target_qty(self, target_weight: float, price: float) -> float:
        if abs(target_weight) < float(self.cfg.target_step_weight):
            return 0.0
        budget = max(float(self.cfg.margin_budget), 0.0)
        leverage = max(float(self.cfg.leverage), 1.0)
        min_qty = float(self.cfg.min_trade_size)
        raw_qty = abs(target_weight) * budget * leverage / max(price, 1e-9)
        rounded = self._round_qty(raw_qty, min_qty)
        if rounded < min_qty:
            return 0.0
        return rounded if target_weight > 0.0 else -rounded

    def _clip_target_qty(self, target_qty: float, price: float) -> float:
        max_weight = max(float(self.cfg.max_short_weight), float(self.cfg.max_long_weight), 0.0)
        budget = max(float(self.cfg.margin_budget), 0.0)
        leverage = max(float(self.cfg.leverage), 1.0)
        max_effective_exposure = max(float(self.cfg.max_effective_exposure), 0.0)
        min_qty = float(self.cfg.min_trade_size)
        max_notional_weight = min(max_weight * leverage, max_effective_exposure)
        max_qty = self._round_qty(max_notional_weight * budget / max(price, 1e-9), min_qty)
        if max_qty <= 0.0:
            return 0.0
        return float(np.clip(target_qty, -max_qty, max_qty))

    @staticmethod
    def _round_qty(value: float, step: float) -> float:
        if step <= 0.0:
            return value
        return float(np.floor((value + 1e-12) / step) * step)

    def _config_dict(self) -> dict[str, float | str | int]:
        keys = (
            "target_step_weight",
            "squeeze_window",
            "stretch_window",
            "trend_window",
            "vol_window",
            "overheat_z",
            "overheat_ret_min",
            "near_high_mult",
            "vol_ceiling",
            "turn_fast_ret_max",
            "fade_from_high_mult",
            "vol_expansion_min",
            "trend_block_ret",
            "washout_z",
            "washout_ret_max",
            "near_low_mult",
            "long_vol_ceiling",
            "turn_fast_ret_min",
            "bounce_from_low_mult",
            "short_target_vol",            "long_target_vol",            "max_signal_weight",
            "max_short_weight",
            "max_long_weight",
            "weight_scale",
            "vol_floor_min",
        )
        return {key: getattr(self.cfg, key) for key in keys}

    @staticmethod
    def _parse_timestamp_ns(value: str) -> int:
        if not value:
            return 0
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return int(parsed.timestamp() * 1_000_000_000)

    def on_stop(self) -> None:
        if self._instrument is not None:
            self.cancel_all_orders(self._instrument.id)
            self.close_all_positions(self._instrument.id)
