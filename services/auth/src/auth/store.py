"""Lớp truy cập DB (asyncpg) cho auth. Chỉ dùng role `ts_auth`. Mọi truy vấn tham số hoá ($n). Không log bí mật."""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any

Row = dict[str, Any]

ACCOUNT_UPDATABLE = {"label", "notes", "server", "status", "ea_token_hash", "ea_hmac_secret_enc", "pairing_code_hash", "pairing_expires_at",
                     "client_id", "last_seen_at", "require_hmac", "config", "ea_cred_pending_enc", "ea_remote_addr"}

SESSION_SQL = """
SELECT s.session_id, s.user_id, s.created_at, s.expires_at, s.last_seen_at, s.revoked, s.ip, s.user_agent,
       u.role, u.login_key, u.display_name, u.status AS user_status, u.must_change_password, u.totp_enabled, u.scope_all,
       COALESCE((SELECT array_agg(a.account_id ORDER BY a.account_id) FROM user_accounts ua JOIN mt_accounts a ON a.account_id = ua.account_id
                 WHERE ua.user_id = u.user_id AND a.status <> 'suspended'), '{}') AS accounts
FROM portal_sessions s JOIN portal_users u ON u.user_id = s.user_id
"""


def _d(r) -> Row | None:
    return dict(r) if r is not None else None


class Store:
    def __init__(self, pool):
        self.pool = pool

    @classmethod
    async def connect(cls, dsn: str) -> "Store":
        import asyncpg
        return cls(await asyncpg.create_pool(dsn, min_size=1, max_size=6, command_timeout=10))

    async def close(self) -> None:
        await self.pool.close()

    async def ping(self) -> bool:
        async with self.pool.acquire() as c:
            return await c.fetchval("SELECT 1") == 1

    # ---------------- users ----------------
    async def get_user(self, user_id: str) -> Row | None:
        async with self.pool.acquire() as c:
            return _d(await c.fetchrow("SELECT * FROM portal_users WHERE user_id = $1", uuid.UUID(str(user_id))))

    async def get_user_by_key(self, login_key: str) -> Row | None:
        async with self.pool.acquire() as c:
            return _d(await c.fetchrow("SELECT * FROM portal_users WHERE login_key = $1", login_key))

    async def count_masters(self) -> int:
        async with self.pool.acquire() as c:
            return await c.fetchval("SELECT count(*) FROM portal_users WHERE role = 'master'")

    async def create_user(self, role: str, login_key: str, display_name: str, password_hash: str, must_change: bool) -> Row:
        async with self.pool.acquire() as c:
            return dict(await c.fetchrow(
                "INSERT INTO portal_users (role, login_key, display_name, password_hash, must_change_password) VALUES ($1,$2,$3,$4,$5) RETURNING *",
                role, login_key, display_name, password_hash, must_change))

    async def set_password(self, user_id: str, pw_hash: str, must_change: bool) -> None:
        async with self.pool.acquire() as c:
            await c.execute("UPDATE portal_users SET password_hash=$2, must_change_password=$3, password_changed_at=now(), failed_attempts=0, locked_until=NULL "
                            "WHERE user_id=$1", uuid.UUID(str(user_id)), pw_hash, must_change)

    async def record_fail(self, user_id: str, max_fails: int, lock_minutes: int) -> Row:
        """Tăng bộ đếm sai; đủ max_fails -> khoá lock_minutes và đặt lại bộ đếm. Trả {failed_attempts, locked_until}."""
        async with self.pool.acquire() as c:
            return dict(await c.fetchrow(
                "UPDATE portal_users SET failed_attempts = CASE WHEN failed_attempts + 1 >= $2 THEN 0 ELSE failed_attempts + 1 END, "
                "locked_until = CASE WHEN failed_attempts + 1 >= $2 THEN now() + make_interval(mins => $3) ELSE locked_until END "
                "WHERE user_id = $1 RETURNING failed_attempts, locked_until", uuid.UUID(str(user_id)), max_fails, lock_minutes))

    async def record_success(self, user_id: str) -> None:
        async with self.pool.acquire() as c:
            await c.execute("UPDATE portal_users SET failed_attempts=0, locked_until=NULL, last_login_at=now() WHERE user_id=$1", uuid.UUID(str(user_id)))

    async def unlock(self, user_id: str) -> None:
        async with self.pool.acquire() as c:
            await c.execute("UPDATE portal_users SET failed_attempts=0, locked_until=NULL WHERE user_id=$1", uuid.UUID(str(user_id)))

    async def set_user_status(self, user_id: str, status: str) -> None:
        async with self.pool.acquire() as c:
            await c.execute("UPDATE portal_users SET status=$2 WHERE user_id=$1", uuid.UUID(str(user_id)), status)

    async def set_totp(self, user_id: str, enc: str | None, enabled: bool) -> None:
        async with self.pool.acquire() as c:
            await c.execute("UPDATE portal_users SET totp_secret_enc=$2, totp_enabled=$3 WHERE user_id=$1", uuid.UUID(str(user_id)), enc, enabled)

    async def list_users(self, limit: int = 500) -> list[Row]:
        async with self.pool.acquire() as c:
            rows = await c.fetch(
                "SELECT u.user_id, u.role, u.login_key, u.display_name, u.status, u.must_change_password, u.totp_enabled, u.failed_attempts, u.locked_until, "
                "u.created_at, u.last_login_at, COALESCE((SELECT array_agg(ua.account_id ORDER BY ua.account_id) FROM user_accounts ua WHERE ua.user_id=u.user_id), '{}') AS accounts, "
                "(SELECT count(*) FROM portal_sessions s WHERE s.user_id=u.user_id AND NOT s.revoked AND s.expires_at > now()) AS active_sessions "
                "FROM portal_users u ORDER BY u.role, u.login_key LIMIT $1", limit)
        return [dict(r) for r in rows]

    # ---------------- accounts ----------------
    async def find_accounts(self, platform: str, login: int, server: str | None = None) -> list[Row]:
        async with self.pool.acquire() as c:
            if server:
                rows = await c.fetch("SELECT * FROM mt_accounts WHERE platform=$1 AND login=$2 AND lower(server)=lower($3)", platform, login, server)
            else:
                rows = await c.fetch("SELECT * FROM mt_accounts WHERE platform=$1 AND login=$2", platform, login)
        return [dict(r) for r in rows]

    async def get_account(self, account_id: str) -> Row | None:
        async with self.pool.acquire() as c:
            return _d(await c.fetchrow("SELECT * FROM mt_accounts WHERE account_id=$1", account_id))

    async def list_accounts(self, limit: int = 2000) -> list[Row]:
        async with self.pool.acquire() as c:
            rows = await c.fetch(
                "SELECT a.account_id, a.platform, a.login, a.server, a.label, a.client_id, a.status, a.created_at, a.last_seen_at, a.notes, "
                "a.pairing_expires_at, (a.pairing_code_hash IS NOT NULL) AS has_pairing, (a.ea_token_hash IS NOT NULL) AS has_ea_token, "
                "(a.ea_hmac_secret_enc IS NOT NULL) AS has_hmac, a.rev, a.require_hmac, a.ea_status, a.ea_reason, a.ea_latency_ms, a.ea_skew_s, a.ea_version, a.ea_build, a.ea_broker, a.ea_health_at, a.ea_remote_addr, a.require_hmac, a.ea_status, a.ea_reason, a.ea_latency_ms, a.ea_skew_s, a.ea_version, a.ea_build, a.ea_broker, a.ea_health_at, a.ea_remote_addr, u.login_key AS client_login, u.display_name AS client_name, u.status AS client_status, "
                "u.must_change_password AS client_must_change, u.last_login_at AS client_last_login, u.locked_until AS client_locked_until "
                "FROM mt_accounts a LEFT JOIN portal_users u ON u.user_id = a.client_id ORDER BY a.account_id LIMIT $1", limit)
        return [dict(r) for r in rows]

    async def create_client_account(self, *, account_id: str, platform: str, login: int, server: str, label: str, notes: str, password_hash: str,
                                    display_name: str, ea_token_hash: str, hmac_enc: str, pairing_hash: str, pairing_expires: datetime) -> tuple[Row, Row]:
        """Một giao dịch: tạo user client + tài khoản MT + liên kết."""
        async with self.pool.acquire() as c, c.transaction():
            u = dict(await c.fetchrow(
                "INSERT INTO portal_users (role, login_key, display_name, password_hash, must_change_password) VALUES ('client',$1,$2,$3,true) RETURNING *",
                account_id, display_name, password_hash))
            a = dict(await c.fetchrow(
                "INSERT INTO mt_accounts (account_id, platform, login, server, label, notes, client_id, status, ea_token_hash, ea_hmac_secret_enc, "
                "pairing_code_hash, pairing_expires_at) VALUES ($1,$2,$3,$4,$5,$6,$7,'pending',$8,$9,$10,$11) RETURNING *",
                account_id, platform, login, server, label, notes, u["user_id"], ea_token_hash, hmac_enc, pairing_hash, pairing_expires))
            await c.execute("INSERT INTO user_accounts (user_id, account_id) VALUES ($1,$2)", u["user_id"], account_id)
        return u, a

    async def update_account(self, account_id: str, **fields) -> Row | None:
        bad = set(fields) - ACCOUNT_UPDATABLE
        if bad or not fields:
            raise ValueError(f"cột không hợp lệ: {sorted(bad)}")
        sets = "rev = rev + 1, " + ", ".join(f"{k}=${i + 2}" for i, k in enumerate(fields))
        async with self.pool.acquire() as c:
            return _d(await c.fetchrow(f"UPDATE mt_accounts SET {sets} WHERE account_id=$1 RETURNING *", account_id, *fields.values()))  # noqa: S608 (khoá từ whitelist)

    async def list_accounts_full(self, limit: int = 5000) -> list[Row]:
        async with self.pool.acquire() as c:
            rows = await c.fetch("SELECT * FROM mt_accounts ORDER BY account_id LIMIT $1", limit)
        return [dict(r) for r in rows]

    async def accounts_rev(self) -> int:
        async with self.pool.acquire() as c:
            return int(await c.fetchval("SELECT COALESCE(sum(rev),0) + count(*) FROM mt_accounts"))

    async def create_selfreg_account(self, *, account_id: str, platform: str, login: int, server: str, pairing_hash: str, pairing_expires: datetime,
                                     cred_enc: str, token_hash: str, hmac_enc: str, remote_addr: str, broker: str, ea_version: str, build: int | None) -> Row:
        """EA tự đăng ký: tài khoản pending CHƯA có chủ (client_id NULL); client ghép cặp bằng mã ở /auth/pair."""
        async with self.pool.acquire() as c:
            return dict(await c.fetchrow(
                "INSERT INTO mt_accounts (account_id, platform, login, server, label, status, ea_token_hash, ea_hmac_secret_enc, pairing_code_hash, pairing_expires_at, "
                "ea_cred_pending_enc, ea_remote_addr, ea_broker, ea_version, ea_build) VALUES ($1,$2,$3,$4,'','pending',$5,$6,$7,$8,$9,$10,$11,$12,$13) RETURNING *",
                account_id, platform, login, server, token_hash, hmac_enc, pairing_hash, pairing_expires, cred_enc, remote_addr[:64], broker[:64], ea_version[:16], build))

    async def count_unclaimed(self) -> int:
        async with self.pool.acquire() as c:
            return int(await c.fetchval("SELECT count(*) FROM mt_accounts WHERE client_id IS NULL AND status='pending'"))

    async def update_health(self, items: list[dict]) -> int:
        n = 0
        async with self.pool.acquire() as c, c.transaction():
            for it in items:
                r = await c.execute(
                    "UPDATE mt_accounts SET last_seen_at=COALESCE($2, now()), ea_status=$3, ea_reason=$4, ea_latency_ms=$5, ea_skew_s=$6, ea_version=$7, ea_build=$8, "
                    "ea_broker=$9, ea_remote_addr=$10, ea_health_at=now(), server=CASE WHEN server='' THEN $11 ELSE server END WHERE account_id=$1",
                    it["account_id"], it.get("last_seen_at"), it["status"], it["reason"], it["latency_ms"], it["skew_s"], it["ea_version"], it["build"], it["broker"], it["remote_addr"], it["server"])
                n += r.endswith(" 1")
        return n

    async def delete_account(self, account_id: str) -> Row | None:
        """Xoá tài khoản MT; xoá luôn user client nếu không còn tài khoản nào khác. Trả {account_id, client_id, user_deleted}."""
        async with self.pool.acquire() as c, c.transaction():
            a = await c.fetchrow("SELECT account_id, client_id FROM mt_accounts WHERE account_id=$1 FOR UPDATE", account_id)
            if not a:
                return None
            await c.execute("DELETE FROM mt_accounts WHERE account_id=$1", account_id)
            user_deleted = False
            if a["client_id"]:
                left = await c.fetchval("SELECT count(*) FROM user_accounts WHERE user_id=$1", a["client_id"])
                if left == 0:
                    await c.execute("DELETE FROM portal_users WHERE user_id=$1 AND role='client'", a["client_id"])
                    user_deleted = True
            return {"account_id": account_id, "client_id": str(a["client_id"]) if a["client_id"] else None, "user_deleted": user_deleted}

    async def accounts_of_user(self, user_id: str) -> list[str]:
        async with self.pool.acquire() as c:
            rows = await c.fetch("SELECT a.account_id FROM user_accounts ua JOIN mt_accounts a ON a.account_id=ua.account_id "
                                 "WHERE ua.user_id=$1 AND a.status <> 'suspended' ORDER BY a.account_id", uuid.UUID(str(user_id)))
        return [r["account_id"] for r in rows]

    async def link_account(self, user_id: str, account_id: str) -> None:
        async with self.pool.acquire() as c:
            await c.execute("INSERT INTO user_accounts (user_id, account_id) VALUES ($1,$2) ON CONFLICT DO NOTHING", uuid.UUID(str(user_id)), account_id)

    async def unlink_account(self, user_id: str, account_id: str) -> bool:
        async with self.pool.acquire() as c:
            r = await c.execute("DELETE FROM user_accounts WHERE user_id=$1 AND account_id=$2", uuid.UUID(str(user_id)), account_id)
        return r.endswith(" 1")

    async def claim_account(self, account_id: str, user_id: str | None, password_hash: str, display_name: str) -> Row:
        """Ghép cặp: đặt mật khẩu cho user chủ (tạo mới nếu EA tự đăng ký chưa có chủ), kích hoạt tài khoản, huỷ mã ghép cặp. Một giao dịch."""
        async with self.pool.acquire() as c, c.transaction():
            if user_id is None:
                u = dict(await c.fetchrow(
                    "INSERT INTO portal_users (role, login_key, display_name, password_hash, must_change_password, password_changed_at) "
                    "VALUES ('client',$1,$2,$3,false,now()) RETURNING *", account_id, display_name, password_hash))
                await c.execute("INSERT INTO user_accounts (user_id, account_id) VALUES ($1,$2) ON CONFLICT DO NOTHING", u["user_id"], account_id)
                await c.execute("UPDATE mt_accounts SET client_id=$2 WHERE account_id=$1", account_id, u["user_id"])
            else:
                u = dict(await c.fetchrow(
                    "UPDATE portal_users SET password_hash=$2, must_change_password=false, password_changed_at=now(), failed_attempts=0, locked_until=NULL "
                    "WHERE user_id=$1 RETURNING *", uuid.UUID(str(user_id)), password_hash))
            await c.execute("UPDATE mt_accounts SET pairing_code_hash=NULL, pairing_expires_at=NULL, status=CASE WHEN status='pending' THEN 'active' ELSE status END, rev=rev+1 "
                            "WHERE account_id=$1", account_id)
            return u

    # ---------------- sessions ----------------
    async def create_session(self, sid_hash: str, user_id: str, expires_at: datetime, ip: str, ua: str) -> None:
        async with self.pool.acquire() as c:
            await c.execute("INSERT INTO portal_sessions (session_id, user_id, expires_at, ip, user_agent) VALUES ($1,$2,$3,$4,$5)",
                            sid_hash, uuid.UUID(str(user_id)), expires_at, ip[:64], ua[:200])

    async def get_session(self, sid_hash: str) -> Row | None:
        async with self.pool.acquire() as c:
            return _d(await c.fetchrow(SESSION_SQL + " WHERE s.session_id = $1", sid_hash))

    async def touch_session(self, sid_hash: str) -> None:
        async with self.pool.acquire() as c:
            await c.execute("UPDATE portal_sessions SET last_seen_at = now() WHERE session_id = $1", sid_hash)

    async def revoke_session(self, sid_hash: str, user_id: str | None = None) -> bool:
        async with self.pool.acquire() as c:
            if user_id:
                r = await c.execute("UPDATE portal_sessions SET revoked=true WHERE session_id=$1 AND user_id=$2 AND NOT revoked", sid_hash, uuid.UUID(str(user_id)))
            else:
                r = await c.execute("UPDATE portal_sessions SET revoked=true WHERE session_id=$1 AND NOT revoked", sid_hash)
        return r.endswith(" 1")

    async def revoke_user_sessions(self, user_id: str, except_hash: str | None = None) -> list[str]:
        async with self.pool.acquire() as c:
            rows = await c.fetch("UPDATE portal_sessions SET revoked=true WHERE user_id=$1 AND NOT revoked AND session_id <> COALESCE($2,'') RETURNING session_id",
                                 uuid.UUID(str(user_id)), except_hash)
        return [r["session_id"] for r in rows]

    async def list_sessions(self, user_id: str | None = None, active_only: bool = True, limit: int = 200) -> list[Row]:
        q = SESSION_SQL + " WHERE ($1::uuid IS NULL OR s.user_id = $1) AND (NOT $2 OR (NOT s.revoked AND s.expires_at > now())) ORDER BY s.last_seen_at DESC LIMIT $3"
        async with self.pool.acquire() as c:
            rows = await c.fetch(q, uuid.UUID(str(user_id)) if user_id else None, active_only, limit)
        return [dict(r) for r in rows]

    async def purge_sessions(self, older_than_days: int = 30) -> int:
        async with self.pool.acquire() as c:
            r = await c.execute("DELETE FROM portal_sessions WHERE (expires_at < now() - make_interval(days => $1)) OR (revoked AND last_seen_at < now() - make_interval(days => $1))",
                                older_than_days)
        return int(r.split()[-1])

    # ---------------- audit (chuỗi băm) ----------------
    @staticmethod
    def _chain(prev: str, ts: datetime, actor_id, actor_label, action, target, ip, detail) -> str:
        body = json.dumps([ts.isoformat(), str(actor_id) if actor_id else "", actor_label, action, target, ip, detail],
                          sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=False)
        return hashlib.sha256((prev + body).encode()).hexdigest()

    async def audit(self, actor_id: str | None, actor_label: str, action: str, target: str = "", ip: str = "", detail: dict | None = None) -> None:
        detail = json.loads(json.dumps(detail or {}, default=str))   # chuẩn hoá về JSON thuần (đúng như jsonb sẽ trả lại)
        ts = datetime.now(timezone.utc)
        async with self.pool.acquire() as c, c.transaction():
            await c.execute("SELECT pg_advisory_xact_lock(7770011)")
            prev = await c.fetchval("SELECT hash FROM audit_log ORDER BY id DESC LIMIT 1") or ""
            h = self._chain(prev, ts, actor_id, actor_label, action, target, ip, detail)
            await c.execute("INSERT INTO audit_log (ts, actor_user_id, actor_label, action, target, ip, detail, prev_hash, hash) VALUES ($1,$2,$3,$4,$5,$6,$7::jsonb,$8,$9)",
                            ts, uuid.UUID(str(actor_id)) if actor_id else None, actor_label[:120], action[:60], target[:200], ip[:64], json.dumps(detail, ensure_ascii=False), prev, h)

    async def list_audit(self, limit: int = 100, action: str | None = None, before_id: int | None = None, target: str | None = None) -> list[Row]:
        async with self.pool.acquire() as c:
            rows = await c.fetch(
                "SELECT id, ts, actor_user_id, actor_label, action, target, ip, detail FROM audit_log "
                "WHERE ($1::text IS NULL OR action = $1) AND ($2::bigint IS NULL OR id < $2) AND ($3::text IS NULL OR target = $3) ORDER BY id DESC LIMIT $4",
                action, before_id, target, limit)
        out = []
        for r in rows:
            d = dict(r)
            if isinstance(d["detail"], str):
                d["detail"] = json.loads(d["detail"])
            out.append(d)
        return out

    async def verify_audit_chain(self) -> dict:
        """Duyệt toàn bộ audit_log theo id, tính lại chuỗi băm. Trả {ok, rows, first_bad_id}."""
        prev, n = "", 0
        async with self.pool.acquire() as c, c.transaction():
            async for r in c.cursor("SELECT id, ts, actor_user_id, actor_label, action, target, ip, detail, prev_hash, hash FROM audit_log ORDER BY id"):
                detail = json.loads(r["detail"]) if isinstance(r["detail"], str) else r["detail"]
                want = self._chain(prev, r["ts"], r["actor_user_id"], r["actor_label"], r["action"], r["target"], r["ip"], detail)
                if r["prev_hash"] != prev or r["hash"] != want:
                    return {"ok": False, "rows": n, "first_bad_id": r["id"]}
                prev, n = r["hash"], n + 1
        return {"ok": True, "rows": n, "first_bad_id": None}
