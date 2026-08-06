SET ROLE appuser;

BEGIN;

CREATE TABLE IF NOT EXISTS public.market_news
(
    news_id          TEXT        NOT NULL,
    title            TEXT        NOT NULL,
    summary          TEXT,
    publisher        TEXT,
    news_type        TEXT,
    related_stocks   JSONB       NOT NULL DEFAULT '[]'::jsonb,
    nation           TEXT,
    created_at       TIMESTAMPTZ NOT NULL,
    collected_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT market_news_pk
        PRIMARY KEY (news_id)
);

CREATE INDEX IF NOT EXISTS idx_market_news_created_at
    ON public.market_news (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_market_news_publisher
    ON public.market_news (publisher);

CREATE INDEX IF NOT EXISTS idx_market_news_news_type
    ON public.market_news (news_type);

CREATE INDEX IF NOT EXISTS idx_market_news_nation
    ON public.market_news (nation);

CREATE INDEX IF NOT EXISTS idx_market_news_related_stocks_gin
    ON public.market_news
    USING GIN (related_stocks);

CREATE TABLE IF NOT EXISTS public.market_news_detail
(
    news_id              TEXT        NOT NULL,
    language             TEXT,
    summary_sentences    JSONB       NOT NULL DEFAULT '[]'::jsonb,
    sentiment            TEXT,
    content              TEXT        NOT NULL DEFAULT '',
    source_code          TEXT,
    source_name          TEXT,
    writers              JSONB       NOT NULL DEFAULT '[]'::jsonb,
    stock_codes          JSONB       NOT NULL DEFAULT '[]'::jsonb,
    company_codes        JSONB       NOT NULL DEFAULT '[]'::jsonb,
    link_url             TEXT,
    created_at           TIMESTAMPTZ,
    updated_at           TIMESTAMPTZ,
    collected_at         TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT market_news_detail_pk
        PRIMARY KEY (news_id),

    CONSTRAINT market_news_detail_news_fk
        FOREIGN KEY (news_id)
        REFERENCES public.market_news (news_id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_market_news_detail_created_at
    ON public.market_news_detail (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_market_news_detail_source_code
    ON public.market_news_detail (source_code);

CREATE INDEX IF NOT EXISTS idx_market_news_detail_stock_codes_gin
    ON public.market_news_detail
    USING GIN (stock_codes);

CREATE INDEX IF NOT EXISTS idx_market_news_detail_company_codes_gin
    ON public.market_news_detail
    USING GIN (company_codes);

CREATE INDEX IF NOT EXISTS idx_market_news_detail_writers_gin
    ON public.market_news_detail
    USING GIN (writers);

CREATE INDEX IF NOT EXISTS idx_market_news_detail_summary_sentences_gin
    ON public.market_news_detail
    USING GIN (summary_sentences);

COMMIT;