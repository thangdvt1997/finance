-- Nhat ky giao dich: lich su deal DA DONG tu MT4/MT5 (EA -> mt-bridge -> account.deals -> storage-writer) + ghi chu/tag thu cong. Idempotent.
-- READ-ONLY ve giao dich: bang chi luu lich su da xay ra, khong co duong dat/sua/dong lenh.
CREATE TABLE IF NOT EXISTS account_deals (
  account_id text NOT NULL,
  ticket text NOT NULL,                              -- MT4: ticket lenh; MT5: ticket deal DONG (OUT)
  position_id text NOT NULL,
  platform text NOT NULL,
  symbol text NOT NULL DEFAULT '',                   -- chuan hoa (EURUSD); rong khi side='balance'
  broker_symbol text NOT NULL DEFAULT '',
  side text NOT NULL CHECK (side IN ('buy','sell','balance')),   -- huong cua vi the da dong
  volume double precision NOT NULL DEFAULT 0,
  price_open double precision,
  price_close double precision,
  sl double precision,
  tp double precision,
  time_open timestamptz,
  time_close timestamptz NOT NULL,
  profit double precision NOT NULL DEFAULT 0,
  swap double precision NOT NULL DEFAULT 0,
  commission double precision NOT NULL DEFAULT 0,
  magic bigint NOT NULL DEFAULT 0,
  comment text NOT NULL DEFAULT '',
  reason text NOT NULL DEFAULT '',                   -- sl | tp | so | expert | client | ''
  source text NOT NULL DEFAULT 'mt',                 -- vd mt5:demo-mt5-01
  ingested_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (account_id, ticket)
);
CREATE INDEX IF NOT EXISTS account_deals_time_idx ON account_deals (account_id, time_close DESC);
CREATE INDEX IF NOT EXISTS account_deals_symbol_idx ON account_deals (account_id, symbol, time_close DESC);

-- Ghi chu/tag thu cong cho deal hoac ky review (tuan/ngay). Ghi CHI qua service journal bang role ts_journal.
CREATE TABLE IF NOT EXISTS journal_notes (
  account_id text NOT NULL,
  kind text NOT NULL CHECK (kind IN ('deal','week','day')),
  ref text NOT NULL,                                 -- deal: ticket; week: 2026-W41; day: 2026-10-12
  tags text[] NOT NULL DEFAULT '{}',                 -- vd setup:breakout, emo:fomo, mistake:early-exit
  note text NOT NULL DEFAULT '',
  rating smallint CHECK (rating BETWEEN 1 AND 5),    -- chat luong setup/ky luat tu cham (tuy chon)
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (account_id, kind, ref)
);
CREATE INDEX IF NOT EXISTS journal_notes_tags_idx ON journal_notes USING gin (tags);

DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ts_ro') THEN
    GRANT SELECT ON account_deals, journal_notes TO ts_ro;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ts_writer') THEN
    GRANT SELECT, INSERT, UPDATE ON account_deals TO ts_writer;
  END IF;
END $$;
