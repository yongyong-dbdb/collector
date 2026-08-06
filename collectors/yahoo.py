from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

from config import AppSettings
from http_client import HttpClient
from models import CollectionResult, MarketCandle, YahooTarget
from repository import CandleRepository


YAHOO_TARGETS = [
    YahooTarget("US", "INDEX", "^IXIC", "NASDAQ Composite"),
    YahooTarget("US", "INDEX", "^GSPC", "S&P 500"),
    YahooTarget("US", "VOLATILITY", "^VIX", "CBOE Volatility Index"),
    YahooTarget("US", "FUTURES", "NQ=F", "NASDAQ 100 Futures"),
    YahooTarget("US", "INDEX", "^DJI", "Dow Jones Industrial Average"),
    YahooTarget("KR", "INDEX", "^KS11", "KOSPI"),
    YahooTarget("US", "INDEX", "^SOX", "PHLX Semiconductor Index"),
    YahooTarget("US", "FUTURES", "GC=F", "Gold Futures"),
    YahooTarget("FX", "FX", "KRW=X", "USD/KRW"),
]


class YahooCollector:
    CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart"

    def __init__(
        self,
        settings: AppSettings,
        http_client: HttpClient,
        repository: CandleRepository,
    ) -> None:
        self.settings = settings
        self.http_client = http_client
        self.repository = repository

    @staticmethod
    def _safe_value(values: list[Any], index: int) -> Any:
        return values[index] if index < len(values) else None

    def _fetch(self, target: YahooTarget) -> dict[str, Any]:
        symbol = quote(target.symbol, safe="")
        return self.http_client.get_json(
            f"{self.CHART_URL}/{symbol}",
            params={
                "interval": self.settings.yahoo_interval,
                "range": self.settings.yahoo_range,
                "includePrePost": str(self.settings.yahoo_include_prepost).lower(),
                "events": "div,splits",
            },
        )

    def _parse(self, target: YahooTarget, payload: dict[str, Any]) -> list[MarketCandle]:
        chart = payload.get("chart") or {}
        if not isinstance(chart, dict):
            return []

        error = chart.get("error")
        if error:
            if isinstance(error, dict):
                raise RuntimeError(f"{error.get('code')} - {error.get('description')}")
            raise RuntimeError(str(error))

        results = chart.get("result") or []
        if not results or not isinstance(results[0], dict):
            return []

        result = results[0]
        timestamps = result.get("timestamp") or []
        indicators = result.get("indicators") or {}
        quote_list = indicators.get("quote") or [] if isinstance(indicators, dict) else []
        if not quote_list or not isinstance(quote_list[0], dict):
            return []

        quote_data = quote_list[0]
        opens = quote_data.get("open") or []
        highs = quote_data.get("high") or []
        lows = quote_data.get("low") or []
        closes = quote_data.get("close") or []
        volumes = quote_data.get("volume") or []
        candles: list[MarketCandle] = []

        for index, epoch in enumerate(timestamps):
            open_price = self._safe_value(opens, index)
            high_price = self._safe_value(highs, index)
            low_price = self._safe_value(lows, index)
            close_price = self._safe_value(closes, index)
            volume = self._safe_value(volumes, index)

            if all(value is None for value in (open_price, high_price, low_price, close_price)):
                continue

            raw_data = {
                "timestamp": epoch,
                "open": open_price,
                "high": high_price,
                "low": low_price,
                "close": close_price,
                "volume": volume,
            }
            candles.append(
                MarketCandle(
                    source="YAHOO",
                    market=target.market,
                    category=target.category,
                    symbol=target.symbol,
                    name=target.name,
                    interval_type=self.settings.yahoo_interval,
                    candle_time=datetime.fromtimestamp(int(epoch), tz=timezone.utc),
                    open_price=open_price,
                    high_price=high_price,
                    low_price=low_price,
                    close_price=close_price,
                    volume=volume,
                    raw_data=raw_data,
                )
            )

        count = self.settings.yahoo_recent_candles
        return candles[-count:] if count > 0 else candles

    def collect_once(self) -> list[CollectionResult]:
        results: list[CollectionResult] = []
        for target in YAHOO_TARGETS:
            try:
                candles = self._parse(target, self._fetch(target))
                saved = self.repository.save_market_candles(candles)
                status = "SUCCESS" if candles else "NO_DATA"
                result = CollectionResult(
                    source="YAHOO",
                    target=target.symbol,
                    status=status,
                    fetched_rows=len(candles),
                    saved_rows=saved,
                )
                print(
                    f"[YAHOO:{target.symbol}] status={status} "
                    f"fetched={len(candles)} upserted={saved}",
                    flush=True,
                )
            except Exception as exc:
                result = CollectionResult(
                    source="YAHOO",
                    target=target.symbol,
                    status="FAILED",
                    fetched_rows=0,
                    saved_rows=0,
                    error_message=f"{type(exc).__name__}: {exc}",
                )
                print(f"[YAHOO:{target.symbol}] ERROR {result.error_message}", flush=True)

            self.repository.save_collection_result(result)
            results.append(result)
        return results
