"""Lưu trữ quy tắc/lịch sử/tuỳ chọn (Postgres qua role hạn chế ts_userconf) + bản in-memory cho test."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from .client_store import MemClientMixin, PgClientMixin
from .models import MAX_CLIENT_RULES_TOTAL, MAX_RULES, MAX_RULES_USER, RuleIn
from .scope import account_of

USER = "admin"


class Conflict(Exception):
    """rev không khớp (ghi đè đồng thời)."""


class LimitReached(Exception):
    pass


def status_of(row: dict, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    if not row["enabled"]:
        return "disabled"
    if row.get("expires_at") and row["expires_at"] <= now:
        return "expired"
    if row.get("once_done"):
        return "fired"
    return "active"


def rule_out(row: dict, now: datetime | None = None, master: bool = False) -> dict:
    spec = row["spec"] if isinstance(row["spec"], dict) else json.loads(row["spec"])
    out = {"id": str(row["id"]), "name": row["name"], "enabled": row["enabled"], **{k: spec.get(k) for k in
           ("logic", "conditions", "mode", "cooldown_min", "level", "channels", "note")},
           "account_id": row.get("account_id"),
           "expires_at": row["expires_at"], "status": status_of(row, now), "last_fired_at": row["last_fired_at"],
           "fire_count": row["fire_count"], "created_at": row["created_at"], "updated_at": row["updated_at"]}
    if master:       # chủ sở hữu chỉ lộ cho master (client luôn chỉ thấy quy tắc của mình, không cần id người dùng)
        out["owner_user_id"] = row.get("owner_user_id")
    return out


class PgStore(PgClientMixin):
    def __init__(self, pool):
        self.pool = pool

    @classmethod
    async def connect(cls, dsn: str) -> "PgStore":
        import asyncpg

        async def init(c):
            await c.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")

        return cls(await asyncpg.create_pool(dsn, min_size=1, max_size=4, command_timeout=20, init=init))

    async def close(self) -> None:
        await self.pool.close()

    async def ping(self) -> bool:
        async with self.pool.acquire() as c:
            return await c.fetchval("SELECT 1") == 1

    # ---- rules ----
    # `owner`: None = không lọc (master/service); chuỗi = CHỈ bản ghi của user đó (client). Không khớp -> như không tồn tại (404, không oracle).
    async def list_rules(self, owner: str | None = None) -> list[dict]:
        async with self.pool.acquire() as c:
            if owner is None:
                return [dict(r) for r in await c.fetch("SELECT * FROM alert_rules ORDER BY created_at DESC")]
            return [dict(r) for r in await c.fetch("SELECT * FROM alert_rules WHERE owner_user_id=$1 ORDER BY created_at DESC", owner)]

    async def get_rule(self, rid: str, owner: str | None = None) -> dict | None:
        async with self.pool.acquire() as c:
            r = await c.fetchrow("SELECT * FROM alert_rules WHERE id=$1 AND ($2::text IS NULL OR owner_user_id=$2)", uuid.UUID(rid), owner)
        return dict(r) if r else None

    async def create_rule(self, r: RuleIn, owner: str | None = None) -> dict:
        async with self.pool.acquire() as c, c.transaction():
            if owner is None:
                n = await c.fetchval("SELECT count(*) FROM alert_rules WHERE owner_user_id IS NULL")
                if n >= MAX_RULES:
                    raise LimitReached(f"tối đa {MAX_RULES} quy tắc")
            else:
                await c.execute("SELECT pg_advisory_xact_lock(hashtext($1))", "rules:" + owner)   # tuần tự hoá theo người dùng: không vượt giới hạn do đua
                if await c.fetchval("SELECT count(*) FROM alert_rules WHERE owner_user_id=$1", owner) >= MAX_RULES_USER:
                    raise LimitReached(f"tối đa {MAX_RULES_USER} quy tắc cho mỗi người dùng")
                if await c.fetchval("SELECT count(*) FROM alert_rules WHERE owner_user_id IS NOT NULL") >= MAX_CLIENT_RULES_TOTAL:
                    raise LimitReached("hệ thống đã đạt giới hạn quy tắc cá nhân")
            row = await c.fetchrow("INSERT INTO alert_rules (name, enabled, spec, expires_at, owner_user_id, account_id) VALUES ($1,$2,$3,$4,$5,$6) RETURNING *",
                                   r.name, r.enabled, r.spec(), r.expires_at, owner, account_of(r.spec()))
        return dict(row)

    async def update_rule(self, rid: str, r: RuleIn, owner: str | None = None) -> dict | None:
        async with self.pool.acquire() as c:  # sửa = nạp lại súng (once_done=false) + reset trạng thái so sánh (updated_at đổi). Không bao giờ đổi chủ sở hữu.
            row = await c.fetchrow("UPDATE alert_rules SET name=$2, enabled=$3, spec=$4, expires_at=$5, account_id=$6, once_done=false, updated_at=now() "
                                   "WHERE id=$1 AND ($7::text IS NULL OR owner_user_id=$7) RETURNING *",
                                   uuid.UUID(rid), r.name, r.enabled, r.spec(), r.expires_at, account_of(r.spec()), owner)
        return dict(row) if row else None

    async def delete_rule(self, rid: str, owner: str | None = None) -> bool:
        async with self.pool.acquire() as c:
            return (await c.execute("DELETE FROM alert_rules WHERE id=$1 AND ($2::text IS NULL OR owner_user_id=$2)", uuid.UUID(rid), owner)).endswith("1")

    async def sweep_owner(self, owner: str, accounts) -> int:
        """Tắt quy tắc của `owner` gắn với tài khoản KHÔNG còn thuộc họ (tài khoản bị gỡ/chuyển chủ). Trả số quy tắc bị tắt."""
        async with self.pool.acquire() as c:
            res = await c.execute("UPDATE alert_rules SET enabled=false, updated_at=now() WHERE owner_user_id=$1 AND enabled AND account_id IS NOT NULL "
                                  "AND NOT (account_id = ANY($2::text[]))", owner, sorted(accounts))
        return int(res.rsplit(" ", 1)[-1])

    async def claim_fire(self, rid: str, now: datetime, cooldown_min: int, once: bool) -> int | None:
        """Nguyên tử: chỉ một lần kích hoạt thành công cho mỗi cooldown. Trả fire_count mới hoặc None."""
        async with self.pool.acquire() as c:
            return await c.fetchval(
                "UPDATE alert_rules SET last_fired_at=$2, fire_count=fire_count+1, once_done=$4 "
                "WHERE id=$1 AND enabled AND NOT once_done AND (expires_at IS NULL OR expires_at > $2) "
                "AND (last_fired_at IS NULL OR last_fired_at <= $2 - make_interval(mins => $3)) RETURNING fire_count",
                uuid.UUID(rid), now, 0 if once else cooldown_min, once)

    # ---- events ----
    async def add_event(self, rid: str, name: str, level: str, title: str, body: str, snapshot: dict, channels: list[str],
                        alert_event_id: str, fired_at: datetime, owner: str | None = None) -> int:
        async with self.pool.acquire() as c:
            return await c.fetchval(
                "INSERT INTO alert_rule_events (rule_id, rule_name, fired_at, level, title, body, snapshot, channels, alert_event_id, owner_user_id) "
                "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10) RETURNING id",
                uuid.UUID(rid), name, fired_at, level, title, body, snapshot, channels, alert_event_id, owner)

    async def set_delivered(self, alert_event_id: str, delivered: bool) -> None:
        async with self.pool.acquire() as c:
            await c.execute("UPDATE alert_rule_events SET delivered=$2 WHERE alert_event_id=$1", alert_event_id, delivered)

    async def list_events(self, rule_id: str | None, limit: int, owner: str | None = None) -> list[dict]:
        async with self.pool.acquire() as c:
            rows = await c.fetch("SELECT * FROM alert_rule_events WHERE ($1::uuid IS NULL OR rule_id=$1) AND ($3::text IS NULL OR owner_user_id=$3) "
                                 "ORDER BY fired_at DESC LIMIT $2", uuid.UUID(rule_id) if rule_id else None, limit, owner)
        return [dict(r) for r in rows]

    # ---- Web Push (chỉ ciphertext; PushService mã hoá/giải mã) ----
    async def upsert_subscription(self, owner: str, ehash: str, endpoint_enc: str, p256dh_enc: str, auth_enc: str, ua: str | None, max_per_user: int) -> None:
        async with self.pool.acquire() as c, c.transaction():
            await c.execute("SELECT pg_advisory_xact_lock(hashtext($1))", "push:" + owner)
            # cùng endpoint (cùng trình duyệt) đăng ký lại bởi người khác -> chuyển chủ (thiết bị dùng chung: người đăng nhập hiện tại giữ)
            await c.execute("INSERT INTO push_subscriptions (owner_user_id, endpoint_hash, endpoint_enc, p256dh_enc, auth_enc, user_agent) VALUES ($1,$2,$3,$4,$5,$6) "
                            "ON CONFLICT (endpoint_hash) DO UPDATE SET owner_user_id=EXCLUDED.owner_user_id, endpoint_enc=EXCLUDED.endpoint_enc, "
                            "p256dh_enc=EXCLUDED.p256dh_enc, auth_enc=EXCLUDED.auth_enc, user_agent=EXCLUDED.user_agent, fail_count=0, created_at=now()",
                            owner, ehash, endpoint_enc, p256dh_enc, auth_enc, ua)
            await c.execute("DELETE FROM push_subscriptions WHERE owner_user_id=$1 AND id NOT IN "
                            "(SELECT id FROM push_subscriptions WHERE owner_user_id=$1 ORDER BY created_at DESC, id DESC LIMIT $2)", owner, max_per_user)

    async def delete_subscription(self, owner: str, ehash: str) -> None:
        async with self.pool.acquire() as c:
            await c.execute("DELETE FROM push_subscriptions WHERE owner_user_id=$1 AND endpoint_hash=$2", owner, ehash)

    async def delete_subscription_id(self, sid: int) -> None:
        async with self.pool.acquire() as c:
            await c.execute("DELETE FROM push_subscriptions WHERE id=$1", sid)

    async def count_subscriptions(self, owner: str) -> int:
        async with self.pool.acquire() as c:
            return await c.fetchval("SELECT count(*) FROM push_subscriptions WHERE owner_user_id=$1", owner)

    async def list_subscriptions(self, owner: str) -> list[dict]:
        async with self.pool.acquire() as c:
            return [dict(r) for r in await c.fetch("SELECT id, endpoint_enc, p256dh_enc, auth_enc FROM push_subscriptions WHERE owner_user_id=$1", owner)]

    async def mark_subscription_ok(self, sid: int) -> None:
        async with self.pool.acquire() as c:
            await c.execute("UPDATE push_subscriptions SET last_ok_at=now(), fail_count=0 WHERE id=$1", sid)

    async def mark_subscription_failed(self, sid: int) -> int:
        async with self.pool.acquire() as c:
            return await c.fetchval("UPDATE push_subscriptions SET last_error_at=now(), fail_count=fail_count+1 WHERE id=$1 RETURNING fail_count", sid) or 0

    async def purge_subscriptions(self) -> int:
        """Dọn đăng ký chết: lỗi liên tiếp, hoặc >120 ngày không gửi thành công."""
        async with self.pool.acquire() as c:
            res = await c.execute("DELETE FROM push_subscriptions WHERE fail_count >= 5 OR (COALESCE(last_ok_at, created_at) < now() - interval '120 days')")
        return int(res.rsplit(" ", 1)[-1])

    # ---- prefs ----
    async def get_prefs(self) -> dict:
        async with self.pool.acquire() as c:
            r = await c.fetchrow("SELECT rev, prefs, updated_at FROM user_prefs WHERE user_id=$1", USER)
        return dict(r) if r else {"rev": 0, "prefs": {}, "updated_at": None}

    async def put_prefs(self, rev: int, prefs: dict) -> dict:
        async with self.pool.acquire() as c, c.transaction():
            if rev == 0:
                r = await c.fetchrow("INSERT INTO user_prefs (user_id, rev, prefs) VALUES ($1, 1, $2) ON CONFLICT (user_id) DO NOTHING "
                                     "RETURNING rev, prefs, updated_at", USER, prefs)
            else:
                r = await c.fetchrow("UPDATE user_prefs SET rev=rev+1, prefs=$3, updated_at=now() WHERE user_id=$1 AND rev=$2 "
                                     "RETURNING rev, prefs, updated_at", USER, rev, prefs)
        if not r:
            raise Conflict("rev")
        return dict(r)


class MemStore(MemClientMixin):
    """Cài đặt in-memory (cùng giao diện) cho test và chạy thử."""

    def __init__(self):
        self.rules: dict[str, dict] = {}
        self.events: list[dict] = []
        self.prefs: dict = {"rev": 0, "prefs": {}, "updated_at": None}
        self._eid = 0
        self.subs: dict[int, dict] = {}
        self._sid = 0

    async def close(self): ...

    async def ping(self) -> bool:
        return True

    def _mine(self, row, owner) -> bool:
        return owner is None or row.get("owner_user_id") == owner

    async def list_rules(self, owner=None):
        return sorted((dict(r) for r in self.rules.values() if self._mine(r, owner)), key=lambda r: r["created_at"], reverse=True)

    async def get_rule(self, rid, owner=None):
        r = self.rules.get(rid)
        return dict(r) if r and self._mine(r, owner) else None

    async def create_rule(self, r: RuleIn, owner=None):
        if owner is None:
            if sum(1 for x in self.rules.values() if x.get("owner_user_id") is None) >= MAX_RULES:
                raise LimitReached(f"tối đa {MAX_RULES} quy tắc")
        else:
            if sum(1 for x in self.rules.values() if x.get("owner_user_id") == owner) >= MAX_RULES_USER:
                raise LimitReached(f"tối đa {MAX_RULES_USER} quy tắc cho mỗi người dùng")
            if sum(1 for x in self.rules.values() if x.get("owner_user_id") is not None) >= MAX_CLIENT_RULES_TOTAL:
                raise LimitReached("hệ thống đã đạt giới hạn quy tắc cá nhân")
        now = datetime.now(timezone.utc)
        row = {"id": uuid.uuid4(), "name": r.name, "enabled": r.enabled, "spec": r.spec(), "expires_at": r.expires_at, "once_done": False,
               "last_fired_at": None, "fire_count": 0, "created_at": now, "updated_at": now, "owner_user_id": owner, "account_id": account_of(r.spec())}
        self.rules[str(row["id"])] = row
        return dict(row)

    async def update_rule(self, rid, r: RuleIn, owner=None):
        row = self.rules.get(rid)
        if not row or not self._mine(row, owner):
            return None
        row.update(name=r.name, enabled=r.enabled, spec=r.spec(), expires_at=r.expires_at, once_done=False, account_id=account_of(r.spec()),
                   updated_at=datetime.now(timezone.utc) + timedelta(microseconds=1))
        return dict(row)

    async def delete_rule(self, rid, owner=None):
        row = self.rules.get(rid)
        if not row or not self._mine(row, owner):
            return False
        del self.rules[rid]
        return True

    async def sweep_owner(self, owner, accounts):
        n = 0
        for row in self.rules.values():
            if row.get("owner_user_id") == owner and row["enabled"] and row.get("account_id") and row["account_id"] not in accounts:
                row.update(enabled=False, updated_at=datetime.now(timezone.utc))
                n += 1
        return n

    async def claim_fire(self, rid, now, cooldown_min, once):
        row = self.rules.get(rid)
        if not row or not row["enabled"] or row["once_done"] or (row["expires_at"] and row["expires_at"] <= now):
            return None
        if row["last_fired_at"] and not once and row["last_fired_at"] > now - timedelta(minutes=cooldown_min):
            return None
        row.update(last_fired_at=now, fire_count=row["fire_count"] + 1, once_done=once)
        return row["fire_count"]

    async def add_event(self, rid, name, level, title, body, snapshot, channels, alert_event_id, fired_at, owner=None):
        self._eid += 1
        self.events.append({"id": self._eid, "rule_id": uuid.UUID(rid), "rule_name": name, "fired_at": fired_at, "level": level,
                            "title": title, "body": body, "snapshot": snapshot, "channels": channels,
                            "alert_event_id": alert_event_id, "delivered": None, "owner_user_id": owner})
        return self._eid

    async def set_delivered(self, alert_event_id, delivered):
        for e in self.events:
            if e["alert_event_id"] == alert_event_id:
                e["delivered"] = delivered

    async def list_events(self, rule_id, limit, owner=None):
        ev = [e for e in self.events if (not rule_id or str(e["rule_id"]) == rule_id) and (owner is None or e.get("owner_user_id") == owner)]
        return sorted(ev, key=lambda e: e["fired_at"], reverse=True)[:limit]

    # ---- Web Push ----
    async def upsert_subscription(self, owner, ehash, endpoint_enc, p256dh_enc, auth_enc, ua, max_per_user):
        for s in self.subs.values():
            if s["endpoint_hash"] == ehash:
                s.update(owner_user_id=owner, endpoint_enc=endpoint_enc, p256dh_enc=p256dh_enc, auth_enc=auth_enc, user_agent=ua, fail_count=0)
                break
        else:
            self._sid += 1
            self.subs[self._sid] = {"id": self._sid, "owner_user_id": owner, "endpoint_hash": ehash, "endpoint_enc": endpoint_enc, "p256dh_enc": p256dh_enc,
                                    "auth_enc": auth_enc, "user_agent": ua, "fail_count": 0, "last_ok_at": None,
                                    "created_at": datetime.now(timezone.utc).isoformat()}
        mine = sorted((s for s in self.subs.values() if s["owner_user_id"] == owner), key=lambda s: s["id"], reverse=True)
        for s in mine[max_per_user:]:
            del self.subs[s["id"]]

    async def delete_subscription(self, owner, ehash):
        for sid in [i for i, s in self.subs.items() if s["owner_user_id"] == owner and s["endpoint_hash"] == ehash]:
            del self.subs[sid]

    async def delete_subscription_id(self, sid):
        self.subs.pop(sid, None)

    async def count_subscriptions(self, owner):
        return sum(1 for s in self.subs.values() if s["owner_user_id"] == owner)

    async def list_subscriptions(self, owner):
        return [dict(s) for s in self.subs.values() if s["owner_user_id"] == owner]

    async def mark_subscription_ok(self, sid):
        if sid in self.subs:
            self.subs[sid].update(fail_count=0, last_ok_at=datetime.now(timezone.utc))

    async def mark_subscription_failed(self, sid):
        if sid not in self.subs:
            return 0
        self.subs[sid]["fail_count"] += 1
        return self.subs[sid]["fail_count"]

    async def purge_subscriptions(self):
        dead = [i for i, s in self.subs.items() if s["fail_count"] >= 5]
        for i in dead:
            del self.subs[i]
        return len(dead)

    async def get_prefs(self):
        return dict(self.prefs)

    async def put_prefs(self, rev, prefs):
        if rev != self.prefs["rev"]:
            raise Conflict("rev")
        self.prefs = {"rev": rev + 1, "prefs": prefs, "updated_at": datetime.now(timezone.utc)}
        return dict(self.prefs)


def event_out(e: dict) -> dict[str, Any]:
    return {"id": e["id"], "rule_id": str(e["rule_id"]), "rule_name": e["rule_name"], "fired_at": e["fired_at"], "level": e["level"],
            "title": e["title"], "body": e["body"], "snapshot": e["snapshot"], "channels": list(e["channels"] or []),
            "delivered": e["delivered"]}
