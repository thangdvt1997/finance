-- 009: nén + retention + continuous aggregate cho TimescaleDB (ARCH_AUDIT D-1). Idempotent. Chạy: sh infra/db/apply_migration.sh migrations/009_retention_compression.sql
-- Chính sách (xem docs/DATA_RETENTION.md):
--   bars               : nén chunk > 30 ngày (segment symbol,tf,source). KHÔNG xoá (bars nhỏ, là nguồn backtest): D1 từ 1990 + intraday 2 năm = ~340MB thô.
--   quotes             : nén chunk > 3 ngày; XOÁ chunk > 30 ngày (tick/quote thô). Bản tóm tắt 1 phút giữ 1 năm trong cagg quotes_1m.
--   account_snapshots  : nén > 14 ngày; xoá > 730 ngày (equity-history cần vài năm; snapshot chi tiết positions jsonb thì không).
--   paper_equity       : KHÔNG nén/xoá (trigger bất biến paper_block_mutation + sổ kiểm toán).
--   cagg bars_daily_stats : thống kê bar/ngày/nguồn (đếm, bar cuối) phục vụ độ tươi + khoảng trống dữ liệu, truy vấn nhanh không quét bars.
--   cagg quotes_1m     : OHLC bid + ask cuối + số tick theo phút/nguồn.
-- Lưu ý vận hành: ghi (INSERT ... ON CONFLICT) vào chunk đã nén được Timescale ≥2.11 hỗ trợ (giải nén theo batch) nhưng chậm hơn; backfill lịch sử cũ nên chạy
-- trước khi nén (hoặc chấp nhận chậm). Hạ thời hạn nén bằng remove_compression_policy + add_compression_policy.

-- ---------- nén ----------
ALTER TABLE bars SET (timescaledb.compress, timescaledb.compress_segmentby = 'symbol,tf,source', timescaledb.compress_orderby = 'ts_open DESC');
ALTER TABLE quotes SET (timescaledb.compress, timescaledb.compress_segmentby = 'symbol,source', timescaledb.compress_orderby = 'ts DESC');
ALTER TABLE account_snapshots SET (timescaledb.compress, timescaledb.compress_segmentby = 'account_id', timescaledb.compress_orderby = 'ts DESC');
SELECT add_compression_policy('bars', INTERVAL '30 days', if_not_exists => TRUE);
SELECT add_compression_policy('quotes', INTERVAL '3 days', if_not_exists => TRUE);
SELECT add_compression_policy('account_snapshots', INTERVAL '14 days', if_not_exists => TRUE);

-- ---------- retention ----------
SELECT add_retention_policy('quotes', INTERVAL '30 days', if_not_exists => TRUE);
SELECT add_retention_policy('account_snapshots', INTERVAL '730 days', if_not_exists => TRUE);

-- ---------- continuous aggregates ----------
CREATE MATERIALIZED VIEW IF NOT EXISTS quotes_1m
WITH (timescaledb.continuous, timescaledb.materialized_only = false) AS
SELECT time_bucket(INTERVAL '1 minute', ts) AS bucket, symbol, source,
       first(bid, ts) AS bid_open, max(bid) AS bid_high, min(bid) AS bid_low, last(bid, ts) AS bid_close,
       last(ask, ts) AS ask_close, count(*) AS ticks
FROM quotes GROUP BY 1, 2, 3
WITH NO DATA;
SELECT add_continuous_aggregate_policy('quotes_1m', start_offset => INTERVAL '2 hours', end_offset => INTERVAL '1 minute', schedule_interval => INTERVAL '1 minute', if_not_exists => TRUE);
SELECT add_retention_policy('quotes_1m', INTERVAL '365 days', if_not_exists => TRUE);

CREATE MATERIALIZED VIEW IF NOT EXISTS bars_daily_stats
WITH (timescaledb.continuous, timescaledb.materialized_only = false) AS
SELECT time_bucket(INTERVAL '1 day', ts_open) AS day, symbol, tf, source,
       count(*) AS bars, max(ts_open) AS last_bar, sum(v) AS volume
FROM bars GROUP BY 1, 2, 3, 4
WITH NO DATA;
SELECT add_continuous_aggregate_policy('bars_daily_stats', start_offset => INTERVAL '3 days', end_offset => INTERVAL '1 hour', schedule_interval => INTERVAL '15 minutes', if_not_exists => TRUE);

-- quyền đọc cho các role chỉ-đọc (nếu tồn tại)
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ts_ro') THEN
    GRANT SELECT ON quotes_1m, bars_daily_stats TO ts_ro;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ts_analytics') THEN
    GRANT SELECT ON quotes_1m, bars_daily_stats TO ts_analytics;
  END IF;
END $$;
