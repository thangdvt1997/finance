"""Lưu trữ báo cáo THEO TÀI KHOẢN + bảng lịch.

Bố cục: {reports_dir}/accounts/<dir>/{daily|weekly|monthly}/{YYYY-MM-DD}.{html,pdf} + <dir>/index.json; lịch: {reports_dir}/account_schedules.json.
Tên thư mục tài khoản được MÃ HOÁ (không bao giờ ghép trực tiếp account_id vào đường dẫn): `a_<sanitized>_<sha256[:10]>`.
Mọi ghi đều nguyên tử (tmp + os.replace). Chống path traversal bằng regex chặt ở mọi điểm vào.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

ACC_RE = re.compile(r"^[A-Za-z0-9_.:\-]{1,64}$")
KINDS = ("daily", "weekly", "monthly")
KIND_RE = re.compile(r"^(daily|weekly|monthly)$")
PERIOD_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
EXT_RE = re.compile(r"^(html|pdf)$")
MEDIA = {"html": "text/html; charset=utf-8", "pdf": "application/pdf"}
KEEP = {"daily": 60, "weekly": 26, "monthly": 24}
SCOPE_TYPES = ("group", "tag", "account", "all")
REF_RE = re.compile(r"^[^\x00-\x1f<>\"'`\\/]{1,64}$")


def valid_account(account_id: str) -> bool:
    return isinstance(account_id, str) and bool(ACC_RE.fullmatch(account_id))


def valid_name(account_id: str, kind: str, period: str, ext: str) -> bool:
    return bool(valid_account(account_id) and KIND_RE.fullmatch(kind) and PERIOD_RE.fullmatch(period) and EXT_RE.fullmatch(ext))


def account_dir_name(account_id: str) -> str:
    if not valid_account(account_id):
        raise ValueError("account_id không hợp lệ")
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", account_id)
    return f"a_{safe}_{hashlib.sha256(account_id.encode()).hexdigest()[:10]}"


def _write_atomic(p: Path, data: bytes) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + f".{uuid.uuid4().hex[:6]}.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, p)


class AccountStore:
    def __init__(self, reports_dir: Path):
        self.root = Path(reports_dir) / "accounts"
        self._lock = threading.Lock()

    def adir(self, account_id: str) -> Path:
        return self.root / account_dir_name(account_id)

    def path(self, account_id: str, kind: str, period: str, ext: str) -> Path:
        if not valid_name(account_id, kind, period, ext):
            raise ValueError("tên báo cáo không hợp lệ")
        return self.adir(account_id) / kind / f"{period}.{ext}"

    def _index_path(self, account_id: str) -> Path:
        return self.adir(account_id) / "index.json"

    def _load(self, account_id: str) -> dict:
        try:
            d = json.loads(self._index_path(account_id).read_text("utf-8"))
            if isinstance(d, dict) and isinstance(d.get("items"), list):
                return d
        except (OSError, ValueError):
            pass
        return {"account_id": account_id, "updated_at": None, "items": []}

    def items(self, account_id: str, released_only: bool = False) -> list[dict]:
        its = self._load(account_id)["items"]
        if released_only:
            its = [i for i in its if i.get("released")]
        return sorted(its, key=lambda x: (x.get("period", ""), x.get("generated_at", "")), reverse=True)

    def find(self, account_id: str, kind: str, period: str) -> dict | None:
        for it in self._load(account_id)["items"]:
            if it.get("kind") == kind and it.get("period") == period:
                return it
        return None

    def find_period(self, account_id: str, period: str, released_only: bool = False) -> dict | None:
        """Không biết kind: lấy bản mới sinh nhất của kỳ này."""
        cand = [i for i in self.items(account_id, released_only) if i.get("period") == period]
        return max(cand, key=lambda i: i.get("generated_at", "")) if cand else None

    def exists(self, account_id: str, kind: str, period: str) -> bool:
        it = self.find(account_id, kind, period)
        return bool(it and it.get("status") in ("ok", "degraded") and self.path(account_id, kind, period, "html").is_file())

    def save(self, account_id: str, kind: str, period: str, html: str, pdf: bytes | None, ok: list[str], fail: list[str],
             released: bool, generated_at: datetime | None = None) -> dict:
        hb = html.encode("utf-8")
        _write_atomic(self.path(account_id, kind, period, "html"), hb)
        if pdf:
            _write_atomic(self.path(account_id, kind, period, "pdf"), pdf)
        else:
            self.path(account_id, kind, period, "pdf").unlink(missing_ok=True)
        entry = {
            "account_id": account_id, "kind": kind, "period": period,
            "generated_at": (generated_at or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "sha256": hashlib.sha256(hb).hexdigest(), "bytes": len(hb),
            "pdf_bytes": len(pdf) if pdf else 0, "has_pdf": bool(pdf),
            "status": "ok" if not fail and pdf else "degraded",
            "sections_ok": ok, "sections_fail": fail, "released": bool(released), "read_only": True,
        }
        with self._lock:
            idx = self._load(account_id)
            idx["items"] = [i for i in idx["items"] if not (i.get("kind") == kind and i.get("period") == period)] + [entry]
            self._prune(account_id, idx)
            idx["updated_at"] = entry["generated_at"]
            idx["account_id"] = account_id
            _write_atomic(self._index_path(account_id), json.dumps(idx, ensure_ascii=False, indent=1).encode("utf-8"))
        return entry

    def purge(self, account_id: str) -> int:
        """Xoá toàn bộ báo cáo của một tài khoản (dọn khi tài khoản bị xoá / dữ liệu thử). Trả số mục đã xoá."""
        import shutil
        with self._lock:
            n = len(self._load(account_id)["items"])
            d = self.adir(account_id)
            if d.is_dir() and d.parent == self.root:
                shutil.rmtree(d, ignore_errors=True)
        return n

    def set_released(self, account_id: str, kind: str, period: str, released: bool) -> dict | None:
        with self._lock:
            idx = self._load(account_id)
            for it in idx["items"]:
                if it.get("kind") == kind and it.get("period") == period:
                    it["released"] = bool(released)
                    it["released_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if released else None
                    _write_atomic(self._index_path(account_id), json.dumps(idx, ensure_ascii=False, indent=1).encode("utf-8"))
                    return it
        return None

    def _prune(self, account_id: str, idx: dict) -> None:
        for kind in KINDS:
            mine = sorted((i for i in idx["items"] if i.get("kind") == kind), key=lambda i: i.get("period", ""), reverse=True)
            for old in mine[KEEP[kind]:]:
                idx["items"].remove(old)
                for ext in ("html", "pdf"):
                    try:
                        self.path(account_id, kind, old["period"], ext).unlink(missing_ok=True)
                    except (ValueError, OSError):
                        pass


def clean_schedule(raw: dict, existing_id: str | None = None) -> dict:
    """Chuẩn hoá + kiểm tra một dòng lịch; ném ValueError(thông báo tiếng Việt) khi sai."""
    if not isinstance(raw, dict):
        raise ValueError("lịch không hợp lệ")
    scope = raw.get("scope") or {}
    st = scope.get("type")
    if st not in SCOPE_TYPES:
        raise ValueError("scope.type phải là group|tag|account|all")
    ref = scope.get("ref")
    if st == "all":
        ref = None
    elif st == "account":
        if not valid_account(ref or ""):
            raise ValueError("scope.ref (account_id) không hợp lệ")
    elif not isinstance(ref, str) or not REF_RE.fullmatch(ref.strip()):
        raise ValueError("scope.ref không hợp lệ")
    else:
        ref = ref.strip()
    kind = raw.get("kind")
    if kind not in KINDS:
        raise ValueError("kind phải là daily|weekly|monthly")
    hour = raw.get("hour", 7)
    if isinstance(hour, bool) or not isinstance(hour, int) or not 0 <= hour <= 23:
        raise ValueError("hour phải là số nguyên 0..23")
    sid = existing_id or raw.get("schedule_id")
    if sid is not None and not re.fullmatch(r"^[0-9a-f]{8,32}$", str(sid)):
        raise ValueError("schedule_id không hợp lệ")
    return {"schedule_id": sid or uuid.uuid4().hex[:16], "scope": {"type": st, "ref": ref}, "kind": kind, "hour": hour,
            "enabled": bool(raw.get("enabled", True)), "auto_release": bool(raw.get("auto_release", False))}


class ScheduleStore:
    def __init__(self, reports_dir: Path):
        self.path = Path(reports_dir) / "account_schedules.json"
        self._lock = threading.Lock()

    def list(self) -> list[dict]:
        try:
            d = json.loads(self.path.read_text("utf-8"))
            return [x for x in d.get("schedules", []) if isinstance(x, dict)]
        except (OSError, ValueError, AttributeError):
            return []

    def replace(self, items: list[dict]) -> list[dict]:
        if not isinstance(items, list) or len(items) > 200:
            raise ValueError("danh sách lịch không hợp lệ (tối đa 200)")
        cleaned, seen = [], set()
        for it in items:
            c = clean_schedule(it)
            if c["schedule_id"] in seen:
                raise ValueError("schedule_id bị trùng")
            seen.add(c["schedule_id"])
            cleaned.append(c)
        with self._lock:
            _write_atomic(self.path, json.dumps({"schedules": cleaned}, ensure_ascii=False, indent=1).encode("utf-8"))
        return cleaned

    def upsert(self, raw: dict) -> dict:
        with self._lock:
            cur = self.list()
            c = clean_schedule(raw)
            cur = [x for x in cur if x.get("schedule_id") != c["schedule_id"]] + [c]
            if len(cur) > 200:
                raise ValueError("tối đa 200 lịch")
            _write_atomic(self.path, json.dumps({"schedules": cur}, ensure_ascii=False, indent=1).encode("utf-8"))
        return c

    def delete(self, schedule_id: str) -> bool:
        with self._lock:
            cur = self.list()
            new = [x for x in cur if x.get("schedule_id") != schedule_id]
            if len(new) == len(cur):
                return False
            _write_atomic(self.path, json.dumps({"schedules": new}, ensure_ascii=False, indent=1).encode("utf-8"))
        return True
