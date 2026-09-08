from __future__ import annotations

import time
from datetime import datetime, timezone

from collectors import NewsCollector, TossCollector, TossReferenceCollector, YahooCollector
from config import load_settings
from database import Database
from http_client import HttpClient
from models import CollectionResult
from news_repository import NewsRepository
from repository import CandleRepository
from toss_auth import TossOpenApiClient
from wts_client import TossWtsClient


def summarize(results: list[CollectionResult]) -> None:
    success = sum(result.status == "SUCCESS" for result in results)
    no_data = sum(result.status == "NO_DATA" for result in results)
    failed = sum(result.status == "FAILED" for result in results)
    rows = sum(result.saved_rows for result in results)
    print(
        f"[SUMMARY] success={success} no_data={no_data} "
        f"failed={failed} upserted={rows}",
        flush=True,
    )


def main() -> None:
    settings = load_settings()
    database = Database(settings.database)
    database.ping()
    repository = CandleRepository(database)
    http_client = HttpClient(
        timeout=settings.request_timeout,
        retries=settings.request_retries,
        backoff_seconds=settings.retry_backoff_seconds,
    )

    collectors = []
    reference_collector = None

    if settings.enable_toss:
        toss_api_client = TossOpenApiClient(
            http_client,
            settings.toss_openapi_base_url,
            settings.toss_openapi_client_id,
            settings.toss_openapi_client_secret,
            settings.toss_token_expiry_skew_seconds,
        )
        collectors.append(TossCollector(settings, toss_api_client, repository))
        if settings.enable_toss_reference_sync:
            reference_collector = TossReferenceCollector(settings, toss_api_client, repository)

    if settings.enable_yahoo:
        collectors.append(YahooCollector(settings, http_client, repository))

    if settings.enable_toss_news:
        news_client = TossWtsClient(
            web_base_url=settings.toss_wts_web_base_url,
            info_base_url=settings.toss_wts_info_base_url,
            timeout=settings.request_timeout,
            retries=settings.request_retries,
            backoff_seconds=settings.retry_backoff_seconds,
        )
        collectors.append(NewsCollector(settings, news_client, NewsRepository(database)))

    print(
        "[START] "
        f"db={settings.database.user}@{settings.database.host}:"
        f"{settings.database.port}/{settings.database.name} "
        f"toss={settings.enable_toss} yahoo={settings.enable_yahoo} "
        f"news={settings.enable_toss_news} "
        f"interval={settings.sleep_seconds}s run_once={settings.run_once}",
        flush=True,
    )

    while True:
        started_at = datetime.now(timezone.utc)
        all_results: list[CollectionResult] = []

        if reference_collector is not None:
            try:
                reference_collector.collect_if_due()
            except Exception as exc:
                print(f"[TOSS:REFERENCE] ERROR {type(exc).__name__}: {exc}", flush=True)

        for collector in collectors:
            all_results.extend(collector.collect_once())

        summarize(all_results)
        elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()
        print(f"[CYCLE] elapsed={elapsed:.2f}s", flush=True)

        if settings.run_once:
            break

        print(f"[SLEEP] {settings.sleep_seconds}s", flush=True)
        time.sleep(settings.sleep_seconds)


if __name__ == "__main__":
    main()
