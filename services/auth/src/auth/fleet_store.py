"""Lớp truy cập DB cho quản trị đội tài khoản (nhóm/tag/views/luật/sự cố/nhân sự). Mọi truy vấn tham số hoá ($n). docs/FLEET_MGMT.md."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

Row = dict[str, Any]


def _j(v, default):
    if v is None:
        return default
    if isinstance(v, (str, bytes)):
        try:
            return json.loads(v)
        except ValueError:
            return default
    return v


def _u(v) -> uuid.UUID:
    return v if isinstance(v, uuid.UUID) else uuid.UUID(str(v))


def _row(r) -> Row:
    d = dict(r)
    for k, v in list(d.items()):
        if isinstance(v, uuid.UUID):
            d[k] = str(v)
    return d


class FleetStore:
    def __init__(self, pool):
        self.pool = pool

    async def _all(self, sql: str, *a) -> list[Row]:
        async with self.pool.acquire() as c:
            return [_row(r) for r in await c.fetch(sql, *a)]

    async def _one(self, sql: str, *a) -> Row | None:
        async with self.pool.acquire() as c:
            r = await c.fetchrow(sql, *a)
        return _row(r) if r is not None else None

    async def _exec(self, sql: str, *a) -> str:
        async with self.pool.acquire() as c:
            return await c.execute(sql, *a)

    # ------------------------------------------------------------------ nhóm
    async def list_groups(self) -> list[Row]:
        rows = await self._all(
            "SELECT g.group_id, g.name, g.description, g.color, g.policy, g.created_at, "
            "(SELECT count(*) FROM account_group_members m WHERE m.group_id = g.group_id) AS members FROM account_groups g ORDER BY g.name")
        for r in rows:
            r["id"] = r.pop("group_id")
            r["policy"] = _j(r["policy"], {})
        return rows

    async def get_group(self, gid: str) -> Row | None:
        r = await self._one("SELECT group_id, name, description, color, policy, created_at FROM account_groups WHERE group_id=$1", _u(gid))
        if r:
            r["id"] = r.pop("group_id")
            r["policy"] = _j(r["policy"], {})
        return r

    async def create_group(self, name: str, description: str, color: str, by: str | None) -> Row:
        r = await self._one("INSERT INTO account_groups (name, description, color, created_by) VALUES ($1,$2,$3,$4) RETURNING group_id, name, description, color, policy, created_at",
                            name, description, color, _u(by) if by else None)
        r["id"] = r.pop("group_id")
        r["policy"] = _j(r["policy"], {})
        return r

    async def update_group(self, gid: str, **f) -> Row | None:
        ok = {k: v for k, v in f.items() if k in ("name", "description", "color") and v is not None}
        if not ok:
            return await self.get_group(gid)
        sets = ", ".join(f"{k}=${i + 2}" for i, k in enumerate(ok))
        await self._exec(f"UPDATE account_groups SET {sets} WHERE group_id=$1", _u(gid), *ok.values())  # noqa: S608 (khoá whitelist)
        return await self.get_group(gid)

    async def set_group_policy(self, gid: str, policy: dict) -> bool:
        return (await self._exec("UPDATE account_groups SET policy=$2::jsonb WHERE group_id=$1", _u(gid), json.dumps(policy))).endswith(" 1")

    async def delete_group(self, gid: str) -> bool:
        return (await self._exec("DELETE FROM account_groups WHERE group_id=$1", _u(gid))).endswith(" 1")

    async def add_members(self, gid: str, account_ids: list[str]) -> int:
        r = await self._exec("INSERT INTO account_group_members (group_id, account_id) SELECT $1, account_id FROM mt_accounts WHERE account_id = ANY($2::text[]) "
                             "ON CONFLICT DO NOTHING", _u(gid), account_ids)
        return int(r.split()[-1])

    async def remove_member(self, gid: str, account_id: str) -> bool:
        return (await self._exec("DELETE FROM account_group_members WHERE group_id=$1 AND account_id=$2", _u(gid), account_id)).endswith(" 1")

    async def set_account_groups(self, account_id: str, group_ids: list[str]) -> None:
        gids = [_u(g) for g in group_ids]
        async with self.pool.acquire() as c, c.transaction():
            await c.execute("DELETE FROM account_group_members WHERE account_id=$1 AND NOT (group_id = ANY($2::uuid[]))", account_id, gids)
            await c.execute("INSERT INTO account_group_members (group_id, account_id) SELECT group_id, $1 FROM account_groups WHERE group_id = ANY($2::uuid[]) ON CONFLICT DO NOTHING",
                            account_id, gids)

    async def remove_account_from_group_bulk(self, gid: str, account_ids: list[str]) -> None:
        await self._exec("DELETE FROM account_group_members WHERE group_id=$1 AND account_id = ANY($2::text[])", _u(gid), account_ids)

    # ------------------------------------------------------------------ tag
    async def list_tags(self) -> list[Row]:
        return await self._all("SELECT tag, count(*) AS count FROM account_tags GROUP BY tag ORDER BY tag")

    async def set_account_tags(self, account_id: str, tags: list[str]) -> None:
        async with self.pool.acquire() as c, c.transaction():
            await c.execute("DELETE FROM account_tags WHERE account_id=$1 AND NOT (tag = ANY($2::text[]))", account_id, tags)
            for t in tags:
                await c.execute("INSERT INTO account_tags (account_id, tag) VALUES ($1,$2) ON CONFLICT DO NOTHING", account_id, t)

    async def add_tag(self, account_ids: list[str], tag: str) -> None:
        await self._exec("INSERT INTO account_tags (account_id, tag) SELECT account_id, $2 FROM mt_accounts WHERE account_id = ANY($1::text[]) ON CONFLICT DO NOTHING", account_ids, tag)

    async def remove_tag(self, account_ids: list[str], tag: str) -> None:
        await self._exec("DELETE FROM account_tags WHERE account_id = ANY($1::text[]) AND tag=$2", account_ids, tag)

    async def tag_counts_for(self, account_id: str) -> int:
        async with self.pool.acquire() as c:
            return int(await c.fetchval("SELECT count(*) FROM account_tags WHERE account_id=$1", account_id))

    # ------------------------------------------------------------------ fleet (danh sách tổng hợp; lọc/sắp xếp ở tầng dịch vụ)
    async def fleet_rows(self, account_ids: list[str] | None) -> list[Row]:
        sql = (
            "SELECT a.account_id, a.platform, a.login, a.server, a.label, a.status, a.ea_status, a.ea_latency_ms, a.ea_version, a.last_seen_at, a.client_notify, "
            "u.display_name AS client_name, "
            "COALESCE((SELECT json_agg(json_build_object('id', g.group_id, 'name', g.name, 'color', g.color) ORDER BY g.name) FROM account_group_members m "
            "          JOIN account_groups g ON g.group_id = m.group_id WHERE m.account_id = a.account_id), '[]'::json) AS groups, "
            "COALESCE((SELECT array_agg(t.tag ORDER BY t.tag) FROM account_tags t WHERE t.account_id = a.account_id), '{}') AS tags, "
            "(SELECT count(*) FROM incidents i WHERE i.account_id = a.account_id AND i.status <> 'resolved') AS incidents_open, "
            "cs.worst_status, cs.worst_usage, cs.worst_rule "
            "FROM mt_accounts a LEFT JOIN portal_users u ON u.user_id = a.client_id "
            "LEFT JOIN LATERAL (SELECT (array_agg(rs.status ORDER BY CASE rs.status WHEN 'red' THEN 0 WHEN 'yellow' THEN 1 WHEN 'green' THEN 2 ELSE 3 END, rs.usage_pct DESC NULLS LAST))[1] AS worst_status, "
            "   max(rs.usage_pct) AS worst_usage, "
            "   (array_agg(t.name ORDER BY CASE rs.status WHEN 'red' THEN 0 WHEN 'yellow' THEN 1 WHEN 'green' THEN 2 ELSE 3 END, rs.usage_pct DESC NULLS LAST))[1] AS worst_rule "
            "   FROM rule_status rs JOIN rule_assignments ra ON ra.assignment_id = rs.assignment_id JOIN rule_templates t ON t.template_id = ra.template_id "
            "   WHERE rs.account_id = a.account_id AND ra.enabled AND rs.status <> 'na') cs ON true "
            "WHERE ($1::text[] IS NULL OR a.account_id = ANY($1::text[])) ORDER BY a.account_id LIMIT 5000")
        rows = await self._all(sql, account_ids)
        for r in rows:
            r["groups"] = _j(r["groups"], [])
            r["tags"] = list(r["tags"] or [])
        return rows

    async def account_ids_in_scope_groups(self, group_ids: list[str]) -> list[str]:
        rows = await self._all("SELECT DISTINCT account_id FROM account_group_members WHERE group_id = ANY($1::uuid[])", [_u(g) for g in group_ids])
        return [r["account_id"] for r in rows]

    async def staff_scope(self, user_id: str) -> list[Row]:
        rows = await self._all("SELECT g.group_id, g.name FROM staff_scopes s JOIN account_groups g ON g.group_id = s.group_id WHERE s.user_id=$1 ORDER BY g.name", _u(user_id))
        return [{"id": r["group_id"], "name": r["name"]} for r in rows]

    async def staff_accounts(self, user_id: str, scope_all: bool) -> list[str]:
        if scope_all:
            return [r["account_id"] for r in await self._all("SELECT account_id FROM mt_accounts ORDER BY account_id")]
        rows = await self._all("SELECT DISTINCT m.account_id FROM staff_scopes s JOIN account_group_members m ON m.group_id = s.group_id WHERE s.user_id=$1 ORDER BY 1", _u(user_id))
        return [r["account_id"] for r in rows]

    # ------------------------------------------------------------------ saved views / notes
    async def list_views(self, user_id: str) -> list[Row]:
        rows = await self._all("SELECT v.view_id, v.name, v.filters, v.shared, v.owner_user_id, v.created_at, u.display_name AS owner_name FROM saved_views v "
                               "JOIN portal_users u ON u.user_id = v.owner_user_id WHERE v.owner_user_id=$1 OR v.shared ORDER BY v.name", _u(user_id))
        for r in rows:
            r["id"] = r.pop("view_id")
            r["filters"] = _j(r["filters"], {})
        return rows

    async def create_view(self, user_id: str, name: str, filters: dict, shared: bool) -> Row:
        r = await self._one("INSERT INTO saved_views (owner_user_id, name, filters, shared) VALUES ($1,$2,$3::jsonb,$4) RETURNING view_id, name, filters, shared, owner_user_id, created_at",
                            _u(user_id), name, json.dumps(filters), shared)
        r["id"] = r.pop("view_id")
        r["filters"] = _j(r["filters"], {})
        return r

    async def get_view(self, vid: str) -> Row | None:
        return await self._one("SELECT view_id, owner_user_id FROM saved_views WHERE view_id=$1", _u(vid))

    async def delete_view(self, vid: str) -> bool:
        return (await self._exec("DELETE FROM saved_views WHERE view_id=$1", _u(vid))).endswith(" 1")

    async def list_notes(self, account_id: str, limit: int = 100) -> list[Row]:
        return await self._all("SELECT note_id, author_user_id, author_label, text, created_at FROM account_notes WHERE account_id=$1 ORDER BY created_at DESC LIMIT $2", account_id, limit)

    async def add_note(self, account_id: str, user_id: str | None, label: str, text: str) -> Row:
        return await self._one("INSERT INTO account_notes (account_id, author_user_id, author_label, text) VALUES ($1,$2,$3,$4) RETURNING note_id, author_label, text, created_at",
                               account_id, _u(user_id) if user_id else None, label[:120], text)

    # ------------------------------------------------------------------ view-as
    async def create_grant(self, user_id: str, label: str, account_id: str, reason: str, expires: datetime) -> Row:
        return await self._one("INSERT INTO view_as_grants (actor_user_id, actor_label, account_id, reason, expires_at) VALUES ($1,$2,$3,$4,$5) RETURNING grant_id, account_id, reason, created_at, expires_at",
                               _u(user_id), label[:120], account_id, reason, expires)

    async def end_grant(self, gid: str, user_id: str) -> Row | None:
        return await self._one("UPDATE view_as_grants SET ended_at = now() WHERE grant_id=$1 AND actor_user_id=$2 AND ended_at IS NULL RETURNING grant_id, account_id", _u(gid), _u(user_id))

    async def active_grants(self, user_id: str) -> list[Row]:
        return await self._all("SELECT grant_id, account_id, reason, created_at, expires_at FROM view_as_grants WHERE actor_user_id=$1 AND ended_at IS NULL AND expires_at > now() ORDER BY created_at DESC",
                               _u(user_id))

    # ------------------------------------------------------------------ luật
    async def list_templates(self) -> list[Row]:
        rows = await self._all("SELECT t.template_id, t.name, t.kind, t.params, t.description, t.created_at, t.updated_at, "
                               "(SELECT count(*) FROM rule_assignments a WHERE a.template_id = t.template_id) AS assignments FROM rule_templates t ORDER BY t.name")
        for r in rows:
            r["id"] = r.pop("template_id")
            r["params"] = _j(r["params"], {})
        return rows

    async def get_template(self, tid: str) -> Row | None:
        r = await self._one("SELECT template_id, name, kind, params, description FROM rule_templates WHERE template_id=$1", _u(tid))
        if r:
            r["id"] = r.pop("template_id")
            r["params"] = _j(r["params"], {})
        return r

    async def create_template(self, name: str, kind: str, params: dict, description: str, by: str | None) -> Row:
        r = await self._one("INSERT INTO rule_templates (name, kind, params, description, created_by) VALUES ($1,$2,$3::jsonb,$4,$5) RETURNING template_id, name, kind, params, description, created_at, updated_at",
                            name, kind, json.dumps(params), description, _u(by) if by else None)
        r["id"] = r.pop("template_id")
        r["params"] = _j(r["params"], {})
        return r

    async def update_template(self, tid: str, name: str, params: dict, description: str) -> Row | None:
        r = await self._one("UPDATE rule_templates SET name=$2, params=$3::jsonb, description=$4, updated_at=now() WHERE template_id=$1 RETURNING template_id, name, kind, params, description, created_at, updated_at",
                            _u(tid), name, json.dumps(params), description)
        if r:
            r["id"] = r.pop("template_id")
            r["params"] = _j(r["params"], {})
        return r

    async def delete_template(self, tid: str) -> list[str]:
        """Trả danh sách assignment_id đã bị xoá theo (để đóng sự cố)."""
        async with self.pool.acquire() as c, c.transaction():
            ids = [str(r["assignment_id"]) for r in await c.fetch("SELECT assignment_id FROM rule_assignments WHERE template_id=$1", _u(tid))]
            await c.execute("DELETE FROM rule_templates WHERE template_id=$1", _u(tid))
        return ids

    async def list_assignments(self) -> list[Row]:
        rows = await self._all("SELECT a.assignment_id, a.template_id, t.name AS template_name, t.kind, a.scope_type, a.scope_ref, a.enabled, a.notify_client, a.created_at, "
                               "CASE a.scope_type WHEN 'group' THEN (SELECT g.name FROM account_groups g WHERE g.group_id::text = a.scope_ref) ELSE a.scope_ref END AS scope_label "
                               "FROM rule_assignments a JOIN rule_templates t ON t.template_id = a.template_id ORDER BY t.name, a.created_at")
        for r in rows:
            r["id"] = r.pop("assignment_id")
        return rows

    async def get_assignment(self, aid: str) -> Row | None:
        r = await self._one("SELECT assignment_id, template_id, scope_type, scope_ref, enabled, notify_client FROM rule_assignments WHERE assignment_id=$1", _u(aid))
        if r:
            r["id"] = r.pop("assignment_id")
        return r

    async def create_assignment(self, template_id: str, scope_type: str, scope_ref: str, enabled: bool, notify_client: bool, by: str | None) -> Row:
        r = await self._one("INSERT INTO rule_assignments (template_id, scope_type, scope_ref, enabled, notify_client, created_by) VALUES ($1,$2,$3,$4,$5,$6) "
                            "RETURNING assignment_id, template_id, scope_type, scope_ref, enabled, notify_client, created_at", _u(template_id), scope_type, scope_ref, enabled, notify_client,
                            _u(by) if by else None)
        r["id"] = r.pop("assignment_id")
        return r

    async def update_assignment(self, aid: str, **f) -> Row | None:
        ok = {k: v for k, v in f.items() if k in ("enabled", "notify_client", "scope_type", "scope_ref") and v is not None}
        if ok:
            sets = ", ".join(f"{k}=${i + 2}" for i, k in enumerate(ok))
            await self._exec(f"UPDATE rule_assignments SET {sets} WHERE assignment_id=$1", _u(aid), *ok.values())  # noqa: S608 (khoá whitelist)
        return await self.get_assignment(aid)

    async def delete_assignment(self, aid: str) -> bool:
        return (await self._exec("DELETE FROM rule_assignments WHERE assignment_id=$1", _u(aid))).endswith(" 1")

    async def clear_rule_status(self, aid: str) -> None:
        await self._exec("DELETE FROM rule_status WHERE assignment_id=$1", _u(aid))

    async def engine_assignments(self) -> list[Row]:
        rows = await self._all("SELECT a.assignment_id, a.template_id, t.name, t.kind, t.params, a.scope_type, a.scope_ref, a.notify_client "
                               "FROM rule_assignments a JOIN rule_templates t ON t.template_id = a.template_id WHERE a.enabled ORDER BY a.created_at")
        for r in rows:
            r["params"] = _j(r["params"], {})
        return rows

    async def scope_index(self) -> dict:
        """Chỉ mục cho phân giải phạm vi: tài khoản active -> {groups:set(id), tags:set, user, notify, label}."""
        accs = await self._all("SELECT account_id, label, client_id, client_notify FROM mt_accounts WHERE status='active'")
        idx = {a["account_id"]: {"label": a["label"], "user": a["client_id"], "notify": bool(a["client_notify"]), "groups": set(), "gnames": [], "tags": set()} for a in accs}
        for r in await self._all("SELECT m.account_id, m.group_id, g.name FROM account_group_members m JOIN account_groups g ON g.group_id = m.group_id"):
            if r["account_id"] in idx:
                idx[r["account_id"]]["groups"].add(r["group_id"])
                idx[r["account_id"]]["gnames"].append(r["name"])
        for r in await self._all("SELECT account_id, tag FROM account_tags"):
            if r["account_id"] in idx:
                idx[r["account_id"]]["tags"].add(r["tag"])
        return idx

    async def upsert_results(self, rows: list[dict]) -> int:
        n = 0
        async with self.pool.acquire() as c, c.transaction():
            for r in rows:
                res = await c.execute(
                    "INSERT INTO rule_status (account_id, assignment_id, status, usage_pct, value, limit_value, headroom, unit, detail, reset_at, evaluated_at) "
                    "SELECT $1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, $10, $11 WHERE EXISTS (SELECT 1 FROM mt_accounts WHERE account_id=$1) "
                    "AND EXISTS (SELECT 1 FROM rule_assignments WHERE assignment_id=$2) "
                    "ON CONFLICT (account_id, assignment_id) DO UPDATE SET status=EXCLUDED.status, usage_pct=EXCLUDED.usage_pct, value=EXCLUDED.value, limit_value=EXCLUDED.limit_value, "
                    "headroom=EXCLUDED.headroom, unit=EXCLUDED.unit, detail=EXCLUDED.detail, reset_at=EXCLUDED.reset_at, evaluated_at=EXCLUDED.evaluated_at",
                    r["account_id"], _u(r["assignment_id"]), r["status"], r["usage_pct"], r["value"], r["limit"], r["headroom"], r["unit"], json.dumps(r["detail"]),
                    r["reset_at"], r["evaluated_at"])
                n += res.endswith(" 1")
        return n

    async def compliance_rows(self, account_ids: list[str] | None) -> list[Row]:
        rows = await self._all(
            "SELECT rs.account_id, a.label, rs.assignment_id, t.name AS rule_name, t.kind, rs.status, rs.usage_pct, rs.value, rs.limit_value AS limit, rs.headroom, rs.unit, "
            "rs.reset_at, rs.evaluated_at, rs.detail, "
            "COALESCE((SELECT array_agg(g.name ORDER BY g.name) FROM account_group_members m JOIN account_groups g ON g.group_id = m.group_id WHERE m.account_id = rs.account_id), '{}') AS groups, "
            "COALESCE((SELECT array_agg(m.group_id::text) FROM account_group_members m WHERE m.account_id = rs.account_id), '{}') AS group_ids, "
            "COALESCE((SELECT array_agg(tg.tag) FROM account_tags tg WHERE tg.account_id = rs.account_id), '{}') AS tags "
            "FROM rule_status rs JOIN rule_assignments ra ON ra.assignment_id = rs.assignment_id AND ra.enabled "
            "JOIN rule_templates t ON t.template_id = ra.template_id JOIN mt_accounts a ON a.account_id = rs.account_id "
            "WHERE ($1::text[] IS NULL OR rs.account_id = ANY($1::text[])) "
            "ORDER BY CASE rs.status WHEN 'red' THEN 0 WHEN 'yellow' THEN 1 WHEN 'green' THEN 2 ELSE 3 END, rs.usage_pct DESC NULLS LAST LIMIT 5000", account_ids)
        for r in rows:
            r["detail"] = _j(r["detail"], {})
            r["groups"], r["group_ids"], r["tags"] = list(r["groups"] or []), list(r["group_ids"] or []), list(r["tags"] or [])
        return rows

    # ------------------------------------------------------------------ sự cố
    async def group_policies_for(self, account_id: str) -> list[dict]:
        rows = await self._all("SELECT g.policy FROM account_group_members m JOIN account_groups g ON g.group_id = m.group_id WHERE m.account_id=$1", account_id)
        return [_j(r["policy"], {}) for r in rows]

    async def upsert_incident(self, key: str, kind: str, account_id: str, cause_key: str, severity: str, title: str, detail: str, meta: dict,
                              assignee: tuple[str, str] | None = None) -> tuple[str, str]:
        """Mở/cập nhật sự cố theo key. Trả (incident_id, 'opened'|'updated'|'escalated'|'unsnoozed')."""
        async with self.pool.acquire() as c, c.transaction():
            cur = await c.fetchrow("SELECT incident_id, severity, status, snoozed_until FROM incidents WHERE key=$1 AND status <> 'resolved' FOR UPDATE", key)
            if cur is None:
                r = await c.fetchrow(
                    "INSERT INTO incidents (key, kind, account_id, cause_key, severity, title, detail, meta, assignee_user_id, assignee_label) VALUES ($1,$2,$3,$4,$5,$6,$7,$8::jsonb,$9,$10) RETURNING incident_id",
                    key, kind, account_id, cause_key, severity, title[:300], detail[:1000], json.dumps(meta), _u(assignee[0]) if assignee else None, assignee[1] if assignee else "")
                await c.execute("INSERT INTO incident_events (incident_id, type, text, actor_label) VALUES ($1,'opened',$2,'hệ thống')", r["incident_id"], title[:300])
                return str(r["incident_id"]), "opened"
            iid, outcome = cur["incident_id"], "updated"
            sets = "last_seen_at=now(), occurrences=occurrences+1, title=$2, detail=$3, meta=$4::jsonb, severity=$5"
            if cur["severity"] != severity:
                await c.execute("INSERT INTO incident_events (incident_id, type, text, actor_label) VALUES ($1,'escalate',$2,'hệ thống')", iid, f"{cur['severity']} -> {severity}")
                outcome = "escalated"
            if cur["status"] == "snoozed" and cur["snoozed_until"] and cur["snoozed_until"] <= datetime.now(timezone.utc):
                sets += ", status='open', snoozed_until=NULL"
                await c.execute("INSERT INTO incident_events (incident_id, type, text, actor_label) VALUES ($1,'unsnooze','hết thời gian tạm hoãn','hệ thống')", iid)
                outcome = "unsnoozed"
            await c.execute(f"UPDATE incidents SET {sets} WHERE incident_id=$1", iid, title[:300], detail[:1000], json.dumps(meta), severity)  # noqa: S608 (chuỗi cố định)
            return str(iid), outcome

    async def close_incident_by_key(self, key: str, by: str = "auto", text: str = "điều kiện đã hết") -> int:
        async with self.pool.acquire() as c, c.transaction():
            rows = await c.fetch("UPDATE incidents SET status='resolved', resolved_at=now(), resolved_by=$2 WHERE key=$1 AND status <> 'resolved' RETURNING incident_id", key, by)
            for r in rows:
                await c.execute("INSERT INTO incident_events (incident_id, type, text, actor_label) VALUES ($1,'auto_resolve',$2,'hệ thống')", r["incident_id"], text)
        return len(rows)

    async def close_incidents_like(self, prefix: str, by: str = "auto", text: str = "luật đã bị gỡ/tắt") -> int:
        async with self.pool.acquire() as c, c.transaction():
            rows = await c.fetch("UPDATE incidents SET status='resolved', resolved_at=now(), resolved_by=$2 WHERE left(key, length($1)) = $1 AND status <> 'resolved' RETURNING incident_id", prefix, by)
            for r in rows:
                await c.execute("INSERT INTO incident_events (incident_id, type, text, actor_label) VALUES ($1,'auto_resolve',$2,'hệ thống')", r["incident_id"], text)
        return len(rows)

    async def open_keys(self, prefix: str) -> list[str]:
        return [r["key"] for r in await self._all("SELECT key FROM incidents WHERE left(key, length($1)) = $1 AND status <> 'resolved'", prefix)]

    async def unsnooze_expired(self) -> int:
        async with self.pool.acquire() as c, c.transaction():
            rows = await c.fetch("UPDATE incidents SET status='open', snoozed_until=NULL WHERE status='snoozed' AND snoozed_until <= now() RETURNING incident_id")
            for r in rows:
                await c.execute("INSERT INTO incident_events (incident_id, type, text, actor_label) VALUES ($1,'unsnooze','hết thời gian tạm hoãn','hệ thống')", r["incident_id"])
        return len(rows)

    INC_COLS = ("incident_id, key, kind, account_id, cause_key, severity, status, title, detail, assignee_user_id, assignee_label, snoozed_until, opened_at, acked_at, "
                "resolved_at, resolved_by, last_seen_at, occurrences")

    async def list_incidents(self, statuses: list[str] | None, limit: int = 500) -> list[Row]:
        rows = await self._all(
            f"SELECT {self.INC_COLS}, COALESCE((SELECT array_agg(m.group_id::text) FROM account_group_members m WHERE m.account_id = incidents.account_id), '{{}}') AS group_ids "  # noqa: S608
            "FROM incidents WHERE ($1::text[] IS NULL OR status = ANY($1::text[])) "
            "ORDER BY CASE severity WHEN 'critical' THEN 0 WHEN 'warning' THEN 1 ELSE 2 END, opened_at DESC LIMIT $2", statuses, limit)
        for r in rows:
            r["id"] = r.pop("incident_id")
            r["group_ids"] = list(r["group_ids"] or [])
        return rows

    async def get_incident(self, iid: str) -> Row | None:
        r = await self._one(f"SELECT {self.INC_COLS}, meta FROM incidents WHERE incident_id=$1", _u(iid))  # noqa: S608
        if not r:
            return None
        r["id"] = r.pop("incident_id")
        r["meta"] = _j(r["meta"], {})
        r["events"] = await self._all("SELECT event_id, ts, actor_label, type, text, meta FROM incident_events WHERE incident_id=$1 ORDER BY ts, event_id", _u(iid))
        return r

    async def incident_counts(self, account_ids: list[str] | None) -> dict:
        r = await self._one(
            "SELECT count(*) FILTER (WHERE status='open') AS open, count(*) FILTER (WHERE status='ack') AS ack, count(*) FILTER (WHERE status='snoozed') AS snoozed, "
            "count(*) FILTER (WHERE status='resolved' AND resolved_at > now() - interval '24 hours') AS resolved_24h, "
            "count(*) FILTER (WHERE status <> 'resolved' AND severity='critical') AS critical_active FROM incidents "
            "WHERE ($1::text[] IS NULL OR account_id = ANY($1::text[]))", account_ids)
        return {k: int(v or 0) for k, v in (r or {}).items()}

    async def incident_action(self, iid: str, action: str, actor_id: str | None, actor_label: str, *, text: str = "", assignee: tuple[str | None, str] | None = None,
                              until: datetime | None = None) -> Row | None:
        """Chuyển trạng thái + ghi sự kiện (một giao dịch). Trả hàng sau cập nhật hoặc None nếu không tồn tại / chuyển không hợp lệ."""
        async with self.pool.acquire() as c, c.transaction():
            cur = await c.fetchrow("SELECT status FROM incidents WHERE incident_id=$1 FOR UPDATE", _u(iid))
            if cur is None:
                return None
            st = cur["status"]
            ev_text, meta = text, {}
            if action == "ack":
                if st == "resolved":
                    return None
                await c.execute("UPDATE incidents SET status='ack', acked_at=now(), snoozed_until=NULL, assignee_user_id=COALESCE(assignee_user_id,$2), "
                                "assignee_label=CASE WHEN assignee_label='' THEN $3 ELSE assignee_label END WHERE incident_id=$1", _u(iid), _u(actor_id) if actor_id else None, actor_label)
            elif action == "assign":
                if st == "resolved":
                    return None
                uid, label = assignee or (None, "")
                await c.execute("UPDATE incidents SET assignee_user_id=$2, assignee_label=$3 WHERE incident_id=$1", _u(iid), _u(uid) if uid else None, label)
                ev_text = f"giao cho {label}" if uid else "bỏ giao"
            elif action == "snooze":
                if st == "resolved":
                    return None
                await c.execute("UPDATE incidents SET status='snoozed', snoozed_until=$2 WHERE incident_id=$1", _u(iid), until)
                meta = {"until": until.isoformat() if until else None}
            elif action == "resolve":
                if st == "resolved":
                    return None
                await c.execute("UPDATE incidents SET status='resolved', resolved_at=now(), resolved_by=$2, snoozed_until=NULL WHERE incident_id=$1", _u(iid), actor_label)
            elif action == "reopen":
                if st != "resolved":
                    return None
                dup = await c.fetchval("SELECT 1 FROM incidents i WHERE i.key = (SELECT key FROM incidents WHERE incident_id=$1) AND i.status <> 'resolved'", _u(iid))
                if dup:
                    return None
                await c.execute("UPDATE incidents SET status='open', resolved_at=NULL, resolved_by='', acked_at=NULL WHERE incident_id=$1", _u(iid))
            elif action == "note":
                pass
            else:
                return None
            await c.execute("INSERT INTO incident_events (incident_id, actor_user_id, actor_label, type, text, meta) VALUES ($1,$2,$3,$4,$5,$6::jsonb)",
                            _u(iid), _u(actor_id) if actor_id else None, actor_label[:120], action, ev_text[:1000], json.dumps(meta))
        return {"ok": True}

    async def ea_candidates(self) -> list[Row]:
        return await self._all("SELECT account_id, label, ea_status, last_seen_at, ea_reason FROM mt_accounts WHERE status='active' AND last_seen_at IS NOT NULL")

    # ------------------------------------------------------------------ nhân sự phụ
    async def list_staff(self) -> list[Row]:
        rows = await self._all(
            "SELECT u.user_id, u.role, u.login_key, u.display_name, u.status, u.totp_enabled, u.scope_all, u.last_login_at, u.created_at, "
            "COALESCE((SELECT json_agg(json_build_object('id', g.group_id, 'name', g.name) ORDER BY g.name) FROM staff_scopes s JOIN account_groups g ON g.group_id = s.group_id WHERE s.user_id = u.user_id), '[]'::json) AS groups "
            "FROM portal_users u WHERE u.role IN ('master','support','analyst','auditor','expert') ORDER BY u.role, u.login_key")
        for r in rows:
            r["groups"] = _j(r["groups"], [])
        return rows

    async def create_staff(self, role: str, login_key: str, display_name: str, password_hash: str, scope_all: bool, group_ids: list[str], by: str | None) -> Row:
        async with self.pool.acquire() as c, c.transaction():
            u = _row(await c.fetchrow(
                "INSERT INTO portal_users (role, login_key, display_name, password_hash, must_change_password, scope_all, created_by) VALUES ($1,$2,$3,$4,true,$5,$6) RETURNING user_id, role, login_key, display_name, scope_all",
                role, login_key, display_name, password_hash, scope_all, _u(by) if by else None))
            for g in group_ids:
                await c.execute("INSERT INTO staff_scopes (user_id, group_id) SELECT $1, group_id FROM account_groups WHERE group_id=$2 ON CONFLICT DO NOTHING", _u(u["user_id"]), _u(g))
        return u

    async def update_staff(self, user_id: str, role: str | None, scope_all: bool | None, group_ids: list[str] | None, display_name: str | None) -> Row | None:
        async with self.pool.acquire() as c, c.transaction():
            u = await c.fetchrow("SELECT user_id, role FROM portal_users WHERE user_id=$1 AND role IN ('support','analyst','auditor','expert') FOR UPDATE", _u(user_id))
            if not u:
                return None
            if role:
                await c.execute("UPDATE portal_users SET role=$2 WHERE user_id=$1", _u(user_id), role)
            if scope_all is not None:
                await c.execute("UPDATE portal_users SET scope_all=$2 WHERE user_id=$1", _u(user_id), scope_all)
            if display_name is not None:
                await c.execute("UPDATE portal_users SET display_name=$2 WHERE user_id=$1", _u(user_id), display_name)
            if group_ids is not None:
                await c.execute("DELETE FROM staff_scopes WHERE user_id=$1", _u(user_id))
                for g in group_ids:
                    await c.execute("INSERT INTO staff_scopes (user_id, group_id) SELECT $1, group_id FROM account_groups WHERE group_id=$2 ON CONFLICT DO NOTHING", _u(user_id), _u(g))
        return {"ok": True}

    async def set_client_notify(self, account_id: str, enabled: bool) -> None:
        await self._exec("UPDATE mt_accounts SET client_notify=$2, client_notify_at=now() WHERE account_id=$1", account_id, enabled)

    async def users_for_assign(self) -> list[Row]:
        return await self._all("SELECT user_id, display_name, login_key, role FROM portal_users WHERE role IN ('master','support') AND status='active' ORDER BY display_name")
