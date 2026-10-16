"""Nghiệp vụ quản trị đội tài khoản: nhóm/tag/views, bulk 2 bước, import CSV, mẫu luật + tuân thủ, hộp thư sự cố, nhân sự phụ, xem-như-khách.
Không phụ thuộc FastAPI. Lỗi nghiệp vụ -> AuthError. docs/FLEET_MGMT.md."""
from __future__ import annotations

import asyncio
import contextlib
import csv
import hashlib
import io
import logging
import re
import secrets
import time
from datetime import datetime, timedelta, timezone

from . import fleet_rules
from . import roles as R
from . import security as sec
from .fleet_store import FleetStore
from .service import ACCOUNT_ID_RE, SERVER_RE, AuthError, AuthService, Principal

log = logging.getLogger("auth.fleet")

TAG_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,23}$")
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,31}$")
SEV_RANK = {"info": 0, "warning": 1, "critical": 2}
STATUS_SEV = {"red": "critical", "yellow": "warning"}
BULK_ACTIONS = {"suspend", "activate", "tag_add", "tag_remove", "group_add", "group_remove", "rotate_ea_token", "rotate_hmac"}
MAX_BULK, MAX_IMPORT = 200, 200
STALE_S = 600
UUID_RX = re.compile(r"^[0-9a-fA-F-]{36}$")


def now() -> datetime:
    return datetime.now(timezone.utc)


def device_label(ua: str) -> str:
    """Rút gọn user-agent thành 'Trình duyệt · Hệ điều hành' (không lưu thêm gì)."""
    u = ua or ""
    br = next((n for k, n in (("Edg/", "Edge"), ("OPR/", "Opera"), ("Firefox/", "Firefox"), ("Chrome/", "Chrome"), ("Safari/", "Safari")) if k in u), "")
    os_ = next((n for k, n in (("Windows", "Windows"), ("Android", "Android"), ("iPhone", "iPhone"), ("iPad", "iPad"), ("Mac OS X", "macOS"), ("Linux", "Linux")) if k in u), "")
    return " · ".join(x for x in (br, os_) if x) or (u[:40] or "không rõ")


class FleetService:
    def __init__(self, svc: AuthService):
        self.svc = svc
        self.fs = FleetStore(svc.store.pool)
        self._pending: dict[str, dict] = {}          # token -> {kind, actor, data, exp}  (bulk/import 2 bước; trong bộ nhớ, 1 instance)
        self._eaw: dict[str, float] = {}

    # ------------------------------------------------------------ quyền / phạm vi
    @staticmethod
    def need(p: Principal, perm: str) -> None:
        if not R.has_perm(p.role, perm):
            raise AuthError(403, "Không đủ quyền")

    def need_master(self, p: Principal, totp: bool = False) -> None:
        if p.role != "master":
            raise AuthError(403, "Chỉ master")
        if totp and self.svc.cfg.master_totp_required and not p.totp_enabled:
            raise AuthError(403, "Cần bật xác thực 2 bước (TOTP) trước khi dùng thao tác này", totp_required=True)

    @staticmethod
    def scope(p: Principal) -> list[str] | None:
        """None = mọi tài khoản (master). Vai trò phụ: danh sách tài khoản trong phạm vi (có thể rỗng)."""
        return None if p.role == "master" else list(p.accounts)

    def check_account(self, p: Principal, account_id: str) -> None:
        sc = self.scope(p)
        if sc is not None and account_id not in sc:
            raise AuthError(403, "Không có quyền")           # đồng nhất: không lộ tài khoản có tồn tại hay không

    async def audit(self, p: Principal, action: str, target: str, ip: str, detail: dict | None = None) -> None:
        await self.svc.store.audit(p.user_id, p.login_key, action, target, ip, detail or {})

    # ------------------------------------------------------------ fleet
    async def fleet(self, p: Principal, q: dict) -> dict:
        self.need(p, "fleet.read")
        rows = await self.fs.fleet_rows(self.scope(p))
        counts = {"total": len(rows), "online": 0, "degraded": 0, "offline": 0, "pending": 0, "suspended": 0, "red": 0, "yellow": 0, "accounts_with_incidents": 0}
        for r in rows:
            counts["pending"] += r["status"] == "pending"
            counts["suspended"] += r["status"] == "suspended"
            if r["status"] == "active" and r["ea_status"] in ("online", "degraded", "offline"):
                counts[r["ea_status"]] += 1
            counts["red"] += r["worst_status"] == "red"
            counts["yellow"] += r["worst_status"] == "yellow"
            counts["accounts_with_incidents"] += int(r["incidents_open"] or 0) > 0
        inc = await self.fs.incident_counts(self.scope(p))
        counts["incidents_open"] = inc["open"] + inc["ack"] + inc["snoozed"]

        def ok(r) -> bool:
            t = (q.get("q") or "").strip().lower()
            if t and t not in " ".join(str(r.get(k) or "") for k in ("account_id", "label", "client_name", "server")).lower():
                return False
            if q.get("group") and not any(g["id"] == q["group"] for g in r["groups"]):
                return False
            if q.get("tag") and q["tag"] not in r["tags"]:
                return False
            if q.get("status") and r["status"] != q["status"]:
                return False
            if q.get("ea") and (r["ea_status"] or "unknown") != q["ea"]:
                return False
            if q.get("compliance") and r["worst_status"] != q["compliance"]:
                return False
            if q.get("incident") and not int(r["incidents_open"] or 0):
                return False
            return True
        rows = [r for r in rows if ok(r)]
        key = {"label": lambda r: (r["label"] or r["account_id"]).lower(), "last_seen": lambda r: r["last_seen_at"] or datetime.min.replace(tzinfo=timezone.utc),
               "usage": lambda r: r["worst_usage"] if r["worst_usage"] is not None else -1.0, "status": lambda r: r["status"]}.get(q.get("sort") or "account_id", lambda r: r["account_id"])
        rows.sort(key=key, reverse=(q.get("dir") == "desc"))
        total = len(rows)
        off, lim = max(0, int(q.get("offset") or 0)), min(500, max(1, int(q.get("limit") or 200)))
        items = []
        for r in rows[off:off + lim]:
            items.append({"account_id": r["account_id"], "platform": r["platform"], "login": r["login"], "server": r["server"], "label": r["label"], "status": r["status"],
                          "ea_status": r["ea_status"] or "unknown", "ea_latency_ms": r["ea_latency_ms"], "ea_version": r["ea_version"],
                          "last_seen_at": r["last_seen_at"].isoformat() if r["last_seen_at"] else None, "groups": r["groups"], "tags": r["tags"],
                          "incidents_open": int(r["incidents_open"] or 0), "client_notify": bool(r["client_notify"]), "client_name": r["client_name"],
                          "compliance": {"status": r["worst_status"], "worst_usage_pct": r["worst_usage"], "worst_rule": r["worst_rule"]}})
        return {"items": items, "total": total, "counts": counts}

    # ------------------------------------------------------------ nhóm / tag / views / ghi chú
    async def groups(self, p: Principal) -> list[dict]:
        self.need(p, "fleet.read")
        gs = await self.fs.list_groups()
        if p.role != "master":                         # vai trò phụ chỉ thấy nhóm trong phạm vi
            allowed = {g["id"] for g in await self.fs.staff_scope(p.user_id)}
            if not await self._scope_all(p):
                gs = [g for g in gs if g["id"] in allowed]
        return gs

    async def _scope_all(self, p: Principal) -> bool:
        u = await self.svc.store.get_user(p.user_id)
        return bool(u and u.get("scope_all"))

    async def create_group(self, p: Principal, name: str, description: str, color: str, ip: str) -> dict:
        self.need_master(p)
        try:
            g = await self.fs.create_group(name.strip()[:60], description[:200], color[:16], p.user_id)
        except Exception as e:  # noqa: BLE001
            if "unique" in str(e).lower() or "duplicate" in str(e).lower():
                raise AuthError(409, "Tên nhóm đã tồn tại") from None
            raise
        await self.audit(p, "group_created", g["id"], ip, {"name": g["name"]})
        return g

    async def update_group(self, p: Principal, gid: str, f: dict, ip: str) -> dict:
        self.need_master(p)
        g = await self.fs.update_group(gid, **f)
        if not g:
            raise AuthError(404, "Không có nhóm này")
        await self.audit(p, "group_updated", gid, ip, {k: v for k, v in f.items() if v is not None})
        return g

    async def delete_group(self, p: Principal, gid: str, ip: str) -> None:
        self.need_master(p)
        if not await self.fs.delete_group(gid):
            raise AuthError(404, "Không có nhóm này")
        await self.audit(p, "group_deleted", gid, ip, {})

    async def group_members(self, p: Principal, gid: str, add: list[str] | None, remove: str | None, ip: str) -> dict:
        self.need_master(p)
        if not await self.fs.get_group(gid):
            raise AuthError(404, "Không có nhóm này")
        if add is not None:
            n = await self.fs.add_members(gid, [a for a in add if ACCOUNT_ID_RE.match(a)][:2000])
            await self.audit(p, "group_members_added", gid, ip, {"n": n})
            return {"added": n}
        if remove:
            await self.fs.remove_member(gid, remove)
            await self.audit(p, "group_member_removed", gid, ip, {"account": remove})
        return {"ok": True}

    async def set_group_policy(self, p: Principal, gid: str, pol: dict, ip: str) -> dict:
        self.need_master(p)
        clean = {"ea_offline_grace_min": int(max(1, min(1440, pol.get("ea_offline_grace_min", 5)))),
                 "min_severity": pol.get("min_severity") if pol.get("min_severity") in SEV_RANK else "info",
                 "client_notify": bool(pol.get("client_notify", False))}
        au = pol.get("auto_assign_user_id")
        if au:
            if not UUID_RX.match(str(au)) or not await self.svc.store.get_user(str(au)):
                raise AuthError(422, "Người xử lý mặc định không hợp lệ")
            clean["auto_assign_user_id"] = str(au)
        if not await self.fs.set_group_policy(gid, clean):
            raise AuthError(404, "Không có nhóm này")
        await self.audit(p, "group_policy_changed", gid, ip, clean)
        return clean

    async def get_policy(self, p: Principal, gid: str) -> dict:
        self.need(p, "fleet.read")
        g = await self.fs.get_group(gid)
        if not g:
            raise AuthError(404, "Không có nhóm này")
        return g["policy"]

    async def set_account_groups(self, p: Principal, account_id: str, group_ids: list[str], ip: str) -> None:
        self.need_master(p)
        if not await self.svc.store.get_account(account_id):
            raise AuthError(404, "Không có tài khoản này")
        await self.fs.set_account_groups(account_id, group_ids)
        await self.audit(p, "account_groups_set", account_id, ip, {"n": len(group_ids)})

    async def set_account_tags(self, p: Principal, account_id: str, tags: list[str], ip: str) -> list[str]:
        self.need_master(p)
        tags = sorted({t.strip().lower() for t in tags if t.strip()})
        if len(tags) > 12 or any(not TAG_RE.match(t) for t in tags):
            raise AuthError(422, "Tag không hợp lệ (a-z, 0-9, _ . -; tối đa 24 ký tự; tối đa 12 tag)")
        if not await self.svc.store.get_account(account_id):
            raise AuthError(404, "Không có tài khoản này")
        await self.fs.set_account_tags(account_id, tags)
        await self.audit(p, "account_tags_set", account_id, ip, {"tags": tags})
        return tags

    async def tags(self, p: Principal) -> list[dict]:
        self.need(p, "fleet.read")
        return await self.fs.list_tags()

    async def views(self, p: Principal) -> list[dict]:
        self.need(p, "fleet.read")
        return [{**v, "owner_user_id": str(v["owner_user_id"]), "mine": str(v["owner_user_id"]) == p.user_id} for v in await self.fs.list_views(p.user_id)]

    async def create_view(self, p: Principal, name: str, filters: dict, shared: bool) -> dict:
        self.need(p, "fleet.read")
        clean = {k: str(filters[k])[:80] for k in ("q", "group", "tag", "status", "ea", "compliance", "incident", "sort", "dir") if filters.get(k) not in (None, "")}
        if shared and p.role != "master":
            shared = False
        return await self.fs.create_view(p.user_id, name.strip()[:60], clean, shared)

    async def delete_view(self, p: Principal, vid: str) -> None:
        v = await self.fs.get_view(vid)
        if not v or (p.role != "master" and str(v["owner_user_id"]) != p.user_id):
            raise AuthError(404, "Không có view này")
        await self.fs.delete_view(vid)

    async def notes(self, p: Principal, account_id: str) -> list[dict]:
        self.need(p, "fleet.read")
        self.check_account(p, account_id)
        return [{**n, "author_user_id": str(n["author_user_id"]) if n["author_user_id"] else None, "created_at": n["created_at"].isoformat()} for n in await self.fs.list_notes(account_id)]

    async def add_note(self, p: Principal, account_id: str, text: str, ip: str) -> dict:
        self.need(p, "note.write")
        self.check_account(p, account_id)
        text = text.strip()
        if not text or len(text) > 1000:
            raise AuthError(422, "Ghi chú trống hoặc quá dài (<=1000)")
        if not await self.svc.store.get_account(account_id):
            raise AuthError(404, "Không có tài khoản này")
        n = await self.fs.add_note(account_id, p.user_id, p.display_name or p.login_key, text)
        await self.audit(p, "account_note_added", account_id, ip, {})
        return {**n, "created_at": n["created_at"].isoformat()}

    # ------------------------------------------------------------ bulk 2 bước
    def _gc(self) -> None:
        t = time.monotonic()
        for k in [k for k, v in self._pending.items() if v["exp"] < t]:
            self._pending.pop(k, None)

    async def bulk_prepare(self, p: Principal, action: str, account_ids: list[str], params: dict, ip: str) -> dict:
        self.need_master(p, totp=True)
        if action not in BULK_ACTIONS:
            raise AuthError(422, "Hành động không hợp lệ")
        ids = list(dict.fromkeys(a for a in account_ids if ACCOUNT_ID_RE.match(a)))
        if not ids or len(ids) > MAX_BULK:
            raise AuthError(422, f"Chọn 1..{MAX_BULK} tài khoản")
        params = params or {}
        if action in ("tag_add", "tag_remove"):
            params = {"tag": str(params.get("tag", "")).strip().lower()}
            if not TAG_RE.match(params["tag"]):
                raise AuthError(422, "Tag không hợp lệ")
        if action in ("group_add", "group_remove"):
            gid = str(params.get("group_id", ""))
            if not UUID_RX.match(gid) or not await self.fs.get_group(gid):
                raise AuthError(422, "Nhóm không hợp lệ")
            params = {"group_id": gid}
        existing = {a["account_id"]: a for a in await self.svc.store.list_accounts_full()}
        ok_ids, skipped = [], []
        for a in ids:
            row = existing.get(a)
            if not row:
                skipped.append({"account_id": a, "reason": "không tồn tại"})
            elif action == "suspend" and row["status"] == "suspended":
                skipped.append({"account_id": a, "reason": "đã bị đình chỉ"})
            elif action == "activate" and row["status"] == "active":
                skipped.append({"account_id": a, "reason": "đã hoạt động"})
            else:
                ok_ids.append(a)
        if not ok_ids:
            raise AuthError(422, "Không có tài khoản hợp lệ để thao tác", skipped=skipped)
        self._gc()
        token = secrets.token_urlsafe(24)
        phrase = f"XAC NHAN {len(ok_ids)}"
        digest = hashlib.sha256(",".join(sorted(ok_ids)).encode()).hexdigest()
        self._pending[token] = {"kind": "bulk", "actor": p.user_id, "action": action, "ids": ok_ids, "params": params, "phrase": phrase, "digest": digest, "exp": time.monotonic() + 120}
        await self.audit(p, "bulk_prepared", action, ip, {"count": len(ok_ids)})
        warn = ["Xoay token/secret làm EA của các tài khoản này ngừng gửi dữ liệu tới khi nhập giá trị mới."] if action.startswith("rotate") else []
        return {"confirm_token": token, "expires_in": 120, "summary": {"count": len(ok_ids), "action": action, "params": params, "skipped": skipped, "phrase": phrase, "warnings": warn}}

    async def bulk_execute(self, p: Principal, token: str, phrase: str, ip: str) -> dict:
        self.need_master(p, totp=True)
        self._gc()
        op = self._pending.pop(token, None)
        if not op or op["kind"] != "bulk" or op["actor"] != p.user_id:
            raise AuthError(400, "Phiên xác nhận không hợp lệ hoặc đã hết hạn")
        if not secrets.compare_digest((phrase or "").strip().upper(), op["phrase"]):
            raise AuthError(400, f"Cụm xác nhận sai (gõ đúng: {op['phrase']})")
        action, params, results = op["action"], op["params"], []
        for a in op["ids"]:
            try:
                secret = None
                if action == "suspend":
                    await self.svc.set_account_status(p, a, True, ip)
                elif action == "activate":
                    await self.svc.set_account_status(p, a, False, ip)
                elif action == "tag_add":
                    await self.fs.add_tag([a], params["tag"])
                elif action == "tag_remove":
                    await self.fs.remove_tag([a], params["tag"])
                elif action == "group_add":
                    await self.fs.add_members(params["group_id"], [a])
                elif action == "group_remove":
                    await self.fs.remove_member(params["group_id"], a)
                elif action == "rotate_ea_token":
                    secret = (await self.svc.rotate_ea_token(p, a, ip))["ea_token"]
                elif action == "rotate_hmac":
                    secret = (await self.svc.rotate_hmac(p, a, ip))["hmac_secret"]
                results.append({"account_id": a, "ok": True, **({"secret": secret} if secret else {})})
            except AuthError as e:
                results.append({"account_id": a, "ok": False, "error": e.message})
            except Exception as e:  # noqa: BLE001
                log.exception("bulk %s %s", action, a)
                results.append({"account_id": a, "ok": False, "error": type(e).__name__})
        await self.audit(p, "bulk_executed", action, ip, {"count": len(results), "ok": sum(1 for r in results if r["ok"]), "digest": op["digest"][:16]})
        return {"results": results, "action": action}

    # ------------------------------------------------------------ import CSV
    async def import_preview(self, p: Principal, text: str, ip: str) -> dict:
        self.need_master(p, totp=True)
        if len(text) > 200_000:
            raise AuthError(413, "CSV quá lớn (<=200 KB)")
        text = text.lstrip("﻿")
        try:
            dialect = csv.Sniffer().sniff(text[:2000], delimiters=",;\t") if text.strip() else csv.excel
        except csv.Error:
            dialect = csv.excel
        rd = csv.reader(io.StringIO(text), dialect)
        rows_in = [r for r in rd if any(c.strip() for c in r)]
        if not rows_in:
            raise AuthError(422, "CSV trống")
        head = [h.strip().lower() for h in rows_in[0]]
        if "login" not in head:
            raise AuthError(422, "Thiếu cột login (cột: platform,login,server,label,group,tags,notes)")
        body = rows_in[1:]
        if len(body) > MAX_IMPORT:
            raise AuthError(422, f"Tối đa {MAX_IMPORT} dòng mỗi lần nhập")
        groups = {g["name"].lower(): g for g in await self.fs.list_groups()}
        existing = {(a["platform"], int(a["login"]), (a["server"] or "").lower()) for a in await self.svc.store.list_accounts_full()}
        seen, out = set(), []
        for i, raw in enumerate(body, start=2):
            d = {h: (raw[j].strip() if j < len(raw) else "") for j, h in enumerate(head)}
            err, warn = [], []
            platform = (d.get("platform") or "mt5").lower()
            if platform not in ("mt4", "mt5"):
                err.append("platform phải là mt4 hoặc mt5")
            try:
                login = int(d.get("login", ""))
                if login <= 0 or login > 2**53:
                    raise ValueError
            except ValueError:
                login = 0
                err.append("login phải là số nguyên dương")
            server = d.get("server", "")[:64]
            if not SERVER_RE.match(server):
                err.append("server không hợp lệ")
            label = d.get("label", "")[:80]
            notes = d.get("notes", "")[:500]
            tags = sorted({t.lower() for t in re.split(r"[;\s|]+", d.get("tags", "")) if t})
            if any(not TAG_RE.match(t) for t in tags) or len(tags) > 12:
                err.append("tag không hợp lệ (a-z0-9_.-, <=24 ký tự, <=12 tag)")
            gname = d.get("group", "")[:60]
            if gname and gname.lower() not in groups:
                warn.append(f"nhóm '{gname}' chưa có — sẽ được tạo")
            sig = (platform, login, server.lower())
            if login and sig in existing:
                err.append("tài khoản đã tồn tại")
            if login and sig in seen:
                err.append("trùng dòng khác trong CSV")
            seen.add(sig)
            out.append({"line": i, "platform": platform, "login": login or d.get("login", ""), "server": server, "label": label, "group": gname, "tags": tags, "notes": notes,
                        "errors": err, "warnings": warn, "ok": not err})
        self._gc()
        token = secrets.token_urlsafe(24)
        okrows = [r for r in out if r["ok"]]
        self._pending[token] = {"kind": "import", "actor": p.user_id, "rows": okrows, "exp": time.monotonic() + 600}
        await self.audit(p, "import_previewed", "csv", ip, {"rows": len(out), "ok": len(okrows)})
        return {"preview_token": token, "rows": out, "summary": {"total": len(out), "ok": len(okrows), "error": len(out) - len(okrows)}}

    async def import_commit(self, p: Principal, token: str, ip: str) -> dict:
        self.need_master(p, totp=True)
        self._gc()
        op = self._pending.pop(token, None)
        if not op or op["kind"] != "import" or op["actor"] != p.user_id:
            raise AuthError(400, "Bản xem trước không hợp lệ hoặc đã hết hạn")
        created, failed = [], []
        gcache: dict[str, str] = {g["name"].lower(): g["id"] for g in await self.fs.list_groups()}
        for r in op["rows"]:
            try:
                res = await self.svc.create_account(p, r["platform"], int(r["login"]), r["server"], r["label"], r["notes"], ip)
                aid = res["account"]["account_id"]
                if r["tags"]:
                    await self.fs.set_account_tags(aid, r["tags"])
                if r["group"]:
                    gid = gcache.get(r["group"].lower())
                    if not gid:
                        gid = (await self.fs.create_group(r["group"], "", "", p.user_id))["id"]
                        gcache[r["group"].lower()] = gid
                    await self.fs.add_members(gid, [aid])
                created.append({"line": r["line"], "account_id": aid, "label": r["label"], "server": r["server"], "secrets": res["secrets"]})
            except AuthError as e:
                failed.append({"line": r["line"], "error": e.message})
            except Exception as e:  # noqa: BLE001
                log.exception("import dòng %s", r["line"])
                failed.append({"line": r["line"], "error": type(e).__name__})
        await self.audit(p, "import_committed", "csv", ip, {"created": len(created), "failed": len(failed)})
        return {"created": created, "failed": failed}

    # ------------------------------------------------------------ luật + tuân thủ
    def presets(self) -> dict:
        return {"presets": fleet_rules.PRESETS, "disclaimer": fleet_rules.DISCLAIMER, "kinds": [{"kind": k, "label": fleet_rules.KIND_LABEL[k]} for k in fleet_rules.KINDS]}

    async def templates(self, p: Principal) -> list[dict]:
        self.need(p, "compliance.read")
        return await self.fs.list_templates()

    async def create_template(self, p: Principal, name: str, kind: str, params: dict, description: str, ip: str) -> dict:
        self.need_master(p)
        try:
            clean = fleet_rules.validate_params(kind, params)
        except ValueError as e:
            raise AuthError(422, str(e)) from None
        try:
            t = await self.fs.create_template(name.strip()[:80], kind, clean, description[:300], p.user_id)
        except Exception as e:  # noqa: BLE001
            if "unique" in str(e).lower() or "duplicate" in str(e).lower():
                raise AuthError(409, "Tên mẫu luật đã tồn tại") from None
            raise
        await self.audit(p, "rule_template_created", t["id"], ip, {"kind": kind})
        return t

    async def update_template(self, p: Principal, tid: str, name: str, params: dict, description: str, ip: str) -> dict:
        self.need_master(p)
        cur = await self.fs.get_template(tid)
        if not cur:
            raise AuthError(404, "Không có mẫu luật này")
        try:
            clean = fleet_rules.validate_params(cur["kind"], params)
        except ValueError as e:
            raise AuthError(422, str(e)) from None
        t = await self.fs.update_template(tid, name.strip()[:80], clean, description[:300])
        await self.audit(p, "rule_template_updated", tid, ip, {})
        return t

    async def delete_template(self, p: Principal, tid: str, ip: str) -> None:
        self.need_master(p)
        if not await self.fs.get_template(tid):
            raise AuthError(404, "Không có mẫu luật này")
        for aid in await self.fs.delete_template(tid):
            await self.fs.close_incidents_like(f"rule:{aid}:")
        await self.audit(p, "rule_template_deleted", tid, ip, {})

    async def assignments(self, p: Principal) -> list[dict]:
        self.need(p, "compliance.read")
        return await self.fs.list_assignments()

    async def _check_scope_ref(self, stype: str, ref: str) -> str:
        if stype == "all":
            return ""
        if stype == "group":
            if not UUID_RX.match(ref) or not await self.fs.get_group(ref):
                raise AuthError(422, "Nhóm không hợp lệ")
        elif stype == "tag":
            if not TAG_RE.match(ref):
                raise AuthError(422, "Tag không hợp lệ")
        elif stype == "account":
            if not ACCOUNT_ID_RE.match(ref) or not await self.svc.store.get_account(ref):
                raise AuthError(422, "Tài khoản không hợp lệ")
        else:
            raise AuthError(422, "Loại phạm vi không hợp lệ")
        return ref

    async def create_assignment(self, p: Principal, template_id: str, stype: str, ref: str, enabled: bool, notify_client: bool, ip: str) -> dict:
        self.need_master(p)
        if not UUID_RX.match(template_id) or not await self.fs.get_template(template_id):
            raise AuthError(422, "Mẫu luật không hợp lệ")
        ref = await self._check_scope_ref(stype, ref)
        a = await self.fs.create_assignment(template_id, stype, ref, enabled, notify_client, p.user_id)
        await self.audit(p, "rule_assigned", a["id"], ip, {"scope": stype, "ref": ref})
        return a

    async def update_assignment(self, p: Principal, aid: str, f: dict, ip: str) -> dict:
        self.need_master(p)
        cur = await self.fs.get_assignment(aid)
        if not cur:
            raise AuthError(404, "Không có gán luật này")
        if f.get("scope_type") is not None:
            f["scope_ref"] = await self._check_scope_ref(f["scope_type"], f.get("scope_ref") or "")
        a = await self.fs.update_assignment(aid, **f)
        if f.get("scope_type") is not None or f.get("enabled") is False:
            await self.fs.clear_rule_status(aid)
            await self.fs.close_incidents_like(f"rule:{aid}:")
        await self.audit(p, "rule_assignment_updated", aid, ip, {k: v for k, v in f.items() if v is not None})
        return a

    async def delete_assignment(self, p: Principal, aid: str, ip: str) -> None:
        self.need_master(p)
        if not await self.fs.delete_assignment(aid):
            raise AuthError(404, "Không có gán luật này")
        await self.fs.close_incidents_like(f"rule:{aid}:")
        await self.audit(p, "rule_assignment_deleted", aid, ip, {})

    async def compliance(self, p: Principal, q: dict) -> dict:
        self.need(p, "compliance.read")
        rows = await self.fs.compliance_rows(self.scope(p))
        t = now()
        items, summ = [], {"green": 0, "yellow": 0, "red": 0, "na": 0, "stale": 0}
        for r in rows:
            if q.get("group") and q["group"] not in r["group_ids"]:
                continue
            if q.get("tag") and q["tag"] not in r["tags"]:
                continue
            if q.get("status") and r["status"] != q["status"]:
                continue
            if q.get("assignment") and r["assignment_id"] != q["assignment"]:
                continue
            stale = (t - r["evaluated_at"]).total_seconds() > STALE_S
            summ[r["status"]] += 1
            summ["stale"] += stale
            items.append({"account_id": r["account_id"], "label": r["label"], "groups": r["groups"], "assignment_id": r["assignment_id"], "rule_name": r["rule_name"], "kind": r["kind"],
                          "status": r["status"], "usage_pct": r["usage_pct"], "value": r["value"], "limit": r["limit"], "headroom": r["headroom"], "unit": r["unit"],
                          "reset_at": r["reset_at"].isoformat() if r["reset_at"] else None, "evaluated_at": r["evaluated_at"].isoformat(), "stale": stale,
                          "detail": r["detail"] if isinstance(r["detail"], dict) else {}})
        return {"summary": summ, "items": items[: min(2000, int(q.get("limit") or 1000))]}

    # ------------------------------------------------------------ sự cố
    async def incidents(self, p: Principal, q: dict) -> dict:
        self.need(p, "incident.read")
        sc = self.scope(p)
        sset = set(sc) if sc is not None else None
        st = q.get("status")
        statuses = {"active": ["open", "ack", "snoozed"]}.get(st) or ([st] if st in ("open", "ack", "snoozed", "resolved") else ["open", "ack", "snoozed"])
        rows = await self.fs.list_incidents(statuses, 1000 if st != "resolved" else 200)
        me = p.user_id
        out = []
        for r in rows:
            if sset is not None and r["account_id"] not in sset:
                continue
            if q.get("severity") and r["severity"] != q["severity"]:
                continue
            if q.get("kind") and r["kind"] != q["kind"]:
                continue
            if q.get("group") and q["group"] not in r["group_ids"]:
                continue
            if q.get("account") and r["account_id"] != q["account"]:
                continue
            a = q.get("assignee")
            if a == "me" and r["assignee_user_id"] != me:
                continue
            if a == "none" and r["assignee_user_id"]:
                continue
            if a and a not in ("me", "none") and r["assignee_user_id"] != a:
                continue
            out.append(self._inc_out(r))
        res: dict = {"items": out[: min(500, int(q.get("limit") or 300))], "counts": await self.fs.incident_counts(sc)}
        if q.get("group_by") == "cause":
            cl: dict[str, dict] = {}
            for i in out:
                c = cl.setdefault(i["cause_key"] or i["id"], {"cause_key": i["cause_key"] or i["id"], "title": i["title"], "count": 0, "severity": "info", "incident_ids": [], "accounts": []})
                c["count"] += 1
                c["incident_ids"].append(i["id"])
                c["accounts"].append(i["account_id"])
                if SEV_RANK[i["severity"]] > SEV_RANK[c["severity"]]:
                    c["severity"] = i["severity"]
            for c in cl.values():
                if c["count"] > 1:
                    c["title"] = re.sub(r":.*$", "", c["title"]) + f" — {c['count']} tài khoản"
            res["clusters"] = sorted(cl.values(), key=lambda c: (-SEV_RANK[c["severity"]], -c["count"]))
        return res

    @staticmethod
    def _inc_out(r: dict) -> dict:
        d = {k: r[k] for k in ("id", "key", "kind", "account_id", "cause_key", "severity", "status", "title", "detail", "assignee_label", "resolved_by", "occurrences")}
        d["assignee_user_id"] = r["assignee_user_id"]
        for k in ("snoozed_until", "opened_at", "acked_at", "resolved_at", "last_seen_at"):
            d[k] = r[k].isoformat() if r.get(k) else None
        return d

    async def incident(self, p: Principal, iid: str) -> dict:
        self.need(p, "incident.read")
        r = await self.fs.get_incident(iid)
        if not r:
            raise AuthError(404, "Không có sự cố này")
        if r["account_id"]:
            self.check_account(p, r["account_id"])
        elif p.role != "master":
            raise AuthError(403, "Không có quyền")
        out = self._inc_out(r)
        out["events"] = [{"id": e["event_id"], "ts": e["ts"].isoformat(), "actor": e["actor_label"], "type": e["type"], "text": e["text"]} for e in r["events"]]
        out["meta"] = r["meta"]
        return out

    async def incident_action(self, p: Principal, iid: str, action: str, ip: str, *, text: str = "", user_id: str | None = None, minutes: int = 0) -> dict:
        if action == "note":
            self.need(p, "incident.note")
        else:
            self.need_master(p)                       # support = chỉ đọc + ghi chú
        r = await self.fs.get_incident(iid)
        if not r:
            raise AuthError(404, "Không có sự cố này")
        if r["account_id"]:
            self.check_account(p, r["account_id"])
        label = p.display_name or p.login_key
        assignee, until = None, None
        if action == "assign":
            if user_id:
                u = await self.svc.store.get_user(user_id) if UUID_RX.match(user_id) else None
                if not u or u["role"] not in ("master", "support") or u["status"] != "active":
                    raise AuthError(422, "Người xử lý không hợp lệ")
                assignee = (str(u["user_id"]), u["display_name"] or u["login_key"])
            else:
                assignee = (None, "")
        if action == "snooze":
            if not 5 <= minutes <= 10080:
                raise AuthError(422, "Thời gian tạm hoãn 5..10080 phút")
            until = now() + timedelta(minutes=minutes)
        if action == "note" and not (text.strip() and len(text) <= 1000):
            raise AuthError(422, "Ghi chú trống hoặc quá dài")
        ok = await self.fs.incident_action(iid, action, p.user_id, label, text=text.strip(), assignee=assignee, until=until)
        if not ok:
            raise AuthError(409, "Trạng thái hiện tại không cho phép thao tác này")
        await self.audit(p, f"incident_{action}", iid, ip, {"account": r["account_id"]})
        return await self.incident(p, iid)

    async def incidents_bulk(self, p: Principal, ids: list[str], action: str, minutes: int, ip: str) -> dict:
        self.need_master(p)
        if action not in ("ack", "resolve", "snooze") or not ids or len(ids) > 100:
            raise AuthError(422, "Tham số không hợp lệ")
        res = []
        for i in ids:
            if not UUID_RX.match(i):
                res.append({"id": i, "ok": False})
                continue
            try:
                await self.incident_action(p, i, action, ip, minutes=minutes)
                res.append({"id": i, "ok": True})
            except AuthError as e:
                res.append({"id": i, "ok": False, "error": e.message})
        return {"results": res}

    async def assignees(self, p: Principal) -> list[dict]:
        self.need(p, "incident.read")
        return [{"user_id": u["user_id"], "name": u["display_name"] or u["login_key"], "role": u["role"]} for u in await self.fs.users_for_assign()]

    # ------------------------------------------------------------ nhân sự phụ
    async def staff(self, p: Principal) -> list[dict]:
        self.need_master(p)
        return [{**s, "last_login_at": s["last_login_at"].isoformat() if s["last_login_at"] else None, "created_at": s["created_at"].isoformat()} for s in await self.fs.list_staff()]

    async def create_staff(self, p: Principal, name: str, role: str, display_name: str, scope_all: bool, group_ids: list[str], ip: str) -> dict:
        self.need_master(p, totp=True)
        name = name.lower().strip()
        if role not in R.STAFF_ROLES or not NAME_RE.match(name):
            raise AuthError(422, "Tên/vai trò không hợp lệ")
        if await self.svc.store.get_user_by_key(f"master:{name}"):
            raise AuthError(409, "Tên đã tồn tại")
        if any(not UUID_RX.match(g) for g in group_ids):
            raise AuthError(422, "Nhóm không hợp lệ")
        pw = secrets.token_urlsafe(18)
        u = await self.fs.create_staff(role, f"master:{name}", (display_name or name)[:80], await sec.ahash(pw), bool(scope_all), group_ids, p.user_id)
        await self.audit(p, "staff_created", u["login_key"], ip, {"role": role, "scope_all": bool(scope_all), "groups": len(group_ids)})
        return {"user": u, "password": pw, "note": "Mật khẩu chỉ hiển thị MỘT lần; người dùng phải đổi khi đăng nhập lần đầu (nền tảng: master, tên đăng nhập = tên)."}

    async def update_staff(self, p: Principal, user_id: str, role: str | None, scope_all: bool | None, group_ids: list[str] | None, display_name: str | None, ip: str) -> dict:
        self.need_master(p, totp=True)
        if role is not None and role not in R.STAFF_ROLES:
            raise AuthError(422, "Vai trò không hợp lệ")
        if not UUID_RX.match(user_id) or (group_ids is not None and any(not UUID_RX.match(g) for g in group_ids)):
            raise AuthError(422, "Định danh không hợp lệ")
        if not await self.fs.update_staff(user_id, role, scope_all, group_ids, display_name):
            raise AuthError(404, "Không có nhân sự phụ này")
        self.svc._cache_drop_user(user_id)
        await self.svc.store.revoke_user_sessions(user_id)       # đổi quyền/phạm vi => buộc đăng nhập lại
        await self.audit(p, "staff_updated", user_id, ip, {"role": role, "scope_all": scope_all, "groups": None if group_ids is None else len(group_ids)})
        return {"ok": True}

    # ------------------------------------------------------------ xem như khách (có hạn + lý do)
    async def view_as(self, p: Principal, account_id: str, reason: str, ip: str) -> dict:
        self.need_master(p, totp=True)
        reason = (reason or "").strip()
        if len(reason) < 8 or len(reason) > 300:
            raise AuthError(422, "Cần nêu lý do (8..300 ký tự)")
        if not await self.svc.store.get_account(account_id):
            raise AuthError(404, "Không có tài khoản này")
        minutes = self.svc.cfg.view_as_minutes
        g = await self.fs.create_grant(p.user_id, p.login_key, account_id, reason, now() + timedelta(minutes=minutes))
        await self.audit(p, "view_as", account_id, ip, {"reason": reason, "grant_id": str(g["grant_id"]), "minutes": minutes})
        return {"grant_id": str(g["grant_id"]), "account_id": account_id, "expires_at": g["expires_at"].isoformat(), "minutes": minutes}

    async def view_as_end(self, p: Principal, grant_id: str, ip: str) -> dict:
        self.need_master(p)
        if not UUID_RX.match(grant_id):
            raise AuthError(404, "Không có phiên xem này")
        g = await self.fs.end_grant(grant_id, p.user_id)
        if g:
            await self.audit(p, "view_as_end", g["account_id"], ip, {"grant_id": grant_id})
        return {"ok": True}

    async def view_as_active(self, p: Principal) -> list[dict]:
        self.need_master(p)
        return [{"grant_id": str(g["grant_id"]), "account_id": g["account_id"], "reason": g["reason"], "created_at": g["created_at"].isoformat(),
                 "expires_at": g["expires_at"].isoformat()} for g in await self.fs.active_grants(p.user_id)]

    # ------------------------------------------------------------ khách opt-in thông báo
    async def client_notify_get(self, p: Principal) -> dict:
        if p.role != "client":
            raise AuthError(403, "Chỉ khách hàng")
        rows = await self.fs.fleet_rows(list(p.accounts)) if p.accounts else []
        return {"enabled": bool(rows) and all(r["client_notify"] for r in rows), "accounts": [r["account_id"] for r in rows]}

    async def client_notify_set(self, p: Principal, enabled: bool, ip: str) -> dict:
        if p.role != "client":
            raise AuthError(403, "Chỉ khách hàng")
        for a in p.accounts:
            await self.fs.set_client_notify(a, enabled)
        await self.svc.store.audit(p.user_id, p.login_key, "client_notify_set", ",".join(p.accounts)[:200], ip, {"enabled": enabled})
        return {"enabled": enabled, "accounts": list(p.accounts)}

    # ------------------------------------------------------------ nội bộ: risk-monitor / reporter
    async def internal_rules(self) -> dict:
        asg = await self.fs.engine_assignments()
        idx = await self.fs.scope_index()
        out, client_push = [], {}
        for a in asg:
            t, ref = a["scope_type"], a["scope_ref"]
            accs = [k for k, v in idx.items() if t == "all" or (t == "group" and ref in v["groups"]) or (t == "tag" and ref in v["tags"]) or (t == "account" and k == ref)]
            out.append({"assignment_id": a["assignment_id"], "template_id": a["template_id"], "name": a["name"], "kind": a["kind"], "params": a["params"],
                        "accounts": sorted(accs), "notify_client": bool(a["notify_client"])})
            if a["notify_client"]:
                for k in accs:
                    if idx[k]["notify"] and idx[k]["user"]:
                        client_push[k] = str(idx[k]["user"])
        return {"rev": int(time.time()), "assignments": out, "client_push": client_push}

    async def internal_results(self, body: dict) -> dict:
        names = {a["assignment_id"]: a for a in await self.fs.engine_assignments()}
        idx_labels = {r["account_id"]: r["label"] for r in await self.fs.fleet_rows(None)} if body.get("results") or body.get("conditions") else {}
        rows, opened, closed, accepted = [], [], 0, 0
        pol_cache: dict[str, dict] = {}

        async def policy(acc: str) -> dict:
            if acc not in pol_cache:
                pols = await self.fs.group_policies_for(acc)
                mins = [SEV_RANK.get(x.get("min_severity", "info"), 0) for x in pols] or [0]
                assign = next((x.get("auto_assign_user_id") for x in pols if x.get("auto_assign_user_id")), None)
                pol_cache[acc] = {"min": min(mins), "assign": assign}
            return pol_cache[acc]

        async def assignee_of(acc: str):
            pol = await policy(acc)
            if pol["assign"]:
                u = await self.svc.store.get_user(pol["assign"])
                if u and u["status"] == "active":
                    return (str(u["user_id"]), u["display_name"] or u["login_key"])
            return None

        def num(v):
            try:
                f = float(v)
                return f if f == f and abs(f) < 1e15 else None
            except (TypeError, ValueError):
                return None

        def ts(v):
            if isinstance(v, str) and v:
                with contextlib.suppress(ValueError):
                    return datetime.fromisoformat(v.replace("Z", "+00:00"))
            return None
        for r in (body.get("results") or [])[:5000]:
            if not isinstance(r, dict) or not ACCOUNT_ID_RE.match(str(r.get("account_id") or "")) or not UUID_RX.match(str(r.get("assignment_id") or "")):
                continue
            st = r.get("status")
            if st not in ("green", "yellow", "red", "na"):
                continue
            detail = r.get("detail") if isinstance(r.get("detail"), dict) else {}
            rows.append({"account_id": r["account_id"], "assignment_id": r["assignment_id"], "status": st, "usage_pct": num(r.get("usage_pct")), "value": num(r.get("value")),
                         "limit": num(r.get("limit")), "headroom": num(r.get("headroom")), "unit": str(r.get("unit") or "")[:8], "detail": detail,
                         "reset_at": ts(r.get("reset_at")), "evaluated_at": ts(r.get("evaluated_at")) or now()})
        accepted = await self.fs.upsert_results(rows)
        for r in rows:
            a = names.get(r["assignment_id"])
            if not a or r["status"] == "na" or r["account_id"] not in idx_labels:      # bỏ tài khoản không tồn tại (không sinh sự cố rác)
                continue
            key = f"rule:{r['assignment_id']}:{r['account_id']}"
            sev = STATUS_SEV.get(r["status"])
            pol = await policy(r["account_id"])
            if sev is None or SEV_RANK[sev] < pol["min"]:
                closed += await self.fs.close_incident_by_key(key)
                continue
            label = idx_labels.get(r["account_id"]) or r["account_id"]
            u = f"{r['usage_pct']:.0f}%" if r["usage_pct"] is not None else "?"
            head = "" if r["headroom"] is None else f" Còn lại: {r['headroom']:.2f}{r['unit']}."
            title = f"{a['name']}: {label} — {'VI PHẠM' if sev == 'critical' else 'sát ngưỡng'} ({u})"
            detail = f"Mức dùng hạn mức {u}.{head}"
            iid, how = await self.fs.upsert_incident(key, "rule", r["account_id"], f"rule:{r['assignment_id']}", sev, title, detail,
                                                     {"assignment_id": r["assignment_id"], "usage_pct": r["usage_pct"], "rule_kind": a["kind"]},
                                                     await assignee_of(r["account_id"]))
            if how == "opened":
                opened.append(iid)
        for c in (body.get("conditions") or [])[:5000]:
            if not isinstance(c, dict) or str(c.get("account_id") or "") not in idx_labels:
                continue
            key = str(c.get("key") or "")
            if not re.match(r"^(budget|other):[\w.:\-]{1,120}$", key):
                continue
            sev = {"critical": "critical", "warning": "warning"}.get(c.get("severity"))
            kind = "budget" if key.startswith("budget:") else "other"
            if sev is None:
                closed += await self.fs.close_incident_by_key(key)
                continue
            pol = await policy(c["account_id"])
            if SEV_RANK[sev] < pol["min"]:
                continue
            iid, how = await self.fs.upsert_incident(key, kind, c["account_id"], str(c.get("cause_key") or key)[:120], sev, str(c.get("title") or key)[:300],
                                                     str(c.get("detail") or "")[:1000], {}, await assignee_of(c["account_id"]))
            if how == "opened":
                opened.append(iid)
        return {"accepted": accepted, "opened": opened, "closed": closed}

    async def scope_accounts(self, stype: str, ref: str) -> dict:
        idx = await self.fs.scope_index()
        gname = {g["id"]: g["name"] for g in await self.fs.list_groups()}
        out = []
        for k, v in sorted(idx.items()):
            if stype == "all" or (stype == "group" and ref in v["groups"]) or (stype == "tag" and ref in v["tags"]) or (stype == "account" and k == ref):
                out.append({"account_id": k, "label": v["label"], "groups": [gname.get(g, g) for g in v["groups"]]})
        return {"accounts": out}

    async def account_compliance(self, account_id: str) -> dict:
        rows = await self.fs.compliance_rows([account_id])
        return {"account_id": account_id, "rules": [{"rule_name": r["rule_name"], "kind": r["kind"], "status": r["status"], "usage_pct": r["usage_pct"], "value": r["value"], "limit": r["limit"],
                                                     "headroom": r["headroom"], "unit": r["unit"], "evaluated_at": r["evaluated_at"].isoformat()} for r in rows]}

    # ------------------------------------------------------------ tác vụ nền: sự cố mất EA + hết snooze
    async def sweep(self) -> dict:
        un = await self.fs.unsnooze_expired()
        t = now()
        rows = await self.fs.ea_candidates()
        flagged = {}
        for r in rows:
            gap = (t - r["last_seen_at"]).total_seconds() / 60
            if r["ea_status"] == "offline" or gap > 15:
                flagged[r["account_id"]] = (r, gap)
        open_keys = set(await self.fs.open_keys("ea:offline:"))
        mass = len(flagged) >= 10 and len(flagged) >= 0.6 * max(1, len(rows))
        cur_keys = set()
        opened = 0
        if mass:
            await self.fs.upsert_incident("ea:mass_offline", "ea", "", "ea:mass_offline", "critical", f"Mất kết nối hàng loạt: {len(flagged)}/{len(rows)} tài khoản",
                                          "Nhiều EA ngừng gửi dữ liệu cùng lúc — kiểm tra cầu nối/mạng trước khi xử lý từng tài khoản.", {})
        else:
            await self.fs.close_incident_by_key("ea:mass_offline")
            for acc, (r, gap) in flagged.items():
                pols = await self.fs.group_policies_for(acc)
                grace = min([int(x.get("ea_offline_grace_min", 5)) for x in pols] or [5])
                if gap < grace:
                    continue
                minsev = min([SEV_RANK.get(x.get("min_severity", "info"), 0) for x in pols] or [0])
                sev = "critical" if gap > 60 else "warning"
                if SEV_RANK[sev] < minsev:
                    continue
                key = f"ea:offline:{acc}"
                cur_keys.add(key)
                _, how = await self.fs.upsert_incident(key, "ea", acc, "ea:offline", sev, f"Mất EA: {r['label'] or acc}",
                                                       f"Không nhận dữ liệu {int(gap)} phút (trạng thái {r['ea_status'] or 'không rõ'}).", {"gap_min": int(gap)})
                opened += how == "opened"
        closed = 0
        for k in open_keys - cur_keys:
            closed += await self.fs.close_incident_by_key(k, text="EA đã hoạt động lại")
        return {"unsnoozed": un, "opened": opened, "closed": closed, "flagged": len(flagged), "mass": mass}

    def start(self) -> asyncio.Task:
        async def loop():
            await asyncio.sleep(20)
            while True:
                try:
                    await self.sweep()
                except Exception:  # noqa: BLE001
                    log.exception("sweep sự cố lỗi")
                await asyncio.sleep(60)
        return asyncio.create_task(loop())
