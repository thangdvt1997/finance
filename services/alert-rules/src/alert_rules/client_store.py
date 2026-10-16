"""Lưu trữ cho giới hạn/thông báo/cài đặt client/ticket (mixin cho PgStore và MemStore). Mọi truy vấn lọc theo chủ sở hữu.
`owner=None` chỉ dành cho master/service (đọc tất cả); các hàm ghi luôn nhận owner cụ thể."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from .limits import decide


class Conflict2(Exception):
    """rev không khớp."""


class RateLimited(Exception):
    pass


class NotFound(Exception):
    pass


def _limit_out(r: dict) -> dict:
    return {"key": r["key"], "value": r["value"],
            "pending_value": r.get("pending_value"), "pending_remove": bool(r.get("pending_remove")),
            "pending_effective_at": r.get("pending_effective_at"), "updated_at": r.get("updated_at")}


def short_id(endpoint_hash: str) -> str:
    return endpoint_hash[:16]


# ============================================================================ Postgres
class PgClientMixin:
    # ---- giới hạn
    async def _apply_due_conn(self, c, now, owner=None, account_id=None) -> list[dict]:
        rows = await c.fetch("SELECT * FROM user_limits WHERE pending_effective_at IS NOT NULL AND pending_effective_at <= $1 "
                             "AND ($2::text IS NULL OR owner_user_id=$2) AND ($3::text IS NULL OR account_id=$3) FOR UPDATE", now, owner, account_id)
        out = []
        for r in rows:
            new = None if r["pending_remove"] else r["pending_value"]
            if new is None:
                await c.execute("DELETE FROM user_limits WHERE owner_user_id=$1 AND account_id=$2 AND key=$3", r["owner_user_id"], r["account_id"], r["key"])
            else:
                await c.execute("UPDATE user_limits SET value=$4, pending_value=NULL, pending_remove=false, pending_effective_at=NULL, updated_at=$5 "
                                "WHERE owner_user_id=$1 AND account_id=$2 AND key=$3", r["owner_user_id"], r["account_id"], r["key"], new, now)
            await c.execute("INSERT INTO user_limit_history (owner_user_id, account_id, key, ts, actor_user_id, actor_role, old_value, new_value, applied) "
                            "VALUES ($1,$2,$3,$4,NULL,'system',$5,$6,'matured')", r["owner_user_id"], r["account_id"], r["key"], now, r["value"], new)
            out.append({"owner": r["owner_user_id"], "account_id": r["account_id"], "key": r["key"], "old": r["value"], "new": new})
        return out

    async def limits_apply_due(self, now: datetime, owner: str | None = None, account_id: str | None = None) -> list[dict]:
        async with self.pool.acquire() as c, c.transaction():
            return await self._apply_due_conn(c, now, owner, account_id)

    async def limits_get(self, owner: str | None, account_id: str) -> list[dict]:
        async with self.pool.acquire() as c:
            if owner is None:
                rows = await c.fetch("SELECT DISTINCT ON (key) * FROM user_limits WHERE account_id=$1 ORDER BY key, updated_at DESC", account_id)
            else:
                rows = await c.fetch("SELECT * FROM user_limits WHERE owner_user_id=$1 AND account_id=$2 ORDER BY key", owner, account_id)
        return [_limit_out(dict(r)) for r in rows]

    async def limits_set(self, owner: str, account_id: str, key: str, value: float | None, now: datetime, actor_role: str):
        async with self.pool.acquire() as c, c.transaction():
            await c.execute("SELECT pg_advisory_xact_lock(hashtext($1))", f"limits:{owner}:{account_id}")
            await self._apply_due_conn(c, now, owner, account_id)
            row = await c.fetchrow("SELECT * FROM user_limits WHERE owner_user_id=$1 AND account_id=$2 AND key=$3", owner, account_id, key)
            d = decide(key, dict(row) if row else None, value, now)
            if d.applied == "now":
                if d.value is None:
                    await c.execute("DELETE FROM user_limits WHERE owner_user_id=$1 AND account_id=$2 AND key=$3", owner, account_id, key)
                else:
                    await c.execute("INSERT INTO user_limits (owner_user_id, account_id, key, value, created_at, updated_at) VALUES ($1,$2,$3,$4,$5,$5) "
                                    "ON CONFLICT (owner_user_id, account_id, key) DO UPDATE SET value=EXCLUDED.value, pending_value=NULL, "
                                    "pending_remove=false, pending_effective_at=NULL, inactive=false, updated_at=EXCLUDED.updated_at", owner, account_id, key, d.value, now)
            elif d.applied == "pending":
                await c.execute("UPDATE user_limits SET pending_value=$4, pending_remove=$5, pending_effective_at=$6, updated_at=$7 "
                                "WHERE owner_user_id=$1 AND account_id=$2 AND key=$3", owner, account_id, key, d.pending_value, d.pending_remove, d.effective_at, now)
            elif d.applied == "cancelled":
                await c.execute("UPDATE user_limits SET pending_value=NULL, pending_remove=false, pending_effective_at=NULL, updated_at=$4 "
                                "WHERE owner_user_id=$1 AND account_id=$2 AND key=$3", owner, account_id, key, now)
            if d.history:
                old, new, applied, eff = d.history
                await c.execute("INSERT INTO user_limit_history (owner_user_id, account_id, key, ts, actor_user_id, actor_role, old_value, new_value, applied, effective_at) "
                                "VALUES ($1,$2,$3,$4,$1,$5,$6,$7,$8,$9)", owner, account_id, key, now, actor_role, old, new, applied, eff)
        return d

    async def limits_history(self, owner: str | None, account_id: str, limit: int) -> list[dict]:
        async with self.pool.acquire() as c:
            rows = await c.fetch("SELECT key, ts, actor_role, old_value, new_value, applied, effective_at FROM user_limit_history "
                                 "WHERE account_id=$1 AND ($2::text IS NULL OR owner_user_id=$2) ORDER BY id DESC LIMIT $3", account_id, owner, limit)
        return [dict(r) for r in rows]

    async def limits_sweep(self, owner: str, accounts) -> None:
        """Đánh dấu inactive các giới hạn gắn tài khoản không còn thuộc chủ (và bật lại nếu tài khoản quay về)."""
        async with self.pool.acquire() as c:
            await c.execute("UPDATE user_limits SET inactive = NOT (account_id = ANY($2::text[])) WHERE owner_user_id=$1 "
                            "AND inactive IS DISTINCT FROM NOT (account_id = ANY($2::text[]))", owner, sorted(accounts))

    async def limits_active(self) -> list[dict]:
        async with self.pool.acquire() as c:
            return [dict(r) for r in await c.fetch("SELECT owner_user_id, account_id, key, value FROM user_limits WHERE NOT inactive")]

    async def limit_alert_claim(self, owner: str, account_id: str, key: str, cycle: str, threshold: int, now: datetime) -> bool:
        async with self.pool.acquire() as c:
            r = await c.execute("INSERT INTO user_limit_alerts (owner_user_id, account_id, key, cycle, threshold, sent_at) VALUES ($1,$2,$3,$4,$5,$6) "
                                "ON CONFLICT DO NOTHING", owner, account_id, key, cycle, threshold, now)
        return r.endswith("1")

    async def limit_alert_purge(self, before: datetime) -> int:
        async with self.pool.acquire() as c:
            return int((await c.execute("DELETE FROM user_limit_alerts WHERE sent_at < $1", before)).rsplit(" ", 1)[-1])

    # ---- thông báo
    async def notif_add(self, owner: str, kind: str, severity: str, title: str, body: str, account_id: str | None, link: str | None,
                        ts: datetime, dedupe_key: str | None = None) -> int | None:
        async with self.pool.acquire() as c:
            return await c.fetchval("INSERT INTO user_notifications (owner_user_id, kind, severity, title, body, account_id, link, ts, dedupe_key) "
                                    "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9) ON CONFLICT (owner_user_id, dedupe_key) WHERE dedupe_key IS NOT NULL DO NOTHING RETURNING id",
                                    owner, kind, severity, title, body, account_id, link, ts, dedupe_key)

    async def notif_list(self, owner: str, kind: str | None, unread: bool, limit: int, before: int | None) -> tuple[list[dict], int]:
        async with self.pool.acquire() as c:
            rows = await c.fetch("SELECT id, kind, severity, title, body, account_id, link, ts, read_at FROM user_notifications WHERE owner_user_id=$1 "
                                 "AND ($2::text IS NULL OR kind=$2) AND (NOT $3 OR read_at IS NULL) AND ($4::bigint IS NULL OR id < $4) ORDER BY id DESC LIMIT $5",
                                 owner, kind, unread, before, limit)
            n = await c.fetchval("SELECT count(*) FROM user_notifications WHERE owner_user_id=$1 AND read_at IS NULL", owner)
        return [dict(r) for r in rows], int(n)

    async def notif_mark_read(self, owner: str, ids: list[int] | None, now: datetime) -> int:
        async with self.pool.acquire() as c:
            r = await c.execute("UPDATE user_notifications SET read_at=$2 WHERE owner_user_id=$1 AND read_at IS NULL AND ($3::bigint[] IS NULL OR id = ANY($3::bigint[]))",
                                owner, now, ids)
        return int(r.rsplit(" ", 1)[-1])

    async def notif_purge(self, before: datetime) -> int:
        async with self.pool.acquire() as c:
            return int((await c.execute("DELETE FROM user_notifications WHERE ts < $1", before)).rsplit(" ", 1)[-1])

    # ---- client prefs
    async def cprefs_get(self, owner: str) -> dict:
        async with self.pool.acquire() as c:
            r = await c.fetchrow("SELECT rev, data FROM client_prefs WHERE owner_user_id=$1", owner)
        return {"rev": r["rev"], "data": r["data"]} if r else {"rev": 0, "data": {}}

    async def cprefs_put(self, owner: str, rev: int, data: dict) -> dict:
        async with self.pool.acquire() as c, c.transaction():
            if rev == 0:
                r = await c.fetchrow("INSERT INTO client_prefs (owner_user_id, rev, data) VALUES ($1, 1, $2) ON CONFLICT (owner_user_id) DO NOTHING RETURNING rev, data", owner, data)
            else:
                r = await c.fetchrow("UPDATE client_prefs SET rev=rev+1, data=$3, updated_at=now() WHERE owner_user_id=$1 AND rev=$2 RETURNING rev, data", owner, rev, data)
        if not r:
            raise Conflict2("rev")
        return {"rev": r["rev"], "data": r["data"]}

    # ---- thiết bị push
    async def devices_list(self, owner: str) -> list[dict]:
        async with self.pool.acquire() as c:
            rows = await c.fetch("SELECT endpoint_hash, user_agent, created_at, last_ok_at FROM push_subscriptions WHERE owner_user_id=$1 ORDER BY created_at DESC", owner)
        return [{"id": short_id(r["endpoint_hash"]), "user_agent": r["user_agent"], "created_at": r["created_at"], "last_ok_at": r["last_ok_at"]} for r in rows]

    async def device_delete(self, owner: str, sid: str) -> bool:
        async with self.pool.acquire() as c:
            r = await c.execute("DELETE FROM push_subscriptions WHERE owner_user_id=$1 AND left(endpoint_hash, 16)=$2", owner, sid)
        return r.endswith(" 1") or int(r.rsplit(" ", 1)[-1]) > 0

    # ---- ticket
    async def ticket_create(self, owner: str, account_id: str | None, category: str, message: str, context: dict, now: datetime, max_per_hour: int) -> tuple[dict, bool]:
        async with self.pool.acquire() as c, c.transaction():
            await c.execute("SELECT pg_advisory_xact_lock(hashtext($1))", "tickets:" + owner)
            ex = await c.fetchrow("SELECT * FROM user_tickets WHERE owner_user_id=$1 AND category=$2 AND status='open' AND account_id IS NOT DISTINCT FROM $3 "
                                  "ORDER BY id DESC LIMIT 1", owner, category, account_id)
            if ex:
                r = await c.fetchrow("UPDATE user_tickets SET updated_at=$2, context=$3 WHERE id=$1 RETURNING *", ex["id"], now, context)
                return dict(r), True
            n = await c.fetchval("SELECT count(*) FROM user_tickets WHERE owner_user_id=$1 AND created_at > $2", owner, now - timedelta(hours=1))
            if n >= max_per_hour:
                raise RateLimited
            r = await c.fetchrow("INSERT INTO user_tickets (owner_user_id, account_id, category, message, context, created_at, updated_at) VALUES ($1,$2,$3,$4,$5,$6,$6) RETURNING *",
                                 owner, account_id, category, message, context, now)
            return dict(r), False

    async def ticket_list(self, owner: str | None, limit: int) -> list[dict]:
        async with self.pool.acquire() as c:
            rows = await c.fetch("SELECT * FROM user_tickets WHERE ($1::text IS NULL OR owner_user_id=$1) ORDER BY id DESC LIMIT $2", owner, limit)
        return [dict(r) for r in rows]

    async def ticket_update(self, tid: int, status: str, reply: str | None, actor: str | None, now: datetime) -> dict | None:
        async with self.pool.acquire() as c:
            r = await c.fetchrow("UPDATE user_tickets SET status=$2, reply=COALESCE($3, reply), handled_by=$4, updated_at=$5 WHERE id=$1 RETURNING *", tid, status, reply, actor, now)
        return dict(r) if r else None


# ============================================================================ In-memory (test)
class MemClientMixin:
    def _c(self) -> dict:
        if not hasattr(self, "_cm"):
            self._cm = {"limits": {}, "hist": [], "lalerts": set(), "notifs": [], "nid": 0, "cprefs": {}, "tickets": [], "tid": 0}
        return self._cm

    def _due(self, now, owner=None, account_id=None) -> list[dict]:
        out = []
        for k, r in list(self._c()["limits"].items()):
            if r.get("pending_effective_at") and r["pending_effective_at"] <= now and (owner is None or k[0] == owner) and (account_id is None or k[1] == account_id):
                new = None if r["pending_remove"] else r["pending_value"]
                old = r["value"]
                if new is None:
                    del self._c()["limits"][k]
                else:
                    r.update(value=new, pending_value=None, pending_remove=False, pending_effective_at=None, updated_at=now)
                self._c()["hist"].append({"owner": k[0], "account_id": k[1], "key": k[2], "ts": now, "actor_role": "system", "old_value": old,
                                          "new_value": new, "applied": "matured", "effective_at": None})
                out.append({"owner": k[0], "account_id": k[1], "key": k[2], "old": old, "new": new})
        return out

    async def limits_apply_due(self, now, owner=None, account_id=None):
        return self._due(now, owner, account_id)

    async def limits_get(self, owner, account_id):
        rows = [r for (o, a, k), r in self._c()["limits"].items() if a == account_id and (owner is None or o == owner)]
        best: dict[str, dict] = {}
        for r in sorted(rows, key=lambda x: x["updated_at"]):
            best[r["key"]] = r
        return [_limit_out(best[k]) for k in sorted(best)]

    async def limits_set(self, owner, account_id, key, value, now, actor_role):
        self._due(now, owner, account_id)
        L = self._c()["limits"]
        row = L.get((owner, account_id, key))
        d = decide(key, dict(row) if row else None, value, now)
        if d.applied == "now":
            if d.value is None:
                L.pop((owner, account_id, key), None)
            else:
                L[(owner, account_id, key)] = {"key": key, "value": d.value, "pending_value": None, "pending_remove": False, "pending_effective_at": None,
                                               "updated_at": now, "inactive": False}
        elif d.applied == "pending":
            row.update(pending_value=d.pending_value, pending_remove=d.pending_remove, pending_effective_at=d.effective_at, updated_at=now)
        elif d.applied == "cancelled":
            row.update(pending_value=None, pending_remove=False, pending_effective_at=None, updated_at=now)
        if d.history:
            old, new, applied, eff = d.history
            self._c()["hist"].append({"owner": owner, "account_id": account_id, "key": key, "ts": now, "actor_role": actor_role, "old_value": old,
                                      "new_value": new, "applied": applied, "effective_at": eff})
        return d

    async def limits_history(self, owner, account_id, limit):
        rows = [h for h in self._c()["hist"] if h["account_id"] == account_id and (owner is None or h["owner"] == owner)]
        return [{k: v for k, v in h.items() if k != "owner" and k != "account_id"} for h in reversed(rows)][:limit]

    async def limits_sweep(self, owner, accounts):
        for (o, a, _k), r in self._c()["limits"].items():
            if o == owner:
                r["inactive"] = a not in accounts

    async def limits_active(self):
        return [{"owner_user_id": o, "account_id": a, "key": k, "value": r["value"]} for (o, a, k), r in self._c()["limits"].items() if not r.get("inactive")]

    async def limit_alert_claim(self, owner, account_id, key, cycle, threshold, now):
        t = (owner, account_id, key, cycle, threshold)
        if t in self._c()["lalerts"]:
            return False
        self._c()["lalerts"].add(t)
        return True

    async def limit_alert_purge(self, before):
        return 0

    async def notif_add(self, owner, kind, severity, title, body, account_id, link, ts, dedupe_key=None):
        c = self._c()
        if dedupe_key and any(n["owner"] == owner and n.get("dedupe_key") == dedupe_key for n in c["notifs"]):
            return None
        c["nid"] += 1
        c["notifs"].append({"id": c["nid"], "owner": owner, "kind": kind, "severity": severity, "title": title, "body": body, "account_id": account_id,
                            "link": link, "ts": ts, "read_at": None, "dedupe_key": dedupe_key})
        return c["nid"]

    async def notif_list(self, owner, kind, unread, limit, before):
        mine = [n for n in self._c()["notifs"] if n["owner"] == owner]
        rows = [n for n in sorted(mine, key=lambda n: n["id"], reverse=True)
                if (not kind or n["kind"] == kind) and (not unread or n["read_at"] is None) and (before is None or n["id"] < before)][:limit]
        return [{k: v for k, v in n.items() if k not in ("owner", "dedupe_key")} for n in rows], sum(1 for n in mine if n["read_at"] is None)

    async def notif_mark_read(self, owner, ids, now):
        n = 0
        for x in self._c()["notifs"]:
            if x["owner"] == owner and x["read_at"] is None and (ids is None or x["id"] in ids):
                x["read_at"] = now
                n += 1
        return n

    async def notif_purge(self, before):
        c = self._c()
        k = len(c["notifs"])
        c["notifs"] = [n for n in c["notifs"] if n["ts"] >= before]
        return k - len(c["notifs"])

    async def cprefs_get(self, owner):
        r = self._c()["cprefs"].get(owner)
        return {"rev": r["rev"], "data": dict(r["data"])} if r else {"rev": 0, "data": {}}

    async def cprefs_put(self, owner, rev, data):
        cur = self._c()["cprefs"].get(owner)
        if (cur["rev"] if cur else 0) != rev:
            raise Conflict2("rev")
        self._c()["cprefs"][owner] = {"rev": rev + 1, "data": json.loads(json.dumps(data))}
        return {"rev": rev + 1, "data": data}

    async def devices_list(self, owner):
        return [{"id": short_id(s["endpoint_hash"]), "user_agent": s.get("user_agent"), "created_at": s.get("created_at"), "last_ok_at": s.get("last_ok_at")}
                for s in sorted(self.subs.values(), key=lambda s: s["id"], reverse=True) if s["owner_user_id"] == owner]

    async def device_delete(self, owner, sid):
        ids = [i for i, s in self.subs.items() if s["owner_user_id"] == owner and short_id(s["endpoint_hash"]) == sid]
        for i in ids:
            del self.subs[i]
        return bool(ids)

    async def ticket_create(self, owner, account_id, category, message, context, now, max_per_hour):
        c = self._c()
        for t in reversed(c["tickets"]):
            if t["owner_user_id"] == owner and t["category"] == category and t["status"] == "open" and t["account_id"] == account_id:
                t.update(updated_at=now, context=context)
                return dict(t), True
        if sum(1 for t in c["tickets"] if t["owner_user_id"] == owner and t["created_at"] > now - timedelta(hours=1)) >= max_per_hour:
            raise RateLimited
        c["tid"] += 1
        t = {"id": c["tid"], "owner_user_id": owner, "account_id": account_id, "category": category, "message": message, "context": context,
             "status": "open", "reply": None, "handled_by": None, "created_at": now, "updated_at": now}
        c["tickets"].append(t)
        return dict(t), False

    async def ticket_list(self, owner, limit):
        return [dict(t) for t in reversed(self._c()["tickets"]) if owner is None or t["owner_user_id"] == owner][:limit]

    async def ticket_update(self, tid, status, reply, actor, now):
        for t in self._c()["tickets"]:
            if t["id"] == tid:
                t.update(status=status, reply=reply if reply is not None else t["reply"], handled_by=actor, updated_at=now)
                return dict(t)
        return None


__all__ = ["PgClientMixin", "MemClientMixin", "Conflict2", "RateLimited", "NotFound", "timezone"]
