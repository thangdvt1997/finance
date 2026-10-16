#!/usr/bin/env python3
"""Sinh dashboard Grafana "Realtime" (uid ts-realtime) -> dashboards/realtime.json. Dùng helper của gen_dashboards.py.
Chạy trên VPS (không chạy local):  docker run --rm -v $PWD/infra/grafana:/g -w /g python:3.12-slim python gen_dashboard_rt.py"""
import json
import pathlib

from gen_dashboards import G, SEL, SVC, dash, row, stat, ts

OUT = pathlib.Path(__file__).parent / "dashboards" / "realtime.json"
Y1, R1 = {"color": "yellow", "value": 1}, {"color": "red", "value": 1}


def q(metric, p, by="le"):
    return f"histogram_quantile({p}, sum by ({by}) (rate({metric}_bucket[5m])))"


def lat(title, metric, x, y, w=8, h=7, desc="", thr=None):
    return ts(title, [(q(metric, p), f"p{int(p * 100)}") for p in (0.5, 0.95, 0.99)], x, y, w, h, "s", desc, thresholds=thr)


def build():
    p, y = [], 0
    p.append(row("Tổng quan realtime (api-gateway hub) — docs/REALTIME.md", y)); y += 1
    p.append(stat("Kết nối đang mở", "sum(rt_connections)", 0, y, 3, 4, "short", [G, {"color": "yellow", "value": 2000}, {"color": "red", "value": 2400}], "trần 2500"))
    p.append(stat("Tuổi lần đọc bus cuối", "time() - rt_hub_last_read_timestamp", 3, y, 3, 4, "s", [G, {"color": "yellow", "value": 10}, {"color": "red", "value": 30}], "RtHubStalled >30s", 1))
    p.append(stat("Symbol im lặng", "rt_silent_symbols", 6, y, 3, 4, "short", [G, {"color": "yellow", "value": 5}, {"color": "red", "value": 20}], "cuối tuần nhiều là bình thường"))
    p.append(stat("Symbol stale", "rt_stale_symbols", 9, y, 3, 4, "short", [G, {"color": "yellow", "value": 5}, {"color": "red", "value": 20}]))
    p.append(stat("Symbol theo dõi", "rt_symbols_tracked", 12, y, 3, 4, "short"))
    p.append(stat("Đăng ký / topic", "rt_subscriptions", 15, y, 3, 4, "short", desc="đăng ký topic đang hiệu lực"))
    p.append(stat("Topic hoạt động", "rt_topics_active", 18, y, 3, 4, "short"))
    p.append(stat("Bỏ tin overflow/s", 'sum(rate(rt_dropped_total{reason="overflow"}[5m])) or vector(0)', 21, y, 3, 4, "ops", [G, R1], "coalesced là gộp tick có chủ đích", 2)); y += 4
    p.append(row("Kết nối & đăng ký", y)); y += 1
    p.append(ts("Kết nối WS/SSE theo loại", ["sum by (kind) (rt_connections)"], 0, y, 8, 7, "short"))
    p.append(ts("Kết nối mới / s theo kết quả", ["sum by (result) (rate(rt_conn_attempts_total[5m]))"], 8, y, 8, 7, "ops", "capacity|user_limit = bị từ chối"))
    p.append(ts("Đóng kết nối bởi server theo lý do (/s)", ["sum by (reason) (rate(rt_closed_total[5m]))"], 16, y, 8, 7, "ops")); y += 7
    p.append(ts("Đăng ký & topic hoạt động", [("rt_subscriptions", "đăng ký"), ("rt_topics_active", "topic")], 0, y, 12, 7, "short"))
    p.append(ts("Kết nối vs trần 2500", [("sum(rt_connections)", "kết nối")], 12, y, 12, 7, "short", thresholds=[G, {"color": "yellow", "value": 2000}, {"color": "red", "value": 2500}])); y += 7
    p.append(row("Luồng dữ liệu", y)); y += 1
    p.append(ts("Sự kiện bus / s theo stream", ["sum by (stream) (rate(rt_bus_events_total[1m]))"], 0, y, 8, 7, "ops"))
    p.append(ts("Tin / khung gửi mỗi giây", [("rate(rt_messages_sent_total[1m])", "tin/s"), ("rate(rt_frames_sent_total[1m])", "khung/s")], 8, y, 8, 7, "ops"))
    p.append(ts("Byte gửi / s (trước nén)", ["rate(rt_bytes_sent_total[1m])"], 16, y, 8, 7, "Bps")); y += 7
    p.append(ts("Bỏ tin / s theo lý do", ["sum by (reason) (rate(rt_dropped_total[5m]))"], 0, y, 12, 7, "ops", "coalesced = gộp có chủ đích; overflow/rate/slow = mất tin"))
    p.append(ts("Tỷ lệ bỏ tin / tin gửi", [("sum by (reason) (rate(rt_dropped_total[5m])) / clamp_min(sum(rate(rt_messages_sent_total[5m])), 1e-9)", "{{reason}}")], 12, y, 12, 7, "percentunit")); y += 7
    p.append(row("Độ trễ từng chặng (p50 / p95 / p99)", y)); y += 1
    p.append(lat("EA -> bridge (mtbridge_ea_to_bridge_seconds)", "mtbridge_ea_to_bridge_seconds", 0, y, desc="now - batch.ts: GỒM lệch đồng hồ EA (skew riêng ở /health)"))
    p.append(lat("Bridge xử lý ingest (mtbridge_ingest_seconds)", "mtbridge_ingest_seconds", 8, y))
    p.append(ts("Bridge XADD theo stream (p95)", [(q("mtbridge_publish_seconds", 0.95, "le, stream"), "p95 {{stream}}")], 16, y, 8, 7, "s")); y += 7
    p.append(ts("Bus -> hub theo stream (p95)", [(q("rt_bus_to_gateway_seconds", 0.95, "le, stream"), "p95 {{stream}}")], 0, y, 8, 7, "s", "Event.ts -> hub đọc", thresholds=[G, {"color": "red", "value": 0.5}]))
    p.append(lat("Tick (giờ nguồn) -> hub (rt_tick_to_gateway_seconds)", "rt_tick_to_gateway_seconds", 8, y, desc="gồm lệch đồng hồ nguồn"))
    p.append(lat("Flush fan-out (rt_flush_seconds)", "rt_flush_seconds", 16, y, desc="throttle <=250ms là chủ đích, không tính ở đây")); y += 7
    p.append(lat("Gửi 1 khung ws.send (rt_send_seconds)", "rt_send_seconds", 0, y))
    p.append(lat("Mạng gateway -> trình duyệt (rt_client_net_seconds)", "rt_client_net_seconds", 8, y, desc="client báo, đã hiệu chỉnh offset", thr=[G, {"color": "red", "value": 1}]))
    p.append(lat("RTT ping/pong (rt_client_rtt_seconds)", "rt_client_rtt_seconds", 16, y)); y += 7
    p.append(row("Độ tươi quote & sức khoẻ hub", y)); y += 1
    p.append(ts("Symbol im lặng / stale / theo dõi", ["rt_silent_symbols", "rt_stale_symbols", "rt_symbols_tracked"], 0, y, 8, 8, "short"))
    p.append(ts("Top 10 tuổi quote theo symbol", ["topk(10, rt_quote_age_seconds)"], 8, y, 8, 8, "s", "chỉ symbol có người đăng ký hoặc im lặng"))
    p.append(ts("Tuổi lần đọc bus cuối", [("time() - rt_hub_last_read_timestamp", "giây")], 16, y, 8, 8, "s", thresholds=[G, {"color": "red", "value": 30}])); y += 8
    p.append(row("api-gateway: CPU / RAM (cAdvisor)", y)); y += 1
    gw = f'{SEL},{SVC}="api-gateway"'
    p.append(ts("CPU api-gateway (nhân) + throttle", [(f"sum(rate(container_cpu_usage_seconds_total{{{gw}}}[5m]))", "CPU"), (f"sum(rate(container_cpu_cfs_throttled_periods_total{{{gw}}}[5m])) / clamp_min(sum(rate(container_cpu_cfs_periods_total{{{gw}}}[5m])), 1e-9)", "throttle")], 0, y, 12, 7, "short", "hub asyncio ~1 nhân; RtGatewayCpuHigh >0,8"))
    p.append(ts("RAM api-gateway", [(f"sum(container_memory_working_set_bytes{{{gw}}})", "working set"), (f"sum(container_spec_memory_limit_bytes{{{gw}}}) > 0", "giới hạn")], 12, y, 12, 7, "bytes"))
    return dash("ts-realtime", "Realtime", p, "Hub realtime WS/SSE: kết nối, luồng, độ trễ từng chặng EA->bridge->bus->hub->trình duyệt. Sinh bởi infra/grafana/gen_dashboard_rt.py")


if __name__ == "__main__":
    d = build()
    OUT.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    print("ghi", OUT, len(d["panels"]), "panel")
