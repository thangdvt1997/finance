# ADR-012: Hai EA tách biệt: EA đọc và EA thực thi (thiết kế, chưa cài đặt)

**Trạng thái:** Proposed (CONTROL_PLANE_DESIGN ADR-C4, 2026-10-12)

## Bối cảnh
Khi (và nếu) vượt cổng G1-G3 cần gửi lệnh tới terminal client. Gộp mã thực thi vào EA chỉ đọc khiến mọi client đều mang mã thực thi và khó chứng minh "chỉ đọc".

## Quyết định
Giữ **EA đọc** (hiện tại) tách hẳn khỏi **EA thực thi** (tương lai, client **chọn tham gia riêng**). Client không opt-in thì không có mã thực thi trong terminal. EA thực thi **kéo** lệnh (long-poll HTTPS, không mở cổng - ADR-003), tự áp giới hạn cứng do **client giữ** (master chỉ thu hẹp, không nới), có kill-switch 4 tầng, duyệt từng lệnh ở bậc L2.

## Hệ quả
- (+) Bề mặt tấn công và tuân thủ tách biệt; lập luận "chỉ đọc" cho EA hiện tại vẫn đúng.
- (-) Hai thành phần phải bảo trì; client phải cài thêm khi muốn dùng.
- **Chưa có mã.** Là thiết kế để tránh làm sai khi tới lúc.
