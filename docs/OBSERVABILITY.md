# OBSERVABILITY — metric, log, trace, SLO (2026-10-12)

## 1. Thành phần
| Lớp | Công cụ (OSS, 0 đồng) | Vị trí | Ghi chú |
|---|---|---|---|
| Metric ứng dụng | `prometheus_client` trong mọi service, `/metrics` port 8000 | scrape job `services` (14 service) | analytics, nlp, paper-trader, journal, vn-market đã được thêm 2026-10-12 |
| Metric Postgres | `postgres-exporter` v0.18.1 (role `ts_monitor`, pg_monitor + SELECT hẹp) | job `postgres` (60s) | `prometheus/pg_queries.yaml`: tuổi bar/quote/tin THEO NGUỒN, chunk nén, bão cảnh báo |
| Metric Redis | `redis-exporter` v1.80.1 (ACL `ts_metrics`, không đọc dữ liệu) | job `redis` | độ dài stream, group lag, pending, DLQ, bộ nhớ |
| Metric container | `cAdvisor` v0.53.0 qua `docker-socket-proxy` (chỉ GET) | job `cadvisor` (30s) | `metric_relabel_configs` chỉ giữ project `tradingsys` — không kéo series container của hệ thống khác trên host dùng chung |
| Backup | `textfile-exporter` (node_exporter thứ hai, chỉ textfile) đọc `/var/lib/tradingsys-backup/backup.prom` | job `backup` | `ts_backup_last_success_timestamp`, restore-test, base backup, PITR, off-site |
| Probe | Gatus (đã có) + `/metrics` | job `gatus` | `gatus_results_endpoint_success` |
| Host | node_exporter CÓ SẴN trên VPS | job `node` | không đụng |
| Log | Dozzle + docker log rotation | `tradingsys-dozzle` :8591 | xem mục 3 |
| Trace | Jaeger v2 + OpenTelemetry cho api-gateway | xem mục 4 | |
| Realtime | metric `rt_*` của hub (api-gateway) + `mtbridge_*` | dashboard `ts-realtime`, luật `rules_rt.yml` | xem mục 6 |
| Dashboard | Grafana 12.4 provisioning | `infra/grafana/dashboards/` | `ts-platform-health`, `ts-slo` (SLO & độ tươi), `ts-resources` (container/Postgres/Redis/host), market-overview |

## 2. Luật cảnh báo
- `prometheus/rules.yml` (21 luật: service down, bus lag/pending, NoNewBars, DLQ, host...) giữ nguyên.
- `prometheus/rules_slo.yml` (40 luật): recording `slo:*`, burn-rate nhiều cửa sổ cho 4 SLO (docs/SLO.md), độ tươi theo nguồn, Postgres/Redis/WAL/DLQ/backup/container (RAM >90% giới hạn, CPU throttle), paper & rủi ro.
- Kiểm tra cú pháp: `docker run --rm -v $PWD/infra/prometheus:/p:ro --entrypoint promtool prom/prometheus:v3.13.4 check rules /p/rules_slo.yml /p/rules.yml` (trên VPS). Trạng thái luật: `/api/v1/rules` (health=ok cho cả 61).
- Mọi cảnh báo đi: Alertmanager -> `alert-service /webhook/alertmanager` -> Telegram/ntfy + bảng `alerts`. Gatus có đường độc lập (cũng về alert-service).

## 3. Log tập trung — chọn phương án rẻ nhất có tìm kiếm
Đã so sánh: (a) Loki + Promtail/Alloy (~300 MB RAM, thêm 2 container, Promtail đã EOL 2026 nên phải dùng Grafana Alloy), (b) Dozzle (đã chạy, ~18 MB RAM, đọc log từ Docker API, có ô tìm kiếm/regex và theo dõi nhiều container cùng lúc). **Chọn (b)** vì ngoài phạm vi đang cần: log chỉ để điều tra sự cố trong vài ngày, khối lượng nhỏ. Bổ sung rẻ để Dozzle đủ dùng:
- Giữ log giới hạn: mỗi container tradingsys dùng driver `json-file` với `max-size 10m, max-file 3` (khai trong compose) => tối đa ~30 MB/container, không đầy đĩa.
- Log có cấu trúc: `tscommon.logsetup` ghi dòng chuẩn (thời gian, mức, logger), `trace_id` của Event có trong thông điệp để tìm theo sự kiện.
- Khi nào nên nâng lên Loki: cần lưu log >7 ngày, cần truy vấn thống kê trên log, hoặc >5 host. Đường nâng cấp: thêm `grafana/loki` + `grafana/alloy` (docker_sd qua docker-socket-proxy, filter project=tradingsys) và datasource Loki vào Grafana.

## 4. Trace (OpenTelemetry) — gateway -> DB/Redis/HTTP nội bộ
Đã triển khai 2026-10-12: `jaeger` (Jaeger v2, lưu RAM, UI `127.0.0.1:16686` qua SSH tunnel; datasource Grafana `jaeger`) nhận OTLP/HTTP `jaeger:4318`. api-gateway bật tracing bằng `OTEL_EXPORTER_OTLP_ENDPOINT` (mã `api_gateway/tracing.py`, mặc định no-op nếu thiếu biến), lấy mẫu 25%, bỏ /healthz /readyz /metrics; span FastAPI -> asyncpg (câu SQL, role ts_ro) -> redis -> httpx proxy. Đã kiểm: service `api-gateway` xuất hiện trong Jaeger với span SELECT. Tắt: bỏ biến trong compose. Chi phí: jaeger ≤512MB (thực tế vài chục MB).

## 5. Kiểm tra nhanh sau mỗi thay đổi
1. `docker ps` mọi container `(healthy)` (Gatus/docker-socket-proxy không có healthcheck vì image không có shell).
2. Prometheus: `http://127.0.0.1:9090/api/v1/targets` — mọi target `up` (23 target: 14 service + exporter + node...). Script: `/tmp`-style `chk` trong nhật ký hardening.
3. `/api/v1/rules`: không luật `health != ok`.
4. e2e: `bash tests/e2e/deploy.sh` rồi `cd /root/qa-e2e && sh run_remote.sh test_flow.py` (chấp nhận lỗi đã biết: `dlq/nhan-du-payload-sai` 14/12).

## 6. Realtime
Hub realtime (`api-gateway/realtime.py`) phát `rt_*`: kết nối/đăng ký/topic, sự kiện bus theo stream, độ trễ từng chặng (`rt_bus_to_gateway_seconds`, `rt_tick_to_gateway_seconds`, `rt_flush_seconds`, `rt_send_seconds`, `rt_client_net_seconds`, `rt_client_rtt_seconds`), tin/khung/byte gửi, bỏ tin (`rt_dropped_total{reason}`), đóng kết nối, symbol im lặng/stale, tuổi lần đọc bus cuối. mt-bridge thêm `mtbridge_ea_to_bridge_seconds` (gồm lệch đồng hồ EA), `mtbridge_ingest_seconds`, `mtbridge_publish_seconds{stream}`.
- Dashboard `ts-realtime` (sinh bằng `infra/grafana/gen_dashboard_rt.py` chạy trên VPS; file `dashboards/realtime.json`).
- Luật `prometheus/rules_rt.yml` (10 luật: RtHubStalled, RtNoQuotesWeekday, RtSilentSymbolsHigh, RtBusLagP95, RtClientNetP95High, RtSlowClientsClosing, RtDropRate, RtConnectionsNearCap, RtRejectedConnections, RtGatewayCpuHigh); file được mount riêng trong `docker-compose.ops.yml`, thêm luật mới cần recreate prometheus.
- Báo cáo p50/p95 từng chặng: `infra/perf/rt_latency_report.py` (xem đầu file để biết lệnh chạy trên VPS).


## 7. Feed toàn bộ cặp (126 forex + 10 kim loại + 26 chỉ số) — 2026-10-14
- Metric (tên thống nhất, A3 implement ở mt-bridge): `docs/handoff/FEED_ALL_contract.md` mục Metrics — `mtbridge_feed_ticks_total{class}`, `mtbridge_feed_symbol_last_quote_timestamp{symbol,class}`, `mtbridge_feed_symbols_expected{class}`, `mtbridge_feed_latency_seconds{class}` (histogram MT5->bridge), `mtbridge_feed_batches_total{result}`, `mtbridge_feed_reconnect_total{account}`, `mtbridge_feed_queue_depth`.
- Luật `prometheus/rules_feed.yml` (20 luật: 3 lịch, 7 recording `feed:*`, 10 cảnh báo `Feed*`). Mount riêng trong `docker-compose.ops.yml` (thêm luật mới cần `docker compose up -d prometheus`). Kiểm: `promtool check rules` như mục 2.
- Lịch phiên (UTC) đã mã hoá trong recording rule `feed:market_open{class}` nên cuối tuần/ngày lễ không báo giả: FX đóng T6 22:00 -> CN 22:00 (+30' ân hạn sau mở); kim loại thêm nghỉ 22:00-23:00 hằng ngày; chỉ số chỉ T2-T6 08:00-20:00; lễ 25/12, 1/1, 24/12 và 31/12 sau 21:00. Muốn đổi lịch: sửa nhóm `tradingsys-feed-calendar` (đã kiểm bằng instant query tại các mốc T4/T7/CN 22:10/22:40/T6 22:30/25-12).
- Cảnh báo: FeedFxNoQuotes (mất hết FX >120s, critical), FeedMetalNoQuotes, FeedIndexNoQuotes, FeedSymbolsSilentHigh (>25% symbol FX im >10 phút; danh sách bằng `topk(30, time()-mtbridge_feed_symbol_last_quote_timestamp{class="fx"})`), FeedTickRateLow (<5 tick/s), FeedLatencyP95High (>2s) / P50High (>0,75s), FeedReconnectStorm (>3 lần/10'), FeedEaOffline, FeedBatchesRejected. Luật chưa khớp khi metric chưa tồn tại (không dùng `absent`) nên deploy luật trước bridge không báo giả.
- Gatus: endpoint `feed-all-fx` (`ops/gatus.d/feed_all.yaml`) đọc recording rule `feed:ok` qua API Prometheus (1 = khoẻ hoặc thị trường đóng; 0 = mất feed FX >120s khi mở cửa); đường cảnh báo độc lập Alertmanager.
- Dashboard Grafana `ts-feed-all` ("Feed toàn bộ cặp", sinh bằng `grafana/gen_dashboard_feed.py`): số symbol có quote/kỳ vọng, tick/s, trễ p50/p95/p99, im lặng theo nhóm + bảng 25 symbol im lâu nhất, batch/reconnect, EA online.
- e2e: `tests/e2e/test_feed_all.py` (chỉ đọc; SKIP có lý do khi thị trường đóng hoặc feed mới chưa live; `FEED_ALL_REQUIRE=1` để bắt buộc).
