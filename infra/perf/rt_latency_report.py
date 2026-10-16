#!/usr/bin/env python3
"""Báo cáo độ trễ đầu-cuối realtime: p50/p95 từng chặng trong N phút gần nhất (histogram_quantile trên rate bucket). Chỉ stdlib.
Chạy TRÊN VPS (Prometheus chỉ nghe nội bộ), dùng chung netns với container prometheus:
  docker run --rm --network container:tradingsys-prometheus-1 -v $PWD/infra/perf:/p:ro python:3.12-slim python /p/rt_latency_report.py --minutes 15 [--json]
Hoặc đặt PROM_URL=http://host:9090. Chặng chưa có dữ liệu in "-"."""
import argparse
import json
import os
import urllib.parse
import urllib.request

STAGES = [
    ("EA->bridge (gồm lệch đồng hồ EA)", "mtbridge_ea_to_bridge_seconds", ""),
    ("bridge ingest (tổng)", "mtbridge_ingest_seconds", ""),
    ("bridge publish XADD", "mtbridge_publish_seconds", ""),
    ("bus->gateway", "rt_bus_to_gateway_seconds", ""),
    ("tick->gateway (gồm lệch đồng hồ nguồn)", "rt_tick_to_gateway_seconds", ""),
    ("flush fan-out", "rt_flush_seconds", ""),
    ("send ws", "rt_send_seconds", ""),
    ("client net (gateway->browser)", "rt_client_net_seconds", ""),
    ("client rtt", "rt_client_rtt_seconds", ""),
]


def query(base, expr):
    url = base.rstrip("/") + "/api/v1/query?" + urllib.parse.urlencode({"query": expr})
    with urllib.request.urlopen(url, timeout=15) as r:
        d = json.load(r)
    res = d.get("data", {}).get("result", [])
    if not res:
        return None
    v = float(res[0]["value"][1])
    return None if v != v else v  # NaN -> None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=int, default=10)
    ap.add_argument("--url", default=os.getenv("PROM_URL", "http://127.0.0.1:9090"))
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    w = f"{a.minutes}m"
    rows = []
    for name, m, sel in STAGES:
        row = {"stage": name, "metric": m}
        cnt = query(a.url, f"sum(increase({m}_count{sel}[{w}]))")
        row["samples"] = int(cnt) if cnt else 0
        for p in (0.5, 0.95):
            v = query(a.url, f"histogram_quantile({p}, sum by (le) (rate({m}_bucket{sel}[{w}])))") if row["samples"] else None
            row[f"p{int(p * 100)}_ms"] = None if v is None else round(v * 1000, 2)
        rows.append(row)
    if a.json:
        print(json.dumps({"window": w, "stages": rows}, ensure_ascii=False, indent=1))
        return
    print(f"Độ trễ từng chặng, cửa sổ {w} (ms; p50/p95 là ước lượng theo bucket histogram)")
    print(f"{'chặng':42} {'mẫu':>8} {'p50':>9} {'p95':>9}")
    f = lambda v: "-" if v is None else f"{v:.1f}"
    for r in rows:
        print(f"{r['stage']:42} {r['samples']:>8} {f(r['p50_ms']):>9} {f(r['p95_ms']):>9}")


if __name__ == "__main__":
    main()
