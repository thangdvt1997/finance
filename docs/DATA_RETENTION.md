# DATA_RETENTION — nén, retention, continuous aggregate (TimescaleDB 2.30.2) — 2026-10-12

Áp bằng `infra/db/migrations/009_retention_compression.sql` (idempotent): `sh`/`bash infra/db/apply_migration.sh migrations/009_retention_compression.sql` trên VPS. Đã áp 2026-10-12 21:00 UTC+0.

## 1. Kích thước thực tế (đo trên VPS trước khi áp)
| Bảng | Dòng | Kích thước | Ghi chú |
|---|---|---|---|
| `bars` (hypertable, 1920 chunk 7 ngày) | D1 366k (từ 1990, 84 mã), M1 184k, M5 126k, H1 124k, H4 94k, M15 86k | 338 MB | D1 lịch sử rải 1900 chunk gần như trống nên tổng chi phí chủ yếu là overhead mỗi chunk (heap+2 index ≈ 170 KB/chunk) |
| `quotes` | ~6,7k (chỉ crypto) | 2 MB | quote thô nhỏ vì mới có 1 nguồn tick |
| `account_snapshots` | 12,6k | 3 MB | jsonb positions |
| `paper_equity` | 74 | 0,4 MB | bất biến (trigger) |
| `vn_daily` v.v. | 319k | 66 MB | bảng thường (module VN, không phải hypertable) |
Tổng dữ liệu < 0,5 GB trên ổ 1,8 TB (đang dùng 36%): đĩa KHÔNG phải ràng buộc; chính sách dưới đây nhằm giữ kỷ luật khi thêm nguồn tick/MT thật, không phải cứu dung lượng hôm nay.

## 2. Chính sách
| Bảng | Nén (segmentby / orderby) | Nén sau | Xoá (retention) | Lý do |
|---|---|---|---|---|
| `bars` | `symbol,tf,source` / `ts_open DESC` | 30 ngày | KHÔNG xoá | nguồn backtest/analytics; nhỏ; muốn bớt M1 cũ thì xem mục 4 |
| `quotes` | `symbol,source` / `ts DESC` | 3 ngày | **30 ngày** (chunk) | quote/tick thô đắt và ít giá trị sau 30 ngày; bản tóm tắt 1 phút giữ 365 ngày (`quotes_1m`) |
| `account_snapshots` | `account_id` / `ts DESC` | 14 ngày | 730 ngày | equity-history cần vài năm; snapshot positions chi tiết thì không |
| `paper_equity` | — | — | — | sổ kiểm toán bất biến (`paper_block_mutation`); nén làm hỏng trigger |
| `news_items`, `calendar_events`, `alerts`, `experts*`, `analytics_snapshots`, `paper_*` | — | — | — | bảng thường rất nhỏ; xem lại khi >1 GB |
Job do Timescale lên lịch (`SELECT * FROM timescaledb_information.jobs WHERE job_id >= 1000`): compression bars=1000, quotes=1001, account_snapshots=1002; retention quotes=1003, account_snapshots=1004; refresh cagg quotes_1m=1005 (mỗi phút), retention quotes_1m=1006, refresh bars_daily_stats=1007 (mỗi 15 phút).

## 3. Continuous aggregate
- `quotes_1m`: `time_bucket('1 minute', ts)`, theo symbol+source: bid open/high/low/close, ask close, số tick. Real-time (materialized_only=false). Giữ 365 ngày.
- `bars_daily_stats`: theo ngày × symbol × tf × source: số bar, bar cuối (`last_bar`), tổng volume. Dùng cho kiểm tra khoảng trống/chất lượng (so số bar mỗi ngày với kỳ vọng M1=1440) và truy vấn D1 nhanh. LƯU Ý: phần "hôm nay" chỉ tươi tới lần refresh gần nhất (≤15 phút) vì bucket 1 ngày; **độ tươi theo phút KHÔNG đọc từ cagg này** mà từ bảng `bars` (xem `infra/prometheus/pg_queries.yaml`).
- Quyền: `ts_ro`, `ts_analytics` SELECT cả hai view; `ts_monitor` SELECT `bars_daily_stats`.

## 4. Vận hành
- Ghi (INSERT ... ON CONFLICT DO UPDATE) vào chunk đã nén được hỗ trợ (kiểm chứng 2026-10-12 trên bảng thử: upsert chunk nén OK) nhưng giải nén theo batch nên chậm hơn. Backfill lịch sử nặng nên chạy trước khi chunk bị nén hoặc chấp nhận chậm.
- Nén thủ công một lần: `CALL run_job(1000);` (đã chạy; 1915/1920 chunk bars đã nén, 5 chunk còn lại là chunk hiện hành). Cảnh báo "already converted to columnstore" khi chạy job là vô hại.
- Muốn bớt M1/M5 cũ (ví dụ giữ 365 ngày): thêm job tuỳ biến `DELETE FROM bars WHERE tf IN ('M1','M5') AND ts_open < now() - interval '365 days'` (lọc theo cột segmentby `tf` nên xoá cả batch, không giải nén) qua `add_job`. KHÔNG bật mặc định (quyết định sản phẩm: backtest cần M1).
- Chunk bars: 1920 chunk 7 ngày quá nhiều cho D1 lịch sử; chunk mới nên tăng interval: `SELECT set_chunk_time_interval('bars', INTERVAL '30 days');` (chỉ áp cho chunk tương lai; chưa áp để không đổi hành vi khi đang chạy). Gộp chunk cũ cần `merge_chunks` (rủi ro, lợi ích ~100 MB) nên hoãn.
- Theo dõi: panel "Chunk đã nén / tổng" (dashboard `ts-resources`), `pg_database_size_bytes`, luật `HostDiskLow`. Kích thước từng hypertable: `SELECT hypertable_name, pg_size_pretty(hypertable_size(format('%I',hypertable_name)::regclass)) FROM timescaledb_information.hypertables;` (~2s do 1900 chunk nên không đưa vào exporter).
- PITR/backup: dump và WAL tính trên dữ liệu sau nén (nhỏ hơn); `timescaledb_pre_restore()/post_restore()` đã nằm trong DR_RUNBOOK.
- Rollback: `SELECT remove_compression_policy('bars');` `SELECT remove_retention_policy('quotes');` `DROP MATERIALIZED VIEW quotes_1m;` ... (chunk đã nén giải bằng `SELECT decompress_chunk(c) FROM show_chunks('bars') c;`).

## 5. Kiểm tra và dự báo đĩa 90 ngày (đo 2026-10-14)
- Job Timescale (id>=1000) đều `Success`, lần chạy gần nhất trong 12 giờ: nén bars/quotes/account_snapshots, retention quotes/account_snapshots/quotes_1m, refresh `quotes_1m` (mỗi phút) và `bars_daily_stats` (15 phút). 1915/1920 chunk bars đã nén. Không bảng nào thiếu chính sách cần thiết: bảng thường (`news_items`, `alerts`, `analytics_snapshots`, `tr_*`, `expert_*`, `vn_*`) đều < 80 MB; `paper_*`, `audit_log`, `tr_*` là sổ cái bất biến/hash-chain — KHÔNG xoá/nén.
- Kích thước: DB 879 MB (bars 505 MB, vn_daily 68 MB, quotes 51 MB, account_snapshots 16 MB); `pg-data` volume 1,5 GB; `prom-data` 1,0 GB (retention 30 ngày); log container giới hạn 10 MB x 3 x 34; `backups` 400 MB; `wal-archive` 3,0 GB.
- Tốc độ tăng: bars ≈ 30–70 nghìn dòng/ngày (crypto M1/M5 + Dukascopy) => DB ≈ +10–15 MB/ngày trước nén (nén ≥5x sau 30 ngày); WAL lưu trữ ≈ 1 GB/ngày (hầu hết là segment 16 MB gần rỗng bị ép chuyển mỗi 5 phút bởi `archive_timeout`, gzip còn ≈3 MB/file) và bị tỉa hằng tuần theo base backup (giữ 2 bản).
- Dự báo 90 ngày: DB ≈ 1,8–2,2 GB, dump hằng ngày ≈ 70–150 MB x 14 bản ≈ 1–2 GB, base backup 2 x ≈150–300 MB, WAL trạng thái ổn định ≈ 7–14 GB (đỉnh trước mỗi lần base backup CN), Prometheus ≈ 1 GB. Tổng tăng thêm < 25 GB trên ổ còn 1,1 TB (38% đã dùng) => đĩa không phải ràng buộc. Phần chiếm nhiều nhất của stack là volume `briefing-models` 32 GB (cố định). Luật mới `HostDiskFillingFast` (dự báo đầy trong <72 giờ) và `HostDiskLow` (<10%) giám sát.
- Nếu muốn giảm WAL: `ALTER SYSTEM SET wal_compression='lz4'` (cần reload; chưa bật vì lợi ích nhỏ so với segment rỗng) hoặc tăng `archive_timeout` lên 15 phút (đánh đổi RPO).
- Dọn dữ liệu thử 2026-10-14: `infra/db/cleanup_test_data_20261014.sql`; bản sao nằm ở schema `archive` (`*_cleanup_20261014`, vài trăm KB), có thể `DROP SCHEMA archive CASCADE` khi chắc chắn không cần.
