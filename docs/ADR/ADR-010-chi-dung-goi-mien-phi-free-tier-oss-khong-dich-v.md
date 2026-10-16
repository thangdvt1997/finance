# ADR-010: Chỉ dùng gói miễn phí (free tier / OSS), không dịch vụ trả phí

**Trạng thái:** Accepted (2026-10-11)

## Bối cảnh
Dự án cá nhân, chưa có ngân sách dữ liệu. Dữ liệu trả phí (realtime chính thức, tự doanh, BCTC point-in-time) sẽ cải thiện chất lượng nhưng chưa cần để chứng minh giá trị.

## Quyết định
Mọi nguồn, công cụ, mô hình AI phải **miễn phí** (`FREE_STACK.md`): nguồn công khai, free tier có key đăng ký miễn phí (OANDA practice, Alpaca, Tiingo, FRED...), mô hình mở chạy cục bộ trên CPU, công cụ OSS tự host. Ưu tiên **tích hợp OSS thay vì viết lại** (`OSS_REUSE.md`); loại giấy phép ràng buộc (AGPL/BSL/Commons Clause...) được ghi rõ trong `THIRD_PARTY_ALL.md`.

## Hệ quả
- (+) Chi phí vận hành = một VPS.
- (-) Hạn chế đã biết: không giá realtime trong phiên cho cổ phiếu VN, không tự doanh, không BCTC lịch sử point-in-time, spread/slippage chỉ ước tính.
- (-) Nguồn miễn phí có thể đổi điều khoản bất cứ lúc nào; có thứ tự ưu tiên và dự phòng (`DATA_SOURCE_PRIORITY.md`).
