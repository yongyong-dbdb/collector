from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any


Number = Decimal | int | float | None


@dataclass(frozen=True)
class TossProduct:
    input_value: str
    code: str
    symbol: str
    name: str
    market_type: str
    interval_type: str
    chart_range: str
    recent_candle_count: int


@dataclass(frozen=True)
class TossCandle:
    candle_time: str
    base_price: Number
    open_price: Number
    high_price: Number
    low_price: Number
    close_price: Number
    volume: Number
    amount: Number
    exchange_rate: Number
    raw_data: dict[str, Any]


@dataclass(frozen=True)
class YahooTarget:
    market: str
    category: str
    symbol: str
    name: str


@dataclass(frozen=True)
class MarketCandle:
    source: str
    market: str
    category: str
    symbol: str
    name: str
    interval_type: str
    candle_time: datetime
    open_price: Number
    high_price: Number
    low_price: Number
    close_price: Number
    volume: Number
    raw_data: dict[str, Any]


@dataclass(frozen=True)
class CollectionResult:
    source: str
    target: str
    status: str
    fetched_rows: int
    saved_rows: int
    error_message: str | None = None
