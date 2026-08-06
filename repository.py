from __future__ import annotations

from psycopg2.extras import Json, execute_values

from database import Database
from models import CollectionResult, MarketCandle, TossCandle, TossProduct


class CandleRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def get_toss_products(self) -> list[TossProduct]:
        sql = """
            SELECT source_code, symbol, name, COALESCE(market_type, 'kr-s'),
                   interval_type, chart_range, recent_candle_count
            FROM public.symbol_master
            WHERE source = 'TOSS'
              AND collection_enabled = true
              AND source_code IS NOT NULL
            ORDER BY collection_priority, symbol_id
        """
        with self.database.connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql)
                rows = cursor.fetchall()
        products: list[TossProduct] = []
        for source_code, symbol, name, market_type, interval_type, chart_range, count in rows:
            if interval_type != "1m":
                print(f"[TOSS:{symbol}] interval_type={interval_type} overridden to 1m", flush=True)
            products.append(
                TossProduct(
                    input_value=str(source_code), code=str(source_code), symbol=str(symbol),
                    name=str(name), market_type=str(market_type), interval_type="1m",
                    chart_range=str(chart_range), recent_candle_count=max(1, min(int(count), 200)),
                )
            )
        return products

    def save_toss_candles(
        self,
        market_type: str,
        chart_range: str,
        product: TossProduct,
        candles: list[TossCandle],
    ) -> int:
        if not candles:
            return 0

        sql = """
            INSERT INTO public.toss_chart_candle (
                market_type,
                product_code,
                product_symbol,
                product_name,
                chart_range,
                candle_time,
                base_price,
                open_price,
                high_price,
                low_price,
                close_price,
                volume,
                amount,
                exchange_rate,
                raw_data,
                updated_at
            )
            VALUES %s
            ON CONFLICT (market_type, product_code, chart_range, candle_time)
            DO UPDATE SET
                product_symbol = EXCLUDED.product_symbol,
                product_name = EXCLUDED.product_name,
                base_price = EXCLUDED.base_price,
                open_price = EXCLUDED.open_price,
                high_price = EXCLUDED.high_price,
                low_price = EXCLUDED.low_price,
                close_price = EXCLUDED.close_price,
                volume = EXCLUDED.volume,
                amount = EXCLUDED.amount,
                exchange_rate = EXCLUDED.exchange_rate,
                raw_data = EXCLUDED.raw_data,
                updated_at = now()
        """

        values = [
            (
                market_type,
                product.code,
                product.symbol,
                product.name,
                chart_range,
                candle.candle_time,
                candle.base_price,
                candle.open_price,
                candle.high_price,
                candle.low_price,
                candle.close_price,
                candle.volume,
                candle.amount,
                candle.exchange_rate,
                Json(candle.raw_data),
                # updated_at is supplied by template below.
            )
            for candle in candles
        ]

        template = "(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now())"
        with self.database.connect() as conn:
            with conn.cursor() as cursor:
                execute_values(cursor, sql, values, template=template, page_size=500)
        return len(candles)

    def save_market_candles(self, candles: list[MarketCandle]) -> int:
        if not candles:
            return 0

        sql = """
            INSERT INTO public.market_indicator_candle (
                source,
                market,
                category,
                symbol,
                name,
                interval_type,
                candle_time,
                open_price,
                high_price,
                low_price,
                close_price,
                volume,
                raw_data
            )
            VALUES %s
            ON CONFLICT (source, symbol, interval_type, candle_time)
            DO UPDATE SET
                market = EXCLUDED.market,
                category = EXCLUDED.category,
                name = EXCLUDED.name,
                open_price = EXCLUDED.open_price,
                high_price = EXCLUDED.high_price,
                low_price = EXCLUDED.low_price,
                close_price = EXCLUDED.close_price,
                volume = EXCLUDED.volume,
                raw_data = EXCLUDED.raw_data,
                updated_at = now()
        """

        values = [
            (
                candle.source,
                candle.market,
                candle.category,
                candle.symbol,
                candle.name,
                candle.interval_type,
                candle.candle_time,
                candle.open_price,
                candle.high_price,
                candle.low_price,
                candle.close_price,
                candle.volume,
                Json(candle.raw_data),
            )
            for candle in candles
        ]

        with self.database.connect() as conn:
            with conn.cursor() as cursor:
                execute_values(cursor, sql, values, page_size=500)
        return len(candles)

    def save_collection_result(self, result: CollectionResult) -> None:
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
