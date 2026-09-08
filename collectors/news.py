from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from config import AppSettings
from models import CollectionResult
from news_repository import NewsRepository
from wts_client import TossWtsClient


KST = ZoneInfo("Asia/Seoul")


@dataclass(frozen=True)
class NewsItem:
    news_id: str
    title: str
    summary: str | None
    publisher: str | None
    news_type: str | None
    related_stocks: list[dict[str, Any]]
    nation: str | None
    created_at: datetime


@dataclass(frozen=True)
class NewsDetail:
    news_id: str
    language: str | None
    summary_sentences: list[Any]
    sentiment: str | None
    content: str
    source_code: str | None
    source_name: str | None
    writers: list[Any]
    stock_codes: list[Any]
    company_codes: list[Any]
    link_url: str | None
    created_at: datetime | None
    updated_at: datetime | None


class NewsCollector:
    def __init__(
        self,
        settings: AppSettings,
        client: TossWtsClient,
        repository: NewsRepository,
    ) -> None:
        self.settings = settings
        self.client = client
        self.repository = repository

    @staticmethod
    def _unwrap(payload: dict[str, Any]) -> dict[str, Any]:
        result = payload.get("result")
        return result if isinstance(result, dict) else payload

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if value is None or value == "":
            return None
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=KST)
        text = str(value).strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=KST)

    @classmethod
    def _parse_list(cls, payload: dict[str, Any]) -> list[NewsItem]:
        result = cls._unwrap(payload)
        raw_news = result.get("news") or result.get("items") or []
        if not isinstance(raw_news, list):
            raise ValueError("WTS news response does not contain a news list")

        items: list[NewsItem] = []
        for row in raw_news:
            if not isinstance(row, dict):
                continue
            news_id = str(row.get("newsId") or "").strip()
            title = str(row.get("title") or "").strip()
            created_at = cls._parse_datetime(row.get("createdAt"))
            if not news_id or not title or created_at is None:
                continue

            related_stocks: list[dict[str, Any]] = []
            raw_stocks = row.get("relatedStocks") or []
            if isinstance(raw_stocks, list):
                for stock in raw_stocks:
                    if not isinstance(stock, dict):
                        continue
                    related_stocks.append(
                        {
                            "stockCode": stock.get("stockCode"),
                            "stockName": stock.get("stockName"),
                            "market": stock.get("market"),
                        }
                    )

            items.append(
                NewsItem(
                    news_id=news_id,
                    title=title,
                    summary=row.get("summary"),
                    publisher=row.get("source"),
                    news_type=row.get("newsType"),
                    related_stocks=related_stocks,
                    nation=row.get("nation"),
                    created_at=created_at,
                )
            )
        return items

    @classmethod
    def _extract_content(cls, raw_content: Any) -> str:
        paragraphs: list[str] = []
        if isinstance(raw_content, str):
            paragraphs.append(raw_content)
        elif isinstance(raw_content, list):
            for block in raw_content:
                if isinstance(block, str):
                    paragraphs.append(block)
                    continue
                if not isinstance(block, dict):
                    continue
                block_type = str(block.get("type") or "").lower()
                value = block.get("text") or block.get("value") or block.get("textContent")
                if value is None and block_type in {"text", "paragraph"}:
                    value = block.get("content")
                if isinstance(value, str):
                    paragraphs.append(value)
                elif isinstance(value, list):
                    paragraphs.extend(str(item) for item in value if isinstance(item, str))

        content = "\n\n".join(part.strip() for part in paragraphs if part and part.strip())
        content = content.replace("[[기사 핵심 요약]]", "")
        content = re.sub(
            r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
            "",
            content,
        )
        content = re.sub(r"\(\s*끝\s*\)", "", content)
        cleaned_lines = []
        for line in content.splitlines():
            stripped = line.strip()
            if re.search(r"(무단\s*전재|저작권자|copyright)", stripped, re.IGNORECASE):
                continue
            cleaned_lines.append(stripped)
        content = "\n".join(cleaned_lines)
        content = re.sub(r"[ \t]+", " ", content)
        content = re.sub(r"\n{3,}", "\n\n", content)
        return content.strip()

    @classmethod
    def _parse_detail(cls, news_id: str, payload: dict[str, Any]) -> NewsDetail:
        result = cls._unwrap(payload)
        language: str | None = None
        localized: dict[str, Any] | None = None

        available_languages = result.get("availableLanguages")
        if isinstance(available_languages, list):
            ordered_languages = ["kr"] + [
                str(value).strip()
                for value in available_languages
                if str(value).strip() and str(value).strip() != "kr"
            ]
            for candidate in ordered_languages:
                nested = result.get(candidate)
                if isinstance(nested, dict):
                    language = candidate
                    localized = nested
                    break

        if localized is None:
            for candidate in ("kr", "ko", "en"):
                nested = result.get(candidate)
                if isinstance(nested, dict):
                    language = candidate
                    localized = nested
                    break

        if localized is None:
            for key in ("news", "article", "detail"):
                nested = result.get(key)
                if isinstance(nested, dict):
                    localized = nested
                    break

        if localized is not None:
            result = localized

        language = str(result.get("language") or language or "").strip() or None

        source = result.get("source")
        source_code = result.get("sourceCode")
        source_name = result.get("sourceName")
        if isinstance(source, dict):
            source_code = source_code or source.get("code")
            source_name = source_name or source.get("name")
        elif isinstance(source, str):
            source_name = source_name or source

        summary_sentences = result.get("summarySentences") or []
        writers = result.get("writers") or []
        stock_codes = result.get("stockCodes") or []
        company_codes = result.get("companyCodes") or []

        if not isinstance(summary_sentences, list):
            summary_sentences = [summary_sentences]
        if not isinstance(writers, list):
            writers = [writers]
        if not isinstance(stock_codes, list):
            stock_codes = [stock_codes]
        if not isinstance(company_codes, list):
            company_codes = [company_codes]

        if not stock_codes:
            related_stocks = result.get("relatedStocks") or []
            if isinstance(related_stocks, list):
                stock_codes = [
                    stock.get("stockCode")
                    for stock in related_stocks
                    if isinstance(stock, dict) and stock.get("stockCode")
                ]

        content = cls._extract_content(result.get("content"))
        if not content:
            raise ValueError(
                f"WTS news detail content is empty after parsing: news_id={news_id}"
            )

        return NewsDetail(
            news_id=news_id,
            language=language,
            summary_sentences=summary_sentences,
            sentiment=result.get("sentiment"),
            content=content,
            source_code=source_code,
            source_name=source_name,
            writers=writers,
            stock_codes=stock_codes,
            company_codes=company_codes,
            link_url=result.get("linkUrl") or result.get("url"),
            created_at=cls._parse_datetime(result.get("createdAt")),
            updated_at=cls._parse_datetime(result.get("updatedAt")),
        )

    def collect_once(self) -> list[CollectionResult]:
        results: list[CollectionResult] = []

        try:
            items = self._parse_list(
                self.client.get_news_list(
                    self.settings.toss_news_scope,
                    self.settings.toss_news_limit,
                )
            )
            saved = self.repository.save_news(items)
            status = "SUCCESS" if items else "NO_DATA"
            list_result = CollectionResult(
                source="TOSS_NEWS",
                target="LIST",
                status=status,
                fetched_rows=len(items),
                saved_rows=saved,
            )
            print(
                f"[TOSS:NEWS:LIST] status={status} fetched={len(items)} upserted={saved}",
                flush=True,
            )
        except Exception as exc:
            list_result = CollectionResult(
                source="TOSS_NEWS",
                target="LIST",
                status="FAILED",
                fetched_rows=0,
                saved_rows=0,
                error_message=f"{type(exc).__name__}: {exc}",
            )
            print(f"[TOSS:NEWS:LIST] ERROR {list_result.error_message}", flush=True)
            self.repository.save_collection_result(list_result)
            return [list_result]

        self.repository.save_collection_result(list_result)
        results.append(list_result)

        if not self.settings.toss_news_detail_enabled or not items:
            return results

        missing_ids = self.repository.get_missing_detail_ids(
            [item.news_id for item in items],
            self.settings.toss_news_detail_max_per_cycle,
        )
        details: list[NewsDetail] = []
        errors: list[str] = []

        for news_id in missing_ids:
            try:
                details.append(self._parse_detail(news_id, self.client.get_news_detail(news_id)))
            except Exception as exc:
                errors.append(f"{news_id}: {type(exc).__name__}: {exc}")

        saved_details = self.repository.save_news_details(details)
        if errors:
            detail_status = "FAILED"
            error_message = "; ".join(errors[:3])
            if len(errors) > 3:
                error_message += f"; ... {len(errors) - 3} more"
        else:
            detail_status = "SUCCESS" if missing_ids else "NO_DATA"
            error_message = None

        detail_result = CollectionResult(
            source="TOSS_NEWS",
            target="DETAIL",
            status=detail_status,
            fetched_rows=len(details),
            saved_rows=saved_details,
            error_message=error_message,
        )
        self.repository.save_collection_result(detail_result)
        results.append(detail_result)
        print(
            f"[TOSS:NEWS:DETAIL] status={detail_status} "
            f"requested={len(missing_ids)} fetched={len(details)} "
            f"upserted={saved_details} failed={len(errors)}",
            flush=True,
        )
        return results