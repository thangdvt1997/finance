-- TimescaleDB/Postgres schema. Idempotent (IF NOT EXISTS). Upsert theo khóa tự nhiên.
CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS bars (
  symbol text NOT NULL, tf text NOT NULL, ts_open timestamptz NOT NULL,
  o double precision NOT NULL, h double precision NOT NULL, l double precision NOT NULL, c double precision NOT NULL,
  v double precision DEFAULT 0, source text NOT NULL,
  PRIMARY KEY (symbol, tf, ts_open, source)
);
SELECT create_hypertable('bars', 'ts_open', if_not_exists => TRUE);

CREATE TABLE IF NOT EXISTS quotes (
  symbol text NOT NULL, ts timestamptz NOT NULL, bid double precision, ask double precision, source text NOT NULL,
  PRIMARY KEY (symbol, ts, source)
);
SELECT create_hypertable('quotes', 'ts', if_not_exists => TRUE);

CREATE TABLE IF NOT EXISTS news_items (
  url text PRIMARY KEY, title text NOT NULL, summary text, published_at timestamptz, source text NOT NULL,
  lang text, symbols text[] DEFAULT '{}', sentiment double precision, event_id text, ingested_at timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS news_pub_idx ON news_items (published_at DESC);

CREATE TABLE IF NOT EXISTS calendar_events (
  event_id text NOT NULL, source text NOT NULL, country text, title text NOT NULL, impact text, ts timestamptz NOT NULL,
  forecast text, previous text, actual text, updated_at timestamptz DEFAULT now(),
  extra jsonb,  -- migration 003: group, forecast_source/actual_source, surprise
  PRIMARY KEY (event_id, source)
);
CREATE INDEX IF NOT EXISTS cal_ts_idx ON calendar_events (ts);

CREATE TABLE IF NOT EXISTS experts (
  expert_id text PRIMARY KEY, source text NOT NULL, display_name text, url text, reputation jsonb DEFAULT '{}'::jsonb,
  tracked boolean DEFAULT true, created_at timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS expert_signals (
  expert_id text NOT NULL, source text NOT NULL, symbol text NOT NULL, side text NOT NULL, opened_at timestamptz NOT NULL,
  entry double precision, sl double precision, tp double precision, status text DEFAULT 'open', url text, raw jsonb,
  updated_at timestamptz DEFAULT now(),
  PRIMARY KEY (expert_id, source, symbol, opened_at, side)
);

CREATE TABLE IF NOT EXISTS expert_positions (
  expert_id text NOT NULL, source text NOT NULL, symbol text NOT NULL, as_of timestamptz NOT NULL,
  net_volume double precision, avg_price double precision, raw jsonb,
  PRIMARY KEY (expert_id, source, symbol, as_of)
);

CREATE TABLE IF NOT EXISTS account_snapshots (
  account_id text NOT NULL, platform text NOT NULL, ts timestamptz NOT NULL,
  balance double precision, equity double precision, margin double precision, positions jsonb DEFAULT '[]'::jsonb,
  PRIMARY KEY (account_id, ts)
);
SELECT create_hypertable('account_snapshots', 'ts', if_not_exists => TRUE);

CREATE TABLE IF NOT EXISTS alerts (
  id bigserial PRIMARY KEY, ts timestamptz DEFAULT now(), level text NOT NULL, title text NOT NULL, body text,
  tags text[] DEFAULT '{}', dedupe_key text, delivered boolean DEFAULT false
);
CREATE INDEX IF NOT EXISTS alerts_ts_idx ON alerts (ts DESC);
