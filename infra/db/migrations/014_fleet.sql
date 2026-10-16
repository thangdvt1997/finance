-- 014: quan ly doi tai khoan (fleet): nhom/tag/saved views, vai tro phu (support/analyst/auditor) theo pham vi nhom, mau luat rui ro + trang thai tuan thu,
-- hop thu su co (incident inbox), ghi chu CRM, cap quyen "xem nhu khach" co han + ly do, VA cac cot CHUAN BI cho control plane (docs/CONTROL_PLANE_DESIGN.md muc 9):
-- tat ca mac dinh TAT/rong, CHECK autonomy_level <= 0 => KHONG co duong thuc thi lenh. Idempotent. Doc: docs/FLEET_MGMT.md
ALTER TABLE portal_users DROP CONSTRAINT IF EXISTS portal_users_role_check;
ALTER TABLE portal_users ADD CONSTRAINT portal_users_role_check CHECK (role IN ('master','client','support','analyst','auditor','expert'));
ALTER TABLE portal_users ADD COLUMN IF NOT EXISTS scope_all boolean NOT NULL DEFAULT false;      -- vai tro phu: thay moi tai khoan (mac dinh: chi nhom duoc giao)
ALTER TABLE portal_users ADD COLUMN IF NOT EXISTS created_by uuid;

-- (control plane, inert) -----------------------------------------------------------------------------------------------------------------
ALTER TABLE mt_accounts ADD COLUMN IF NOT EXISTS permissions jsonb NOT NULL DEFAULT '{}'::jsonb;  -- view/propose/approve_trade...: chua co hieu luc
ALTER TABLE mt_accounts ADD COLUMN IF NOT EXISTS exec_optin boolean NOT NULL DEFAULT false;
ALTER TABLE mt_accounts ADD COLUMN IF NOT EXISTS exec_optin_at timestamptz;
ALTER TABLE mt_accounts ADD COLUMN IF NOT EXISTS exec_optin_consent_version text;
ALTER TABLE mt_accounts ADD COLUMN IF NOT EXISTS cmd_pubkey text;                                  -- Ed25519 cong khai (tuong lai)
ALTER TABLE mt_accounts ADD COLUMN IF NOT EXISTS cmd_key_id text;
ALTER TABLE mt_accounts ADD COLUMN IF NOT EXISTS margin_mode text;                                 -- hedging | netting
ALTER TABLE mt_accounts ADD COLUMN IF NOT EXISTS cmd_state text NOT NULL DEFAULT 'disabled';
ALTER TABLE mt_accounts ADD COLUMN IF NOT EXISTS autonomy_level smallint NOT NULL DEFAULT 0;
ALTER TABLE mt_accounts DROP CONSTRAINT IF EXISTS mt_accounts_cmd_state_check;
ALTER TABLE mt_accounts ADD CONSTRAINT mt_accounts_cmd_state_check CHECK (cmd_state IN ('disabled','halted','shadow','live'));
ALTER TABLE mt_accounts DROP CONSTRAINT IF EXISTS mt_accounts_autonomy_check;
ALTER TABLE mt_accounts ADD CONSTRAINT mt_accounts_autonomy_check CHECK (autonomy_level <= 0);    -- go bang migration co chu dich
-- khach tu opt-in nhan thong bao push khi vi pham/sat nguong luat (mac dinh TAT; chi chinh khach doi duoc)
ALTER TABLE mt_accounts ADD COLUMN IF NOT EXISTS client_notify boolean NOT NULL DEFAULT false;
ALTER TABLE mt_accounts ADD COLUMN IF NOT EXISTS client_notify_at timestamptz;

CREATE TABLE IF NOT EXISTS consent_records (        -- cho giu cho (chua dung)
  id bigserial PRIMARY KEY, user_id uuid, account_id text, doc_version text NOT NULL, doc_hash text NOT NULL,
  accepted_at timestamptz NOT NULL DEFAULT now(), revoked_at timestamptz, ip text NOT NULL DEFAULT '', ua text NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS policy_versions (        -- cho giu cho (chua co hieu luc)
  id bigserial PRIMARY KEY, scope text NOT NULL DEFAULT '', body jsonb NOT NULL DEFAULT '{}'::jsonb, created_at timestamptz NOT NULL DEFAULT now(),
  created_by uuid, effective boolean NOT NULL DEFAULT false CHECK (effective = false)
);

-- nhom / tag / saved views ---------------------------------------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS account_groups (
  group_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL UNIQUE,
  description text NOT NULL DEFAULT '',
  color text NOT NULL DEFAULT '',
  policy jsonb NOT NULL DEFAULT '{}'::jsonb,        -- chinh sach canh bao theo nhom (docs/FLEET_MGMT.md)
  created_at timestamptz NOT NULL DEFAULT now(),
  created_by uuid
);
CREATE TABLE IF NOT EXISTS account_group_members (
  group_id uuid NOT NULL REFERENCES account_groups(group_id) ON DELETE CASCADE,
  account_id text NOT NULL REFERENCES mt_accounts(account_id) ON DELETE CASCADE,
  added_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (group_id, account_id)
);
CREATE INDEX IF NOT EXISTS account_group_members_acc_idx ON account_group_members (account_id);
CREATE TABLE IF NOT EXISTS account_tags (
  account_id text NOT NULL REFERENCES mt_accounts(account_id) ON DELETE CASCADE,
  tag text NOT NULL,
  PRIMARY KEY (account_id, tag)
);
CREATE INDEX IF NOT EXISTS account_tags_tag_idx ON account_tags (tag);
CREATE TABLE IF NOT EXISTS saved_views (
  view_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_user_id uuid NOT NULL REFERENCES portal_users(user_id) ON DELETE CASCADE,
  name text NOT NULL,
  filters jsonb NOT NULL DEFAULT '{}'::jsonb,
  shared boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS staff_scopes (          -- vai tro phu chi thay tai khoan thuoc cac nhom nay (hoac scope_all)
  user_id uuid NOT NULL REFERENCES portal_users(user_id) ON DELETE CASCADE,
  group_id uuid NOT NULL REFERENCES account_groups(group_id) ON DELETE CASCADE,
  PRIMARY KEY (user_id, group_id)
);
CREATE TABLE IF NOT EXISTS account_notes (
  note_id bigserial PRIMARY KEY,
  account_id text NOT NULL REFERENCES mt_accounts(account_id) ON DELETE CASCADE,
  author_user_id uuid, author_label text NOT NULL DEFAULT '',
  text text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS account_notes_acc_idx ON account_notes (account_id, created_at DESC);
CREATE TABLE IF NOT EXISTS view_as_grants (        -- "xem nhu khach": co han + ly do bat buoc (ghi them audit_log)
  grant_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  actor_user_id uuid, actor_label text NOT NULL DEFAULT '',
  account_id text NOT NULL, reason text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(), expires_at timestamptz NOT NULL, ended_at timestamptz
);

-- mau luat rui ro ---------------------------------------------------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS rule_templates (
  template_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL UNIQUE,
  kind text NOT NULL CHECK (kind IN ('daily_loss','max_drawdown','margin_level','best_day','max_trades_day')),
  params jsonb NOT NULL DEFAULT '{}'::jsonb,
  description text NOT NULL DEFAULT '',
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(), created_by uuid
);
CREATE TABLE IF NOT EXISTS rule_assignments (
  assignment_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  template_id uuid NOT NULL REFERENCES rule_templates(template_id) ON DELETE CASCADE,
  scope_type text NOT NULL CHECK (scope_type IN ('group','tag','account','all')),
  scope_ref text NOT NULL DEFAULT '',               -- group_id | tag | account_id | ''
  enabled boolean NOT NULL DEFAULT true,
  notify_client boolean NOT NULL DEFAULT false,     -- chi co hieu luc voi tai khoan khach da opt-in (mt_accounts.client_notify)
  created_at timestamptz NOT NULL DEFAULT now(), created_by uuid
);
CREATE TABLE IF NOT EXISTS rule_status (
  account_id text NOT NULL REFERENCES mt_accounts(account_id) ON DELETE CASCADE,
  assignment_id uuid NOT NULL REFERENCES rule_assignments(assignment_id) ON DELETE CASCADE,
  status text NOT NULL CHECK (status IN ('green','yellow','red','na')),
  usage_pct double precision, value double precision, limit_value double precision, headroom double precision,
  unit text NOT NULL DEFAULT '', detail jsonb NOT NULL DEFAULT '{}'::jsonb,
  reset_at timestamptz, evaluated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (account_id, assignment_id)
);

-- hop thu su co -----------------------------------------------------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS incidents (
  incident_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  key text NOT NULL,                                -- khoa dieu kien, vd rule:<assignment>:<account>, ea:offline:<account>
  kind text NOT NULL DEFAULT 'other' CHECK (kind IN ('rule','budget','ea','other')),
  account_id text NOT NULL DEFAULT '',
  cause_key text NOT NULL DEFAULT '',               -- gop "N tai khoan cung loi"
  severity text NOT NULL DEFAULT 'warning' CHECK (severity IN ('info','warning','critical')),
  status text NOT NULL DEFAULT 'open' CHECK (status IN ('open','ack','snoozed','resolved')),
  title text NOT NULL, detail text NOT NULL DEFAULT '',
  assignee_user_id uuid, assignee_label text NOT NULL DEFAULT '',
  snoozed_until timestamptz,
  opened_at timestamptz NOT NULL DEFAULT now(), acked_at timestamptz, resolved_at timestamptz, resolved_by text NOT NULL DEFAULT '',
  last_seen_at timestamptz NOT NULL DEFAULT now(), occurrences integer NOT NULL DEFAULT 1,
  meta jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE UNIQUE INDEX IF NOT EXISTS incidents_open_key_uq ON incidents (key) WHERE status <> 'resolved';
CREATE INDEX IF NOT EXISTS incidents_status_idx ON incidents (status, opened_at DESC);
CREATE INDEX IF NOT EXISTS incidents_account_idx ON incidents (account_id);
CREATE TABLE IF NOT EXISTS incident_events (
  event_id bigserial PRIMARY KEY,
  incident_id uuid NOT NULL REFERENCES incidents(incident_id) ON DELETE CASCADE,
  ts timestamptz NOT NULL DEFAULT now(),
  actor_user_id uuid, actor_label text NOT NULL DEFAULT '',
  type text NOT NULL, text text NOT NULL DEFAULT '', meta jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS incident_events_inc_idx ON incident_events (incident_id, ts);

DO $$
DECLARE t text;
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ts_auth') THEN
    FOREACH t IN ARRAY ARRAY['consent_records','policy_versions','account_groups','account_group_members','account_tags','saved_views','staff_scopes',
      'account_notes','view_as_grants','rule_templates','rule_assignments','rule_status','incidents','incident_events'] LOOP
      EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON %I TO ts_auth', t);
    END LOOP;
    GRANT USAGE, SELECT ON SEQUENCE consent_records_id_seq, policy_versions_id_seq, account_notes_note_id_seq, incident_events_event_id_seq TO ts_auth;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ts_ro') THEN   -- mac dinh ts_ro doc moi bang moi: thu hoi (du lieu quan tri khong de service khac doc)
    REVOKE ALL ON consent_records, policy_versions, account_groups, account_group_members, account_tags, saved_views, staff_scopes, account_notes,
      view_as_grants, rule_templates, rule_assignments, rule_status, incidents, incident_events FROM ts_ro;
  END IF;
END $$;
