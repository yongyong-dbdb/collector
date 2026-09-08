from __future__ import annotations

import time
from datetime import datetime
from typing import Any

from config import AppSettings
from models import CollectionResult, TossCandle, TossProduct
from repository import CandleRepository
from toss_auth import TossOpenApiClient


class TossCollector:
    CANDLES_PATH = "/api/v1/candles"
    BACKFILL_PAGE_SIZE = 200

    def __init__(self, settings: AppSettings, api_client: TossOpenApiClient,
                 repository: CandleRepository) -> None:
        self.settings = settings
        self.api_client = api_client
        self.repository = repository
        self._last_request_started_at = 0.0

    def _wait_for_rate_limit(self) -> None:
        minimum = self.settings.toss_candle_min_interval_seconds
        elapsed = time.monotonic() - self._last_request_started_at
        if elapsed < minimum:
            time.sleep(minimum - elapsed)
        self._last_request_started_at = time.monotonic()

    def _fetch(
        self,
        product: TossProduct,
        *,
        before: str | None = None,
        count: int | None = None,
    ) -> dict[str, Any]:
        self._wait_for_rate_limit()
        params: dict[str, Any] = {
            "symbol": product.code,
            "interval": product.interval_type,
            "count": count if count is not None else product.recent_candle_count,
            "adjusted": "true",
        }
        if before is not None:
            params["before"] = before
        return self.api_client.get_json(self.CANDLES_PATH, params=params)

    @staticmethod
    def _parse_timestamp(value: str) -> datetime:
        normalized = value.strip()
        if normalized.endswith("Z"):
            normalized = f"{normalized[:-1]}+00:00"
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError(f"Candle timestamp must include timezone offset: {value}")
        return parsed

    @classmethod
    def _parse_page(cls, payload: dict[str, Any]) -> tuple[list[TossCandle], str | None]:
        result = payload.get("result") or {}
        if not isinstance(result, dict):
            return [], None

        raw_candles = result.get("candles") or []
        if not isinstance(raw_candles, list):
            raise ValueError("Candle API result.candles is not a list")

        next_before = result.get("nextBefore")
        if next_before is not None and not isinstance(next_before, str):
            raise ValueError("Candle API result.nextBefore is not a string or null")

        candles: list[TossCandle] = []
        for row in raw_candles:
            if not isinstance(row, dict) or row.get("timestamp") is None:
                continue
            candle_time = str(row["timestamp"])
            cls._parse_timestamp(candle_time)
            candles.append(
                TossCandle(
                    candle_time=candle_time,
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
        return candles, next_before

    @classmethod
    def _merge_candles(
        cls,
        destination: dict[datetime, TossCandle],
        candles: list[TossCandle],
        *,
        newer_than: datetime | None = None,
    ) -> int:
        added = 0
        for candle in candles:
            candle_time = cls._parse_timestamp(candle.candle_time)
            if newer_than is not None and candle_time <= newer_than:
                continue
            if candle_time not in destination:
                added += 1
            destination[candle_time] = candle
        return added

    def _collect_product(
        self,
        product: TossProduct,
    ) -> tuple[list[TossCandle], int, int, int]:
        anchor = self.repository.get_latest_toss_candle_time(
            product.market_type,
            product.code,
            product.chart_range,
        )

        first_page, next_before = self._parse_page(self._fetch(product))
        fetched_rows = len(first_page)
        if not first_page:
            return [], fetched_rows, 0, 0

        collected: dict[datetime, TossCandle] = {}
        self._merge_candles(collected, first_page)

        if anchor is None:
            candles = [collected[key] for key in sorted(collected)]
            return candles, fetched_rows, 0, 0

        page_times = [self._parse_timestamp(candle.candle_time) for candle in first_page]
        oldest_seen = min(page_times)
        if oldest_seen <= anchor:
            candles = [collected[key] for key in sorted(collected)]
            return candles, fetched_rows, 0, 0

        cursor = next_before
        seen_cursors: set[str] = set()
        backfill_pages = 0
        recovered_rows = 0

        while oldest_seen > anchor:
            if not cursor:
                raise RuntimeError(
                    "Candle backfill ended before reaching DB anchor "
                    f"anchor={anchor.isoformat()} oldest={oldest_seen.isoformat()}"
                )
            if cursor in seen_cursors:
                raise RuntimeError(f"Candle pagination cursor repeated: {cursor}")
            seen_cursors.add(cursor)

            page, new_cursor = self._parse_page(
                self._fetch(
                    product,
                    before=cursor,
                    count=self.BACKFILL_PAGE_SIZE,
                )
            )
            fetched_rows += len(page)
            backfill_pages += 1
            if not page:
                raise RuntimeError(
                    "Candle backfill returned an empty page before reaching DB anchor "
                    f"anchor={anchor.isoformat()} before={cursor}"
                )

            page_times = [self._parse_timestamp(candle.candle_time) for candle in page]
            page_oldest = min(page_times)
            if page_oldest >= oldest_seen:
                raise RuntimeError(
                    "Candle pagination did not move backward "
                    f"before={cursor} oldest={page_oldest.isoformat()}"
                )

            recovered_rows += self._merge_candles(
                collected,
                page,
                newer_than=anchor,
            )
            oldest_seen = page_oldest
            cursor = new_cursor

        candles = [collected[key] for key in sorted(collected)]
        return candles, fetched_rows, backfill_pages, recovered_rows

    def collect_once(self) -> list[CollectionResult]:
        results: list[CollectionResult] = []
        products = self.repository.get_toss_products()
        for product in products:
            try:
                candles, fetched_rows, backfill_pages, recovered_rows = self._collect_product(product)
                saved = self.repository.save_toss_candles(
                    product.market_type, product.chart_range, product, candles
                )
                status = "SUCCESS" if candles else "NO_DATA"
                result = CollectionResult("TOSS", product.symbol, status, fetched_rows, saved)
                print(
                    f"[TOSS:{product.symbol}] status={status} fetched={fetched_rows} "
                    f"upserted={saved} backfill_pages={backfill_pages} "
                    f"recovered={recovered_rows}",
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
