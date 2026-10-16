#!/usr/bin/env python3
"""Sinh dashboard Grafana "local-llm" (uid ts-local-llm) -> dashboards/local-llm.json.
Chay tren VPS:  docker run --rm -v $PWD/infra/grafana:/g -w /g python:3.12-slim python gen_dashboard_llm.py"""
import json
import pathlib

from gen_dashboards import G, dash, row, stat, ts

OUT = pathlib.Path(__file__).parent / "dashboards" / "local-llm.json"
CN = 'container_label_com_docker_compose_service="local-llm"'
LOAD = [G, {"color": "yellow", "value": 50}, {"color": "red", "value": 60}]


def build():
    p, y = [], 0
    p.append(row("Tong quan", y)); y += 1
    p.append(stat("Gatus local-llm (1=OK)", 'max(gatus_results_endpoint_success{name="local-llm"}) or vector(0)', 0, y, 4, 4, "short", [{"color": "red", "value": None}, G]))
    p.append(stat("Load host (1m)", 'llamaswap_load_average{interval="1m"}', 4, y, 4, 4, "short", LOAD, "Nguong: > 60 thi llama-swap tu choi nap model"))
    p.append(stat("CPU local-llm (nhan)", f"sum(rate(container_cpu_usage_seconds_total{{{CN}}}[1m]))", 8, y, 4, 4, "short", [G, {"color": "yellow", "value": 10}, {"color": "red", "value": 13}], "cpuset ghim 12 luong"))
    p.append(stat("RAM local-llm", f"container_memory_working_set_bytes{{{CN}}}", 12, y, 4, 4, "bytes", [G, {"color": "yellow", "value": 26e9}, {"color": "red", "value": 29e9}], "mem_limit 30g"))
    p.append(stat("RAM host trong", "llamaswap_memory_free_bytes", 16, y, 4, 4, "bytes"))
    p.append(stat("p95 tre feed (guard)", "dk_guard_feed_p95_seconds or vector(0)", 20, y, 4, 4, "s", [G, {"color": "yellow", "value": 0.35}, {"color": "red", "value": 0.5}], "tran 0,5 s")); y += 4
    p.append(row("Tai nguyen", y)); y += 1
    p.append(ts("CPU local-llm (nhan)", [f"sum(rate(container_cpu_usage_seconds_total{{{CN}}}[1m]))"], 0, y, 8, 7, "short"))
    p.append(ts("RAM local-llm", [f"container_memory_working_set_bytes{{{CN}}}"], 8, y, 8, 7, "bytes"))
    p.append(ts("Load host", ["llamaswap_load_average"], 16, y, 8, 7, "short", thresholds=[G, {"color": "red", "value": 60}])); y += 7
    p.append(ts("p95 tre feed (guard) khi LLM chay", ["dk_guard_feed_p95_seconds", f"sum(rate(container_cpu_usage_seconds_total{{{CN}}}[1m])) / 100"], 0, y, 12, 7, "s", "duong thu 2 = CPU local-llm / 100 (tuong quan tai)"))
    p.append(ts("RAM host", ["llamaswap_memory_used_bytes", "llamaswap_memory_free_bytes"], 12, y, 12, 7, "bytes")); y += 7
    return dash("ts-local-llm", "local-llm", p, "LLM local (llama-swap): tai nguyen, load host, anh huong duong gia. Sinh boi infra/grafana/gen_dashboard_llm.py")


if __name__ == "__main__":
    d = build()
    OUT.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    print("ghi", OUT, len(d["panels"]), "panel")
