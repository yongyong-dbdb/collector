CREATE TABLE IF NOT EXISTS public.toss_chart_candle (
    id bigserial PRIMARY KEY,
    market_type text NOT NULL,
    product_code text NOT NULL,
    product_symbol text,
    product_name text,
    chart_range text NOT NULL,
    candle_time text NOT NULL,
    base_price numeric,
    open_price numeric,
    high_price numeric,
    low_price numeric,
    close_price numeric,
    volume numeric,
    amount numeric,
    exchange_rate numeric,
    raw_data jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT toss_chart_candle_unique_candle
        UNIQUE (market_type, product_code, chart_range, candle_time)
);

CREATE INDEX IF NOT EXISTS idx_toss_chart_candle_lookup
    ON public.toss_chart_candle (market_type, product_code, chart_range, candle_time DESC);

CREATE INDEX IF NOT EXISTS idx_toss_chart_candle_product_time
    ON public.toss_chart_candle (product_code, candle_time DESC);

CREATE TABLE IF NOT EXISTS public.market_indicator_candle (
    id bigserial PRIMARY KEY,
    source text NOT NULL,
    market text NOT NULL,
    category text NOT NULL,
    symbol text NOT NULL,
    name text NOT NULL,
    interval_type text NOT NULL,
    candle_time timestamptz NOT NULL,
    open_price numeric,
    high_price numeric,
    low_price numeric,
    close_price numeric,
    volume numeric,
    raw_data jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT market_indicator_candle_unique_candle
        UNIQUE (source, symbol, interval_type, candle_time)
);

CREATE INDEX IF NOT EXISTS idx_market_indicator_candle_lookup
    ON public.market_indicator_candle (source, symbol, interval_type, candle_time DESC);

CREATE INDEX IF NOT EXISTS idx_market_indicator_candle_category_time
    ON public.market_indicator_candle (category, candle_time DESC);

CREATE TABLE IF NOT EXISTS public.collector_run_history (
    run_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source text NOT NULL,
    target text NOT NULL,
    status text NOT NULL CHECK (status IN ('SUCCESS', 'NO_DATA', 'FAILED')),
    fetched_rows integer NOT NULL DEFAULT 0,
    saved_rows integer NOT NULL DEFAULT 0,
    error_message text,
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    CONSTRAINT collector_run_history_row_check
        CHECK (fetched_rows >= 0 AND saved_rows >= 0)
);

CREATE INDEX IF NOT EXISTS idx_collector_run_history_target_time
    ON public.collector_run_history (source, target, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_collector_run_history_status_time
    ON public.collector_run_history (status, started_at DESC);

CREATE TABLE IF NOT EXISTS public.toss_stock_info
(
    symbol                    TEXT PRIMARY KEY,
    name                      TEXT NOT NULL,
    english_name              TEXT,
    isin_code                 TEXT,
    market                    TEXT,
    security_type             TEXT,
    is_common_share           BOOLEAN,
    status                    TEXT,
    currency                  TEXT,
    list_date                 DATE,
    delist_date               DATE,
    shares_outstanding        NUMERIC,
    leverage_factor           NUMERIC,
    liquidation_trading       BOOLEAN,
    nxt_supported             BOOLEAN,
    krx_trading_suspended     BOOLEAN,
    nxt_trading_suspended     BOOLEAN,
    raw_data                  JSONB NOT NULL,
    collected_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_toss_stock_info_status_market
    ON public.toss_stock_info (status, market);
