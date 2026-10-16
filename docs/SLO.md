# SLO — mục tiêu mức dịch vụ và luật burn-rate (2026-10-12)

Phạm vi: nền tảng READ-ONLY + paper. Chưa có người dùng trả tiền nên SLO ở mức "kỷ luật vận hành", không phải cam kết hợp đồng. Số đo lấy từ Prometheus (giữ 30 ngày); luật ở `infra/prometheus/rules_slo.yml`; dashboard `SLO & độ tươi dữ liệu` (uid `ts-slo`, sinh bởi `infra/grafana/gen_dashboards.py`).

## 1. Bốn SLO
| # | SLO | SLI (cách đo) | Mục tiêu / 30 ngày | Ngân sách lỗi |
|---|---|---|---|---|
| 1 | Sẵn có API | `1 - 5xx / tất cả` của `gateway_http_requests_total` (route /v1) | 99,5% | 0,5% request (~3,6 giờ nếu lỗi toàn phần) |
| 2 | Độ trễ API | tỉ lệ request /v1 hoàn tất ≤ 0,5s từ histogram `gateway_http_request_seconds` (p95 hiển thị: `slo:api_latency_p95:5m`) | 95% request ≤ 500ms | 5% request chậm |
| 3 | Độ tươi dữ liệu | canary nguồn luôn-mở `crypto_ccxt`: tuổi quote trong DB < 120s VÀ tuổi bar M1 < 300s (`ts_data_quotes_age_seconds`, `ts_data_bars_age_seconds` từ postgres-exporter truy vấn thẳng DB, nên bắt cả lỗi bus->DB) | 99% thời gian | 1% (~7,2 giờ) |
| 4 | Bus không tồn đọng | `max(sw_stream_lag) < 1000` (storage-writer) | 99,9% thời gian | 0,1% (~43 phút) |

Vì sao canary crypto cho độ tươi: FX/chứng khoán nghỉ cuối tuần/ngoài phiên nên "cũ" là bình thường; crypto chạy 24/7 nên là phép thử không nhiễu cho toàn đường ống collector -> bus -> storage-writer -> DB. Độ tươi theo từng nguồn/khung vẫn hiển thị trong dashboard (`ts_data_bars_age_seconds{source,tf}`) và có luật riêng: `DataSourceStaleQuotes`, `DataSourceStaleBarsM1`, `NewsIngestStale`.

## 2. Luật burn-rate (Google SRE Workbook, nhiều cửa sổ)
`burn = tỉ lệ lỗi / ngân sách`. Báo khi cả cửa sổ dài lẫn ngắn cùng vượt (tránh báo lâu sau khi đã hết lỗi):
| Mức | Cửa sổ | Hệ số | Ý nghĩa | Severity |
|---|---|---|---|---|
| Fast burn | 1h và 5m | 14,4x (API sẵn có), 6x (độ trễ), 14,4x (độ tươi), 14,4x (bus) | hết ngân sách 30 ngày trong ~2 ngày | critical |
| Slow burn | 6h và 30m | 6x (sẵn có), 2x (độ trễ), 6x (độ tươi) | hết ngân sách trong ~5 ngày | warning |
Chốt tối thiểu: chỉ báo SLO API khi `slo:api_requests:rate5m > 0.02` (≥ 1 request/50s) để tránh báo giả lúc không có lưu lượng. Cảnh báo đi theo đường cũ: Prometheus -> Alertmanager -> alert-service -> Telegram/ntfy (+ Gatus độc lập).

## 3. Quy trình khi ngân sách cạn
1. Fast burn: xử lý ngay (rollback `infra/ops/rollback.sh` nếu do release vừa deploy).
2. Slow burn: lập việc trong tuần; không deploy tính năng mới vào service liên quan cho tới khi tỉ lệ lỗi về dưới ngưỡng.
3. Ngân sách 30 ngày đã vượt: đóng băng thay đổi không phải sửa lỗi; viết post-mortem ngắn (nguyên nhân, phát hiện bao lâu, vì sao luật không bắt sớm hơn).

## 4. Giới hạn đã biết
- Histogram độ trễ chỉ có từ lúc api-gateway chạy bản có `HTTP_LAT` (app.py). Trước đó các panel độ trễ rỗng.
- Số liệu SLO 30 ngày cần Prometheus giữ đủ 30 ngày (`--storage.tsdb.retention.time=30d`); khi Prometheus bị tạo lại volume, SLO bắt đầu lại từ 0.
- SLO sẵn có đo ở gateway, không đo từ ngoài (không có probe blackbox qua tunnel). Gatus kiểm `/healthz` nội bộ mỗi 30s; probe từ ngoài cần domain/tunnel cố định (hoãn).
- Mới có 1 node nên "sẵn có" không bao gồm sự cố host; khi host chết thì cả Prometheus chết (cần máy giám sát thứ hai để cảnh báo — hoãn, cần máy/tiền).
