from __future__ import annotations

import threading
import time
from typing import Any

from http_client import HttpClient, HttpStatusError


class TossOpenApiClient:
    READ_ONLY_PATHS = {
        "/api/v1/accounts",
        "/api/v1/holdings",
        "/api/v1/stocks",
        "/api/v1/candles",
    }

    def __init__(self, http_client: HttpClient, base_url: str, client_id: str,
                 client_secret: str, expiry_skew_seconds: int = 60) -> None:
        self.http_client = http_client
        self.base_url = base_url.rstrip("/")
        self.client_id = client_id
        self.client_secret = client_secret
        self.expiry_skew_seconds = max(expiry_skew_seconds, 0)
        self._access_token: str | None = None
        self._expires_at = 0.0
        self._lock = threading.Lock()

    def _issue_token(self) -> str:
        payload = self.http_client.post_json(
            f"{self.base_url}/oauth2/token",
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        token = payload.get("access_token")
        if not isinstance(token, str) or not token:
            raise RuntimeError("OAuth2 token response does not contain access_token")
        try:
            expires_in = max(int(payload.get("expires_in", 3600)), 1)
        except (TypeError, ValueError):
            expires_in = 3600
        self._access_token = token
        self._expires_at = time.monotonic() + max(expires_in - self.expiry_skew_seconds, 1)
        print(f"[TOSS:AUTH] access token issued expires_in={expires_in}s", flush=True)
        return token

    def _get_token(self, force_refresh: bool = False) -> str:
        with self._lock:
            if force_refresh or not self._access_token or time.monotonic() >= self._expires_at:
                return self._issue_token()
            return self._access_token

    def invalidate_token(self) -> None:
        with self._lock:
            self._access_token = None
            self._expires_at = 0.0

    def get_json(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        if path not in self.READ_ONLY_PATHS:
            raise ValueError(f"Toss Open API path is not allowed by read-only policy: {path}")
        for auth_attempt in range(2):
            token = self._get_token(force_refresh=auth_attempt == 1)
            try:
                request_headers = dict(headers or {})
                request_headers["Authorization"] = f"Bearer {token}"
                return self.http_client.get_json(
                    f"{self.base_url}{path}",
                    params=params,
                    headers=request_headers,
                )
            except HttpStatusError as exc:
                if exc.status_code != 401 or auth_attempt == 1:
                    raise
                print("[TOSS:AUTH] received 401; refreshing token once", flush=True)
                self.invalidate_token()
        raise RuntimeError("Toss Open API authentication failed")
