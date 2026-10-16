"""Lưu trữ "Kịch bản mới" + job nền trên volume /state (API ghi kịch bản/job; worker ghi result.json + cập nhật job).
Không có đường dẫn nào lấy từ người dùng ngoài id/tên đã khớp regex chặt -> không path traversal. Ghi nguyên tử (tmp + rename)."""
from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .scenario_schema import IMG_NAME, SC_ID

JOB_ID = re.compile(r"^[0-9a-f]{32}$")
JOB_TYPES = ("detector_test", "backtest", "final_test", "scan_examples")
ACTIVE = ("queued", "running")
MAX_ACTIVE_JOBS = 3


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def atomic_write(p: Path, data: bytes) -> None:
    tmp = p.with_name(f".{p.name}.{uuid.uuid4().hex[:8]}.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, p)


class Store:
    def __init__(self, state_dir: str):
        self.root = Path(state_dir)
        self.sdir = self.root / "scenarios"
        self.jdir = self.root / "jobs"

    def ids(self) -> list[str]:
        return sorted(p.name for p in self.sdir.iterdir() if p.is_dir() and SC_ID.match(p.name)) if self.sdir.is_dir() else []

    def path(self, sid: str) -> Path | None:
        return self.sdir / sid if SC_ID.match(sid or "") and (self.sdir / sid).is_dir() else None

    def read_json(self, p: Path):
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def scenario(self, sid: str) -> dict | None:
        d = self.path(sid)
        if not d:
            return None
        try:
            sc = yaml.safe_load((d / "scenario.yaml").read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError):
            return None
        return sc if isinstance(sc, dict) else None

    def result(self, sid: str) -> dict:
        d = self.path(sid)
        return (self.read_json(d / "result.json") if d else None) or {}

    def meta(self, sid: str) -> dict:
        d = self.path(sid)
        return (self.read_json(d / "meta.json") if d else None) or {}

    def test_opened(self, sid: str) -> dict | None:
        d = self.path(sid)
        return (self.read_json(d / "test_opened.json") or {"opened": True}) if d and (d / "test_opened.json").exists() else None

    def create(self, sc: dict, images: dict[str, bytes], by: str) -> None:
        d = self.sdir / sc["id"]
        (self.sdir).mkdir(parents=True, exist_ok=True)
        for n in images:                          # kiểm tên ảnh TRƯỚC khi tạo thư mục (không để lại thư mục dở dang)
            if not IMG_NAME.match(n):
                raise ValueError("tên ảnh")
        d.mkdir(mode=0o775)                       # FileExistsError nếu trùng -> API trả 409 (không ghi đè, không đặt lại khoá test)
        (d / "images").mkdir(mode=0o775)
        for n, b in images.items():
            (d / "images" / n).write_bytes(b)
        atomic_write(d / "scenario.yaml", yaml.safe_dump(sc, allow_unicode=True, sort_keys=False).encode())
        # scenario.yaml đã ghi nên family_size đã gồm chính nó -> trial_index (1-based) = family_size
        atomic_write(d / "meta.json", json.dumps({"created_at": now(), "created_by": by, "trial_index": self.family_size(sc["family"])}).encode())

    def family_size(self, fam: str) -> int:
        return sum(1 for i in self.ids() if (self.scenario(i) or {}).get("family") == fam)

    def image(self, sid: str, name: str) -> Path | None:
        d = self.path(sid)
        if not d or not IMG_NAME.match(name or ""):
            return None
        p = d / "images" / name
        return p if p.is_file() else None

    # ---- jobs ----
    def jobs(self, sid: str | None = None) -> list[dict]:
        out = []
        for f in sorted(self.jdir.glob("*.json")) if self.jdir.is_dir() else []:
            j = self.read_json(f)
            if isinstance(j, dict) and JOB_ID.match(str(j.get("id", ""))) and (sid is None or j.get("scenario_id") == sid):
                out.append(j)
        out.sort(key=lambda j: j.get("created_at", ""))
        return out

    def job(self, jid: str) -> dict | None:
        return self.read_json(self.jdir / f"{jid}.json") if JOB_ID.match(jid or "") else None

    def enqueue(self, sid: str, typ: str, by: str, params: dict | None = None) -> dict:
        self.jdir.mkdir(parents=True, exist_ok=True)
        j = {"id": uuid.uuid4().hex, "scenario_id": sid, "type": typ, "status": "queued", "stage": "queued", "progress": 0.0,
             "created_at": now(), "created_by": by, "message": "Đang xếp hàng (mỗi lần chỉ chạy 1 job nền)."}
        if params:
            j["params"] = params
        atomic_write(self.jdir / f"{j['id']}.json", json.dumps(j).encode())
        return j


# ---- chuyển kịch bản + kết quả thành "thẻ chiến lược" cho registry/tab ----
PHASES = ("created", "detector_ok", "dev_done", "test_done")


def phase_of(res: dict, store: Store, sid: str) -> str:
    if store.test_opened(sid) and (res.get("test") or {}).get("status") == "done":
        return "test_done"
    if (res.get("dev") or {}).get("status") == "done":
        return "dev_done"
    if (res.get("detector") or {}).get("status") == "done":
        return "detector_ok"
    return "created"


def scenario_strategy(store: Store, sid: str) -> dict | None:
    sc = store.scenario(sid)
    if not sc or sc.get("id") != sid:
        return None
    res = store.result(sid)
    ph = phase_of(res, store, sid)
    dev, te = res.get("dev") or {}, res.get("test") or {}
    oos = dev.get("oos") or {}
    main = te if ph == "test_done" and te.get("summary") else None
    src = (te.get("summary") if main else oos.get("pooled")) or {}
    verdict = res.get("verdict") or "unproven"
    fam_n = store.family_size(sc.get("family", sid))
    warn = {"created": "Mới nạp: chưa có kết quả nào. Chưa phải bằng chứng.",
            "detector_ok": "Detector đã chạy thử; CHƯA backtest. Chưa có bằng chứng thống kê.",
            "dev_done": "Mới có kết quả walk-forward trên dữ liệu dev; test khoá CHƯA mở. Chưa đủ để kết luận có edge.",
            "test_done": "Test khoá đã mở (1 lần, không lặp lại). Kết quả này là cuối cùng cho id này."}[ph]
    if verdict == "no_edge":
        warn = "Không có edge sau chi phí theo tiêu chí đã khai báo. " + warn
    return {
        "id": sid, "name": sc.get("name", sid), "module": "pattern", "status": "research", "origin": "user", "phase": ph,
        "summary": sc.get("summary", ""), "verdict": verdict, "warning": warn,
        "honesty_note": (f"Kịch bản do người dùng nạp (thử nghiệm {fam_n} trong họ '{sc.get('family', sid)}': DSR đã trừ số lần thử). "
                         "Walk-forward chỉ dùng dữ liệu trước ngày test; test khoá mở tối đa 1 lần cho mỗi id và được ghi nhật ký. Chỉ nghiên cứu/paper."),
        "metrics": {"expectancy_r": src.get("exp_r"), "p_vs_random": (te.get("p_vs_random") if main else oos.get("p_vs_random")),
                    "trades": src.get("n"), "scope_note": "test khoá" if main else ("walk-forward dev (ngoài mẫu)" if oos else "chưa có kết quả")},
        "source": {"type": "scenario"}, "scenario": sc, "result": res,
    }
