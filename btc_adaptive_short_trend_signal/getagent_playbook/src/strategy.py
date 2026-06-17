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


class AdaptiveShortTrendStrategyConfig(StrategyConfig):
    instrument_id: Optional[InstrumentId] = None
    bar_type: Optional[BarType] = None
    instrument_ids: tuple[InstrumentId, ...] = ()
    bar_types: tuple[BarType, ...] = ()
    order_id_tag: str = "001"
    margin_budget: str = "1000"
    min_trade_size: str = "0.001"
    target_step_weight: float = 0.02
    fast_window: int = 30
    mid_window: int = 60
    slow_window: int = 126
    long_window: int = 126
    vol_window: int = 60
    bear_on: float = 0.48
    bear_off: float = 0.30
    ret_slow_max: float = -0.02
    ret_mid_max: float = -0.02
    short_sma_mult: float = 1.02
    mid_sma_mult: float = 1.0
    rebound_ret_max: float = 0.055
    rebound_sma_mult: float = 1.015
    short_target_vol: float = 0.55
    short_floor_cap: float = 1.0
    max_short_weight: float = 1.0
    short_base: float = 0.35
    short_conf: float = 0.65
    weight_scale: float = 1.0
    vol_ceiling: float = 0.35
    vol_floor_min: float = 0.20
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
        fast = values[-self.cfg.fast_window :]
        mid = values[-self.cfg.mid_window :]
        slow = values[-self.cfg.slow_window :]
        long = values[-self.cfg.long_window :]

        sma_fast = float(np.mean(fast))
        sma_mid = float(np.mean(mid))
        sma_slow = float(np.mean(slow))
        sma_long = float(np.mean(long))
        ret_fast = latest / float(values[-self.cfg.fast_window]) - 1.0
        ret_mid = latest / float(values[-self.cfg.mid_window]) - 1.0
        ret_slow = latest / float(values[-self.cfg.slow_window]) - 1.0
        vol_returns = np.diff(values[-(self.cfg.vol_window + 1) :]) / values[-(self.cfg.vol_window + 1) : -1]
        realized_vol = float(np.std(vol_returns) * np.sqrt(365.0 * 6.0)) if len(vol_returns) else 9.0

        bear_strength = (
            float(latest < sma_fast)
            + float(latest < sma_mid)
            + float(latest < sma_slow)
            + float(sma_fast < sma_mid)
            + float(sma_mid < sma_slow)
            + float(ret_mid < 0.0)
            + float(ret_slow < 0.0)
        ) / 7.0

        weak_momentum = (
            ret_mid < self.cfg.ret_mid_max
            or ret_slow < self.cfg.ret_slow_max
            or latest < sma_mid * self.cfg.mid_sma_mult
        )
        rebound_blocked = (
            ret_fast > self.cfg.rebound_ret_max
            and latest > sma_fast * self.cfg.rebound_sma_mult
        )
        short_ok = (
            bear_strength >= self.cfg.bear_on
            and weak_momentum
            and latest < sma_long * self.cfg.short_sma_mult
            and not rebound_blocked
            and realized_vol <= self.cfg.vol_ceiling
        )

        instrument = self._instrument
        if instrument is None:
            return
        if self._trade_start_ns and int(bar.ts_event) < self._trade_start_ns:
            return
        target_weight = self._target_weight(short_ok, bear_strength, realized_vol)
        target_qty = self._target_short_qty(target_weight, latest)
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

    def _target_weight(self, short_ok: bool, bear_strength: float, realized_vol: float) -> float:
        if not short_ok:
            return 0.0
        safe_vol = max(float(realized_vol), float(self.cfg.vol_floor_min))
        bear_conf = min(
            1.0,
            max(0.0, (bear_strength - self.cfg.bear_on) / max(1.0 - self.cfg.bear_on, 1e-9)),
        )
        raw = -min(
            float(self.cfg.short_floor_cap),
            (float(self.cfg.short_target_vol) / safe_vol)
            * (float(self.cfg.short_base) + float(self.cfg.short_conf) * bear_conf),
        )
        scaled = raw * float(self.cfg.weight_scale)
        return max(-float(self.cfg.max_short_weight), min(0.0, scaled))

    def _target_short_qty(self, target_weight: float, price: float) -> float:
        if abs(target_weight) < float(self.cfg.target_step_weight):
            return 0.0
        budget = max(float(self.cfg.margin_budget), 0.0)
        min_qty = float(self.cfg.min_trade_size)
        raw_qty = abs(target_weight) * budget / max(price, 1e-9)
        rounded = self._round_qty(raw_qty, min_qty)
        return -rounded if rounded >= min_qty else 0.0

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
