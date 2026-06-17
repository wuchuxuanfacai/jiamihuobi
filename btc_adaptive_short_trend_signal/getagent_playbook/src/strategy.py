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


class AdaptiveShortTrendStrategyConfig(StrategyConfig):
    instrument_id: Optional[InstrumentId] = None
    bar_type: Optional[BarType] = None
    instrument_ids: tuple[InstrumentId, ...] = ()
    bar_types: tuple[BarType, ...] = ()
    order_id_tag: str = "001"
    trade_size: str = "0.001"
    fast_window: int = 18
    mid_window: int = 60
    slow_window: int = 180
    long_window: int = 360
    vol_window: int = 60
    bear_on: float = 0.56
    ret_slow_max: float = -0.08
    ret_mid_max: float = -0.04
    short_sma_mult: float = 0.98
    fast_sma_mult: float = 1.00
    rebound_ret_max: float = 0.08
    vol_ceiling: float = 0.45


class AdaptiveShortTrendStrategy(Strategy):
    def __init__(self, config: AdaptiveShortTrendStrategyConfig) -> None:
        super().__init__(config)
        self.cfg = config
        self._closes: list[float] = []
        self._position: str = "NONE"
        self._instrument: Optional[Instrument] = None

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

        short_ok = (
            bear_strength >= self.cfg.bear_on
            and ret_slow < self.cfg.ret_slow_max
            and ret_mid < self.cfg.ret_mid_max
            and latest < sma_long * self.cfg.short_sma_mult
            and latest < sma_fast * self.cfg.fast_sma_mult
            and ret_fast < self.cfg.rebound_ret_max
            and realized_vol <= self.cfg.vol_ceiling
        )

        instrument = self._instrument
        if instrument is None:
            return
        qty = Quantity(Decimal(self.cfg.trade_size), instrument.size_precision)

        has_open_position = self._has_open_position(instrument.id)
        if has_open_position and self._position == "NONE":
            self._position = "SHORT"
        elif not has_open_position and self._position == "SHORT":
            self._position = "NONE"

        if not has_open_position and short_ok:
            self._submit(instrument.id, OrderSide.SELL, qty)
            self._position = "SHORT"
        elif has_open_position and not short_ok:
            self.close_all_positions(instrument.id)
            self._position = "NONE"

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

    def _has_open_position(self, instrument_id: InstrumentId) -> bool:
        return bool(list(self.cache.positions_open(instrument_id=instrument_id)))

    def on_stop(self) -> None:
        if self._instrument is not None:
            self.cancel_all_orders(self._instrument.id)
            self.close_all_positions(self._instrument.id)
