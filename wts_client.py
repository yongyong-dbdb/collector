from __future__ import annotations

import time
from typing import Any
from urllib.parse import quote, unquote

import requests


class WtsHttpStatusError(RuntimeError):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code


class TossWtsClient:
    NEWS_LIST_PATH = "/api/v1/dashboard/wts/news"
    NEWS_DETAIL_PATH = "/api/v2/news/{news_id}"
    MAX_NEWS_LIMIT = 50

    def __init__(
        self,
        web_base_url: str,
        info_base_url: str,
        timeout: int,
        retries: int,
        backoff_seconds: int,
    ) -> None:
        self.web_base_url = web_base_url.rstrip("/")
        self.info_base_url = info_base_url.rstrip("/")
        self.timeout = timeout
        self.retries = max(retries, 1)
        self.backoff_seconds = max(backoff_seconds, 1)
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/140.0.0.0 Safari/537.36"
                ),
                "Accept": "application/json, text/plain, */*",
                "Referer": f"{self.web_base_url}/feed",
            }
        )
        self._session_ready = False

    def _initialize_session(self, force: bool = False) -> None:
        if self._session_ready and not force:
            return

        response = self.session.get(
            f"{self.web_base_url}/feed/recommended",
            headers={"Accept": "text/html,application/xhtml+xml"},
            timeout=self.timeout,
        )
        response.raise_for_status()

        xsrf_token = (
            self.session.cookies.get("XSRF-TOKEN")
            or self.session.cookies.get("XSRF_TOKEN")
            or self.session.cookies.get("xsrf-token")
        )
        if xsrf_token:
            self.session.headers["X-XSRF-TOKEN"] = unquote(xsrf_token)

        self._session_ready = True

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._initialize_session()
        url = f"{self.info_base_url}{path}"
        last_error: Exception | None = None

        for attempt in range(1, self.retries + 1):
            retry_after: str | None = None
            try:
                response = self.session.request(
                    method,
                    url,
                    json=json_body,
                    headers={"Origin": self.web_base_url},
                    timeout=self.timeout,
                )
                if response.status_code >= 400:
                    message = response.text[:1000]
                    error = WtsHttpStatusError(
                        response.status_code,
                        f"HTTP {response.status_code}: {message}",
                    )
                    if response.status_code in {401, 403} and attempt == 1:
                        self._session_ready = False
                        self._initialize_session(force=True)
                        last_error = error
                    elif response.status_code < 500 and response.status_code != 429:
                        raise error
                    else:
                        last_error = error
                        retry_after = response.headers.get("Retry-After")
                else:
                    payload = response.json()
                    if not isinstance(payload, dict):
                        raise ValueError("WTS API response is not a JSON object")
                    return payload
            except WtsHttpStatusError:
                raise
            except (requests.RequestException, ValueError) as exc:
                last_error = exc

            if attempt >= self.retries:
                break
            wait_seconds = self.backoff_seconds * attempt
            if retry_after:
                try:
                    wait_seconds = max(wait_seconds, float(retry_after))
                except ValueError:
                    pass
            print(
                f"[TOSS:NEWS:HTTP] retry={attempt}/{self.retries - 1} "
                f"wait={wait_seconds}s error={type(last_error).__name__}: {last_error}",
                flush=True,
            )
            time.sleep(wait_seconds)

        raise RuntimeError(
            f"WTS request failed after {self.retries} attempts: {last_error}"
        )

    def get_news_list(self, scope: str, limit: int) -> dict[str, Any]:
        size = max(1, min(int(limit), self.MAX_NEWS_LIMIT))
        return self._request_json(
            "POST",
            self.NEWS_LIST_PATH,
            json_body={"type": scope, "size": size},
        )

    def get_news_detail(self, news_id: str) -> dict[str, Any]:
        encoded_news_id = quote(news_id, safe="")
        return self._request_json(
            "GET",
            self.NEWS_DETAIL_PATH.format(news_id=encoded_news_id),
        )