from __future__ import annotations

import time
from typing import Any

import requests


class HttpStatusError(RuntimeError):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code


class HttpClient:
    def __init__(self, timeout: int, retries: int, backoff_seconds: int) -> None:
        self.timeout = timeout
        self.retries = max(retries, 1)
        self.backoff_seconds = max(backoff_seconds, 1)
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "toss-chart-collector/1.4.0", "Accept": "application/json"})

    def request_json(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(1, self.retries + 1):
            try:
                response = self.session.request(
                    method, url, params=params, data=data, headers=headers, timeout=self.timeout
                )
                if response.status_code >= 400:
                    message = response.text[:1000]
                    error = HttpStatusError(response.status_code, f"HTTP {response.status_code}: {message}")
                    if response.status_code < 500 and response.status_code != 429:
                        raise error
                    last_error = error
                else:
                    payload = response.json()
                    if not isinstance(payload, dict):
                        raise ValueError("API response is not a JSON object")
                    return payload
            except HttpStatusError:
                raise
            except (requests.RequestException, ValueError) as exc:
                last_error = exc

            if attempt >= self.retries:
                break
            wait_seconds = self.backoff_seconds * attempt
            print(
                f"[HTTP] retry={attempt}/{self.retries - 1} wait={wait_seconds}s "
                f"error={type(last_error).__name__}: {last_error}",
                flush=True,
            )
            time.sleep(wait_seconds)
        raise RuntimeError(f"HTTP request failed after {self.retries} attempts: {last_error}")

    def get_json(self, url: str, *, params: dict[str, Any] | None = None,
                 headers: dict[str, str] | None = None) -> dict[str, Any]:
        return self.request_json("GET", url, params=params, headers=headers)

    def post_json(self, url: str, *, data: dict[str, Any] | None = None,
                  headers: dict[str, str] | None = None) -> dict[str, Any]:
        return self.request_json("POST", url, data=data, headers=headers)
