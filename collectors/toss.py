from __future__ import annotations

from typing import Any

from config import AppSettings
from models import CollectionResult, TossCandle, TossProduct
from repository import CandleRepository
from toss_auth import TossOpenApiClient


class TossCollector:
    CANDLES_PATH = "/api/v1/candles"

    def __init__(self, settings: AppSettings, api_client: TossOpenApiClient,
                 repository: CandleRepository) -> None:
        self.settings = settings
        self.api_client = api_client
        self.repository = repository

    def _fetch(self, product: TossProduct) -> dict[str, Any]:
        return self.api_client.get_json(
            self.CANDLES_PATH,
            params={
                "symbol": product.code,
                "interval": product.interval_type,
                "count": product.recent_candle_count,
                "adjusted": "true",
            },
        )

    @staticmethod
    def _parse(payload: dict[str, Any]) -> list[TossCandle]:
        result = payload.get("result") or {}
        if not isinstance(result, dict):
            return []
        raw_candles = result.get("candles") or []
        candles: list[TossCandle] = []
        for row in raw_candles:
            if not isinstance(row, dict) or row.get("timestamp") is None:
                continue
            candles.append(
                TossCandle(
                    candle_time=str(row["timestamp"]),
                    base_price=None,
                    open_price=row.get("openPrice"),
                    high_price=row.get("highPrice"),
                    low_price=row.get("lowPrice"),
                    close_price=row.get("closePrice"),
                    volume=row.get("volume"),
                    amount=None,
                    exchange_rate=None,
                    raw_data=row,
                )
            )
        return candles

    def collect_once(self) -> list[CollectionResult]:
        results: list[CollectionResult] = []
        products = self.repository.get_toss_products()
        for product in products:
            try:
                candles = self._parse(self._fetch(product))
                saved = self.repository.save_toss_candles(
                    product.market_type, product.chart_range, product, candles
                )
                status = "SUCCESS" if candles else "NO_DATA"
                result = CollectionResult("TOSS", product.symbol, status, len(candles), saved)
                print(
                    f"[TOSS:{product.symbol}] status={status} fetched={len(candles)} upserted={saved}",
                    flush=True,
                )
            except Exception as exc:
                result = CollectionResult(
                    "TOSS", product.symbol, "FAILED", 0, 0,
                    f"{type(exc).__name__}: {exc}",
                )
                print(f"[TOSS:{product.symbol}] ERROR {result.error_message}", flush=True)
            self.repository.save_collection_result(result)
            results.append(result)
        return results
