from __future__ import annotations

from psycopg2.extras import Json, execute_values

from database import Database


class NewsRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def save_news(self, rows: list[object]) -> int:
        if not rows:
            return 0

        sql = """
            INSERT INTO public.market_news (
                news_id,
                title,
                summary,
                publisher,
                news_type,
                related_stocks,
                nation,
                created_at,
                updated_at
            )
            VALUES %s
            ON CONFLICT (news_id) DO UPDATE SET
                title = EXCLUDED.title,
                summary = EXCLUDED.summary,
                publisher = EXCLUDED.publisher,
                news_type = EXCLUDED.news_type,
                related_stocks = EXCLUDED.related_stocks,
                nation = EXCLUDED.nation,
                created_at = EXCLUDED.created_at,
                updated_at = now()
        """
        values = [
            (
                row.news_id,
                row.title,
                row.summary,
                row.publisher,
                row.news_type,
                Json(row.related_stocks),
                row.nation,
                row.created_at,
            )
            for row in rows
        ]
        template = "(%s,%s,%s,%s,%s,%s,%s,%s,now())"
        with self.database.connect() as conn:
            with conn.cursor() as cursor:
                execute_values(cursor, sql, values, template=template, page_size=100)
        return len(values)

    def get_missing_detail_ids(self, news_ids: list[str], limit: int) -> list[str]:
        if not news_ids or limit <= 0:
            return []

        sql = """
            SELECT n.news_id
            FROM public.market_news AS n
            LEFT JOIN public.market_news_detail AS d
                   ON d.news_id = n.news_id
            WHERE n.news_id = ANY(%s)
              AND (
                    d.news_id IS NULL
                    OR NULLIF(BTRIM(d.content), '') IS NULL
              )
            ORDER BY n.created_at DESC, n.news_id
            LIMIT %s
        """
        with self.database.connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, (news_ids, limit))
                return [str(row[0]) for row in cursor.fetchall()]

    def save_news_details(self, rows: list[object]) -> int:
        if not rows:
            return 0

        sql = """
            INSERT INTO public.market_news_detail (
                news_id,
                language,
                summary_sentences,
                sentiment,
                content,
                source_code,
                source_name,
                writers,
                stock_codes,
                company_codes,
                link_url,
                created_at,
                updated_at,
                collected_at
            )
            VALUES %s
            ON CONFLICT (news_id) DO UPDATE SET
                language = EXCLUDED.language,
                summary_sentences = EXCLUDED.summary_sentences,
                sentiment = EXCLUDED.sentiment,
                content = EXCLUDED.content,
                source_code = EXCLUDED.source_code,
                source_name = EXCLUDED.source_name,
                writers = EXCLUDED.writers,
                stock_codes = EXCLUDED.stock_codes,
                company_codes = EXCLUDED.company_codes,
                link_url = EXCLUDED.link_url,
                created_at = EXCLUDED.created_at,
                updated_at = EXCLUDED.updated_at,
                collected_at = now()
        """
        values = [
            (
                row.news_id,
                row.language,
                Json(row.summary_sentences),
                row.sentiment,
                row.content,
                row.source_code,
                row.source_name,
                Json(row.writers),
                Json(row.stock_codes),
                Json(row.company_codes),
                row.link_url,
                row.created_at,
                row.updated_at,
            )
            for row in rows
        ]
        template = "(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now())"
        with self.database.connect() as conn:
            with conn.cursor() as cursor:
                execute_values(cursor, sql, values, template=template, page_size=100)
        return len(values)

    def save_collection_result(self, result: object) -> None:
        sql = """
            INSERT INTO public.collector_run_history (
                source,
                target,
                status,
                fetched_rows,
                saved_rows,
                error_message,
                finished_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, now())
        """
        with self.database.connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    sql,
                    (
                        result.source,
                        result.target,
                        result.status,
                        result.fetched_rows,
                        result.saved_rows,
                        result.error_message,
                    ),
                )