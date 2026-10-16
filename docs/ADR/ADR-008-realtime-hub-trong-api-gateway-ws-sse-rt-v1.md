# ADR-008: Realtime hub trong api-gateway (WS/SSE rt.v1)

**Trạng thái:** Accepted (2026-10-12)

## Bối cảnh
Giao diện cần giá/nến/tài khoản/tin cập nhật tức thời cho hàng trăm kết nối mà không đọc Redis hay DB riêng cho từng kết nối; cần chịu được client chậm và mất kết nối.

## Quyết định
Một **Hub** trong gateway: MỘT vòng XREAD cho mọi kết nối, `QuoteEngine` gộp nguồn theo ưu tiên + đánh dấu cũ/im lặng, nến đang hình thành, tuần tự hoá một lần cho mỗi topic, flush 50 ms. Topic `q:`, `c:`, `a:`, `e:`, `n`, `sys` (chỉ master). Hai loại: latest-state (gộp, chỉ giữ bản mới nhất) và reliable (có `seq`, ring 256, resume được). Kết nối sống tối đa 30/60 phút rồi buộc `reauth`; có `kick` thu hồi tức thì. SDK dùng chung `realtime.js` (hai bản byte-giống ở web-ui và client-ui). `/v1/stream` cũ giữ để tương thích.

## Hệ quả
- (+) Tải gateway không phụ thuộc số kết nối; client chậm bị đóng thay vì làm nghẽn.
- (-) Hub nằm trong một tiến trình gateway (một instance): scale ngang cần chia topic/bus riêng.
- (-) Hai bản SDK phải giữ đồng bộ bằng `cmp`.
