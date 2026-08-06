BEGIN;

ALTER TABLE public.symbol_master
    ADD COLUMN IF NOT EXISTS held_in_account BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS managed_by_holdings BOOLEAN NOT NULL DEFAULT false;

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

COMMIT;
