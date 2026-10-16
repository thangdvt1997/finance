-- Cap phat dong EA <-> auth <-> mt-bridge (docs/CLIENT_PLATFORM.md). Idempotent. Them cot cho tai khoan MT: rev, require_hmac, cau hinh bridge, suc khoe EA.
ALTER TABLE mt_accounts ADD COLUMN IF NOT EXISTS rev bigint NOT NULL DEFAULT 1;              -- tang moi lan doi ban ghi (bridge dung de nhan biet thay doi)
ALTER TABLE mt_accounts ADD COLUMN IF NOT EXISTS require_hmac boolean NOT NULL DEFAULT true;
ALTER TABLE mt_accounts ADD COLUMN IF NOT EXISTS config jsonb NOT NULL DEFAULT '{}'::jsonb;   -- chi cac khoa bridge cho phep (symbol_prefix, watch_symbols...)
ALTER TABLE mt_accounts ADD COLUMN IF NOT EXISTS ea_cred_pending_enc text;                     -- Fernet({"token","hmac"}) cho EA tu dang ky: giao MOT lan sau khi client ghep cap
ALTER TABLE mt_accounts ADD COLUMN IF NOT EXISTS ea_remote_addr text NOT NULL DEFAULT '';
ALTER TABLE mt_accounts ADD COLUMN IF NOT EXISTS ea_status text NOT NULL DEFAULT '';           -- online | degraded | offline (bridge bao qua /seen)
ALTER TABLE mt_accounts ADD COLUMN IF NOT EXISTS ea_reason text NOT NULL DEFAULT '';
ALTER TABLE mt_accounts ADD COLUMN IF NOT EXISTS ea_latency_ms integer;
ALTER TABLE mt_accounts ADD COLUMN IF NOT EXISTS ea_skew_s real;
ALTER TABLE mt_accounts ADD COLUMN IF NOT EXISTS ea_version text NOT NULL DEFAULT '';
ALTER TABLE mt_accounts ADD COLUMN IF NOT EXISTS ea_build integer;
ALTER TABLE mt_accounts ADD COLUMN IF NOT EXISTS ea_broker text NOT NULL DEFAULT '';
ALTER TABLE mt_accounts ADD COLUMN IF NOT EXISTS ea_health_at timestamptz;
