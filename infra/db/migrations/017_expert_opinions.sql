-- Y KIEN chuyen gia/to chuc (expert-collector, kind='opinion'): moi bai = 1 hang; chi la tham khao, KHONG phai khuyen nghi.
-- Idempotent. Ap xong moi bat STORAGE_EXPERT_OPINIONS=true (storage-writer). api-gateway tu phat hien bang (khong can cau hinh).
CREATE TABLE IF NOT EXISTS expert_opinions (
  url text PRIMARY KEY,                 -- khoa tu nhien (= news_items.url)
  expert_id text NOT NULL,              -- 'op:<id>' (experts.expert_id)
  name text,                            -- ten chuyen gia/to chuc (tac gia neu co)
  grp text,                             -- nhom: cb_speech|cb_research|intl_org|bank_research|indep_macro|indep_markets|crypto|commodity|insider|vn_analysis|social...
  title text NOT NULL,
  stance text,                          -- hawkish|dovish|bullish|bearish|neutral (quy tac tu khoa)
  stance_score double precision,
  topics text[] DEFAULT '{}',
  symbols text[] DEFAULT '{}',
  credibility double precision,
  published_at timestamptz,
  lang text,
  ingested_at timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS expert_opinions_pub_idx ON expert_opinions (published_at DESC);
CREATE INDEX IF NOT EXISTS expert_opinions_exp_idx ON expert_opinions (expert_id, published_at DESC);
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ts_ro') THEN GRANT SELECT ON expert_opinions TO ts_ro; END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ts_writer') THEN GRANT SELECT, INSERT, UPDATE ON expert_opinions TO ts_writer; END IF;
END $$;
