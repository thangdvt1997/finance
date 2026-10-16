-- Snapshot phân tích kỹ thuật do service `analytics` tính (xem services/analytics/README.md). Idempotent.
-- kind: summary | detail (key 'SYMBOL:TF') | correlation (key = TF) | sessions (key = SYMBOL)
CREATE TABLE IF NOT EXISTS analytics_snapshots (
  kind text NOT NULL,
  key text NOT NULL,
  ts timestamptz NOT NULL DEFAULT now(),
  payload jsonb NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (kind, key)
);
CREATE INDEX IF NOT EXISTS analytics_snapshots_symbol_idx ON analytics_snapshots (kind, (payload->>'symbol'));
-- api-gateway đọc bằng role chỉ-đọc ts_ro (nếu đã tạo; ALTER DEFAULT PRIVILEGES của create_readonly_role.sh chỉ phủ bảng do user ts tạo sau đó).
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ts_ro') THEN
    GRANT SELECT ON analytics_snapshots TO ts_ro;
  END IF;
END $$;
