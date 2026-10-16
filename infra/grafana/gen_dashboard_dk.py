#!/usr/bin/env python3
"""Sinh dashboard Grafana "data-keeper" (uid ts-data-keeper) -> dashboards/data_keeper.json. Metric: services/data-keeper (inventory.py, main.py).
Chay tren VPS:  docker run --rm -v $PWD/infra/grafana:/g -w /g python:3.12-slim python gen_dashboard_dk.py"""
import json
import pathlib

from gen_dashboards import G, dash, row, stat, table, ts

OUT = pathlib.Path(__file__).parent / "dashboards" / "data_keeper.json"
Y = {"color": "yellow", "value": 1}
R = {"color": "red", "value": 1}


def build():
    p, y = [], 0
    p.append(row("Phu du lieu (ma x khung)", y)); y += 1
    p.append(stat("Tong ma", "dk_symbols_total or vector(0)", 0, y, 3, 4, "short"))
    p.append(stat("Phu M1 (OK+dong cua)", 'dk_coverage_pct{tf="M1"} or vector(0)', 3, y, 4, 4, "percent", [{"color": "red", "value": None}, {"color": "yellow", "value": 90}, {"color": "green", "value": 98}], "(OK+CLOSED)/tong ma; CLOSED/NO_SOURCE tinh la dat"))
    p.append(stat("Phu M1 chi ma dang mo", 'dk_coverage_open_pct{tf="M1"} or vector(0)', 7, y, 4, 4, "percent", [{"color": "red", "value": None}, {"color": "yellow", "value": 90}, {"color": "green", "value": 98}], "OK/(OK+SLOW+BROKEN): chi ma dang mo cua co nguon, loai CLOSED/NO_SOURCE"))
    p.append(stat("Ma im khi mo cua (M1)", "dk_symbols_silent_open_market or vector(0)", 11, y, 3, 4, "short", [G, Y, {"color": "red", "value": 5}], "BROKEN: mo cua theo lich nhung khong co nen"))
    p.append(stat("Nen thieu M1 (6h)", 'dk_gap_count{tf="M1"} or vector(0)', 14, y, 3, 4, "short", [G, Y, {"color": "red", "value": 200}]))
    p.append(stat("p95 tre feed (guard)", "dk_guard_feed_p95_seconds or vector(0)", 17, y, 3, 4, "s", [G, {"color": "yellow", "value": 0.35}, {"color": "red", "value": 0.5}], "tran 0,5 s", 3))
    p.append(stat("Kiem ke cuoi (giay truoc)", "time() - dk_inventory_last_run_timestamp", 20, y, 4, 4, "s", [G, {"color": "yellow", "value": 600}, {"color": "red", "value": 1800}])); y += 4
    p.append(row("Trang thai o theo khung", y)); y += 1
    p.append(ts("Phu % theo khung", ["dk_coverage_pct", "dk_coverage_open_pct"], 0, y, 8, 7, "percent"))
    p.append(ts("O theo trang thai (M1)", ['dk_cells_status{tf="M1"}'], 8, y, 8, 7, "short"))
    p.append(ts("Phu % theo nhom ma", ["dk_coverage_group_pct"], 16, y, 8, 7, "percent")); y += 7
    p.append(ts("Nen thieu theo khung", ["dk_gap_count"], 0, y, 12, 7, "short"))
    p.append(ts("Ma im khi mo cua", ["dk_symbols_silent_open_market"], 12, y, 12, 7, "short")); y += 7
    p.append(row("Van hanh agent", y)); y += 1
    p.append(ts("Thoi gian kiem ke (s)", ["dk_inventory_duration_seconds"], 0, y, 8, 6, "s"))
    p.append(ts("Loi chu ky (10 phut)", ["sum by (stage) (increase(dk_cycle_errors_total[10m]))"], 8, y, 8, 6, "short"))
    p.append(table("Module da nap", "dk_module_loaded", 16, y, 8, 6, "short", "1 = nap duoc; module chua co -> 0 (nap long)"))
    return dash("ts-data-keeper", "data-keeper", p, "Phu du lieu gia moi ma x khung, ma im khi mo cua, nen thieu, p95 tre feed. Sinh boi infra/grafana/gen_dashboard_dk.py")


if __name__ == "__main__":
    d = build()
    OUT.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    print("ghi", OUT, len(d["panels"]), "panel")
