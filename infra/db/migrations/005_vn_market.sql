-- vn-market: dữ liệu CHỨNG KHOÁN VIỆT NAM cuối ngày (nguồn công khai VNDirect finfo + seed vnstock/KBS). Idempotent.
-- Giá lưu theo VND thật (nguồn trả nghìn đồng, service nhân 1000). Ghi bằng role hạn chế ts_vn (create_vn_role.sh).
CREATE TABLE IF NOT EXISTS vn_symbols (
  code text PRIMARY KEY,
  floor text NOT NULL,                       -- HOSE | HNX | UPCOM
  kind text NOT NULL DEFAULT 'STOCK',        -- STOCK | ETF
  name text, short_name text, listed_date date,
  industry_code integer, industry_name text, -- phân ngành KBS (vnstock), KHÔNG phải ICB chính thức
  in_vn30 boolean NOT NULL DEFAULT false, in_vn100 boolean NOT NULL DEFAULT false, in_hnx30 boolean NOT NULL DEFAULT false,
  focus boolean NOT NULL DEFAULT false,      -- VN100 + HNX30 + ETF: có lịch sử dài/ratios đầy đủ
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS vn_daily (
  code text NOT NULL, d date NOT NULL, floor text NOT NULL,
  basic double precision, ceil double precision, flr double precision,           -- giá tham chiếu / trần / sàn (VND)
  open double precision, high double precision, low double precision, close double precision,
  ad_close double precision,                                                      -- giá đóng đã điều chỉnh (cổ tức/thưởng/chia tách)
  avg_price double precision,
  volume double precision, value double precision,                                -- khớp lệnh
  pt_volume double precision, pt_value double precision,                          -- thoả thuận
  pct double precision,                                                           -- % thay đổi so với tham chiếu
  PRIMARY KEY (code, d)
);
CREATE INDEX IF NOT EXISTS vn_daily_d_idx ON vn_daily (d);

CREATE TABLE IF NOT EXISTS vn_index_daily (
  code text NOT NULL, d date NOT NULL, floor text, kind text,
  open double precision, high double precision, low double precision, close double precision,
  chg double precision, pct double precision,
  volume double precision, value double precision, pt_value double precision,
  advances integer, declines integer, no_change integer, no_trade integer, ceiling_n integer, floor_n integer,
  PRIMARY KEY (code, d)
);

CREATE TABLE IF NOT EXISTS vn_foreign (
  code text NOT NULL, d date NOT NULL, floor text,
  buy_val double precision, sell_val double precision, net_val double precision,
  buy_vol double precision, sell_vol double precision, net_vol double precision,
  total_room double precision, current_room double precision,
  PRIMARY KEY (code, d)
);
CREATE INDEX IF NOT EXISTS vn_foreign_d_idx ON vn_foreign (d);

CREATE TABLE IF NOT EXISTS vn_ratios (
  code text PRIMARY KEY, as_of date NOT NULL,
  marketcap double precision, pe double precision, pb double precision, ps double precision,
  div_yield double precision, beta double precision, bvps double precision,
  chg_1m double precision, chg_3m double precision, chg_6m double precision, chg_1y double precision,
  hi_52w double precision, lo_52w double precision,
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS vn_events (
  event_id text PRIMARY KEY, code text NOT NULL, etype text NOT NULL, type_desc text, note text,
  dividend double precision, ratio double precision,
  disclosure_date date, effective_date date, expired_date date, actual_date date,
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS vn_events_eff_idx ON vn_events (effective_date);

CREATE TABLE IF NOT EXISTS vn_meta (
  key text PRIMARY KEY, value jsonb NOT NULL DEFAULT '{}'::jsonb, updated_at timestamptz NOT NULL DEFAULT now()
);

DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ts_ro') THEN
    GRANT SELECT ON vn_symbols, vn_daily, vn_index_daily, vn_foreign, vn_ratios, vn_events, vn_meta TO ts_ro;
  END IF;
END $$;
