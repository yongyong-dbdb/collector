from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import psycopg2
from psycopg2.extensions import connection

from config import DatabaseSettings


class Database:
    def __init__(self, settings: DatabaseSettings) -> None:
        self.settings = settings

    @contextmanager
    def connect(self) -> Iterator[connection]:
        conn = psycopg2.connect(
            host=self.settings.host,
            port=self.settings.port,
            dbname=self.settings.name,
            user=self.settings.user,
            password=self.settings.password,
            connect_timeout=self.settings.connect_timeout,
            application_name="market-data-collector",
        )
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def ping(self) -> None:
        with self.connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1")
                if cursor.fetchone() != (1,):
                    raise RuntimeError("Database ping failed")
