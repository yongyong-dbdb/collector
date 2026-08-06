from __future__ import annotations

import os
from dataclasses import dataclass


def env_bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "y", "on"}


def env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer: {value}") from exc


def env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number: {value}") from exc


@dataclass(frozen=True)
class DatabaseSettings:
    host: str
    port: int
    name: str
    user: str
    password: str
    connect_timeout: int


@dataclass(frozen=True)
class AppSettings:
    database: DatabaseSettings
    enable_toss: bool
    enable_yahoo: bool
    run_once: bool
    sleep_seconds: int
    request_timeout: int
    request_retries: int
    retry_backoff_seconds: int
    toss_openapi_base_url: str
    toss_openapi_client_id: str
    toss_openapi_client_secret: str
    toss_token_expiry_skew_seconds: int
    toss_candle_min_interval_seconds: float
    enable_toss_reference_sync: bool
    toss_reference_sync_seconds: int
    yahoo_range: str
    yahoo_interval: str
    yahoo_recent_candles: int
    yahoo_include_prepost: bool


def load_settings() -> AppSettings:
    database = DatabaseSettings(
        host=os.getenv("DB_HOST", "pg-cluster-rw"),
        port=env_int("DB_PORT", 5432),
        name=os.getenv("DB_NAME", "appdb"),
        user=os.getenv("DB_USER", "appuser"),
        password=os.getenv("DB_PASSWORD", ""),
        connect_timeout=env_int("DB_CONNECT_TIMEOUT", 10),
    )
    settings = AppSettings(
        database=database,
        enable_toss=env_bool("ENABLE_TOSS", True),
        enable_yahoo=env_bool("ENABLE_YAHOO", True),
        run_once=env_bool("RUN_ONCE", False),
        sleep_seconds=env_int("SLEEP_SECONDS", 300),
        request_timeout=env_int("REQUEST_TIMEOUT", 20),
        request_retries=env_int("REQUEST_RETRIES", 3),
        retry_backoff_seconds=env_int("RETRY_BACKOFF_SECONDS", 2),
        toss_openapi_base_url=os.getenv(
            "TOSS_OPENAPI_BASE_URL", "https://openapi.tossinvest.com"
        ).rstrip("/"),
        toss_openapi_client_id=os.getenv("TOSS_OPENAPI_CLIENT_ID", "").strip(),
        toss_openapi_client_secret=os.getenv("TOSS_OPENAPI_CLIENT_SECRET", "").strip(),
        toss_token_expiry_skew_seconds=env_int("TOSS_TOKEN_EXPIRY_SKEW_SECONDS", 60),
        toss_candle_min_interval_seconds=env_float("TOSS_CANDLE_MIN_INTERVAL_SECONDS", 0.22),
        enable_toss_reference_sync=env_bool("ENABLE_TOSS_REFERENCE_SYNC", True),
        toss_reference_sync_seconds=env_int("TOSS_REFERENCE_SYNC_SECONDS", 86400),
        yahoo_range=os.getenv("YAHOO_RANGE", "1d"),
        yahoo_interval=os.getenv("YAHOO_INTERVAL", "1m"),
        yahoo_recent_candles=env_int("YAHOO_RECENT_CANDLES", 15),
        yahoo_include_prepost=env_bool("YAHOO_INCLUDE_PREPOST", True),
    )
    if not settings.enable_toss and not settings.enable_yahoo:
        raise ValueError("At least one collector must be enabled")
    if settings.enable_toss and (
        not settings.toss_openapi_client_id or not settings.toss_openapi_client_secret
    ):
        raise ValueError(
            "TOSS_OPENAPI_CLIENT_ID and TOSS_OPENAPI_CLIENT_SECRET are required when ENABLE_TOSS=true"
        )
    if settings.sleep_seconds < 1:
        raise ValueError("SLEEP_SECONDS must be at least 1")
    if settings.toss_reference_sync_seconds < 60:
        raise ValueError("TOSS_REFERENCE_SYNC_SECONDS must be at least 60")
    if settings.toss_candle_min_interval_seconds < 0:
        raise ValueError("TOSS_CANDLE_MIN_INTERVAL_SECONDS must be at least 0")
    return settings
