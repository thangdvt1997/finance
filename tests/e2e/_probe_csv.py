import asyncio, re, secrets, subprocess, sys
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--disable-pip-version-check", "argon2-cffi"], capture_output=True, check=False)
import httpx
from argon2 import PasswordHasher
from qalib import Ctx
WEB = "http://web-ui:8080"
async def main():
    async with Ctx() as c, httpx.AsyncClient(timeout=30) as h:
        RUN = secrets.token_hex(3); PW = "Qa-" + secrets.token_urlsafe(12)
        await c.db.execute("insert into portal_users (role, login_key, display_name, password_hash, must_change_password) values ('master',$1,'qa',$2,false)", f"master:qa-{RUN}", PasswordHasher().hash(PW))
        try:
            r = await h.post(f"{WEB}/auth/login", json={"platform": "master", "login": f"qa-{RUN}", "secret": PW}, headers={"Origin": "http://web-ui:8080", "X-Real-IP": "10.94.0.5"})
            sid = re.search(r"ts_session=([^;]+)", r.headers.get("set-cookie", "")).group(1)
            for n in (100_000, 250_000):
                r = await h.post(f"{WEB}/auth/admin/import/preview", json={"csv": "x" * n}, headers={"Origin": "http://web-ui:8080", "Cookie": f"ts_session={sid}"})
                print("PROBE", n, r.status_code, r.text[:100].replace("\n", " "))
                await asyncio.sleep(1.2)
        finally:
            await c.db.execute("delete from portal_users where login_key=$1", f"master:qa-{RUN}")
asyncio.run(main())
