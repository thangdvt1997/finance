# ADR-007: Cache nhiều tầng, không bao giờ cache chéo người dùng

**Trạng thái:** Accepted (2026-10-12)

## Bối cảnh
Giao diện master + client cùng truy vấn nhiều endpoint giống nhau; polling làm tải gateway/DB cao. Cache sai phạm vi có thể làm rò dữ liệu tài khoản giữa các client.

## Quyết định
Năm tầng: T1 Redis cache trong gateway (instance `redis-cache` riêng, user `ts_cache` chỉ `cache:*`), T2 micro-cache nginx cho route dùng chung, T3 `auth_cache` chỉ cho trang tĩnh, T4 ETag/Cache-Control/gzip_static, T5 DB. Khoá cache = **phạm vi (master `m` | client `c` | `c.<băm tập tài khoản>`) + đường dẫn + query**; không đưa `user_id` vào khoá; chỉ ghi entry sau khi app trả 200 đúng phạm vi; danh sách route **không cache** (`/me`, `/user/*`, `/journal/*`, `/paper/*`, `/system`...). Có công tắc tắt tức thì (`cache:ctl:off`, file `/tmp/ts-cache-off`). Đo trước/sau trong `PERFORMANCE.md`.

## Hệ quả
- (+) Giảm tải, trang nhanh hơn; an toàn dữ liệu được kiểm bằng test.
- (-) Dữ liệu có thể cũ vài giây (TTL ngắn, SWR); thêm route mới phải khai báo phạm vi cache.
- (-) Redis 7.4.5 của cache: xem lưu ý giấy phép trong `THIRD_PARTY_ALL.md`.
