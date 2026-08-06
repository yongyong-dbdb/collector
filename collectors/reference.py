from __future__ import annotations

import time
from typing import Any

from config import AppSettings
from repository import CandleRepository
from toss_auth import TossOpenApiClient


class TossReferenceCollector:
    ACCOUNTS_PATH = "/api/v1/accounts"
    HOLDINGS_PATH = "/api/v1/holdings"
    STOCKS_PATH = "/api/v1/stocks"
    STOCKS_CHUNK_SIZE = 100

    def __init__(self, settings: AppSettings, api_client: TossOpenApiClient,
                 repository: CandleRepository) -> None:
        self.settings = settings
        self.api_client = api_client
        self.repository = repository
        self._next_run_at = 0.0

    @staticmethod
    def _canonical_symbol(value: Any) -> str:
        symbol = str(value or "").strip()
        if len(symbol) == 7 and symbol.startswith("A") and symbol[1:].isdigit():
            return symbol[1:]
        return symbol

    def _get_holdings(self) -> list[dict[str, Any]]:
        accounts = self.api_client.get_json(self.ACCOUNTS_PATH).get("result") or []
        holdings_by_symbol: dict[str, dict[str, Any]] = {}
        for account in accounts:
            if not isinstance(account, dict) or account.get("accountSeq") is None:
                continue
            payload = self.api_client.get_json(
                self.HOLDINGS_PATH,
                headers={"X-Tossinvest-Account": str(account["accountSeq"])},
            )
            result = payload.get("result") or {}
            items = result.get("items") or [] if isinstance(result, dict) else []
            for item in items:
                if not isinstance(item, dict):
                    continue
                symbol = self._canonical_symbol(item.get("symbol"))
                if not symbol:
                    continue
                holdings_by_symbol[symbol] = {
                    "symbol": symbol,
                    "name": item.get("name") or symbol,
                    "marketCountry": item.get("marketCountry"),
                    "currency": item.get("currency"),
                }
        return list(holdings_by_symbol.values())

    def _get_stock_info(self, symbols: list[str]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for index in range(0, len(symbols), self.STOCKS_CHUNK_SIZE):
            chunk = symbols[index:index + self.STOCKS_CHUNK_SIZE]
            try:
                payload = self.api_client.get_json(
                    self.STOCKS_PATH,
                    params={"symbols": ",".join(chunk)},
                )
                result = payload.get("result") or []
                rows.extend(row for row in result if isinstance(row, dict))
            except Exception as batch_error:
                print(
                    f"[TOSS:REFERENCE] stock batch failed; retrying individually: {batch_error}",
                    flush=True,
                )
                for symbol in chunk:
                    try:
                        payload = self.api_client.get_json(
                            self.STOCKS_PATH, params={"symbols": symbol}
                        )
                        result = payload.get("result") or []
                        rows.extend(row for row in result if isinstance(row, dict))
                    except Exception as exc:
                        print(
                            f"[TOSS:REFERENCE] skip unsupported stock_info symbol={symbol}: {exc}",
                            flush=True,
                        )
        return rows

    def collect_if_due(self) -> bool:
        now = time.monotonic()
        if now < self._next_run_at:
            return False

        holdings = self._get_holdings()
        existing = [self._canonical_symbol(symbol) for symbol in self.repository.get_toss_symbols()]
        symbols = sorted({*existing, *(row["symbol"] for row in holdings)})
        stock_info = self._get_stock_info(symbols) if symbols else []
        saved_info = self.repository.save_toss_stock_info(stock_info)
        synced_holdings = self.repository.sync_holding_symbols(holdings, stock_info)
        synced_metadata = self.repository.sync_toss_stock_metadata()
        self._next_run_at = now + self.settings.toss_reference_sync_seconds
        print(
            f"[TOSS:REFERENCE] stock_info={saved_info} holdings={len(holdings)} "
            f"symbols_synced={synced_holdings} metadata_synced={synced_metadata} "
            f"next_run_seconds={self.settings.toss_reference_sync_seconds}",
            flush=True,
        )
        return True
