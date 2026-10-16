-- pattern-scan: quét live kịch bản Sell -> ảnh -> thông báo -> lệnh PAPER (không lệnh thật). Idempotent.
CREATE TABLE IF NOT EXISTS pattern_scan_events (
  id bigserial PRIMARY KEY,
  setup_id text NOT NULL,
  pattern text NOT NULL,
  symbol text NOT NULL,
  tf text NOT NULL,
  state text NOT NULL CHECK (state IN ('forming','armed','triggered','invalid')),
  score real NOT NULL DEFAULT 0,
  bar_ts timestamptz NOT NULL,
  ts timestamptz NOT NULL,
  levels jsonb NOT NULL DEFAULT '{}'::jsonb,
  steps jsonb NOT NULL DEFAULT '[]'::jsonb,
  reason text,
  points jsonb NOT NULL DEFAULT '[]'::jsonb,
  live boolean NOT NULL DEFAULT false,          -- nhận trong <= fresh_bars nến sau khi nến đóng (false = replay/bù)
  received_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (setup_id, symbol, tf, state)
);
CREATE INDEX IF NOT EXISTS pattern_scan_events_bar_ts_idx ON pattern_scan_events (bar_ts DESC);

CREATE TABLE IF NOT EXISTS pattern_scan_media (
  event_id bigint PRIMARY KEY REFERENCES pattern_scan_events(id),
  png bytea NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS pattern_paper_trades (
  id bigserial PRIMARY KEY,
  setup_id text NOT NULL, pattern text NOT NULL, symbol text NOT NULL, tf text NOT NULL,
  side text NOT NULL DEFAULT 'sell' CHECK (side = 'sell'),
  opened_at timestamptz NOT NULL,
  entry double precision NOT NULL, sl double precision NOT NULL, r double precision NOT NULL CHECK (r > 0),
  tp jsonb NOT NULL,
  status text NOT NULL CHECK (status IN ('open','closed')),
  closed_at timestamptz,
  legs jsonb NOT NULL,
  cost_r double precision NOT NULL DEFAULT 0,
  result_r double precision,
  mfe_r double precision NOT NULL DEFAULT 0, mae_r double precision NOT NULL DEFAULT 0,
  bars_held integer NOT NULL DEFAULT 0,
  last_bar_ts timestamptz NOT NULL,
  replay boolean NOT NULL DEFAULT false,
  open_hash text,
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (setup_id, symbol, tf)
);
CREATE INDEX IF NOT EXISTS pattern_paper_trades_status_idx ON pattern_paper_trades (status, opened_at DESC);

-- Sổ cái hash-chain chỉ-thêm: row hash = sha256(prev|kind|ref|json chuẩn hoá) (services/pattern-scan/src/pattern_scan/paper.py)
CREATE TABLE IF NOT EXISTS pattern_paper_ledger (
  seq bigserial PRIMARY KEY,
  kind text NOT NULL CHECK (kind IN ('open','close')),
  ref text NOT NULL,
  content jsonb NOT NULL,
  prev_hash text NOT NULL,
  hash text NOT NULL UNIQUE,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE OR REPLACE FUNCTION pattern_paper_ledger_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'pattern_paper_ledger là chỉ-thêm (append-only)'; END $$;
DROP TRIGGER IF EXISTS pattern_paper_ledger_no_mod ON pattern_paper_ledger;
CREATE TRIGGER pattern_paper_ledger_no_mod BEFORE UPDATE OR DELETE ON pattern_paper_ledger
  FOR EACH ROW EXECUTE FUNCTION pattern_paper_ledger_immutable();
-- Lệnh đã đóng không được sửa nữa
CREATE OR REPLACE FUNCTION pattern_paper_trades_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' OR OLD.status = 'closed' THEN RAISE EXCEPTION 'lệnh paper đã đóng là bất biến'; END IF;
  IF NEW.entry <> OLD.entry OR NEW.sl <> OLD.sl OR NEW.opened_at <> OLD.opened_at OR NEW.tp <> OLD.tp THEN
    RAISE EXCEPTION 'không được sửa thông số vào lệnh'; END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS pattern_paper_trades_guard ON pattern_paper_trades;
CREATE TRIGGER pattern_paper_trades_guard BEFORE UPDATE OR DELETE ON pattern_paper_trades
  FOR EACH ROW EXECUTE FUNCTION pattern_paper_trades_guard();

DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ts_ro') THEN
    GRANT SELECT ON pattern_scan_events, pattern_paper_trades, pattern_paper_ledger TO ts_ro;
  END IF;
END $$;
