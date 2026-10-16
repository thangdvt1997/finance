# ADR-002: TimescaleDB (PostgreSQL 16) cho dữ liệu chuỗi thời gian

**Trạng thái:** Accepted (2026-10-11)

## Bối cảnh
Cần lưu hàng chục triệu nến/tick/tin, truy vấn theo mã+khung+thời gian, nén và giữ lại theo chính sách, kèm dữ liệu quan hệ (tài khoản, luật, nhật ký). Cần Grafana và công cụ SQL chuẩn.

## Quyết định
Dùng **TimescaleDB 2.30 trên PostgreSQL 16** (hypertable cho bars/quotes...), schema ở `infra/db/schema.sql` + 17 migration idempotent, nén và retention theo `docs/DATA_RETENTION.md`, backup `pg_dump` mã hoá + base backup vật lý (PITR) + restore-test tự động. Mỗi service dùng **role hẹp** (`ts_ro`, `ts_writer`, ... xem ADR-014).

## Hệ quả
- (+) SQL chuẩn, Grafana/Postgres exporter có sẵn, một công nghệ cho cả chuỗi thời gian và quan hệ.
- (-) Thành phần nén/continuous aggregate thuộc **Timescale License (không phải OSI)** - đã dùng nén (migration 009); dùng nội bộ ổn, **không** dựng dịch vụ DB-as-a-service từ nó. Xem `THIRD_PARTY_ALL.md`.
- (-) Một DB cho mọi thứ: shared_buffers 32 GB trên VPS dùng chung; cần theo dõi tài nguyên.
