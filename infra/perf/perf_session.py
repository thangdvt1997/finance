"""Tạo/xoá phiên QA master cho benchmark (chạy trong container qa trên VPS: sh /root/qa-e2e/run_remote.sh perf_session.py setup|cleanup).
setup  : tạo portal_users master `master:perf-<run>` (must_change_password=false) + đăng nhập qua auth -> ghi cookie vào $QA_OUT/perf.cookie (0600).
cleanup: xoá mọi user `master:perf-%` (cascade phiên). Không in bí mật."""
import asyncio
import os
import re
import secrets
import subprocess
import sys

subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--disable-pip-version-check", "argon2-cffi"], capture_output=True, check=False)
import asyncpg  # noqa: E402
import httpx  # noqa: E402
from argon2 import PasswordHasher  # noqa: E402
from qalib import DSN, OUT  # noqa: E402

AUTH = os.getenv("QA_AUTH", "http://auth:8000")


async def main(cmd: str) -> int:
    db = await asyncpg.connect(DSN)
    try:
        if cmd == "cleanup":
            n = await db.execute("delete from portal_users where login_key like 'master:perf-%'")
            print("cleanup", n)
            if os.path.exists(f"{OUT}/perf.cookie"):
                os.remove(f"{OUT}/perf.cookie")
            return 0
        run = secrets.token_hex(3)
        pw = "Perf-" + secrets.token_urlsafe(14)
        await db.execute("insert into portal_users (role, login_key, display_name, password_hash, must_change_password) values ('master',$1,'perf',$2,false)",
                         f"master:perf-{run}", PasswordHasher().hash(pw))
        async with httpx.AsyncClient(timeout=20) as h:
            r = await h.post(f"{AUTH}/auth/login", json={"platform": "master", "login": f"perf-{run}", "secret": pw}, headers={"X-Real-IP": "10.98.0.1"})
        m = re.search(r"ts_session=([^;]+)", r.headers.get("set-cookie", ""))
        if r.status_code != 200 or not m:
            print("login lỗi", r.status_code, r.text[:200])
            return 1
        with open(f"{OUT}/perf.cookie", "w") as fh:
            fh.write("ts_session=" + m.group(1))
        os.chmod(f"{OUT}/perf.cookie", 0o600)
        print("ok session created")
        return 0
    finally:
        await db.close()


sys.exit(asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "setup")))
