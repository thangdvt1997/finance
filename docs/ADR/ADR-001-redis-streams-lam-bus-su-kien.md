# ADR-001: Redis Streams làm bus sự kiện

**Trạng thái:** Accepted (2026-10-11)

## Bối cảnh
Các service (collector, nlp, storage-writer, cảnh báo, gateway realtime...) cần trao đổi sự kiện giá/tin/tài khoản với độ tin cậy cao, có thể phát lại khi service khởi động lại, và không muốn đọc DB của nhau. Khối lượng thấp (một VPS). PLAN.md đã nêu hai ứng viên: Redis Streams hoặc NATS; `docs/OSS_REUSE.md` khảo sát thêm Kafka/Redpanda (nặng, BSL), NATS JetStream.

## Quyết định
Dùng **Redis Streams** làm bus duy nhất: mỗi loại sự kiện một stream (`md.quotes`, `md.bars`, `news.items`, `news.enriched`, `calendar.events`, `expert.*`, `account.*`, `mt.account_status`, `alerts.out`, `alerts.delivery`), envelope chung `tscommon.Event`, mỗi service một consumer group, ghi DB **idempotent** theo khoá tự nhiên, `XAUTOCLAIM` để nhận lại tin bị treo, stream bị cắt ở ~100k entry, stream `dlq` cho sự kiện lỗi. Hợp đồng nằm ở `docs/CONTRACTS.md`.

## Hệ quả
- (+) Đơn giản, đã chạy ổn, bật AOF; gateway realtime đọc MỘT vòng `XREAD` cho mọi kết nối.
- (-) Redis là điểm chung; tin có thể mất tối đa ~1 giây (AOF everysec) - chấp nhận vì dữ liệu có thể thu lại/backfill.
- (-) Giấy phép Redis: bus đang chạy Redis 8.10 (AGPLv3 là một lựa chọn cấp phép) và cache chạy 7.4.5 (RSALv2/SSPL, không phải OSI) - xem `THIRD_PARTY_ALL.md`. Phương án thay thế cùng giao thức: **Valkey** (BSD-3).
- Khi cần thông lượng lớn/đa máy: chuyển NATS JetStream; giao diện bus nằm trong `tscommon` nên thay được.
