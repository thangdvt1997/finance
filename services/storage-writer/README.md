# storage-writer

Consume 9 stream (`md.bars, md.quotes, news.items, news.enriched, calendar.events, expert.signals, expert.positions, account.snapshots, alerts.out`) bằng consumer group `storage-writer` và UPSERT idempotent vào TimescaleDB. `news.enriched` (từ `nlp`) cập nhật `news_items` theo url: sentiment + hợp nhất symbols (cột mở rộng chỉ khi `STORAGE_ENRICH_EXTENDED=true`, cần migration 002).

- Ack chỉ sau khi ghi DB thành công (at-least-once + upsert = effectively-once).
- Payload sai / thiếu trường -> stream `dlq` ngay (không retry). Lỗi DB -> retry 3 lần backoff, hết thì `dlq`.
- Khi khởi động đọc lại message pending (recover sau crash).
- Mapping thuần ở `mapping.py` (Event -> [(SQL, args)]).
- Metrics: `sw_events_total{stream,result}`, `sw_errors_total{stream,kind}`, `sw_stream_lag`, `sw_stream_pending`, `sw_write_seconds`. `/healthz`, `/metrics` trên PORT.
- Yêu cầu migration `infra/db/migrations/001_alerts_event_id.sql` (cột `alerts.event_id UNIQUE`).

Test: `.venv\Scripts\python -m pytest services/storage-writer` (pyproject đã đặt `pythonpath=src`).
