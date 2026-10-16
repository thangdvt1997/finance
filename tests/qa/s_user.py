"""Tao/xoa tai khoan nhan vien THU cho cong chat luong (chay TRONG container auth; mat khau ra STDOUT -> host ghi file 0600).
   docker exec -i tradingsys-auth python - create qa_stab_s_m master < s_user.py
   docker exec -i tradingsys-auth python - delete qa_stab_s_m < s_user.py
Chi nhan role master|expert|support|analyst. Khong dung master that. Luon xoa sau khi test."""
import asyncio
import secrets
import sys

from auth import security as sec
from auth.config import AuthSettings
from auth.store import Store


async def main(cmd: str, name: str, role: str) -> None:
    if not name.startswith("qa_stab_"):
        raise SystemExit("ten phai bat dau qa_stab_")
    store = await Store.connect(AuthSettings().db_url)
    key = f"master:{name}"
    try:
        if cmd == "create":
            if await store.get_user_by_key(key):
                print("EXISTS", file=sys.stderr)
                raise SystemExit(3)
            pw = secrets.token_urlsafe(18)
            await store.create_user(role, key, f"QA {name}", await sec.ahash(pw), False)
            print(pw)
        elif cmd == "delete":
            u = await store.get_user_by_key(key)
            if not u:
                print("none")
                return
            async with store.pool.acquire() as c:
                await c.execute("DELETE FROM portal_sessions WHERE user_id=$1", u["user_id"])
                try:
                    await c.execute("DELETE FROM portal_users WHERE user_id=$1", u["user_id"])
                    print("deleted")
                except Exception as e:
                    await c.execute("UPDATE portal_users SET status='suspended' WHERE user_id=$1", u["user_id"])
                    print(f"suspended ({type(e).__name__})")
    finally:
        await store.close()


asyncio.run(main(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "master"))
