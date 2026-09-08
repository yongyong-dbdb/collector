from __future__ import annotations

import importlib.util
import pathlib
import sys
import types
import unittest
from dataclasses import dataclass

ROOT = pathlib.Path(__file__).resolve().parents[1]

# Load collectors/news.py without importing collectors/__init__.py and unrelated collectors.
config_stub = types.ModuleType("config")
config_stub.AppSettings = object
sys.modules["config"] = config_stub


@dataclass(frozen=True)
class CollectionResult:
    source: str
    target: str
    status: str
    fetched_rows: int
    saved_rows: int
    error_message: str | None = None


models_stub = types.ModuleType("models")
models_stub.CollectionResult = CollectionResult
sys.modules["models"] = models_stub

news_repo_stub = types.ModuleType("news_repository")
news_repo_stub.NewsRepository = object
sys.modules["news_repository"] = news_repo_stub

wts_stub = types.ModuleType("wts_client")
wts_stub.TossWtsClient = object
sys.modules["wts_client"] = wts_stub

spec = importlib.util.spec_from_file_location(
    "news_collector_under_test", ROOT / "collectors" / "news.py"
)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
NewsCollector = module.NewsCollector


class Settings:
    toss_news_scope = "ALL_HIGHLIGHT"
    toss_news_limit = 50
    toss_news_detail_enabled = True
    toss_news_detail_max_per_cycle = 20


class FakeClient:
    def __init__(self, list_payload, detail_payloads=None, detail_error_ids=None):
        self.list_payload = list_payload
        self.detail_payloads = detail_payloads or {}
        self.detail_error_ids = set(detail_error_ids or [])
        self.detail_calls = []

    def get_news_list(self, scope, limit):
        self.scope = scope
        self.limit = limit
        return self.list_payload

    def get_news_detail(self, news_id):
        self.detail_calls.append(news_id)
        if news_id in self.detail_error_ids:
            raise RuntimeError("detail failed")
        return self.detail_payloads[news_id]


class FakeRepository:
    def __init__(self, missing_ids=None):
        self.missing_ids = list(missing_ids or [])
        self.news_rows = []
        self.detail_rows = []
        self.history = []

    def save_news(self, rows):
        self.news_rows.extend(rows)
        return len(rows)

    def get_missing_detail_ids(self, news_ids, limit):
        self.requested_news_ids = list(news_ids)
        return self.missing_ids[:limit]

    def save_news_details(self, rows):
        self.detail_rows.extend(rows)
        return len(rows)

    def save_collection_result(self, result):
        self.history.append(result)


LIST_PAYLOAD = {
    "result": {
        "type": "ALL_HIGHLIGHT",
        "title": "뉴스",
        "news": [
            {
                "newsId": "news_1",
                "title": "테스트 뉴스",
                "summary": "요약",
                "createdAt": "2026-09-08T15:00:00",
                "source": "테스트신문",
                "newsType": "impact_news",
                "relatedStocks": [
                    {
                        "stockCode": "A005930",
                        "stockName": "삼성전자",
                        "market": "kr",
                        "fluctuation": 2.1,
                        "logoImageUrl": "https://example/logo.png",
                    }
                ],
                "nation": "KR",
            }
        ],
    }
}

DETAIL_PAYLOAD = {
    "result": {
        "news": {
            "language": "ko",
            "summarySentences": ["첫 문장"],
            "sentiment": "POSITIVE",
            "content": [
                {"type": "text", "text": "[[기사 핵심 요약]] 본문 첫 문단"},
                {"type": "text", "text": "contact@example.com (끝)"},
                {"type": "text", "text": "Copyright 무단 전재 금지"},
            ],
            "source": {"code": "TEST", "name": "테스트신문"},
            "writers": ["홍길동"],
            "stockCodes": ["A005930"],
            "companyCodes": ["005930"],
            "linkUrl": "https://example.com/article",
            "createdAt": "2026-09-08T15:00:00+09:00",
            "updatedAt": "2026-09-08T15:01:00+09:00",
        }
    }
}


class NewsCollectorTests(unittest.TestCase):
    def test_parse_list_keeps_storage_fields_and_kst(self):
        rows = NewsCollector._parse_list(LIST_PAYLOAD)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row.news_id, "news_1")
        self.assertEqual(row.created_at.utcoffset().total_seconds(), 9 * 3600)
        self.assertEqual(
            row.related_stocks,
            [{"stockCode": "A005930", "stockName": "삼성전자", "market": "kr"}],
        )

    def test_parse_detail_cleans_content(self):
        detail = NewsCollector._parse_detail("news_1", DETAIL_PAYLOAD)
        self.assertEqual(detail.source_code, "TEST")
        self.assertEqual(detail.source_name, "테스트신문")
        self.assertEqual(detail.stock_codes, ["A005930"])
        self.assertIn("본문 첫 문단", detail.content)
        self.assertNotIn("[[기사 핵심 요약]]", detail.content)
        self.assertNotIn("contact@example.com", detail.content)
        self.assertNotIn("Copyright", detail.content)

    def test_collect_once_fetches_only_missing_detail(self):
        repo = FakeRepository(missing_ids=["news_1"])
        client = FakeClient(LIST_PAYLOAD, {"news_1": DETAIL_PAYLOAD})
        collector = NewsCollector(Settings(), client, repo)
        results = collector.collect_once()
        self.assertEqual([result.status for result in results], ["SUCCESS", "SUCCESS"])
        self.assertEqual(client.detail_calls, ["news_1"])
        self.assertEqual(len(repo.news_rows), 1)
        self.assertEqual(len(repo.detail_rows), 1)
        self.assertEqual(len(repo.history), 2)

    def test_detail_partial_failure_does_not_undo_list(self):
        payload = {
            "result": {
                "news": [
                    LIST_PAYLOAD["result"]["news"][0],
                    {
                        **LIST_PAYLOAD["result"]["news"][0],
                        "newsId": "news_2",
                        "title": "두 번째",
                    },
                ]
            }
        }
        repo = FakeRepository(missing_ids=["news_1", "news_2"])
        client = FakeClient(
            payload,
            {"news_1": DETAIL_PAYLOAD},
            detail_error_ids={"news_2"},
        )
        collector = NewsCollector(Settings(), client, repo)
        results = collector.collect_once()
        self.assertEqual(results[0].status, "SUCCESS")
        self.assertEqual(results[1].status, "FAILED")
        self.assertEqual(len(repo.news_rows), 2)
        self.assertEqual(len(repo.detail_rows), 1)
        self.assertIn("news_2", results[1].error_message)


if __name__ == "__main__":
    unittest.main()
