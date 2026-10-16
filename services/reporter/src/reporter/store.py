"""Lưu trữ báo cáo trên volume: /data/reports/{daily|weekly}/{YYYY-MM-DD}.{html,pdf} + index.json (ghi nguyên tử)."""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

KINDS = ("daily", "weekly")
KIND_RE = re.compile(r"^(daily|weekly)$")
PERIOD_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
EXT_RE = re.compile(r"^(html|pdf)$")
MEDIA = {"html": "text/html; charset=utf-8", "pdf": "application/pdf"}


def valid_name(kind: str, period: str, ext: str) -> bool:
    """Regex chặt cho đường dẫn tải file (chống path traversal): chỉ chấp nhận đúng 3 thành phần đã biết."""
    return bool(KIND_RE.fullmatch(kind) and PERIOD_RE.fullmatch(period) and EXT_RE.fullmatch(ext))


class Store:
    def __init__(self, root: Path, keep_daily: int = 60, keep_weekly: int = 26):
        self.root = Path(root)
        self.keep = {"daily": keep_daily, "weekly": keep_weekly}
        self._lock = threading.Lock()

    @property
    def index_path(self) -> Path:
        return self.root / "index.json"

    def path(self, kind: str, period: str, ext: str) -> Path:
        if not valid_name(kind, period, ext):
            raise ValueError("tên báo cáo không hợp lệ")
        return self.root / kind / f"{period}.{ext}"

    def load(self) -> dict:
        try:
            d = json.loads(self.index_path.read_text("utf-8"))
            if isinstance(d, dict) and isinstance(d.get("items"), list):
                return d
        except (OSError, ValueError):
            pass
        return {"updated_at": None, "items": []}

    def items(self) -> list[dict]:
        its = self.load()["items"]
        return sorted(its, key=lambda x: (x.get("period", ""), x.get("generated_at", "")), reverse=True)

    def find(self, kind: str, period: str) -> dict | None:
        for it in self.load()["items"]:
            if it.get("kind") == kind and it.get("period") == period:
                return it
        return None

    def exists(self, kind: str, period: str) -> bool:
        """Đã có báo cáo cho kỳ này (index ghi nhận + file HTML còn trên đĩa)."""
        it = self.find(kind, period)
        return bool(it and it.get("status") in ("ok", "degraded") and self.path(kind, period, "html").is_file())

    def _write_atomic(self, p: Path, data: bytes) -> None:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, p)

    def save(self, kind: str, period: str, html: str, pdf: bytes | None, sections_ok: list[str], sections_fail: list[str],
             generated_at: datetime | None = None) -> dict:
        hb = html.encode("utf-8")
        self._write_atomic(self.path(kind, period, "html"), hb)
        if pdf:
            self._write_atomic(self.path(kind, period, "pdf"), pdf)
        entry = {
            "kind": kind, "period": period,
            "generated_at": (generated_at or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "sha256": hashlib.sha256(hb).hexdigest(), "bytes": len(hb),
            "pdf_sha256": hashlib.sha256(pdf).hexdigest() if pdf else None, "pdf_bytes": len(pdf) if pdf else 0,
            "status": "ok" if not sections_fail and pdf else "degraded",
            "sections_ok": sections_ok, "sections_fail": sections_fail, "read_only": True,
        }
        with self._lock:
            idx = self.load()
            idx["items"] = [i for i in idx["items"] if not (i.get("kind") == kind and i.get("period") == period)] + [entry]
            self._prune(idx)
            idx["updated_at"] = entry["generated_at"]
            self._write_atomic(self.index_path, json.dumps(idx, ensure_ascii=False, indent=1).encode("utf-8"))
        return entry

    def _prune(self, idx: dict) -> None:
        for kind in KINDS:
            mine = sorted((i for i in idx["items"] if i.get("kind") == kind), key=lambda i: i.get("period", ""), reverse=True)
            for old in mine[self.keep[kind]:]:
                idx["items"].remove(old)
                for ext in ("html", "pdf"):
                    try:
                        self.path(kind, old["period"], ext).unlink(missing_ok=True)
                    except (ValueError, OSError):
                        pass
