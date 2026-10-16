-- paper-trader: quản trị journal MÔ PHỎNG — hash-chain (tamper-evident) + phiên bản cấu hình bất biến. Idempotent.
-- Chạy bằng superuser/owner (create_paper_role.sh). Cả hai bảng append-only (trigger paper_block_mutation từ 003).
CREATE TABLE IF NOT EXISTS paper_chain (
  account_id text NOT NULL,
  seq bigint NOT NULL,                              -- 1,2,3... liên tục theo tài khoản
  kind text NOT NULL CHECK (kind IN ('order','order_status','fill','event','equity')),
  ref text NOT NULL,                                -- khoá tự nhiên của bản ghi nguồn (client_order_id | client_order_id#status | event_key | ts)
  ts timestamptz NOT NULL,
  content_hash text NOT NULL,                       -- sha256(canonical_json(nội dung bất biến của bản ghi))
  prev_hash text NOT NULL,                          -- row_hash của dòng trước (genesis = sha256('genesis:'||account_id))
  row_hash text NOT NULL,                           -- sha256(prev_hash|seq|kind|ref|content_hash)
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (account_id, seq),
  UNIQUE (account_id, kind, ref)
);

CREATE TABLE IF NOT EXISTS paper_config_versions (
  account_id text NOT NULL,
  version integer NOT NULL,
  config_hash text NOT NULL,                        -- sha256 cấu hình hiệu lực (tham số, universe, rủi ro, chi phí giả định)
  params_hash text NOT NULL,                        -- sha256 riêng tham số chiến lược
  config jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (account_id, version)
);

DROP TRIGGER IF EXISTS paper_chain_immutable ON paper_chain;
CREATE TRIGGER paper_chain_immutable BEFORE UPDATE OR DELETE ON paper_chain FOR EACH ROW EXECUTE FUNCTION paper_block_mutation();
DROP TRIGGER IF EXISTS paper_config_versions_immutable ON paper_config_versions;
CREATE TRIGGER paper_config_versions_immutable BEFORE UPDATE OR DELETE ON paper_config_versions FOR EACH ROW EXECUTE FUNCTION paper_block_mutation();

DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ts_ro') THEN
    GRANT SELECT ON paper_chain, paper_config_versions TO ts_ro;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ts_paper') THEN
    GRANT SELECT, INSERT ON paper_chain, paper_config_versions TO ts_paper;
  END IF;
END $$;
