from decimal import Decimal
from datetime import datetime, timezone
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
except ImportError:  # Nautilus may import this module from the src path.
    from decision_logic import compute_signal_state


class AdaptiveShortTrendStrategyConfig(StrategyConfig):
    instrument_id: Optional[InstrumentId] = None
    bar_type: Optional[BarType] = None
    instrument_ids: tuple[InstrumentId, ...] = ()
    bar_types: tuple[BarType, ...] = ()
    order_id_tag: str = "001"
    margin_budget: str = "1000"
    min_trade_size: str = "0.001"
    target_step_weight: float = 0.02
    fast_window: int = 12
    mid_window: int = 42
    slow_window: int = 84
    long_window: int = 270
    vol_window: int = 60
    bear_on: float = 0.35635
    bear_off: float = 0.30
    ret_slow_max: float = -0.04
    ret_mid_max: float = 0.01
    short_sma_mult: float = 1.03
    mid_sma_mult: float = 1.0
    rebound_ret_max: float = 0.04942
    rebound_sma_mult: float = 1.005
    short_target_vol: float = 1.16824
    short_floor_cap: float = 1.45442
    max_short_weight: float = 1.71114
    max_signal_weight: float = 2.00
    short_base: float = 0.65
    short_conf: float = 0.55
    weight_scale: float = 1.43858
    vol_ceiling: float = 0.34090
    vol_floor_min: float = 0.20
    high_vol_floor: float = 0.40996
    high_vol_ceiling: float = 0.54369
    high_vol_bear_on: float = 0.42
    high_vol_sma_mult: float = 1.02
    high_vol_target_vol: float = 0.50
    high_vol_short_cap: float = 1.0
    high_vol_short_base: float = 0.65
    high_vol_short_conf: float = 0.0
    long_on: float = 0.52496
    long_ret_mid_min: float = 0.00710
    long_sma_mult: float = 1.0
    long_vol_ceiling: float = 0.60752
    long_floor_cap: float = 0.72963
    max_long_weight: float = 0.82879
    dynamic_long_cap: float = 0.15126
    dynamic_short_cap: float = 0.11467
    dynamic_long_trend_on: float = 0.59954
    dynamic_long_sma_mult: float = 0.99679
    dynamic_long_vol_ceiling: float = 0.68010
    long_accel_ret_min: float = 0.02445
    long_pullback_z: float = -0.37573
    long_pullback_ret_mid_min: float = -0.02667
    long_pullback_slow_mult: float = 0.97249
    dynamic_long_target_vol: float = 0.38522
    dynamic_long_base: float = 0.21780
    dynamic_long_conf: float = 0.30226
    dynamic_short_bear_on: float = 0.62661
    short_accel_ret_max: float = -0.00817
    short_rebound_z: float = 1.07511
    dynamic_short_sma_mult: float = 0.99830
    dynamic_short_target_vol: float = 0.51004
    dynamic_short_base: float = 0.17381
    dynamic_short_conf: float = 0.26965
    channel_slope_deadband: float = 0.00313
    range_bias_strength: float = 0.54640
    channel_slope_window: int = 45
    range_mr_cap: float = 0.04855
    range_z_entry: float = 0.65902
    range_trend_max: float = 0.72880
    range_bear_max: float = 0.56401
    range_vol_ceiling: float = 0.59266
    trade_start: str = ""


class AdaptiveShortTrendStrategy(Strategy):
    def __init__(self, config: AdaptiveShortTrendStrategyConfig) -> None:
        super().__init__(config)
        self.cfg = config
        self._closes: list[float] = []
        self._instrument: Optional[Instrument] = None
        self._trade_start_ns = self._parse_timestamp_ns(config.trade_start)

    def on_start(self) -> None:
        bar_type = self.cfg.bar_type or (
            self.cfg.bar_types[0] if self.cfg.bar_types else None
        )
        instrument_id = self.cfg.instrument_id or (
            self.cfg.instrument_ids[0] if self.cfg.instrument_ids else None
        )
        if bar_type is None or instrument_id is None:
            raise RuntimeError("bar_type and instrument_id must be set")
        self._instrument = self.cache.instrument(instrument_id)
        self.subscribe_bars(bar_type)

    def on_bar(self, bar: Bar) -> None:
        close = float(bar.close)
        self._closes.append(close)
        if len(self._closes) < self.cfg.long_window + 2:
            return

        values = np.asarray(self._closes, dtype=float)
        latest = float(values[-1])
        instrument = self._instrument
        if instrument is None:
            return
        if self._trade_start_ns and int(bar.ts_event) < self._trade_start_ns:
            return
        target_weight = compute_signal_state(values, self._config_dict(), bars_per_day=6.0).target_weight
        target_qty = self._target_qty(target_weight, latest)
        current_qty = self._current_signed_qty(instrument.id)
        delta_qty = target_qty - current_qty
        min_qty = float(self.cfg.min_trade_size)
        if abs(delta_qty) < min_qty:
            return

        rounded_delta = self._round_qty(abs(delta_qty), min_qty)
        if rounded_delta < min_qty:
            return
        qty = Quantity(Decimal(str(rounded_delta)), instrument.size_precision)
        side = OrderSide.SELL if delta_qty < 0.0 else OrderSide.BUY
        self._submit(instrument.id, side, qty)

    def _submit(
        self,
        instrument_id: InstrumentId,
        side: OrderSide,
        quantity: Quantity,
    ) -> None:
        order = self.order_factory.market(
            instrument_id=instrument_id,
            order_side=side,
            quantity=quantity,
            time_in_force=TimeInForce.GTC,
        )
        self.submit_order(order)

    def _target_qty(self, target_weight: float, price: float) -> float:
        if abs(target_weight) < float(self.cfg.target_step_weight):
            return 0.0
        budget = max(float(self.cfg.margin_budget), 0.0)
        min_qty = float(self.cfg.min_trade_size)
        raw_qty = abs(target_weight) * budget / max(price, 1e-9)
        rounded = self._round_qty(raw_qty, min_qty)
        if rounded < min_qty:
            return 0.0
        return rounded if target_weight > 0.0 else -rounded

    @staticmethod
    def _round_qty(value: float, step: float) -> float:
        if step <= 0.0:
            return value
        return float(np.floor((value + 1e-12) / step) * step)

    def _current_signed_qty(self, instrument_id: InstrumentId) -> float:
        signed = 0.0
        for position in self.cache.positions_open(instrument_id=instrument_id):
            quantity = float(position.quantity)
            side = str(getattr(position, "side", "")).upper()
            if "SHORT" in side:
                signed -= quantity
            else:
                signed += quantity
        return signed

    def _config_dict(self) -> dict[str, float | str]:
        keys = (
            "margin_budget",
            "min_trade_size",
            "target_step_weight",
            "fast_window",
            "mid_window",
            "slow_window",
            "long_window",
            "vol_window",
            "bear_on",
            "bear_off",
            "ret_slow_max",
            "ret_mid_max",
            "short_sma_mult",
            "mid_sma_mult",
            "rebound_ret_max",
            "rebound_sma_mult",
            "short_target_vol",
            "short_floor_cap",
            "max_short_weight",
            "max_signal_weight",
            "short_base",
            "short_conf",
            "weight_scale",
            "vol_ceiling",
            "vol_floor_min",
            "high_vol_floor",
            "high_vol_ceiling",
            "high_vol_bear_on",
            "high_vol_sma_mult",
            "high_vol_target_vol",
            "high_vol_short_cap",
            "high_vol_short_base",
            "high_vol_short_conf",
            "long_on",
            "long_ret_mid_min",
            "long_sma_mult",
            "long_vol_ceiling",
            "long_floor_cap",
            "max_long_weight",
            "dynamic_long_cap",
            "dynamic_short_cap",
            "dynamic_long_trend_on",
            "dynamic_long_sma_mult",
            "dynamic_long_vol_ceiling",
            "long_accel_ret_min",
            "long_pullback_z",
            "long_pullback_ret_mid_min",
            "long_pullback_slow_mult",
            "dynamic_long_target_vol",
            "dynamic_long_base",
            "dynamic_long_conf",
            "dynamic_short_bear_on",
            "short_accel_ret_max",
            "short_rebound_z",
            "dynamic_short_sma_mult",
            "dynamic_short_target_vol",
            "dynamic_short_base",
            "dynamic_short_conf",
            "channel_slope_deadband",
            "range_bias_strength",
            "channel_slope_window",
            "range_mr_cap",
            "range_z_entry",
            "range_trend_max",
            "range_bear_max",
            "range_vol_ceiling",
        )
        return {key: getattr(self.cfg, key) for key in keys}

    @staticmethod
    def _parse_timestamp_ns(value: str) -> int:
        if not value:
            return 0
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return int(parsed.timestamp() * 1_000_000_000)

    def on_stop(self) -> None:
        if self._instrument is not None:
            self.cancel_all_orders(self._instrument.id)
            self.close_all_positions(self._instrument.id)
