# ADR - Architecture Decision Records

Mỗi tệp ghi một quyết định kiến trúc đã đưa ra: **Bối cảnh, Quyết định, Hệ quả**. Trạng thái: *Accepted* = đã triển khai/đang áp dụng; *Proposed* = thiết kế đã chốt hướng nhưng **chưa có mã**. Các ADR ngắn của giai đoạn điều khiển (ADR-C1 đến C8) nằm trong [`../CONTROL_PLANE_DESIGN.md`](../CONTROL_PLANE_DESIGN.md) mục 7. Kiến trúc tổng: [`../KIEN_TRUC.md`](../KIEN_TRUC.md).

| # | Quyết định | Trạng thái |
|---|---|---|
| 001 | [Redis Streams làm bus sự kiện](ADR-001-redis-streams-lam-bus-su-kien.md) | Accepted |
| 002 | [TimescaleDB (PostgreSQL 16) cho dữ liệu chuỗi thời gian](ADR-002-timescaledb-postgresql-16-cho-du-lieu-chuoi-thoi.md) | Accepted |
| 003 | [EA chủ động đẩy dữ liệu ra (outbound), không mở cổng vào](ADR-003-ea-chu-dong-day-du-lieu-ra-outbound-khong-mo-con.md) | Accepted |
| 004 | [Chỉ đọc trước, thực thi sau cổng pháp lý G1-G3](ADR-004-chi-doc-truoc-thuc-thi-sau-cong-phap-ly-g1-g3.md) | Accepted |
| 005 | [Tự xây dịch vụ auth (phiên + vai trò) thay vì nhúng OSS SSO](ADR-005-tu-xay-dich-vu-auth-phien-vai-tro-thay-vi-nhung.md) | Accepted |
| 006 | [Không bao giờ thu hay lưu mật khẩu giao dịch/investor của MT](ADR-006-khong-bao-gio-thu-hay-luu-mat-khau-giao-dich-inv.md) | Accepted |
| 007 | [Cache nhiều tầng, không bao giờ cache chéo người dùng](ADR-007-cache-nhieu-tang-khong-bao-gio-cache-cheo-nguoi.md) | Accepted |
| 008 | [Realtime hub trong api-gateway (WS/SSE rt.v1)](ADR-008-realtime-hub-trong-api-gateway-ws-sse-rt-v1.md) | Accepted |
| 009 | [Ẩn tên nguồn dữ liệu trên mọi giao diện và đầu ra](ADR-009-an-ten-nguon-du-lieu-tren-moi-giao-dien-va-dau-r.md) | Accepted |
| 010 | [Chỉ dùng gói miễn phí (free tier / OSS), không dịch vụ trả phí](ADR-010-chi-dung-goi-mien-phi-free-tier-oss-khong-dich-v.md) | Accepted |
| 011 | [Paper trading (tiền ảo) trước live, có hash-chain và tiêu chí tự đặt](ADR-011-paper-trading-tien-ao-truoc-live-co-hash-chain-v.md) | Accepted |
| 012 | [Hai EA tách biệt: EA đọc và EA thực thi (thiết kế, chưa cài đặt)](ADR-012-hai-ea-tach-biet-ea-doc-va-ea-thuc-thi-thiet-ke.md) | Proposed |
| 013 | [Lệnh ký bất đối xứng Ed25519; dữ liệu vào ký HMAC (thiết kế)](ADR-013-lenh-ky-bat-doi-xung-ed25519-du-lieu-vao-ky-hmac.md) | Proposed |
| 014 | [Tách mạng, role DB hẹp, secret theo từng service](ADR-014-tach-mang-role-db-hep-secret-theo-tung-service.md) | Accepted |
| 015 | [Track-record chuyên gia: nói thẳng "chưa đủ mẫu" thay vì xếp hạng giả](ADR-015-track-record-chuyen-gia-noi-thang-chua-du-mau-th.md) | Accepted |
| 016 | [LLM cục bộ chỉ tóm tắt, hậu kiểm tất định, không công cụ](ADR-016-llm-cuc-bo-chi-tom-tat-hau-kiem-tat-dinh-khong-c.md) | Accepted |
| 017 | [Build, test, deploy chỉ trên VPS; laptop chỉ sửa file và git](ADR-017-build-test-deploy-chi-tren-vps-laptop-chi-sua-fi.md) | Accepted |

Mẫu cho ADR mới: sao chép một tệp, đánh số tiếp, giữ ba mục Bối cảnh / Quyết định / Hệ quả; thêm một dòng vào bảng trên.
