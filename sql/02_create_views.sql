CREATE OR REPLACE VIEW public.toss_chart_candle_1m_tableau AS
SELECT
    id,
    market_type,
    product_code,
    product_symbol,
    product_name,
    chart_range,
    candle_time,
    candle_time::timestamptz AS candle_time_ts,
    base_price,
    open_price,
    high_price,
    low_price,
    close_price,
    volume,
    amount,
    exchange_rate,
    created_at,
    updated_at
FROM public.toss_chart_candle
WHERE chart_range = 'min:1';

CREATE OR REPLACE VIEW public.market_indicator_candle_1m_tableau AS
SELECT
    id,
    source,
    market,
    category,
    symbol,
    name,
    interval_type,
    candle_time,
    candle_time AT TIME ZONE 'Asia/Seoul' AS candle_time_kst,
    open_price,
    high_price,
    low_price,
    close_price,
    volume,
    created_at,
    updated_at
FROM public.market_indicator_candle
WHERE interval_type = '1m';

CREATE OR REPLACE VIEW public.collector_latest_status AS
SELECT DISTINCT ON (source, target)
    source,
    target,
    status,
    fetched_rows,
    saved_rows,
    error_message,
    started_at,
    finished_at
FROM public.collector_run_history
ORDER BY source, target, started_at DESC;
