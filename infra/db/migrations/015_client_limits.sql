-- 015: giới hạn/mục tiêu do client đặt + trung tâm thông báo + cài đặt đồng bộ thiết bị + báo quản trị (ticket). Idempotent.
-- Chủ sở hữu duy nhất: alert-rules (role ts_userconf). Dữ liệu cá nhân -> THU HỒI ts_ro (default privileges cấp SELECT mọi bảng mới).
-- READ-ONLY về giao dịch: giới hạn chỉ để NHẮC/hiển thị tiến độ, không chặn/đặt lệnh.

-- (1) giới hạn theo (chủ, tài khoản, khoá). Siết chặt = áp ngay; nới lỏng/xoá = pending 24 giờ (pending_* + pending_effective_at).
CREATE TABLE IF NOT EXISTS user_limits (
  owner_user_id text NOT NULL,
  account_id text NOT NULL,
  key text NOT NULL CHECK (key IN ('daily_loss_pct','max_dd_pct','min_margin_level','max_orders_day','monthly_target_pct')),
  value double precision NOT NULL,
  pending_value double precision,
  pending_remove boolean NOT NULL DEFAULT false,
  pending_effective_at timestamptz,
  inactive boolean NOT NULL DEFAULT false,      -- tài khoản không còn thuộc chủ: bỏ qua đánh giá/nhắc
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (owner_user_id, account_id, key)
);
CREATE INDEX IF NOT EXISTS user_limits_pending_idx ON user_limits (pending_effective_at) WHERE pending_effective_at IS NOT NULL;

CREATE TABLE IF NOT EXISTS user_limit_history (
  id bigserial PRIMARY KEY,
  owner_user_id text NOT NULL,
  account_id text NOT NULL,
  key text NOT NULL,
  ts timestamptz NOT NULL DEFAULT now(),
  actor_user_id text,
  actor_role text,
  old_value double precision,
  new_value double precision,                   -- NULL = xoá giới hạn
  applied text NOT NULL CHECK (applied IN ('now','pending','cancelled','matured')),
  effective_at timestamptz
);
CREATE INDEX IF NOT EXISTS user_limit_history_idx ON user_limit_history (owner_user_id, account_id, id DESC);

-- ngưỡng nhắc đã gửi trong chu kỳ (ngày|tháng): mỗi ngưỡng 1 lần/chu kỳ
CREATE TABLE IF NOT EXISTS user_limit_alerts (
  owner_user_id text NOT NULL,
  account_id text NOT NULL,
  key text NOT NULL,
  cycle text NOT NULL,                          -- 2026-10-12 | 2026-10
  threshold smallint NOT NULL,                  -- 70 | 90 | 100
  sent_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (owner_user_id, account_id, key, cycle, threshold)
);

-- (2) thông báo
CREATE TABLE IF NOT EXISTS user_notifications (
  id bigserial PRIMARY KEY,
  owner_user_id text NOT NULL,
  kind text NOT NULL CHECK (kind IN ('rule','limit','report','briefing','support','system')),
  severity text NOT NULL DEFAULT 'info' CHECK (severity IN ('info','warn','danger')),
  title text NOT NULL,
  body text NOT NULL DEFAULT '',
  account_id text,
  link text,
  ts timestamptz NOT NULL DEFAULT now(),
  read_at timestamptz,
  dedupe_key text
);
CREATE INDEX IF NOT EXISTS user_notifications_owner_idx ON user_notifications (owner_user_id, id DESC);
CREATE INDEX IF NOT EXISTS user_notifications_unread_idx ON user_notifications (owner_user_id) WHERE read_at IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS user_notifications_dedupe_idx ON user_notifications (owner_user_id, dedupe_key) WHERE dedupe_key IS NOT NULL;

-- (3) cài đặt client đồng bộ thiết bị (lạc quan theo rev)
CREATE TABLE IF NOT EXISTS client_prefs (
  owner_user_id text PRIMARY KEY,
  rev integer NOT NULL DEFAULT 1,
  data jsonb NOT NULL DEFAULT '{}'::jsonb,
  updated_at timestamptz NOT NULL DEFAULT now()
);

-- (4) ticket báo quản trị
CREATE TABLE IF NOT EXISTS user_tickets (
  id bigserial PRIMARY KEY,
  owner_user_id text NOT NULL,
  account_id text,
  category text NOT NULL CHECK (category IN ('ea_disconnected','stale_data','wrong_data','other')),
  message text NOT NULL DEFAULT '',
  context jsonb NOT NULL DEFAULT '{}'::jsonb,
  status text NOT NULL DEFAULT 'open' CHECK (status IN ('open','ack','resolved')),
  reply text,
  handled_by text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS user_tickets_owner_idx ON user_tickets (owner_user_id, id DESC);
CREATE INDEX IF NOT EXISTS user_tickets_open_idx ON user_tickets (status, id DESC);

DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ts_ro') THEN
    REVOKE ALL ON user_limits, user_limit_history, user_limit_alerts, user_notifications, client_prefs, user_tickets FROM ts_ro;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ts_userconf') THEN
    GRANT SELECT, INSERT, UPDATE, DELETE ON user_limits, user_limit_alerts, user_notifications, client_prefs TO ts_userconf;
    GRANT SELECT, INSERT ON user_limit_history TO ts_userconf;
    GRANT SELECT, INSERT, UPDATE ON user_tickets TO ts_userconf;
    GRANT USAGE, SELECT ON SEQUENCE user_limit_history_id_seq, user_notifications_id_seq, user_tickets_id_seq TO ts_userconf;
  END IF;
END $$;
