#!/bin/sh
# e2e API client (giới hạn/thông báo/prefs/thiết bị/ticket + chéo A/B). CHẠY TRÊN VPS: sh /root/trading-system/services/client-ui/qa/e2e_client_api.sh
# Tạo 2 tài khoản THỬ (nhãn QA-E2E-XOA-DI) rồi LUÔN xoá khi xong. Không in mật khẩu.
SRC="$(cd "$(dirname "$0")" && pwd)"
UA=99900021; UB=99900022
mk() { docker exec -i tradingsys-auth python - create "$1" < "$SRC/auth_testacct.py"; }
rm_() { docker exec -i tradingsys-auth python - delete "$1" < "$SRC/auth_testacct.py" >/dev/null 2>&1; }
trap 'rm_ $UA; rm_ $UB' EXIT
rm_ $UA; rm_ $UB
JA=$(mk $UA); JB=$(mk $UB)
pw() { echo "$1" | python3 -c 'import sys,json;print(json.load(sys.stdin)["passcode"])'; }
PA=$(pw "$JA"); PB=$(pw "$JB")
docker run --rm --network host -v "$SRC:/qa:ro" -e BASE="${BASE:-http://127.0.0.1:8581}" -e A_USER=$UA -e B_USER=$UB -e A_PASS="$PA" -e B_PASS="$PB" python:3.12-slim python /qa/e2e_client_api.py
RC=$?
exit $RC
