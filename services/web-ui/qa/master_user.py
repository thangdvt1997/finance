"""Tạo/xoá master THỬ cho QA giao diện (chạy TRONG container auth; mật khẩu ghi ra STDOUT -> host redirect vào file 0600, KHÔNG in ra log):
   docker exec -i tradingsys-auth python - create qa-ui-a < master_user.py > /tmp/qa-ui-a/pw.txt
   docker exec -i tradingsys-auth python - delete qa-ui-a < master_user.py
Không đụng master thật. Luôn xoá sau khi test."""
import asyncio
import secrets
import sys

from auth import security as sec
from auth.config import AuthSettings
from auth.store import Store


async def main(cmd: str, name: str) -> None:
    store = await Store.connect(AuthSettings().db_url)
    key = f"master:{name}"
    try:
        if cmd == "create":
            if await store.get_user_by_key(key):
                print("EXISTS", file=sys.stderr)
                raise SystemExit(3)
            pw = secrets.token_urlsafe(18)
            await store.create_user("master", key, f"QA {name}", await sec.ahash(pw), False)
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
                except Exception as e:  # nếu role không có quyền xoá: đình chỉ tài khoản
                    await c.execute("UPDATE portal_users SET status='suspended' WHERE user_id=$1", u["user_id"])
                    print(f"suspended ({type(e).__name__})")
    finally:
        await store.close()


asyncio.run(main(sys.argv[1], sys.argv[2]))
