# ADR-016: LLM cục bộ chỉ tóm tắt, hậu kiểm tất định, không công cụ

**Trạng thái:** Accepted (2026-10-12)

## Bối cảnh
Bản tin AI hữu ích nhưng LLM có thể bịa số; gói 0 đồng và yêu cầu riêng tư loại API trả phí.

## Quyết định
`briefing-llm` (llama.cpp, Qwen3.5-9B Q4_K_M, Apache-2.0) chạy **trong mạng `ops` không internet**, read-only, không truyền công cụ/URL, đầu ra bị ràng buộc bằng JSON-schema grammar. `briefing` đưa vào dữ liệu có đánh số và **hậu kiểm tất định** từng ý (phải trích dẫn đúng số/mã tham chiếu); lịch 06:15 và 16:30 giờ VN x hai phạm vi (Việt Nam, Quốc tế). LLM không có đường nào tới lệnh giao dịch.

## Hệ quả
- (+) Riêng tư, miễn phí, hạn chế hallucination.
- (-) Chậm (~3-3,5 phút/bản tin, CPU) và tốn 16 GB RAM; chỉ phù hợp bản tin theo lịch.
- Mô hình hạn chế giấy phép (Gemma/Llama) không dùng.
