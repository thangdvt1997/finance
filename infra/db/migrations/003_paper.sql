-- paper-trader: journal giao dịch MÔ PHỎNG (KHÔNG tiền thật). Idempotent. Chạy bằng superuser/owner (create_paper_role.sh).
-- Journal append-only: paper_events / paper_fills / paper_equity cấm UPDATE/DELETE (trigger); paper_orders chỉ đổi status/reason.
CREATE TABLE IF NOT EXISTS paper_accounts (
  account_id text PRIMARY KEY,
  name text NOT NULL,
  strategy text NOT NULL,
  base_ccy text NOT NULL,
  initial_capital double precision NOT NULL,
  benchmark_id text,
  meaningful boolean NOT NULL DEFAULT true,
  status text NOT NULL DEFAULT 'active',            -- active | halted | locked
  halt_reason text DEFAULT '',
  halt_until timestamptz,
  cash double precision NOT NULL,
  last_close timestamptz,                           -- đóng cửa bar đã xử lý gần nhất
  config jsonb NOT NULL DEFAULT '{}'::jsonb,
  state jsonb NOT NULL DEFAULT '{}'::jsonb,         -- trạng thái engine (khôi phục sau restart)
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS paper_orders (
  client_order_id text PRIMARY KEY,                 -- idempotency: <account>:<decision_close>:<symbol>
  account_id text NOT NULL REFERENCES paper_accounts(account_id),
  symbol text NOT NULL,
  side text NOT NULL CHECK (side IN ('buy','sell')),
  qty double precision NOT NULL CHECK (qty > 0),
  kind text NOT NULL DEFAULT 'rebalance',
  status text NOT NULL DEFAULT 'pending',           -- pending | filled | rejected | cancelled | expired
  reason text DEFAULT '',
  target_weight double precision,
  ref_price double precision,
  decision_ts timestamptz NOT NULL,
  eligible_from timestamptz NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS paper_orders_acct_idx ON paper_orders (account_id, decision_ts DESC);

CREATE TABLE IF NOT EXISTS paper_fills (
  fill_id bigserial PRIMARY KEY,
  client_order_id text NOT NULL UNIQUE REFERENCES paper_orders(client_order_id),
  account_id text NOT NULL,
  symbol text NOT NULL,
  side text NOT NULL,
  qty double precision NOT NULL,
  ts timestamptz NOT NULL,                          -- ts_open của bar khớp
  ref_price double precision NOT NULL,              -- giá mở cửa (mid)
  price double precision NOT NULL,                  -- giá khớp (đã gồm spread + trượt giá)
  spread_cost double precision NOT NULL DEFAULT 0,
  slippage_cost double precision NOT NULL DEFAULT 0,
  commission double precision NOT NULL DEFAULT 0,
  tax double precision NOT NULL DEFAULT 0,
  realized_pnl double precision NOT NULL DEFAULT 0,
  q2b double precision NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS paper_fills_acct_idx ON paper_fills (account_id, ts DESC);

CREATE TABLE IF NOT EXISTS paper_positions (
  account_id text NOT NULL,
  symbol text NOT NULL,
  qty double precision NOT NULL,
  avg_price double precision NOT NULL,
  mark_price double precision,
  unrealized_pnl double precision,
  notional double precision,
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (account_id, symbol)
);

CREATE TABLE IF NOT EXISTS paper_equity (
  account_id text NOT NULL,
  ts timestamptz NOT NULL,                          -- đóng cửa bar được định giá
  equity double precision NOT NULL,
  cash double precision,
  gross_exposure double precision,
  net_exposure double precision,
  drawdown double precision,
  swap_cost double precision DEFAULT 0,
  PRIMARY KEY (account_id, ts)
);
SELECT create_hypertable('paper_equity', 'ts', if_not_exists => TRUE);

CREATE TABLE IF NOT EXISTS paper_events (
  id bigserial PRIMARY KEY,
  account_id text NOT NULL,
  ts timestamptz NOT NULL,
  type text NOT NULL,                               -- account_started | rebalance | fill | risk_reject | warmup | kill_switch | halt_released | ...
  severity text NOT NULL DEFAULT 'info',
  message text NOT NULL,
  data jsonb NOT NULL DEFAULT '{}'::jsonb,
  event_key text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (account_id, event_key)
);
CREATE INDEX IF NOT EXISTS paper_events_ts_idx ON paper_events (ts DESC);

-- Bất biến
CREATE OR REPLACE FUNCTION paper_block_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'paper journal là append-only: % không được % ', TG_TABLE_NAME, TG_OP; END $$;

CREATE OR REPLACE FUNCTION paper_orders_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'paper_orders không được xoá'; END IF;
  IF (NEW.client_order_id, NEW.account_id, NEW.symbol, NEW.side, NEW.qty, NEW.kind, NEW.decision_ts, NEW.eligible_from)
     IS DISTINCT FROM (OLD.client_order_id, OLD.account_id, OLD.symbol, OLD.side, OLD.qty, OLD.kind, OLD.decision_ts, OLD.eligible_from) THEN
    RAISE EXCEPTION 'paper_orders: chỉ được đổi status/reason';
  END IF;
  NEW.updated_at := now();
  RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS paper_events_immutable ON paper_events;
CREATE TRIGGER paper_events_immutable BEFORE UPDATE OR DELETE ON paper_events FOR EACH ROW EXECUTE FUNCTION paper_block_mutation();
DROP TRIGGER IF EXISTS paper_fills_immutable ON paper_fills;
CREATE TRIGGER paper_fills_immutable BEFORE UPDATE OR DELETE ON paper_fills FOR EACH ROW EXECUTE FUNCTION paper_block_mutation();
DROP TRIGGER IF EXISTS paper_equity_immutable ON paper_equity;
CREATE TRIGGER paper_equity_immutable BEFORE UPDATE OR DELETE ON paper_equity FOR EACH ROW EXECUTE FUNCTION paper_block_mutation();
DROP TRIGGER IF EXISTS paper_orders_guard_trg ON paper_orders;
CREATE TRIGGER paper_orders_guard_trg BEFORE UPDATE OR DELETE ON paper_orders FOR EACH ROW EXECUTE FUNCTION paper_orders_guard();

-- Đọc: role chỉ-đọc ts_ro (api-gateway/Grafana) nếu đã tạo.
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ts_ro') THEN
    GRANT SELECT ON paper_accounts, paper_orders, paper_fills, paper_positions, paper_equity, paper_events TO ts_ro;
  END IF;
END $$;
