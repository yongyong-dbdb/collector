BEGIN;

CREATE TABLE IF NOT EXISTS public.symbol_master
(
    symbol_id              BIGINT GENERATED ALWAYS AS IDENTITY,
    source                 VARCHAR(20)  NOT NULL,
    market                 VARCHAR(30)  NOT NULL,
    category               VARCHAR(50)  NOT NULL,
    symbol                 VARCHAR(100) NOT NULL,
    name                   VARCHAR(200) NOT NULL,
    source_code            VARCHAR(200),
    market_type            VARCHAR(30),
    interval_type          VARCHAR(20)  NOT NULL DEFAULT '1m',
    chart_range            VARCHAR(20)  NOT NULL DEFAULT 'day',
    recent_candle_count    INTEGER      NOT NULL DEFAULT 20,
    collection_priority    INTEGER      NOT NULL DEFAULT 100,
    collection_enabled     BOOLEAN      NOT NULL DEFAULT true,
    created_at             TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at             TIMESTAMPTZ  NOT NULL DEFAULT now(),

    CONSTRAINT symbol_master_pk
        PRIMARY KEY (symbol_id),

    CONSTRAINT symbol_master_source_symbol_uk
        UNIQUE (source, symbol),

    CONSTRAINT symbol_master_recent_candle_count_ck
        CHECK (recent_candle_count > 0),

    CONSTRAINT symbol_master_collection_priority_ck
        CHECK (collection_priority >= 0)
);

CREATE INDEX IF NOT EXISTS idx_symbol_master_collect
    ON public.symbol_master
    (
        source,
        collection_enabled,
        collection_priority,
        symbol_id
    );

COMMENT ON TABLE public.symbol_master IS
    'Collector 수집 대상 심볼 관리 테이블';

COMMENT ON COLUMN public.symbol_master.source IS
    '데이터 제공처: TOSS, YAHOO';

COMMENT ON COLUMN public.symbol_master.source_code IS
    '각 데이터 제공처 API 요청에 사용하는 실제 코드';

COMMENT ON COLUMN public.symbol_master.market_type IS
    'Toss API 시장 구분값: kr-s, us-s 등';

COMMENT ON COLUMN public.symbol_master.interval_type IS
    '수집 주기: 1m, 5m 등';

COMMENT ON COLUMN public.symbol_master.chart_range IS
    'API 차트 조회 범위';

COMMENT ON COLUMN public.symbol_master.recent_candle_count IS
    '한 번의 API 요청에서 가져올 최근 캔들 수';

COMMENT ON COLUMN public.symbol_master.collection_priority IS
    '낮은 값부터 먼저 수집';

COMMENT ON COLUMN public.symbol_master.collection_enabled IS
    '수집 활성화 여부';

INSERT INTO public.symbol_master
(
    source,
    market,
    category,
    symbol,
    name,
    source_code,
    market_type,
    interval_type,
    chart_range,
    recent_candle_count,
    collection_priority,
    collection_enabled
)
VALUES
    (
        'TOSS',
        'KR',
        'STOCK',
        'A005930',
        '삼성전자',
        '005930',
        'kr-s',
        '1m',
        'day',
        21,
        10,
        true
    ),
    (
        'TOSS',
        'KR',
        'STOCK',
        'A000660',
        'SK하이닉스',
        '000660',
        'kr-s',
        '1m',
        'day',
        21,
        20,
        true
    ),
    (
        'YAHOO',
        'US',
        'INDEX',
        '^IXIC',
        'NASDAQ Composite',
        '^IXIC',
        NULL,
        '1m',
        '1d',
        20,
        100,
        true
    ),
    (
        'YAHOO',
        'US',
        'INDEX',
        '^GSPC',
        'S&P 500',
        '^GSPC',
        NULL,
        '1m',
        '1d',
        20,
        110,
        true
    ),
    (
        'YAHOO',
        'US',
        'VOLATILITY',
        '^VIX',
        'CBOE Volatility Index',
        '^VIX',
        NULL,
        '1m',
        '1d',
        20,
        120,
        true
    ),
    (
        'YAHOO',
        'US',
        'FUTURES',
        'NQ=F',
        'NASDAQ 100 Futures',
        'NQ=F',
        NULL,
        '1m',
        '1d',
        20,
        130,
        true
    ),
    (
        'YAHOO',
        'US',
        'INDEX',
        '^DJI',
        'Dow Jones Industrial Average',
        '^DJI',
        NULL,
        '1m',
        '1d',
        20,
        140,
        true
    ),
    (
        'YAHOO',
        'KR',
        'INDEX',
        '^KS11',
        'KOSPI',
        '^KS11',
        NULL,
        '1m',
        '1d',
        20,
        150,
        true
    ),
    (
        'YAHOO',
        'US',
        'SEMICONDUCTOR',
        '^SOX',
        'Philadelphia Semiconductor Index',
        '^SOX',
        NULL,
        '1m',
        '1d',
        20,
        160,
        true
    ),
    (
        'YAHOO',
        'GLOBAL',
        'COMMODITY',
        'GC=F',
        'Gold Futures',
        'GC=F',
        NULL,
        '1m',
        '1d',
        20,
        170,
        true
    ),
    (
        'YAHOO',
        'KR',
        'FX',
        'KRW=X',
        'USD/KRW',
        'KRW=X',
        NULL,
        '1m',
        '1d',
        20,
        180,
        true
    )
ON CONFLICT (source, symbol)
DO UPDATE
SET
    market                 = EXCLUDED.market,
    category               = EXCLUDED.category,
    name                   = EXCLUDED.name,
    source_code            = EXCLUDED.source_code,
    market_type            = EXCLUDED.market_type,
    interval_type          = EXCLUDED.interval_type,
    chart_range            = EXCLUDED.chart_range,
    recent_candle_count    = EXCLUDED.recent_candle_count,
    collection_priority    = EXCLUDED.collection_priority,
    collection_enabled     = EXCLUDED.collection_enabled,
    updated_at             = now();

COMMIT;
