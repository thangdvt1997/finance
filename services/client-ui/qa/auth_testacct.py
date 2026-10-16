"""Tạo/xoá tài khoản THỬ cho e2e client-ui (chạy TRONG container auth):
   docker exec -i tradingsys-auth python - create 99900001 < auth_testacct.py     -> in JSON {account_id, passcode, pairing_code}
   docker exec -i tradingsys-auth python - delete 99900001 < auth_testacct.py
Tài khoản gắn nhãn 'QA-E2E-XOA-DI' để dễ nhận biết; luôn xoá sau khi test (delete)."""
import asyncio
import json
import sys

from auth.config import AuthSettings
from auth.service import AuthService, Principal
from auth.store import Store


async def main(cmd: str, login: int) -> None:
    cfg = AuthSettings()
    store = await Store.connect(cfg.db_url)
    svc = AuthService(store, cfg)
    try:
        m = None
        for key in ("master:admin",):
            m = await store.get_user_by_key(key)
        if not m:
            print(json.dumps({"error": "không tìm thấy master:admin để làm actor audit"}))
            return
        actor = Principal(str(m["user_id"]), "master", m["login_key"], m["display_name"], ["*"], False, False, "", None)
        if cmd == "create":
            r = await svc.create_account(actor, "mt5", login, "QA-Test", "QA-E2E-XOA-DI", "tạo bởi qa/auth_testacct.py, xoá sau test", "127.0.0.1")
            print(json.dumps({"account_id": r["account"]["account_id"], "passcode": r["secrets"]["passcode"], "pairing_code": r["secrets"]["pairing_code"]}))
        elif cmd == "pairing":
            r = await svc.new_pairing_code(actor, f"mt5:{login}", "127.0.0.1")
            print(json.dumps(r))
        elif cmd == "delete":
            print(json.dumps(await svc.delete_account(actor, f"mt5:{login}", "127.0.0.1"), default=str))
    finally:
        await store.close()


asyncio.run(main(sys.argv[1], int(sys.argv[2])))
