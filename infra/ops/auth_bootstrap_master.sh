#!/usr/bin/env bash
# Tạo/khôi phục tài khoản MASTER (service auth). Mật khẩu NGẪU NHIÊN, ghi vào file chỉ root đọc; KHÔNG in ra màn hình/log.
#   bash infra/ops/auth_bootstrap_master.sh                 tạo master `admin` nếu CHƯA có master nào (đã có -> thoát 3, không đổi gì)
#   bash infra/ops/auth_bootstrap_master.sh --name ten      đặt tên master khác (a-z0-9._-)
#   bash infra/ops/auth_bootstrap_master.sh --reset         đặt lại mật khẩu ngẫu nhiên cho master (KHÔI PHỤC khi mất mật khẩu / thiết bị 2FA: tắt luôn TOTP + thu hồi mọi phiên)
# File mật khẩu: <SECRETS_DIR>/auth_master_<tên>.txt (0600). Đọc:  cat <SECRETS_DIR>/auth_master_admin.txt
# Lần đăng nhập đầu hệ thống BẮT BUỘC đổi mật khẩu (must_change_password). Sau khi đổi, file này không còn đúng -> nên xoá.
set -euo pipefail
NAME=admin; CMD=bootstrap-master
while [ $# -gt 0 ]; do
  case "$1" in
    --name) NAME="${2:?thiếu tên}"; shift 2;;
    --reset) CMD=reset-master; shift;;
    *) echo "đối số lạ: $1" >&2; exit 2;;
  esac
done
case "$NAME" in *[!a-z0-9._-]*|'') echo "tên master chỉ gồm a-z 0-9 . _ -" >&2; exit 2;; esac
DIR=<SECRETS_DIR>; OUT="$DIR/auth_master_$NAME.txt"
umask 077; mkdir -p "$DIR"; chmod 700 "$DIR"
TMP="$(mktemp "$DIR/.tmp.XXXXXX")"; trap 'rm -f "$TMP"' EXIT
set +e
docker exec -i tradingsys-auth python -m auth.cli "$CMD" --name "$NAME" > "$TMP" 2>"$TMP.err"
rc=$?
set -e
if [ $rc -eq 3 ]; then echo "đã có master — không thay đổi (dùng --reset nếu cần khôi phục)"; rm -f "$TMP.err"; exit 3; fi
if [ $rc -ne 0 ]; then echo "lỗi (mã $rc): $(head -c 300 "$TMP.err")" >&2; rm -f "$TMP.err"; exit $rc; fi
rm -f "$TMP.err"
PW="$(sed -n 's/^PASSWORD=//p' "$TMP" | head -1)"
[ -n "$PW" ] || { echo "không nhận được mật khẩu" >&2; exit 1; }
{ printf 'Dang nhap master (trang /auth/login hoac trang dang nhap cua web-ui)\n'
  printf 'loai tai khoan: master\nten dang nhap: %s\nmat khau: %s\n' "$NAME" "$PW"
  printf 'tao luc: %s UTC\nBat buoc doi mat khau o lan dang nhap dau. Sau khi doi, XOA file nay.\n' "$(date -u +%FT%TZ)"; } > "$OUT"
chmod 600 "$OUT"
echo "ok: mật khẩu master '$NAME' ghi vào $OUT (0600, root)"
