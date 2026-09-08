from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


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
    base_price: Any
    open_price: Any
    high_price: Any
    low_price: Any
    close_price: Any
    volume: Any
    amount: Any
    exchange_rate: Any
    raw_data: dict[str, Any]


@dataclass(frozen=True)
class CollectionResult:
    source: str
    target: str
    status: str
    fetched_rows: int
    saved_rows: int
    error_message: str | None = None


config_stub = types.ModuleType("config")
config_stub.AppSettings = object
sys.modules["config"] = config_stub

models_stub = types.ModuleType("models")
models_stub.CollectionResult = CollectionResult
models_stub.TossCandle = TossCandle
models_stub.TossProduct = TossProduct
sys.modules["models"] = models_stub

repository_stub = types.ModuleType("repository")
repository_stub.CandleRepository = object
sys.modules["repository"] = repository_stub

toss_auth_stub = types.ModuleType("toss_auth")
toss_auth_stub.TossOpenApiClient = object
sys.modules["toss_auth"] = toss_auth_stub

spec = importlib.util.spec_from_file_location(
    "toss_module",
    Path(__file__).parents[1] / "collectors" / "toss.py",
)
assert spec is not None and spec.loader is not None
toss_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(toss_module)
TossCollector = toss_module.TossCollector


class Settings:
    toss_candle_min_interval_seconds = 0.0


class FakeApi:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def get_json(self, path: str, *, params: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(dict(params))
        if not self.responses:
            raise AssertionError("unexpected API call")
        return self.responses.pop(0)


class FakeRepository:
    def __init__(self, anchor: datetime | None, product: TossProduct) -> None:
        self.anchor = anchor
        self.product = product
        self.saved: list[TossCandle] = []
        self.history: list[CollectionResult] = []

    def get_toss_products(self) -> list[TossProduct]:
        return [self.product]

    def get_latest_toss_candle_time(self, market_type: str, product_code: str,
                                    chart_range: str) -> datetime | None:
        return self.anchor

    def save_toss_candles(self, market_type: str, chart_range: str,
                          product: TossProduct, candles: list[TossCandle]) -> int:
        self.saved.extend(candles)
        return len(candles)

    def save_collection_result(self, result: CollectionResult) -> None:
        self.history.append(result)


def page(times: list[str], next_before: str | None) -> dict[str, Any]:
    return {
        "result": {
            "candles": [
                {
                    "timestamp": value,
                    "openPrice": "1",
                    "highPrice": "2",
                    "lowPrice": "1",
                    "closePrice": "2",
                    "volume": "10",
                }
                for value in times
            ],
            "nextBefore": next_before,
        }
    }


PRODUCT = TossProduct(
    input_value="005930",
    code="005930",
    symbol="005930",
    name="삼성전자",
    market_type="kr-s",
    interval_type="1m",
    chart_range="min:1",
    recent_candle_count=2,
)


class TossBackfillTests(unittest.TestCase):
    def test_initial_symbol_keeps_recent_only_behavior(self) -> None:
        api = FakeApi([page([
            "2026-09-08T09:05:00+09:00",
            "2026-09-08T09:04:00+09:00",
        ], "2026-09-08T09:04:00+09:00")])
        repo = FakeRepository(None, PRODUCT)
        collector = TossCollector(Settings(), api, repo)

        candles, fetched, pages, recovered = collector._collect_product(PRODUCT)

        self.assertEqual(len(candles), 2)
        self.assertEqual(fetched, 2)
        self.assertEqual(pages, 0)
        self.assertEqual(recovered, 0)
        self.assertEqual(len(api.calls), 1)
        self.assertNotIn("before", api.calls[0])
        self.assertEqual(api.calls[0]["count"], 2)

    def test_backfill_reaches_anchor_and_deduplicates_inclusive_pages(self) -> None:
        anchor = datetime.fromisoformat("2026-09-08T09:00:00+09:00")
        api = FakeApi([
            page([
                "2026-09-08T09:05:00+09:00",
                "2026-09-08T09:04:00+09:00",
            ], "2026-09-08T09:04:00+09:00"),
            page([
                "2026-09-08T09:04:00+09:00",
                "2026-09-08T09:03:00+09:00",
                "2026-09-08T09:02:00+09:00",
            ], "2026-09-08T09:02:00+09:00"),
            page([
                "2026-09-08T09:02:00+09:00",
                "2026-09-08T09:01:00+09:00",
                "2026-09-08T09:00:00+09:00",
            ], "2026-09-08T09:00:00+09:00"),
        ])
        repo = FakeRepository(anchor, PRODUCT)
        collector = TossCollector(Settings(), api, repo)

        candles, fetched, pages, recovered = collector._collect_product(PRODUCT)

        self.assertEqual(
            [c.candle_time for c in candles],
            [
                "2026-09-08T09:01:00+09:00",
                "2026-09-08T09:02:00+09:00",
                "2026-09-08T09:03:00+09:00",
                "2026-09-08T09:04:00+09:00",
                "2026-09-08T09:05:00+09:00",
            ],
        )
        self.assertEqual(fetched, 8)
        self.assertEqual(pages, 2)
        self.assertEqual(recovered, 3)
        self.assertEqual(api.calls[1]["count"], 200)
        self.assertEqual(api.calls[1]["before"], "2026-09-08T09:04:00+09:00")
        self.assertEqual(api.calls[2]["before"], "2026-09-08T09:02:00+09:00")

    def test_anchor_in_first_page_does_not_paginate(self) -> None:
        anchor = datetime.fromisoformat("2026-09-08T09:04:00+09:00")
        api = FakeApi([page([
            "2026-09-08T09:05:00+09:00",
            "2026-09-08T09:04:00+09:00",
        ], "2026-09-08T09:04:00+09:00")])
        repo = FakeRepository(anchor, PRODUCT)
        collector = TossCollector(Settings(), api, repo)

        candles, fetched, pages, recovered = collector._collect_product(PRODUCT)

        self.assertEqual(len(candles), 2)
        self.assertEqual(fetched, 2)
        self.assertEqual(pages, 0)
        self.assertEqual(recovered, 0)
        self.assertEqual(len(api.calls), 1)

    def test_incomplete_history_fails_before_saving(self) -> None:
        anchor = datetime.fromisoformat("2026-09-08T09:00:00+09:00")
        api = FakeApi([
            page([
                "2026-09-08T09:05:00+09:00",
                "2026-09-08T09:04:00+09:00",
            ], None),
        ])
        repo = FakeRepository(anchor, PRODUCT)
        collector = TossCollector(Settings(), api, repo)

        results = collector.collect_once()

        self.assertEqual(results[0].status, "FAILED")
        self.assertEqual(repo.saved, [])
        self.assertIn("before reaching DB anchor", results[0].error_message or "")

    def test_non_timezone_timestamp_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "timezone offset"):
            TossCollector._parse_timestamp("2026-09-08T09:05:00")


if __name__ == "__main__":
    unittest.main()
