# Chay trong container tradingsys-auth: tao tai khoan thu mt5:100000001 (nhan LAB, de xoa khi xong). In JSON secrets ra stdout.
import asyncio, json, sys
from auth.config import AuthSettings
from auth.store import Store
from auth.service import AuthService, Principal

async def main():
    cfg = AuthSettings(); store = await Store.connect(cfg.db_url); svc = AuthService(store, cfg)
    try:
        actor = Principal(user_id="00000000-0000-0000-0000-000000000000", role="master", login_key="master:lab-provision", display_name="lab", accounts=[])
        mode = sys.argv[1]
        if mode == "create":
            r = await svc.create_account(actor, "mt5", 100000001, "MetaQuotes-Demo", "LAB demo 100000001 (thu nghiem, xoa khi xong)", "lab MT5 demo; investor-only; KHONG mat khau", "127.0.0.1")
            print(json.dumps(r))
        elif mode == "create-feed":   # tai khoan EA market-feed mt5:100000001-feed (FEED_ALL_contract); stdout = secrets -> CHI redirect vao file 600 (umask 077), khong in ra man hinh
            r = await svc.create_account(actor, "mt5", 100000001, "MetaQuotes-Demo", "FEED market-feed 100000001 (investor, chi doc)", "EA market-feed read-only; khong mat khau", "127.0.0.1", suffix="feed")
            print(json.dumps(r, default=str))
        elif mode == "newcode":   # ma ghep cap moi cho account (stdout = secret -> chi redirect file 600)
            print(json.dumps(await svc.new_pairing_code(actor, sys.argv[2], "127.0.0.1"), default=str))
        elif mode == "activate":
            print(json.dumps(await svc.set_account_status(actor, sys.argv[2], False, "127.0.0.1"), default=str))
        elif mode == "delete":
            print(json.dumps(await svc.delete_account(actor, sys.argv[2], "127.0.0.1"), default=str))
    finally:
        await store.close()
asyncio.run(main())
