# ADR-013: Lệnh ký bất đối xứng Ed25519; dữ liệu vào ký HMAC (thiết kế)

**Trạng thái:** Proposed (CONTROL_PLANE_DESIGN ADR-C2) - phần HMAC đã triển khai

## Bối cảnh
Dữ liệu EA gửi lên cần xác thực nguồn (đã làm bằng HMAC đối xứng vì bridge phải tự tính được). Lệnh đi xuống cần mạnh hơn: nếu bridge/master bị chiếm, kẻ tấn công không được tự tạo lệnh hợp lệ.

## Quyết định
**Ingest (đã chạy):** HMAC mỗi gói, secret riêng từng tài khoản, bật mặc định, chữ ký sai/thiếu cho 401. **Lệnh (thiết kế):** envelope lệnh ký **Ed25519** bằng khoá ký tách khỏi bridge (bridge không thể giả lệnh); EA xác minh chữ ký, nonce chống phát lại, state machine lệnh idempotent, đối soát vị thế khi khởi động; risk engine tất định (không LLM, fail-closed) chạy trước khi lệnh tới EA.

## Hệ quả
- (+) Chiếm bridge không đủ để ra lệnh.
- (-) Cài Ed25519 trong MQL chưa xác minh khả thi (ghi trong mục rủi ro mở của tài liệu thiết kế).
- Phần lệnh **chưa cài đặt**.
