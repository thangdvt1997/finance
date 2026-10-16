# ADR-003: EA chủ động đẩy dữ liệu ra (outbound), không mở cổng vào

**Trạng thái:** Accepted (2026-10-11, EA v1.1 2026-10-12)

## Bối cảnh
Cần lấy số dư/vị thế/giá từ terminal MT4 và MT5 của client. MT4 không có API Python chính hãng; MT5 có package nhưng chỉ Windows. Mở cổng vào máy client hoặc vào VPS làm tăng bề mặt tấn công; phương án ZeroMQ/dwxconnect bị loại (mở cổng, dự án lưu trữ).

## Quyết định
Viết **một EA chỉ đọc cho MQL4 và MQL5** (chung `Include/MTAgent/Core.mqh`) gọi **ra ngoài** bằng `WebRequest` HTTPS tới `mt-bridge` mỗi `SendIntervalSec` giây: snapshot tài khoản, vị thế, lệnh chờ, quote, nến đã đóng, deal đã đóng. Mỗi gói ký **HMAC**; ghép cặp bằng `PairCode`; xử lý 202 pending / 403 suspended / 429.

## Hệ quả
- (+) Không cần mở cổng; một giao thức cho cả MT4/MT5; client chỉ cần cho phép URL trong Options.
- (-) Độ trễ cấp giây (theo chu kỳ gửi); `WebRequest` đồng bộ, dễ timeout, nên bắt buộc idempotent.
- (-) Mỗi terminal chỉ một tài khoản; N tài khoản = N terminal.
- Giới hạn trung thực: EA đã biên dịch sạch (MetaEditor MT4 build 1492, MT5 build 6253) và chạy trong lab Wine, **chưa thử với tài khoản broker thật**.
