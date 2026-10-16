# ADR-004: Chỉ đọc trước, thực thi sau cổng pháp lý G1-G3

**Trạng thái:** Accepted (2026-10-11)

## Bối cảnh
Pháp lý ở Việt Nam chưa rõ: forex cho cá nhân (Nghị định 340/2025 phạt phái sinh ngoại hối không phép), UBCKNN 2023 về robot giao dịch chứng khoán, điều khoản broker về EA/VPS. Đặt lệnh sai gây thiệt hại tiền thật không hoàn tác.

## Quyết định
Hệ thống giai đoạn này **chỉ quan sát + mô phỏng**. Không có mã đặt/sửa/đóng lệnh ở bất kỳ đâu; có test chặn (`test_no_trading_code_anywhere`, `test_gateway_is_read_only`, kiểm tra gateway chỉ cho GET trừ whitelist `/v1/user/*`). Chuyển sang thực thi cần **cả ba cổng G1 (luật sư forex), G2 (công ty chứng khoán), G3 (broker ToS)** bằng văn bản, rồi đi theo thang L0 đến L4 trong `CONTROL_PLANE_DESIGN.md`.

## Hệ quả
- (+) Rủi ro pháp lý và tài chính của giai đoạn này gần bằng 0; thiết kế kênh lệnh được làm trước, không vội.
- (-) Người dùng không thể "bấm mua/bán" trong hệ thống; giá trị nằm ở theo dõi, cảnh báo, rủi ro, nhật ký.
- Việc cần người dùng: gửi hỏi pháp lý, chọn broker.
