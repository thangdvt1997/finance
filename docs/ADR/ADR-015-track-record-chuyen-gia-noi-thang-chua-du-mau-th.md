# ADR-015: Track-record chuyên gia: nói thẳng "chưa đủ mẫu" thay vì xếp hạng giả

**Trạng thái:** Accepted (2026-10-12)

## Bối cảnh
Nghiên cứu (`INFO_SIGNALS_STUDY.md`) cho thấy ý kiến công khai thường không vượt ngẫu nhiên; các bảng xếp hạng chuyên gia thương mại thường dựa vào danh tiếng/quảng cáo và thiên lệch sống sót.

## Quyết định
Chấm bằng **lợi suất thật** với chống look-ahead (vào ở nến sau thời điểm *ta biết*), mẫu độc lập, Wilson + bootstrap + kiểm định hoán vị, hiệu chỉnh đa kiểm định BH-FDR, chỉ xếp hạng khi **n >= 30**, co Beta, sổ cái hash-chain. Đồng thuận có trọng số hiển thị rõ khi chỉ là "đếm phiếu".

## Hệ quả
- (+) Không tạo niềm tin sai; kết quả tái lập được.
- Kết quả hiện tại: **0/99 entity vượt baseline** - đúng như kỳ vọng từ nghiên cứu; người dùng thấy nhiều nhãn "chưa đủ mẫu".
- (-) Giao diện kém "hấp dẫn" hơn bảng xếp hạng thương mại; chấp nhận.
