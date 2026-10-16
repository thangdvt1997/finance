# ADR-011: Paper trading (tiền ảo) trước live, có hash-chain và tiêu chí tự đặt

**Trạng thái:** Accepted (2026-10-11/12)

## Bối cảnh
Chiến lược trông tốt trên backtest thường thất bại khi chạy thật (quá khớp, thiên lệch sống sót). Cần bằng chứng khách quan, không thể sửa lén.

## Quyết định
`paper-trader` chạy chiến lược trên dữ liệu thật bằng tiền ảo: chỉ dùng nến đã đóng, khớp ở giá mở nến kế + chi phí giả định, risk engine tất định, kill-switch, **benchmark đối chứng**, strategy card (kể cả mục không đạt), phát hiện suy giảm (CUSUM), **hash-chain** cho lệnh/khớp/sự kiện/equity. Tiêu chí "đủ điều kiện xét duyệt": >=12 tuần, >=60 ngày dữ liệu, >=30 lệnh khớp, >=3 kỳ tái cân bằng, Sharpe >= 0, |MaxDD| <= 15%, chi phí <= 1,5x giả định... **Đạt = đáng xem xét tiếp, không phải được dùng tiền thật.** Không có bước tự động sang live.

## Hệ quả
- (+) Ngăn "tối ưu rồi chạy"; lịch sử mô phỏng có thể kiểm chứng.
- (-) Cần hàng năm dữ liệu mới có ý nghĩa thống kê; 12 tuần chưa đủ kết luận (xem HUONG_DAN_SU_DUNG mục 7).
- (-) Hash-chain không chống được người có toàn quyền DB tính lại cả chuỗi (giảm bằng neo ngoài + role chỉ INSERT/SELECT + trigger chặn UPDATE/DELETE).
- Kết quả nghiên cứu hiện tại: chiến lược xu hướng chậm đa tài sản Sharpe 0,55 nhưng không thắng 60/40; momentum cổ phiếu VN không có alpha - xem `docs/research/`.
