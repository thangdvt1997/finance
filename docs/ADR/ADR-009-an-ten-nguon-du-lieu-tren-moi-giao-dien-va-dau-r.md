# ADR-009: Ẩn tên nguồn dữ liệu trên mọi giao diện và đầu ra

**Trạng thái:** Accepted (2026-10-12)

## Bối cảnh
Dữ liệu đến từ nhiều nguồn miễn phí/không chính thức; điều khoản của nhiều nguồn không cho phát hành lại, và tên nguồn không phải thông tin người dùng cần để ra quyết định.

## Quyết định
Mọi nội dung người dùng thấy (web, PDF/HTML, thông báo, bản tin, nhật ký) chỉ hiển thị **nội dung**. Bộ lọc trung tâm `tscommon.sources` (+ `sources.yaml`) được áp ở: gateway (middleware `HIDE_SOURCES`, kể cả WebSocket), alert-service (điểm phát cuối), reporter, track-record (nhãn trung lập, `entity_id` băm có muối), UI (lint `lint-sources.cjs`, kể cả từ điển en). Công cụ vận hành nội bộ (log, Prometheus, Gatus, Grafana, `docs/*`) **giữ nguyên** tên nguồn để chẩn đoán.

## Hệ quả
- (+) Giảm rủi ro điều khoản nguồn; nội dung nhất quán.
- (-) Khó chẩn đoán từ giao diện (phải dùng công cụ vận hành); danh sách tên cần bảo trì khi thêm nguồn (sửa `sources.yaml`).
- (-) Bộ lọc là heuristic, có thể sót; có test và lint nhưng không phải bảo đảm tuyệt đối.
