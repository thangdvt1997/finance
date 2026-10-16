#!/usr/bin/env python3
"""Sinh dashboard Grafana "Feed toan bo cap" (uid ts-feed-all) -> dashboards/feed_all.json. Metric: docs/handoff/FEED_ALL_contract.md (Metrics).
Chay tren VPS:  docker run --rm -v $PWD/infra/grafana:/g -w /g python:3.12-slim python gen_dashboard_feed.py"""
import json
import pathlib

from gen_dashboards import G, dash, row, stat, table, ts

OUT = pathlib.Path(__file__).parent / "dashboards" / "feed_all.json"
R1 = {"color": "red", "value": 1}
Y1 = {"color": "yellow", "value": 1}


def q(metric, p, by="le"):
    return f"histogram_quantile({p}, sum by ({by}) (rate({metric}_bucket[5m])))"


def build():
    p, y = [], 0
    p.append(row("Tong quan feed (126 forex + 10 kim loai + 26 chi so)", y)); y += 1
    p.append(stat("Symbol dang co quote", "sum(feed:symbols_active) or vector(0)", 0, y, 4, 4, "short", desc="tuoi quote <=600s"))
    p.append(stat("Symbol ky vong", "sum(mtbridge_feed_symbols_expected) or vector(0)", 4, y, 4, 4, "short"))
    p.append(stat("Symbol im lang (khi mo cua)", "sum(feed:symbols_silent) or vector(0)", 8, y, 4, 4, "short", [G, {"color": "yellow", "value": 10}, {"color": "red", "value": 30}], "0 khi thi truong dong"))
    p.append(stat("Tick/s tong", "sum(feed:tick_rate) or vector(0)", 12, y, 4, 4, "ops"))
    p.append(stat("Tre MT5->bridge p95", "max(feed:latency_p95_seconds) or vector(0)", 16, y, 4, 4, "s", [G, {"color": "yellow", "value": 1}, {"color": "red", "value": 2}], "", 2))
    p.append(stat("Feed khoe (Gatus)", "feed:ok", 20, y, 4, 4, "none", [{"color": "red", "value": None}, G], "1 = khoe hoac thi truong dong", None,
                  [{"type": "value", "options": {"0": {"text": "MAT FEED"}, "1": {"text": "OK"}}}])); y += 4
    p.append(row("Luu luong & do tre", y)); y += 1
    p.append(ts("Tick/s theo nhom", ["sum by (class) (feed:tick_rate)"], 0, y, 8, 7, "ops"))
    p.append(ts("Tre MT5 -> bridge (p50/p95/p99)", [(q("mtbridge_feed_latency_seconds", p), f"p{int(p * 100)}") for p in (0.5, 0.95, 0.99)], 8, y, 8, 7, "s", thresholds=[G, {"color": "red", "value": 2}]))
    p.append(ts("Tre p95 theo nhom", ["feed:latency_p95_seconds"], 16, y, 8, 7, "s")); y += 7
    p.append(ts("Batch EA feed / s theo ket qua", ["sum by (result) (rate(mtbridge_feed_batches_total[5m]))"], 0, y, 8, 7, "ops"))
    p.append(ts("Ket noi lai EA (10 phut)", ["sum by (account) (increase(mtbridge_feed_reconnect_total[10m]))"], 8, y, 8, 7, "short"))
    p.append(ts("Hang doi EA", ["mtbridge_feed_queue_depth"], 16, y, 8, 7, "short")); y += 7
    p.append(row("Symbol theo nhom", y)); y += 1
    p.append(ts("Symbol co quote / ky vong theo nhom", [("feed:symbols_active", "co quote {{class}}"), ("mtbridge_feed_symbols_expected", "ky vong {{class}}")], 0, y, 12, 7, "short"))
    p.append(ts("Symbol im lang theo nhom (khi mo cua)", ["feed:symbols_silent"], 12, y, 12, 7, "short")); y += 7
    p.append(table("Symbol im lang lau nhat (tuoi quote, giay)", "topk(25, time() - mtbridge_feed_symbol_last_quote_timestamp)", 0, y, 12, 9, "s", "danh sach symbol im lang; cuoi tuan tuoi lon la binh thuong"))
    p.append(ts("Tuoi quote lon nhat theo nhom", ["feed:quote_age_seconds_max"], 12, y, 12, 9, "s")); y += 9
    p.append(row("Ket noi EA", y)); y += 1
    p.append(ts("EA feed online", ['mtbridge_account_connected{account=~".*-feed"}', 'mtbridge_ea_online_accounts'], 0, y, 12, 6, "short"))
    p.append(ts("Bus -> hub p95 (md.quotes)", [(q("rt_bus_to_gateway_seconds", 0.95, "le, stream"), "p95 {{stream}}")], 12, y, 12, 6, "s"))
    return dash("ts-feed-all", "Feed toan bo cap", p, "Feed MT5 126 forex + 10 kim loai + 26 chi so: tick/s, tre, symbol im lang, ket noi lai. Luat: prometheus/rules_feed.yml. Sinh boi infra/grafana/gen_dashboard_feed.py")


if __name__ == "__main__":
    d = build()
    OUT.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    print("ghi", OUT, len(d["panels"]), "panel")
