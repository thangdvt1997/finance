#!/usr/bin/env python3
"""Sinh 2 dashboard Grafana (JSON) từ mô tả ngắn gọn: slo-observability.json + resources-db.json.
Chạy:  python infra/grafana/gen_dashboards.py   (ghi vào infra/grafana/dashboards/). Chỉ dùng datasource Prometheus uid=prom.
Giữ generator trong repo để chỉnh panel bằng code thay vì sửa JSON tay; JSON sinh ra được commit và provisioning nạp trực tiếp."""
import json
import pathlib

OUT = pathlib.Path(__file__).parent / "dashboards"
DS = {"type": "prometheus", "uid": "prom"}
_id = [0]


def _nid():
    _id[0] += 1
    return _id[0]


def targets(exprs):
    out = []
    for i, e in enumerate(exprs):
        expr, legend = (e, "") if isinstance(e, str) else e
        t = {"datasource": DS, "expr": expr, "refId": chr(65 + i)}
        if legend:
            t["legendFormat"] = legend
        out.append(t)
    return out


def row(title, y):
    return {"type": "row", "title": title, "collapsed": False, "id": _nid(), "gridPos": {"h": 1, "w": 24, "x": 0, "y": y}, "panels": []}


def stat(title, expr, x, y, w=4, h=4, unit="none", thresholds=None, desc="", decimals=None, mappings=None):
    steps = thresholds or [{"color": "green", "value": None}]
    fc = {"defaults": {"unit": unit, "thresholds": {"mode": "absolute", "steps": steps}, "mappings": mappings or []}, "overrides": []}
    if decimals is not None:
        fc["defaults"]["decimals"] = decimals
    return {"type": "stat", "title": title, "description": desc, "id": _nid(), "datasource": DS, "gridPos": {"h": h, "w": w, "x": x, "y": y},
            "targets": targets([expr]), "fieldConfig": fc,
            "options": {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}, "colorMode": "background", "graphMode": "area", "textMode": "auto"}}


def ts(title, exprs, x, y, w=12, h=8, unit="none", desc="", stack=False, minv=None, maxv=None, thresholds=None):
    defaults = {"unit": unit, "custom": {"lineWidth": 1, "fillOpacity": 10 if not stack else 40, "showPoints": "never", "stacking": {"mode": "normal" if stack else "none"}}}
    if minv is not None:
        defaults["min"] = minv
    if maxv is not None:
        defaults["max"] = maxv
    if thresholds:
        defaults["thresholds"] = {"mode": "absolute", "steps": thresholds}
        defaults["custom"]["thresholdsStyle"] = {"mode": "line"}
    return {"type": "timeseries", "title": title, "description": desc, "id": _nid(), "datasource": DS, "gridPos": {"h": h, "w": w, "x": x, "y": y},
            "targets": targets(exprs), "fieldConfig": {"defaults": defaults, "overrides": []},
            "options": {"legend": {"displayMode": "list", "placement": "bottom"}, "tooltip": {"mode": "multi"}}}


def table(title, expr, x, y, w=12, h=8, unit="none", desc=""):
    t = targets([expr])
    t[0].update({"format": "table", "instant": True})
    return {"type": "table", "title": title, "description": desc, "id": _nid(), "datasource": DS, "gridPos": {"h": h, "w": w, "x": x, "y": y},
            "targets": t, "fieldConfig": {"defaults": {"unit": unit}, "overrides": []},
            "options": {"showHeader": True},
            "transformations": [{"id": "organize", "options": {"excludeByName": {"Time": True, "__name__": True, "job": True, "instance": True, "server": True}}}]}


def dash(uid, title, panels, desc=""):
    return {"uid": uid, "title": title, "description": desc, "tags": ["trading-system", "generated"], "timezone": "browser", "schemaVersion": 39, "version": 1,
            "refresh": "30s", "time": {"from": "now-6h", "to": "now"}, "editable": True, "panels": panels, "templating": {"list": []}, "annotations": {"list": []}, "links": []}


G, Y, R = {"color": "green", "value": None}, {"color": "yellow", "value": 1}, {"color": "red", "value": 2}
SEL = 'container_label_com_docker_compose_project="tradingsys"'
SVC = "container_label_com_docker_compose_service"


def slo_dashboard():
    p = []
    y = 0
    p.append(row("SLO (30 ngày) — xem docs/SLO.md", y)); y += 1
    pct = lambda lo, mid: [{"color": "red", "value": None}, {"color": "yellow", "value": lo}, {"color": "green", "value": mid}]
    p.append(stat("SLO-1 Sẵn có API (mục tiêu 99,5%)", "1 - ((sum(increase(gateway_http_requests_total{status=~\"5..\"}[30d])) or vector(0)) / clamp_min(sum(increase(gateway_http_requests_total[30d])), 1))", 0, y, 4, 4, "percentunit", pct(0.99, 0.995), "tỉ lệ request /v1 không 5xx", 3))
    p.append(stat("Ngân sách lỗi API còn lại", "1 - (((sum(increase(gateway_http_requests_total{status=~\"5..\"}[30d])) or vector(0)) / clamp_min(sum(increase(gateway_http_requests_total[30d])), 1)) / 0.005)", 4, y, 4, 4, "percentunit", [{"color": "red", "value": None}, {"color": "yellow", "value": 0.25}, {"color": "green", "value": 0.5}], "1 = chưa tiêu; <0 = đã vượt ngân sách 0,5%", 1))
    p.append(stat("SLO-2 p95 độ trễ API (5m)", "slo:api_latency_p95:5m", 8, y, 4, 4, "s", [G, {"color": "yellow", "value": 0.5}, {"color": "red", "value": 1.5}], "mục tiêu: 95% request <0,5s", 3))
    p.append(stat("SLO-2 request chậm >0,5s (6h)", "slo:api_slow_ratio:rate6h", 12, y, 4, 4, "percentunit", [G, {"color": "yellow", "value": 0.05}, {"color": "red", "value": 0.1}], "ngân sách 5%", 1))
    p.append(stat("SLO-3 Độ tươi dữ liệu 30d (mục tiêu 99%)", "avg_over_time(slo:data_fresh:crypto[30d])", 16, y, 4, 4, "percentunit", pct(0.95, 0.99), "canary crypto_ccxt: quote<120s & bar M1<300s", 2))
    p.append(stat("SLO-4 Bus không backlog (mục tiêu 99,9%)", "avg_over_time(slo:bus_ok[30d])", 20, y, 4, 4, "percentunit", pct(0.99, 0.999), "sw_stream_lag <1000", 3)); y += 4
    p.append(ts("Tỉ lệ lỗi 5xx vs ngân sách 0,5% (burn-rate: fast 14,4x / slow 6x)", [("slo:api_error_ratio:rate5m", "5m"), ("slo:api_error_ratio:rate1h", "1h"), ("slo:api_error_ratio:rate6h", "6h")], 0, y, 12, 8, "percentunit", thresholds=[G, {"color": "red", "value": 0.005}]))
    p.append(ts("Độ trễ API p50/p95/p99 (gateway_http_request_seconds)", [("histogram_quantile(0.5, sum by (le) (rate(gateway_http_request_seconds_bucket[5m])))", "p50"), ("slo:api_latency_p95:5m", "p95"), ("histogram_quantile(0.99, sum by (le) (rate(gateway_http_request_seconds_bucket[5m])))", "p99")], 12, y, 12, 8, "s", "Chỉ có dữ liệu sau khi api-gateway build bản có histogram", thresholds=[G, {"color": "red", "value": 0.5}])); y += 8
    p.append(row("Độ tươi dữ liệu theo nguồn (từ DB, postgres-exporter)", y)); y += 1
    p.append(ts("Tuổi bar mới nhất theo nguồn (M1)", ['ts_data_bars_age_seconds{tf="M1"}'], 0, y, 8, 8, "s", "FX nghỉ cuối tuần nên tuổi lớn là bình thường; crypto phải <5 phút", ))
    p.append(ts("Tuổi bar mới nhất theo khung (crypto_ccxt)", ['ts_data_bars_age_seconds{source="crypto_ccxt"}'], 8, y, 8, 8, "s"))
    p.append(ts("Tuổi quote / tin trong DB", [("ts_data_quotes_age_seconds", "quote {{source}}"), ("ts_data_news_age_seconds", "tin mới nhất")], 16, y, 8, 8, "s")); y += 8
    p.append(ts("Bar xuất bản / phút theo provider (market-collector)", ["sum by (provider) (rate(mc_bars_published_total[5m])) * 60"], 0, y, 8, 8, "short"))
    p.append(ts("Lỗi fetch / 15 phút theo provider", ["sum by (provider) (increase(mc_fetch_errors_total[15m]))"], 8, y, 8, 8, "short"))
    p.append(ts("Tin xuất bản / giờ theo nguồn (top)", ["topk(8, sum by (source) (increase(nc_items_published_total[1h])))"], 16, y, 8, 8, "short")); y += 8
    p.append(row("Bus Redis Streams / DLQ / pending", y)); y += 1
    p.append(ts("Độ dài stream (redis_stream_length)", ["redis_stream_length"], 0, y, 8, 8, "short"))
    p.append(ts("Consumer-group lag", ["max by (stream, group) (redis_stream_group_lag)"], 8, y, 8, 8, "short", thresholds=[G, {"color": "red", "value": 5000}]))
    p.append(ts("Pending (đã giao, chưa ack)", ["max by (stream, group) (redis_stream_group_messages_pending)", ("sw_stream_pending", "storage-writer pending")], 16, y, 8, 8, "short")); y += 8
    p.append(stat("DLQ hiện có", 'redis_stream_length{stream="dlq"}', 0, y, 4, 4, "short", [G, {"color": "yellow", "value": 1}, {"color": "red", "value": 100}], "sự kiện lỗi chờ xem xét"))
    p.append(stat("Tuổi sự kiện cũ nhất chưa tiêu thụ", "max(sw_stream_lag_age_seconds)", 4, y, 4, 4, "s", [G, {"color": "yellow", "value": 3600}, {"color": "red", "value": 43200}], "trim MAXLEN ~100000 có thể xoá nếu >12h"))
    p.append(ts("Sự kiện xử lý / giây (storage-writer) theo kết quả", ["sum by (result) (rate(sw_events_total[5m]))"], 8, y, 8, 4, "ops"))
    p.append(ts("Lỗi ghi DB/Redis (storage-writer)", ["sum by (kind) (increase(sw_errors_total[15m]))"], 16, y, 8, 4, "short")); y += 4
    p.append(row("Sao lưu / phục hồi", y)); y += 1
    p.append(stat("Tuổi backup thành công gần nhất", "time() - ts_backup_last_success_timestamp", 0, y, 4, 4, "s", [G, {"color": "yellow", "value": 86400}, {"color": "red", "value": 93600}], "cảnh báo >26h"))
    p.append(stat("Tuổi restore-test", "time() - ts_restore_test_last_success_timestamp", 4, y, 4, 4, "s", [G, {"color": "yellow", "value": 604800}, {"color": "red", "value": 691200}], "cảnh báo >8 ngày"))
    p.append(stat("Tuổi base backup (PITR)", "time() - ts_basebackup_last_success_timestamp", 8, y, 4, 4, "s", [G, {"color": "yellow", "value": 691200}, {"color": "red", "value": 1209600}]))
    p.append(stat("Tuổi bản off-site", "clamp_min(time() - ts_offsite_last_success_timestamp, 0)", 12, y, 4, 4, "s", [{"color": "red", "value": None}], "ts_offsite=0 nghĩa là CHƯA cấu hình off-site (đỏ)"))
    p.append(stat("WAL lưu trữ lỗi (24h)", "increase(pg_stat_archiver_failed_count[24h])", 16, y, 4, 4, "short", [G, {"color": "red", "value": 1}]))
    p.append(stat("Tuổi WAL archive cuối", "time() - pg_stat_archiver_last_archive_time", 20, y, 4, 4, "s", [G, {"color": "yellow", "value": 600}, {"color": "red", "value": 1800}], "archive_timeout=300s")); y += 4
    p.append(row("Mô phỏng (paper) & rủi ro", y)); y += 1
    p.append(ts("paper-trader: tuổi chu kỳ thành công", ["time() - paper_last_success_timestamp"], 0, y, 8, 7, "s"))
    p.append(ts("paper-trader: chu kỳ / phút theo trạng thái", ["sum by (status) (rate(paper_cycles_total[5m])) * 60"], 8, y, 8, 7, "short"))
    p.append(ts("risk-monitor: mức ký quỹ %, drawdown từ đỉnh %", [("risk_margin_level_pct", "margin% {{account}}"), ("risk_dd_from_peak_pct", "dd% {{account}}")], 16, y, 8, 7, "short")); y += 7
    p.append(table("Cảnh báo đang bắn (Prometheus)", 'ALERTS{alertstate="firing"}', 0, y, 24, 6))
    return dash("ts-slo", "SLO & độ tươi dữ liệu", p, "SLO API/độ tươi/bus, bus & DLQ, backup, paper & rủi ro. Sinh bởi infra/grafana/gen_dashboards.py")


def resources_dashboard():
    p = []
    y = 0
    p.append(row("Container (cAdvisor, chỉ project tradingsys)", y)); y += 1
    p.append(ts("RAM working set theo service", [(f"sum by ({SVC}) (container_memory_working_set_bytes{{{SEL}}})", "{{" + SVC + "}}")], 0, y, 12, 8, "bytes"))
    p.append(ts("RAM / giới hạn (>0,9 = nguy cơ OOM)", [(f"container_memory_working_set_bytes{{{SEL}}} / (container_spec_memory_limit_bytes{{{SEL}}} > 0)", "{{" + SVC + "}}")], 12, y, 12, 8, "percentunit", thresholds=[G, {"color": "red", "value": 0.9}])); y += 8
    p.append(ts("CPU (nhân) theo service", [(f"sum by ({SVC}) (rate(container_cpu_usage_seconds_total{{{SEL}}}[5m]))", "{{" + SVC + "}}")], 0, y, 12, 8, "short"))
    p.append(ts("CPU bị throttle (tỉ lệ chu kỳ)", [(f"sum by ({SVC}) (rate(container_cpu_cfs_throttled_periods_total{{{SEL}}}[5m])) / sum by ({SVC}) (rate(container_cpu_cfs_periods_total{{{SEL}}}[5m]))", "{{" + SVC + "}}")], 12, y, 12, 8, "percentunit")); y += 8
    p.append(ts("Mạng nhận/gửi (B/s)", [(f"sum by ({SVC}) (rate(container_network_receive_bytes_total{{{SEL}}}[5m]))", "rx {{" + SVC + "}}"), (f"-sum by ({SVC}) (rate(container_network_transmit_bytes_total{{{SEL}}}[5m]))", "tx {{" + SVC + "}}")], 0, y, 12, 8, "Bps"))
    p.append(ts("Đọc/ghi đĩa (B/s)", [(f"sum by ({SVC}) (rate(container_fs_reads_bytes_total{{{SEL}}}[5m]))", "read {{" + SVC + "}}"), (f"-sum by ({SVC}) (rate(container_fs_writes_bytes_total{{{SEL}}}[5m]))", "write {{" + SVC + "}}")], 12, y, 12, 8, "Bps")); y += 8
    p.append(table("Uptime container (giây)", f"time() - container_start_time_seconds{{{SEL}}}", 0, y, 24, 7, "s", "container nào uptime thấp bất thường = vừa restart/crash-loop")); y += 7
    p.append(row("PostgreSQL / TimescaleDB", y)); y += 1
    p.append(stat("pg_up", "pg_up", 0, y, 3, 4, "none", [{"color": "red", "value": None}, {"color": "green", "value": 1}]))
    p.append(stat("Kích thước DB", "pg_database_size_bytes{datname=\"ts\"}", 3, y, 3, 4, "bytes"))
    p.append(stat("Kết nối / max", "sum(pg_stat_activity_count) / max(pg_settings_max_connections)", 6, y, 3, 4, "percentunit", [G, {"color": "yellow", "value": 0.6}, {"color": "red", "value": 0.8}]))
    p.append(stat("Cache hit", "sum(rate(pg_stat_database_blks_hit{datname=\"ts\"}[5m])) / clamp_min(sum(rate(pg_stat_database_blks_hit{datname=\"ts\"}[5m])) + sum(rate(pg_stat_database_blks_read{datname=\"ts\"}[5m])), 1)", 9, y, 3, 4, "percentunit", [{"color": "red", "value": None}, {"color": "yellow", "value": 0.9}, {"color": "green", "value": 0.98}]))
    p.append(ts("Giao dịch / giây, rollback", [("sum(rate(pg_stat_database_xact_commit{datname=\"ts\"}[5m]))", "commit/s"), ("sum(rate(pg_stat_database_xact_rollback{datname=\"ts\"}[5m]))", "rollback/s")], 12, y, 12, 4, "ops")); y += 4
    p.append(ts("Kết nối theo trạng thái", ["sum by (state) (pg_stat_activity_count)"], 0, y, 8, 7, "short"))
    p.append(ts("Dung lượng các bảng lớn (pg_stat_user_tables)", [("pg_stat_user_tables_n_live_tup", "{{relname}} dòng")], 8, y, 8, 7, "short", "nén/retention: docs/DATA_RETENTION.md"))
    p.append(ts("Chunk đã nén / tổng", [("ts_hypertable_chunks_compressed", "nén {{name}}"), ("ts_hypertable_chunks", "tổng {{name}}")], 16, y, 8, 7, "short")); y += 7
    p.append(ts("Tuple ghi/giây (insert/update)", ["sum(rate(pg_stat_database_tup_inserted{datname=\"ts\"}[5m]))", "sum(rate(pg_stat_database_tup_updated{datname=\"ts\"}[5m]))"], 0, y, 12, 7, "ops"))
    p.append(ts("WAL: tuổi archive cuối, lỗi", [("time() - pg_stat_archiver_last_archive_time", "tuổi WAL archive (s)"), ("pg_stat_archiver_failed_count", "lỗi tích luỹ")], 12, y, 12, 7, "short")); y += 7
    p.append(row("Redis", y)); y += 1
    p.append(stat("redis_up", "redis_up", 0, y, 3, 4, "none", [{"color": "red", "value": None}, {"color": "green", "value": 1}]))
    p.append(stat("Bộ nhớ / maxmemory", "redis_memory_used_bytes / redis_memory_max_bytes", 3, y, 3, 4, "percentunit", [G, {"color": "yellow", "value": 0.6}, {"color": "red", "value": 0.8}]))
    p.append(stat("Client", "redis_connected_clients", 6, y, 3, 4))
    p.append(stat("Key", "sum(redis_db_keys)", 9, y, 3, 4))
    p.append(ts("Lệnh/giây", ["rate(redis_commands_processed_total[5m])"], 12, y, 6, 4, "ops"))
    p.append(ts("Bộ nhớ dùng (B)", ["redis_memory_used_bytes", "redis_memory_max_bytes"], 18, y, 6, 4, "bytes")); y += 4
    p.append(row("Host (node_exporter có sẵn trên VPS dùng chung)", y)); y += 1
    p.append(ts("Đĩa trống % ( / )", ['node_filesystem_avail_bytes{job="node",mountpoint="/",fstype!~"tmpfs|overlay"} / node_filesystem_size_bytes{job="node",mountpoint="/",fstype!~"tmpfs|overlay"}'], 0, y, 8, 7, "percentunit"))
    p.append(ts("RAM khả dụng %", ['node_memory_MemAvailable_bytes{job="node"} / node_memory_MemTotal_bytes{job="node"}'], 8, y, 8, 7, "percentunit"))
    p.append(ts("Load average", ['node_load1{job="node"}', 'node_load5{job="node"}'], 16, y, 8, 7, "short")); y += 7
    p.append(row("Prometheus / ops", y)); y += 1
    p.append(ts("Số series đang hoạt động / mẫu nạp mỗi giây", [("prometheus_tsdb_head_series", "series"), ("rate(prometheus_tsdb_head_samples_appended_total[5m])", "mẫu/s")], 0, y, 12, 7, "short"))
    p.append(ts("Thời gian scrape theo job", ["max by (job) (scrape_duration_seconds)"], 12, y, 12, 7, "s"))
    return dash("ts-resources", "Tài nguyên: container, Postgres, Redis, host", p, "cAdvisor + postgres-exporter + redis-exporter + node. Sinh bởi infra/grafana/gen_dashboards.py")




def cache_dashboard():
    p = []
    y = 0
    HR = 'sum(rate(gateway_cache_requests_total{result=~"hit|stale"}[5m])) / clamp_min(sum(rate(gateway_cache_requests_total{result=~"hit|stale|miss"}[5m])), 1e-9)'
    p.append(row("Tầng cache gateway (Redis) — docs/PERFORMANCE.md", y)); y += 1
    p.append(stat("Hit ratio (5m)", HR, 0, y, 4, 4, "percentunit", [{"color": "red", "value": None}, {"color": "yellow", "value": 0.3}, {"color": "green", "value": 0.6}], "hit+stale / (hit+stale+miss)"))
    p.append(stat("Cache bật", "max(gateway_cache_enabled)", 4, y, 3, 4, "none", [{"color": "red", "value": None}, {"color": "green", "value": 1}], "0 = CACHE_ENABLED=0 hoặc thiếu REDIS_CACHE_PASSWORD"))
    p.append(stat("Mạch hở (fail-open)", "max(gateway_cache_circuit_open)", 7, y, 3, 4, "none", [{"color": "green", "value": None}, {"color": "red", "value": 1}], "1 = Redis cache lỗi, đang đi thẳng xuống app"))
    p.append(stat("p95 phục vụ cache hit", 'histogram_quantile(0.95, sum by (le) (rate(gateway_cache_request_seconds_bucket{result="hit"}[5m])))', 10, y, 4, 4, "s", None, "", 4))
    p.append(stat("p95 miss", 'histogram_quantile(0.95, sum by (le) (rate(gateway_cache_request_seconds_bucket{result="miss"}[5m])))', 14, y, 4, 4, "s", None, "", 3))
    p.append(stat("Lỗi cache/s", "sum(rate(gateway_cache_errors_total[5m]))", 18, y, 3, 4, "ops", [G, {"color": "yellow", "value": 0.01}, {"color": "red", "value": 0.1}]))
    p.append(stat("Tỉ lệ nén", "sum(rate(gateway_cache_stored_raw_bytes_total[15m])) / clamp_min(sum(rate(gateway_cache_stored_bytes_total[15m])), 1e-9)", 21, y, 3, 4, "none", None, "raw/nén (zstd)", 1)); y += 4
    p.append(ts("Request theo kết quả (/s)", ["sum by (result) (rate(gateway_cache_requests_total[5m]))"], 0, y, 8, 8, "ops", "hit | stale (SWR) | miss | bypass (không cache được/mạch hở) | error (fail-open)"))
    p.append(ts("Hit ratio theo policy", [f'sum by (policy) (rate(gateway_cache_requests_total{{result=~"hit|stale"}}[5m])) / clamp_min(sum by (policy) (rate(gateway_cache_requests_total{{result=~"hit|stale|miss"}}[5m])), 1e-9)'], 8, y, 8, 8, "percentunit", minv=0, maxv=1))
    p.append(ts("Độ trễ tầng cache p50/p95/p99 (hit)", [(f'histogram_quantile({q}, sum by (le) (rate(gateway_cache_request_seconds_bucket{{result="hit"}}[5m])))', f"p{int(q*100)}") for q in (0.5, 0.95, 0.99)], 16, y, 8, 8, "s")); y += 8
    p.append(row("Độ trễ API (toàn bộ, kể cả hit) + Redis cache", y)); y += 1
    p.append(ts("API p95 theo route (s)", ["histogram_quantile(0.95, sum by (le, path) (rate(gateway_http_request_seconds_bucket[5m])))"], 0, y, 12, 8, "s", "SLO-2: 95% < 500ms (docs/SLO.md)", thresholds=[{"color": "green", "value": None}, {"color": "red", "value": 0.5}]))
    p.append(ts("Lệnh Redis cache p95 (s)", ['histogram_quantile(0.95, sum by (le, op) (rate(gateway_cache_redis_seconds_bucket[5m])))'], 12, y, 12, 8, "s")); y += 8
    p.append(row("Vô hiệu hoá / làm mới / chống stampede", y)); y += 1
    p.append(ts("Vô hiệu hoá theo sự kiện bus (/s)", ["sum by (domain) (rate(gateway_cache_invalidations_total[5m]))"], 0, y, 8, 7, "ops"))
    p.append(ts("Làm mới nền (/s)", ["sum by (kind) (rate(gateway_cache_refresh_total[5m]))"], 8, y, 8, 7, "ops", "swr = bản stale được làm mới; warm = refresh-ahead (precompute)"))
    p.append(ts("Request chờ chung 1 lần tính (single-flight, /s)", ["rate(gateway_cache_singleflight_waits_total[5m])"], 16, y, 8, 7, "ops")); y += 7
    p.append(ts("Lỗi cache theo loại (/s)", ["sum by (kind) (rate(gateway_cache_errors_total[5m]))"], 0, y, 12, 7, "ops", "mget/set/bump = Redis; decode = entry hỏng; serve/warm/invalidate = lỗi nội bộ (đều fail-open)"))
    p.append(ts("Byte ghi vào cache (B/s, sau nén)", ["rate(gateway_cache_stored_bytes_total[5m])"], 12, y, 12, 7, "Bps"))
    return dash("ts-cache-latency", "Cache & Latency", p, "Hit ratio, độ trễ, fail-open, vô hiệu hoá của tầng cache gateway + độ trễ API. Sinh bởi infra/grafana/gen_dashboards.py")


if __name__ == "__main__":
    for name, d in (("slo-observability.json", slo_dashboard()), ("resources-db.json", resources_dashboard()), ("cache-latency.json", cache_dashboard())):
        (OUT / name).write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        print("ghi", OUT / name, len(d["panels"]), "panel")
