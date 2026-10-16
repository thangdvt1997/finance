# ADR-017: Build, test, deploy chỉ trên VPS; laptop chỉ sửa file và git

**Trạng thái:** Accepted (2026-10-11)

## Bối cảnh
Máy dev không có Docker/dữ liệu thật; môi trường VPS dùng chung với hệ thống khác nên cần thao tác có kiểm soát; build trên laptop dễ lệch môi trường.

## Quyết định
Chỉ sửa file + git trên laptop. Mọi build/test/chạy qua `deploy.sh "<lệnh compose>"` (SSH) trên VPS, **luôn** với `COMPOSE_FILE` ba file; chỉ thao tác container `tradingsys-*`. Test đơn vị chạy không cần Docker/mạng (fake/fixture); e2e chạy trên VPS (`tests/e2e/`). Có `release.sh`/`rollback.sh`, lockfile có hash cho image.

## Hệ quả
- (+) Một môi trường thật duy nhất, tái lập được.
- (-) Vòng phản hồi chậm hơn local; phụ thuộc kết nối tới VPS.
- Rủi ro đã gặp: `up` chỉ với compose chính đảo ngược nâng cấp image, nên luôn dùng `deploy.sh`.
