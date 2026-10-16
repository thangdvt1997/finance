-- 013: backend cho ứng dụng client (docs/CLIENT_PLATFORM.md). Idempotent.
--  (1) cảnh báo cá nhân theo chủ sở hữu: alert_rules/alert_rule_events.owner_user_id (+ account_id)
--  (2) lệnh chờ theo tài khoản: account_orders (upsert theo (account_id, ticket); open -> removed khi biến mất khỏi snapshot)
--  (3) tiền tệ tài khoản: account_snapshots.currency
--  (4) Web Push: push_subscriptions (khoá + endpoint MÃ HOÁ Fernet ở tầng ứng dụng; chỉ role ts_userconf đọc/ghi)

-- (1)
ALTER TABLE alert_rules ADD COLUMN IF NOT EXISTS owner_user_id text;      -- NULL = quy tắc của master (toàn cục)
ALTER TABLE alert_rules ADD COLUMN IF NOT EXISTS account_id text;         -- tài khoản MT mà quy tắc gắn với (điều kiện margin/drawdown); NULL = không gắn
CREATE INDEX IF NOT EXISTS alert_rules_owner_idx ON alert_rules (owner_user_id) WHERE owner_user_id IS NOT NULL;
ALTER TABLE alert_rule_events ADD COLUMN IF NOT EXISTS owner_user_id text;
CREATE INDEX IF NOT EXISTS alert_rule_events_owner_idx ON alert_rule_events (owner_user_id, fired_at DESC) WHERE owner_user_id IS NOT NULL;

-- (2)
CREATE TABLE IF NOT EXISTS account_orders (
  account_id text NOT NULL,
  ticket text NOT NULL,
  platform text,
  symbol text NOT NULL DEFAULT '',
  broker_symbol text NOT NULL DEFAULT '',
  kind text NOT NULL DEFAULT 'other',          -- buy_limit|sell_limit|buy_stop|sell_stop|other
  volume double precision,
  price double precision,
  sl double precision,
  tp double precision,
  magic bigint,
  comment text,
  time_setup timestamptz,
  status text NOT NULL DEFAULT 'open' CHECK (status IN ('open','removed')),
  first_seen_at timestamptz NOT NULL DEFAULT now(),
  last_seen_at timestamptz NOT NULL,           -- mốc (giờ sự kiện) snapshot cuối cùng còn thấy lệnh này
  removed_at timestamptz,
  PRIMARY KEY (account_id, ticket)
);
CREATE INDEX IF NOT EXISTS account_orders_open_idx ON account_orders (account_id) WHERE status = 'open';

-- (3)
ALTER TABLE account_snapshots ADD COLUMN IF NOT EXISTS currency text;

-- (4)
CREATE TABLE IF NOT EXISTS push_subscriptions (
  id bigserial PRIMARY KEY,
  owner_user_id text NOT NULL,
  endpoint_hash text NOT NULL UNIQUE,          -- sha256(endpoint): chống trùng + huỷ theo endpoint
  endpoint_enc text NOT NULL,                  -- Fernet(PUSH_ENC_KEY)
  p256dh_enc text NOT NULL,
  auth_enc text NOT NULL,
  user_agent text,
  created_at timestamptz NOT NULL DEFAULT now(),
  last_ok_at timestamptz,
  last_error_at timestamptz,
  fail_count integer NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS push_subscriptions_owner_idx ON push_subscriptions (owner_user_id);

DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ts_ro') THEN
    GRANT SELECT ON account_orders TO ts_ro;
    REVOKE ALL ON push_subscriptions FROM ts_ro;     -- default privileges cấp SELECT mọi bảng mới: thu hồi, dịch vụ khác không cần đọc
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ts_writer') THEN
    GRANT SELECT, INSERT, UPDATE ON account_orders TO ts_writer;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ts_userconf') THEN
    GRANT SELECT, INSERT, UPDATE, DELETE ON push_subscriptions TO ts_userconf;
    GRANT USAGE, SELECT ON SEQUENCE push_subscriptions_id_seq TO ts_userconf;
  END IF;
END $$;
