from __future__ import annotations

from datetime import datetime

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

    def get_latest_toss_candle_time(
        self,
        market_type: str,
        product_code: str,
        chart_range: str,
    ) -> datetime | None:
        sql = """
            SELECT MAX(candle_time::timestamptz)
            FROM public.toss_chart_candle
            WHERE market_type = %s
              AND product_code = %s
              AND chart_range = %s
        """
        with self.database.connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, (market_type, product_code, chart_range))
                row = cursor.fetchone()
        return row[0] if row and row[0] is not None else None

    def get_toss_symbols(self) -> list[str]:
        sql = """
            SELECT symbol
            FROM public.symbol_master
            WHERE source = 'TOSS' AND symbol IS NOT NULL
            ORDER BY collection_priority, symbol_id
        """
        with self.database.connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql)
                return [str(row[0]) for row in cursor.fetchall()]

    def sync_toss_stock_metadata(self) -> int:
        sql_master = """
            UPDATE public.symbol_master AS sm
            SET name = tsi.name,
                category = tsi.security_type,
                market = CASE WHEN tsi.currency = 'KRW' THEN 'KR' ELSE 'US' END,
                market_type = CASE WHEN tsi.currency = 'KRW' THEN 'kr-s' ELSE 'us-s' END,
                updated_at = now()
            FROM public.toss_stock_info AS tsi
            WHERE sm.source = 'TOSS'
              AND tsi.symbol = CASE
                    WHEN sm.symbol ~ '^A[0-9]{6}$' THEN substring(sm.symbol FROM 2)
                    ELSE sm.symbol
                  END
        """
        sql_candles = """
            UPDATE public.toss_chart_candle AS candle
            SET product_name = tsi.name,
                updated_at = now()
            FROM public.toss_stock_info AS tsi
            WHERE tsi.symbol = CASE
                    WHEN candle.product_symbol ~ '^A[0-9]{6}$'
                        THEN substring(candle.product_symbol FROM 2)
                    ELSE candle.product_symbol
                  END
              AND candle.product_name IS DISTINCT FROM tsi.name
        """
        sql_disable_unresolved = """
            UPDATE public.symbol_master AS sm
            SET collection_enabled = false,
                updated_at = now()
            WHERE sm.source = 'TOSS'
              AND sm.held_in_account = false
              AND EXISTS (SELECT 1 FROM public.toss_stock_info)
              AND NOT EXISTS (
                    SELECT 1
                    FROM public.toss_stock_info AS tsi
                    WHERE tsi.symbol = CASE
                            WHEN sm.symbol ~ '^A[0-9]{6}$'
                                THEN substring(sm.symbol FROM 2)
                            ELSE sm.symbol
                          END
              )
        """
        with self.database.connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql_master)
                updated_master = cursor.rowcount
                cursor.execute(sql_candles)
                cursor.execute(sql_disable_unresolved)
        return updated_master

    def save_toss_stock_info(self, rows: list[dict]) -> int:
        if not rows:
            return 0
        sql = """
            INSERT INTO public.toss_stock_info (
                symbol, name, english_name, isin_code, market, security_type,
                is_common_share, status, currency, list_date, delist_date,
                shares_outstanding, leverage_factor, liquidation_trading,
                nxt_supported, krx_trading_suspended, nxt_trading_suspended,
                raw_data
            ) VALUES %s
            ON CONFLICT (symbol) DO UPDATE SET
                name = EXCLUDED.name,
                english_name = EXCLUDED.english_name,
                isin_code = EXCLUDED.isin_code,
                market = EXCLUDED.market,
                security_type = EXCLUDED.security_type,
                is_common_share = EXCLUDED.is_common_share,
                status = EXCLUDED.status,
                currency = EXCLUDED.currency,
                list_date = EXCLUDED.list_date,
                delist_date = EXCLUDED.delist_date,
                shares_outstanding = EXCLUDED.shares_outstanding,
                leverage_factor = EXCLUDED.leverage_factor,
                liquidation_trading = EXCLUDED.liquidation_trading,
                nxt_supported = EXCLUDED.nxt_supported,
                krx_trading_suspended = EXCLUDED.krx_trading_suspended,
                nxt_trading_suspended = EXCLUDED.nxt_trading_suspended,
                raw_data = EXCLUDED.raw_data,
                updated_at = now()
        """
        values = []
        for row in rows:
            detail = row.get("koreanMarketDetail") or {}
            values.append((
                row.get("symbol"), row.get("name"), row.get("englishName"),
                row.get("isinCode"), row.get("market"), row.get("securityType"),
                row.get("isCommonShare"), row.get("status"), row.get("currency"),
                row.get("listDate"), row.get("delistDate"), row.get("sharesOutstanding"),
                row.get("leverageFactor"), detail.get("liquidationTrading"),
                detail.get("nxtSupported"), detail.get("krxTradingSuspended"),
                detail.get("nxtTradingSuspended"), Json(row),
            ))
        with self.database.connect() as conn:
            with conn.cursor() as cursor:
                execute_values(cursor, sql, values, page_size=200)
        return len(values)

    def sync_holding_symbols(self, holdings: list[dict], stock_info: list[dict]) -> int:
        info_by_symbol = {str(row.get("symbol")): row for row in stock_info}
        sql_reset = """
            UPDATE public.symbol_master
            SET held_in_account = false,
                collection_enabled = CASE
                    WHEN managed_by_holdings THEN false
                    ELSE collection_enabled
                END,
                updated_at = now()
            WHERE source = 'TOSS' AND held_in_account = true
        """
        sql_upsert = """
            INSERT INTO public.symbol_master AS sm (
                source, market, category, symbol, name, source_code, market_type,
                interval_type, chart_range, recent_candle_count,
                collection_enabled, collection_priority, held_in_account,
                managed_by_holdings, description, updated_at
            ) VALUES %s
            ON CONFLICT (source, source_code)
                WHERE source = 'TOSS' AND source_code IS NOT NULL
            DO UPDATE SET
                market = EXCLUDED.market,
                category = EXCLUDED.category,
                name = EXCLUDED.name,
                market_type = EXCLUDED.market_type,
                held_in_account = true,
                collection_enabled = CASE
                    WHEN sm.managed_by_holdings THEN true
                    ELSE sm.collection_enabled
                END,
                updated_at = now()
        """
        values = []
        for holding in holdings:
            symbol = str(holding["symbol"])
            info = info_by_symbol.get(symbol, {})
            currency = info.get("currency") or holding.get("currency")
            country = holding.get("marketCountry") or ("KR" if currency == "KRW" else "US")
            market_type = "kr-s" if country == "KR" else "us-s"
            values.append((
                "TOSS", country, info.get("securityType") or "STOCK", symbol,
                info.get("name") or holding.get("name") or symbol, symbol, market_type,
                "1m", "min:1", 21, True, 50, True, True,
                "Automatically synchronized from Toss holdings",
            ))
        with self.database.connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql_reset)
                if values:
                    template = "(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now())"
                    execute_values(cursor, sql_upsert, values, template=template, page_size=200)
        return len(values)

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