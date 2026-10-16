-- Dang nhap master/client (service `auth`, docs/AUTH.md + docs/CLIENT_PLATFORM.md). Idempotent. Role ghi: ts_auth (create_auth_role.sh).
-- KHONG luu mat khau giao dich/investor MT. Passcode/pairing/token: chi luu BAM (argon2id / sha256); HMAC secret luu MA HOA (Fernet) vi bridge can gia tri goc.
CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- gen_random_uuid() (PG13+ da co san; giu cho an toan)

CREATE TABLE IF NOT EXISTS portal_users (
  user_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  role text NOT NULL CHECK (role IN ('master','client')),
  login_key text NOT NULL UNIQUE,                    -- master: master:<ten>; client: <platform>:<login> (tai khoan MT chinh)
  display_name text NOT NULL DEFAULT '',
  password_hash text NOT NULL,                       -- argon2id
  totp_secret_enc text,                              -- Fernet; chi master
  totp_enabled boolean NOT NULL DEFAULT false,
  status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','suspended','disabled')),
  failed_attempts integer NOT NULL DEFAULT 0,
  locked_until timestamptz,
  must_change_password boolean NOT NULL DEFAULT true,
  password_changed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  last_login_at timestamptz
);

CREATE TABLE IF NOT EXISTS mt_accounts (
  account_id text PRIMARY KEY,                       -- <platform>:<login>, vd mt5:12345678
  platform text NOT NULL CHECK (platform IN ('mt4','mt5')),
  login bigint NOT NULL,
  server text NOT NULL DEFAULT '',
  label text NOT NULL DEFAULT '',
  client_id uuid REFERENCES portal_users(user_id) ON DELETE SET NULL,   -- chu so huu chinh
  status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','active','suspended')),
  ea_token_hash text,                                -- sha256 hex cua token EA (mt-bridge so khop)
  ea_hmac_secret_enc text,                           -- Fernet(HMAC secret) - bridge giai ma bang AUTH_SECRET_KEY
  pairing_code_hash text,                            -- sha256 hex cua ma ghep cap CHUAN HOA (chu hoa, bo ky tu khong phai chu-so)
  pairing_expires_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  last_seen_at timestamptz,
  notes text NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS mt_accounts_login_idx ON mt_accounts (platform, login);
CREATE INDEX IF NOT EXISTS mt_accounts_client_idx ON mt_accounts (client_id);

CREATE TABLE IF NOT EXISTS user_accounts (
  user_id uuid NOT NULL REFERENCES portal_users(user_id) ON DELETE CASCADE,
  account_id text NOT NULL REFERENCES mt_accounts(account_id) ON DELETE CASCADE,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, account_id)
);
CREATE INDEX IF NOT EXISTS user_accounts_acc_idx ON user_accounts (account_id);

CREATE TABLE IF NOT EXISTS portal_sessions (
  session_id text PRIMARY KEY,                       -- sha256 hex cua id trong cookie (KHONG luu id goc)
  user_id uuid NOT NULL REFERENCES portal_users(user_id) ON DELETE CASCADE,
  created_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL,
  last_seen_at timestamptz NOT NULL DEFAULT now(),
  ip text NOT NULL DEFAULT '',
  user_agent text NOT NULL DEFAULT '',
  revoked boolean NOT NULL DEFAULT false
);
CREATE INDEX IF NOT EXISTS portal_sessions_user_idx ON portal_sessions (user_id) WHERE NOT revoked;
CREATE INDEX IF NOT EXISTS portal_sessions_exp_idx ON portal_sessions (expires_at);

-- Nhat ky kiem toan: CHI THEM (khong UPDATE/DELETE cho ts_auth), chuoi bam (prev_hash -> hash) de phat hien sua/xoa.
CREATE TABLE IF NOT EXISTS audit_log (
  id bigserial PRIMARY KEY,
  ts timestamptz NOT NULL DEFAULT now(),
  actor_user_id uuid,                                -- khong FK: giu lai khi user bi xoa
  actor_label text NOT NULL DEFAULT '',
  action text NOT NULL,
  target text NOT NULL DEFAULT '',
  ip text NOT NULL DEFAULT '',
  detail jsonb NOT NULL DEFAULT '{}'::jsonb,
  prev_hash text NOT NULL DEFAULT '',
  hash text NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS audit_log_ts_idx ON audit_log (ts DESC);
CREATE INDEX IF NOT EXISTS audit_log_action_idx ON audit_log (action, ts DESC);
