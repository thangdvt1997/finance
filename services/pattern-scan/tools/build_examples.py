"""Sinh thư viện ví dụ "mẫu chuẩn" (golden) cho trang Kịch bản: chạy pattern-engine trên fixture 3 ảnh mẫu, mỗi tín hiệu triggered
-> ảnh bằng CÙNG pipeline live (pattern_scan.annot + pattern_render) + JSON mô tả. Ảnh không chứa tên nguồn dữ liệu.
Chạy (container có pattern-engine, pattern-render, pattern-scan):  python tools/build_examples.py <fixture.csv> <out_dir>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from pattern_engine.csvio import load_csv
from pattern_engine.detector import Detector
from pattern_engine.specs import load_specs
from pattern_render import render_png_bytes

from pattern_scan import annot

NOTE = {"KB-1": "Ảnh mẫu 2: hồi - giảm nhẹ - hồi vượt đỉnh - 2 đỉnh giảm dần - nhấn chìm giảm.",
        "KB-2": "Ảnh mẫu 1: sóng giảm mạnh - hồi ~50% - nêm thu hẹp - nhấn chìm phá cạnh dưới.",
        "KB-3": "Ảnh mẫu 3: sóng giảm - đi ngang - vai-đầu-vai - cụm nến nén ở đường cổ."}


def main(csv_path: str, out: str) -> None:
    bars = load_csv(csv_path)
    sigs = Detector("XAUUSD", "M15", load_specs()).feed_many(bars)
    od = Path(out)
    od.mkdir(parents=True, exist_ok=True)
    cs_all = [{"t": b.ts.timestamp(), "o": b.o, "h": b.h, "l": b.l, "c": b.c} for b in bars]
    for s in sigs:
        if s.state != "triggered":
            continue
        p = s.to_payload()
        i = s.bar_index
        cs = cs_all[: i + 1]
        st = annot.window_start(p, [c["t"] for c in cs], 60)
        cs = cs[max(st, len(cs) - 260):]
        ann, _ = annot.build(p, cs, 7)
        xid = f"golden-{s.pattern.lower()}-{s.bar_ts.strftime('%Y%m%d%H%M')}"
        (od / f"{xid}.png").write_bytes(render_png_bytes(cs, ann, size=(1600, 800), max_kb=180))
        (od / f"{xid}.json").write_text(json.dumps({
            "kind": "golden", "pattern": s.pattern, "title": f"{s.pattern} · XAUUSD M15 (mẫu chuẩn)", "symbol": "XAUUSD", "tf": "M15",
            "ts": s.ts.isoformat(), "note": NOTE.get(s.pattern, ""), "levels": p["levels"], "steps": p["steps"]}, ensure_ascii=False, indent=1),
            encoding="utf-8")
        print(xid)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
