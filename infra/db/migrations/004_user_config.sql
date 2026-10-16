-- alert-rules: cảnh báo do người dùng tự đặt + tuỳ chọn giao diện (watchlist/layout) lưu phía server. Idempotent.
-- Một người dùng admin (user_prefs.user_id = 'admin'). Ghi bằng role hạn chế ts_userconf (create_userconf_role.sh).
CREATE TABLE IF NOT EXISTS alert_rules (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL,
  enabled boolean NOT NULL DEFAULT true,
  spec jsonb NOT NULL,                        -- logic, conditions[], mode, cooldown_min, level, channels[], note
  expires_at timestamptz,
  once_done boolean NOT NULL DEFAULT false,   -- mode=once đã kích hoạt
  last_fired_at timestamptz,
  fire_count integer NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS alert_rules_enabled_idx ON alert_rules (enabled) WHERE enabled;

-- Lịch sử kích hoạt: giữ lại cả khi quy tắc bị xoá (không FK).
CREATE TABLE IF NOT EXISTS alert_rule_events (
  id bigserial PRIMARY KEY,
  rule_id uuid NOT NULL,
  rule_name text NOT NULL,
  fired_at timestamptz NOT NULL DEFAULT now(),
  level text NOT NULL,
  title text NOT NULL,
  body text,
  snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
  channels text[] NOT NULL DEFAULT '{}',
  alert_event_id text,                        -- id sự kiện trên alerts.out (khớp alerts.delivery)
  delivered boolean
);
CREATE INDEX IF NOT EXISTS alert_rule_events_rule_idx ON alert_rule_events (rule_id, fired_at DESC);
CREATE INDEX IF NOT EXISTS alert_rule_events_time_idx ON alert_rule_events (fired_at DESC);

CREATE TABLE IF NOT EXISTS user_prefs (
  user_id text PRIMARY KEY,
  rev integer NOT NULL DEFAULT 1,
  prefs jsonb NOT NULL DEFAULT '{}'::jsonb,
  updated_at timestamptz NOT NULL DEFAULT now()
);

DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ts_ro') THEN
    GRANT SELECT ON alert_rules, alert_rule_events, user_prefs TO ts_ro;
  END IF;
END $$;
