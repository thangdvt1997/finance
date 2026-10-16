-- Track record chuyên gia/nguồn ý kiến (service track-record). Idempotent. Chỉ dữ liệu phái sinh; KHÔNG chứa tên nguồn/website.
-- tr_views: sổ cái BẤT BIẾN (hash-chain): trigger chặn UPDATE/DELETE/TRUNCATE; role ts_trackrec chỉ INSERT/SELECT.
CREATE TABLE IF NOT EXISTS tr_entities (
  entity_id text PRIMARY KEY,                       -- 'ent:<hash8>' ổn định
  label text NOT NULL,                              -- nhãn trung lập hiển thị được
  kind text NOT NULL CHECK (kind IN ('analyst','central_bank','media','positioning','signal_provider','other')),
  lang text NOT NULL DEFAULT 'other' CHECK (lang IN ('vi','en','other')),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tr_views (
  seq bigint PRIMARY KEY,                           -- tuần tự do service gán dưới advisory lock
  view_id text NOT NULL UNIQUE,
  ref text NOT NULL UNIQUE,                         -- khoá nguồn băm (idempotent)
  entity_id text NOT NULL,
  symbol text NOT NULL,
  direction text NOT NULL CHECK (direction IN ('bullish','bearish')),
  published_at timestamptz NOT NULL,
  observed_at timestamptz NOT NULL,
  invalidation double precision,
  horizon_hint text,
  basis text NOT NULL CHECK (basis IN ('news','signal','cot')),
  recorded_at timestamptz NOT NULL,
  prev_hash text NOT NULL,
  hash text NOT NULL
);
CREATE INDEX IF NOT EXISTS tr_views_entity_idx ON tr_views (entity_id, observed_at);
CREATE INDEX IF NOT EXISTS tr_views_obs_idx ON tr_views (observed_at DESC);

CREATE OR REPLACE FUNCTION tr_views_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'tr_views là sổ cái bất biến (append-only): % bị chặn', TG_OP; END $$;
DROP TRIGGER IF EXISTS tr_views_no_update ON tr_views;
CREATE TRIGGER tr_views_no_update BEFORE UPDATE OR DELETE ON tr_views FOR EACH ROW EXECUTE FUNCTION tr_views_immutable();
DROP TRIGGER IF EXISTS tr_views_no_truncate ON tr_views;
CREATE TRIGGER tr_views_no_truncate BEFORE TRUNCATE ON tr_views FOR EACH STATEMENT EXECUTE FUNCTION tr_views_immutable();

CREATE TABLE IF NOT EXISTS tr_outcomes (
  view_id text NOT NULL,
  horizon text NOT NULL CHECK (horizon IN ('1D','1W','1M')),
  entry_ts timestamptz NOT NULL,
  entry_px double precision NOT NULL,
  exit_ts timestamptz NOT NULL,
  exit_px double precision NOT NULL,
  ret_log double precision NOT NULL,                -- ln(exit/entry) của tài sản (chưa nhân hướng)
  hit boolean NOT NULL,
  regime text,
  computed_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (view_id, horizon)
);

CREATE TABLE IF NOT EXISTS tr_scorecards (
  entity_id text NOT NULL,
  scope text NOT NULL,
  horizon text NOT NULL,
  n integer NOT NULL,
  n_total integer NOT NULL,
  status text NOT NULL,
  stats jsonb NOT NULL,
  computed_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (entity_id, scope, horizon)
);

CREATE TABLE IF NOT EXISTS tr_runs (
  id bigserial PRIMARY KEY,
  started_at timestamptz NOT NULL,
  finished_at timestamptz,
  n_views integer, n_new_views integer, n_outcomes integer, n_tests integer, n_rated integer, n_beating integer,
  seconds double precision,
  note jsonb
);
