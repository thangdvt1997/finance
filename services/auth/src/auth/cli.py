"""CLI quản trị chạy TRONG container auth (qua `docker compose exec -T auth python -m auth.cli ...`), dùng cho bootstrap/khôi phục master.
Mật khẩu sinh ngẫu nhiên chỉ in ra STDOUT dạng `PASSWORD=<...>` để script host (infra/ops/auth_bootstrap_master.sh) ghi vào file 0600 của root;
KHÔNG ghi vào log container/ứng dụng. Không bao giờ nhận mật khẩu qua đối số dòng lệnh (lộ trong ps/history).

  bootstrap-master [--name admin]   tạo master đầu tiên nếu CHƯA có master nào (mã thoát 3 nếu đã có)
  reset-master --name admin         đặt mật khẩu ngẫu nhiên mới (+ tắt TOTP, thu hồi phiên) — khôi phục khi mất mật khẩu/thiết bị 2FA
  verify-audit                      kiểm tra chuỗi băm audit_log
"""
from __future__ import annotations

import argparse
import asyncio
import secrets
import sys

from .config import AuthSettings
from .service import AuthError, AuthService
from .store import Store


def gen_password() -> str:
    return secrets.token_urlsafe(18)      # 24 ký tự, ~144 bit


async def run(args) -> int:
    cfg = AuthSettings()
    if not cfg.db_url:
        print("AUTH_DB_URL chưa đặt", file=sys.stderr)
        return 2
    store = await Store.connect(cfg.db_url)
    svc = AuthService(store, cfg)
    try:
        if args.cmd == "bootstrap-master":
            if await store.count_masters() > 0:
                print("EXISTS", file=sys.stderr)
                return 3
            pw = gen_password()
            await svc.create_master(args.name, pw, args.name)
            print(f"PASSWORD={pw}")
            return 0
        if args.cmd == "reset-master":
            pw = gen_password()
            await svc.reset_master(args.name, pw)
            print(f"PASSWORD={pw}")
            return 0
        if args.cmd == "verify-audit":
            r = await store.verify_audit_chain()
            print(r)
            return 0 if r["ok"] else 1
    except AuthError as e:
        print(f"lỗi: {e.message}", file=sys.stderr)
        return 1
    finally:
        await store.close()
    return 2


def main() -> None:
    ap = argparse.ArgumentParser(prog="auth.cli")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for c in ("bootstrap-master", "reset-master"):
        p = sub.add_parser(c)
        p.add_argument("--name", default="admin")
    sub.add_parser("verify-audit")
    sys.exit(asyncio.run(run(ap.parse_args())))


if __name__ == "__main__":
    main()
