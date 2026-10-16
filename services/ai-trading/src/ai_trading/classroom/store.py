"""Lưu trữ BỀN cho AI Training Class: SQLite (WAL) trên volume riêng chỉ ai-trading ghi (/classroom).

Lý do chọn SQLite thay Postgres/Redis (ghi trong docs/AI_CLASSROOM.md): dữ liệu quan hệ nhỏ (phòng/tin/nhãn/phiên bản), 1 tiến trình ghi, cần giao dịch + tìm kiếm;
service ai-trading vốn không có DB và không có đường tới Postgres (read_only, mạng backend); Redis ACL của nó là cache (không AOF) nên không bền;
volume riêng cô lập quyền ghi (worker không gắn volume này) tương đương "role hẹp", không thêm bí mật/lock-file/migration cho DB chung.
Mọi truy vấn dùng tham số hoá (không nối chuỗi). Thread-safe qua RLock (API gọi từ thread)."""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS class_rooms(id TEXT PRIMARY KEY, title TEXT NOT NULL, created_by TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS class_members(room_id TEXT NOT NULL, user_id TEXT NOT NULL, name TEXT NOT NULL, role TEXT NOT NULL, joined_at TEXT NOT NULL, PRIMARY KEY(room_id,user_id));
CREATE TABLE IF NOT EXISTS class_messages(seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL, room_id TEXT NOT NULL, kind TEXT NOT NULL,
  author TEXT NOT NULL, text TEXT NOT NULL, data TEXT, attachments TEXT, pinned INTEGER NOT NULL DEFAULT 0, review TEXT, understanding TEXT, chips TEXT, created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_msg_room ON class_messages(room_id, seq);
CREATE TABLE IF NOT EXISTS class_examples(id TEXT PRIMARY KEY, room_id TEXT NOT NULL, round INTEGER NOT NULL, action_id TEXT, data TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_ex_room ON class_examples(room_id);
CREATE TABLE IF NOT EXISTS class_labels(id TEXT PRIMARY KEY, room_id TEXT NOT NULL, example_id TEXT NOT NULL, verdict TEXT NOT NULL, reason TEXT, by_user TEXT NOT NULL,
  round INTEGER NOT NULL, created_at TEXT NOT NULL, superseded INTEGER NOT NULL DEFAULT 0);
CREATE INDEX IF NOT EXISTS ix_lab_room ON class_labels(room_id);
CREATE TABLE IF NOT EXISTS class_profiles(room_id TEXT PRIMARY KEY, state TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS class_profile_versions(room_id TEXT NOT NULL, version INTEGER NOT NULL, snapshot TEXT NOT NULL, note TEXT, by_user TEXT, created_at TEXT NOT NULL, PRIMARY KEY(room_id,version));
CREATE TABLE IF NOT EXISTS class_actions(id TEXT PRIMARY KEY, room_id TEXT NOT NULL, command TEXT NOT NULL, status TEXT NOT NULL, params TEXT, job_id TEXT, scenario_id TEXT,
  result_message_id TEXT, message TEXT, created_by TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_act_room ON class_actions(room_id);
CREATE TABLE IF NOT EXISTS class_audit(id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, user_id TEXT, role TEXT, room_id TEXT, event TEXT NOT NULL, detail TEXT);
CREATE TABLE IF NOT EXISTS class_attachments(id TEXT PRIMARY KEY, room_id TEXT NOT NULL, kind TEXT NOT NULL, name TEXT NOT NULL, size INTEGER NOT NULL, file TEXT NOT NULL, ctype TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS class_room_trash(room_id TEXT PRIMARY KEY, deleted_at TEXT NOT NULL, deleted_by TEXT NOT NULL, deleted_by_name TEXT, reason TEXT, forget_learned INTEGER NOT NULL DEFAULT 0, purge_after TEXT NOT NULL);
"""
J = ("author", "data", "attachments", "review", "understanding", "chips")


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def nid() -> str:
    return uuid.uuid4().hex


class ClassStore:
    def __init__(self, root: str):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "media").mkdir(exist_ok=True)
        self._lock = threading.RLock()
        self.db = sqlite3.connect(str(self.root / "classroom.db"), check_same_thread=False, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript(SCHEMA)
        self.room_locks: dict[str, threading.Lock] = {}

    # ---- tiện ích ----
    def q(self, sql: str, args=()) -> list[sqlite3.Row]:
        with self._lock:
            return self.db.execute(sql, args).fetchall()

    def x(self, sql: str, args=()) -> int:
        with self._lock:
            return self.db.execute(sql, args).lastrowid

    def room_lock(self, rid: str) -> threading.Lock:
        with self._lock:
            return self.room_locks.setdefault(rid, threading.Lock())

    def audit(self, user: str, role: str, room: str | None, event: str, detail: str = "") -> None:
        self.x("INSERT INTO class_audit(ts,user_id,role,room_id,event,detail) VALUES(?,?,?,?,?,?)", (now(), user, role, room, event, detail[:300]))

    # ---- phòng/thành viên ----
    def create_room(self, title: str, user: str, name: str, role: str) -> dict:
        rid, t = nid(), now()
        with self._lock:
            self.x("INSERT INTO class_rooms VALUES(?,?,?,?,?)", (rid, title, user, t, t))
            self.x("INSERT INTO class_members VALUES(?,?,?,?,?)", (rid, user, name, role, t))
        return self.room(rid)

    def room(self, rid: str, include_trashed: bool = False) -> dict | None:
        """Phòng đã vào thùng rác (class_room_trash) bị coi như không tồn tại với mọi route cũ (404 đồng nhất)."""
        r = self.q("SELECT * FROM class_rooms WHERE id=?" + ("" if include_trashed else " AND id NOT IN (SELECT room_id FROM class_room_trash)"), (rid,))
        if not r:
            return None
        d = dict(r[0])
        d["members"] = self.members(rid)
        return d

    def members(self, rid: str) -> list[dict]:
        return [dict(m) for m in self.q("SELECT user_id,name,role,joined_at FROM class_members WHERE room_id=? ORDER BY joined_at", (rid,))]

    def is_member(self, rid: str, user: str) -> bool:
        return bool(self.q("SELECT 1 FROM class_members WHERE room_id=? AND user_id=?", (rid, user)))

    def add_member(self, rid: str, user: str, name: str, role: str) -> dict:
        self.x("INSERT OR REPLACE INTO class_members VALUES(?,?,?,?,COALESCE((SELECT joined_at FROM class_members WHERE room_id=? AND user_id=?),?))", (rid, user, name, role, rid, user, now()))
        return next(m for m in self.members(rid) if m["user_id"] == user)

    def rooms_for(self, user: str, master: bool) -> list[dict]:
        rows = self.q("SELECT id FROM class_rooms WHERE id NOT IN (SELECT room_id FROM class_room_trash) ORDER BY updated_at DESC") if master else \
            self.q("SELECT r.id FROM class_rooms r JOIN class_members m ON m.room_id=r.id WHERE m.user_id=? AND r.id NOT IN (SELECT room_id FROM class_room_trash) ORDER BY r.updated_at DESC", (user,))
        return [self.room(r["id"]) for r in rows]

    def touch(self, rid: str) -> None:
        self.x("UPDATE class_rooms SET updated_at=? WHERE id=?", (now(), rid))

    # ---- tin nhắn ----
    def add_message(self, rid: str, kind: str, author: dict, text: str, data=None, attachments=None, understanding=None, chips=None, mid: str | None = None) -> dict:
        mid = mid or nid()
        self.x("INSERT INTO class_messages(id,room_id,kind,author,text,data,attachments,understanding,chips,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
               (mid, rid, kind, json.dumps(author, ensure_ascii=False), text, json.dumps(data, ensure_ascii=False) if data is not None else None,
                json.dumps(attachments or [], ensure_ascii=False), json.dumps(understanding, ensure_ascii=False) if understanding is not None else None,
                json.dumps(chips or [], ensure_ascii=False), now()))
        self.touch(rid)
        return self.message(rid, mid)

    @staticmethod
    def _msg(r) -> dict:
        d = dict(r)
        for k in J:
            d[k] = json.loads(d[k]) if d.get(k) else ([] if k in ("attachments", "chips") else None)
        d["pinned"] = bool(d["pinned"])
        d["room_id"] = d.get("room_id")
        return d

    def message(self, rid: str, mid: str) -> dict | None:
        r = self.q("SELECT * FROM class_messages WHERE room_id=? AND id=?", (rid, mid))
        return self._msg(r[0]) if r else None

    def messages(self, rid: str, limit: int = 50, before: int | None = None, q: str | None = None) -> tuple[list[dict], bool]:
        sql, args = "SELECT * FROM class_messages WHERE room_id=?", [rid]
        if before:
            sql += " AND seq<?"
            args.append(before)
        if q:
            sql += " AND lower(text) LIKE ? ESCAPE '\\'"
            args.append("%" + q.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%")
        rows = self.q(sql + " ORDER BY seq DESC LIMIT ?", (*args, limit + 1))
        more = len(rows) > limit
        return [self._msg(r) for r in reversed(rows[:limit])], more

    def pinned(self, rid: str) -> list[dict]:
        return [self._msg(r) for r in self.q("SELECT * FROM class_messages WHERE room_id=? AND pinned=1 ORDER BY seq", (rid,))]

    def set_pin(self, rid: str, mid: str, pinned: bool) -> bool:
        with self._lock:
            c = self.db.execute("UPDATE class_messages SET pinned=? WHERE room_id=? AND id=?", (1 if pinned else 0, rid, mid))
            return c.rowcount > 0

    def set_review(self, rid: str, mid: str, review: dict) -> bool:
        with self._lock:
            c = self.db.execute("UPDATE class_messages SET review=? WHERE room_id=? AND id=?", (json.dumps(review, ensure_ascii=False), rid, mid))
            return c.rowcount > 0

    def count_messages(self, rid: str) -> int:
        return self.q("SELECT COUNT(*) c FROM class_messages WHERE room_id=?", (rid,))[0]["c"]

    def last_message(self, rid: str) -> dict | None:
        r = self.q("SELECT * FROM class_messages WHERE room_id=? ORDER BY seq DESC LIMIT 1", (rid,))
        return self._msg(r[0]) if r else None

    # ---- hồ sơ (trạng thái máy) + phiên bản ----
    def get_state(self, rid: str) -> dict | None:
        r = self.q("SELECT state FROM class_profiles WHERE room_id=?", (rid,))
        return json.loads(r[0]["state"]) if r else None

    def put_state(self, rid: str, state: dict) -> None:
        self.x("INSERT INTO class_profiles(room_id,state,updated_at) VALUES(?,?,?) ON CONFLICT(room_id) DO UPDATE SET state=excluded.state, updated_at=excluded.updated_at",
               (rid, json.dumps(state, ensure_ascii=False), now()))

    def put_version(self, rid: str, version: int, snap: dict, note: str, by: str) -> None:
        self.x("INSERT OR IGNORE INTO class_profile_versions VALUES(?,?,?,?,?,?)", (rid, version, json.dumps(snap, ensure_ascii=False), note[:200], by, now()))

    def versions(self, rid: str) -> list[dict]:
        return [{"version": r["version"], "note": r["note"], "by": r["by_user"], "created_at": r["created_at"]}
                for r in self.q("SELECT version,note,by_user,created_at FROM class_profile_versions WHERE room_id=? ORDER BY version", (rid,))]

    def version(self, rid: str, v: int) -> dict | None:
        r = self.q("SELECT snapshot FROM class_profile_versions WHERE room_id=? AND version=?", (rid, v))
        return json.loads(r[0]["snapshot"]) if r else None

    # ---- ví dụ + nhãn ----
    def add_example(self, rid: str, rnd: int, action_id: str | None, data: dict) -> str:
        eid = nid()[:16]
        self.x("INSERT INTO class_examples VALUES(?,?,?,?,?,?)", (eid, rid, rnd, action_id, json.dumps(data, ensure_ascii=False), now()))
        return eid

    def examples(self, rid: str) -> list[dict]:
        return [{"id": r["id"], "round": r["round"], **json.loads(r["data"])} for r in self.q("SELECT * FROM class_examples WHERE room_id=? ORDER BY created_at,id", (rid,))]

    def example(self, rid: str, eid: str) -> dict | None:
        r = self.q("SELECT * FROM class_examples WHERE room_id=? AND id=?", (rid, eid))
        return {"id": r[0]["id"], "round": r[0]["round"], **json.loads(r[0]["data"])} if r else None

    def rounds(self, rid: str) -> int:
        return self.q("SELECT COALESCE(MAX(round),0) m FROM class_examples WHERE room_id=?", (rid,))[0]["m"]

    def add_label(self, rid: str, eid: str, verdict: str, reason: str, user: str, rnd: int) -> dict:
        with self._lock:
            self.db.execute("UPDATE class_labels SET superseded=1 WHERE room_id=? AND example_id=? AND by_user=? AND superseded=0", (rid, eid, user))
            lid = nid()
            self.db.execute("INSERT INTO class_labels VALUES(?,?,?,?,?,?,?,?,0)", (lid, rid, eid, verdict, reason, user, rnd, now()))
        return {"id": lid, "example_id": eid, "verdict": verdict, "reason": reason, "by": user, "round": rnd}

    def labels(self, rid: str) -> list[dict]:
        return [{"id": r["id"], "example_id": r["example_id"], "verdict": r["verdict"], "reason": r["reason"], "by": r["by_user"], "round": r["round"], "created_at": r["created_at"]}
                for r in self.q("SELECT * FROM class_labels WHERE room_id=? AND superseded=0 ORDER BY created_at", (rid,))]

    # ---- action ----
    def add_action(self, rid: str, command: str, status: str, params: dict, by: str, **kw) -> dict:
        aid, t = nid(), now()
        self.x("INSERT INTO class_actions(id,room_id,command,status,params,job_id,scenario_id,message,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
               (aid, rid, command, status, json.dumps(params, ensure_ascii=False), kw.get("job_id"), kw.get("scenario_id"), kw.get("message"), by, t, t))
        return self.action(rid, aid)

    @staticmethod
    def _act(r) -> dict:
        d = dict(r)
        d["params"] = json.loads(d["params"]) if d.get("params") else {}
        return d

    def action(self, rid: str, aid: str) -> dict | None:
        r = self.q("SELECT * FROM class_actions WHERE room_id=? AND id=?", (rid, aid))
        return self._act(r[0]) if r else None

    def actions(self, rid: str, statuses: tuple = ()) -> list[dict]:
        rows = self.q("SELECT * FROM class_actions WHERE room_id=? ORDER BY created_at", (rid,))
        return [self._act(r) for r in rows if not statuses or r["status"] in statuses]

    def upd_action(self, aid: str, **kw) -> None:
        cols = {"status", "job_id", "scenario_id", "result_message_id", "message", "params"}
        sets, args = [], []
        for k, v in kw.items():
            if k in cols:
                sets.append(f"{k}=?")
                args.append(json.dumps(v, ensure_ascii=False) if k == "params" else v)
        if sets:
            self.x(f"UPDATE class_actions SET {','.join(sets)}, updated_at=? WHERE id=?", (*args, now(), aid))  # noqa: S608 (tên cột từ danh sách cố định)

    # ---- tệp đính kèm ----
    def add_attachment(self, rid: str, kind: str, name: str, data: bytes, ctype: str, ext: str) -> dict:
        aid = nid()
        d = self.root / "media" / rid
        d.mkdir(parents=True, exist_ok=True)
        fn = f"{aid}.{ext}"
        (d / fn).write_bytes(data)
        self.x("INSERT INTO class_attachments VALUES(?,?,?,?,?,?,?,?)", (aid, rid, kind, name, len(data), fn, ctype, now()))
        return {"id": aid, "kind": kind, "name": name, "size": len(data)}

    def attachment(self, rid: str, aid: str) -> tuple[dict, Path] | None:
        r = self.q("SELECT * FROM class_attachments WHERE room_id=? AND id=?", (rid, aid))
        if not r:
            return None
        p = self.root / "media" / rid / r[0]["file"]
        return (dict(r[0]), p) if p.is_file() else None
