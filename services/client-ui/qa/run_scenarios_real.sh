#!/bin/sh
# QA trang Kịch bản với API thật: tạo tài khoản MT thử (auth_testacct.py), chạy scenarios_real.mjs, LUÔN xoá tài khoản. Chạy TRÊN VPS.
# Dùng: QA_W=<thư mục tạm> sh qa/run_scenarios_real.sh
set -e
SRC="$(cd "$(dirname "$0")" && pwd)"
W=${QA_W:-/tmp/qa-client-scr}; mkdir -p "$W"; chmod 700 "$W"; cp "$SRC"/scenarios_real.mjs "$W"/
LOGIN=99900078
docker exec -i tradingsys-auth python - delete $LOGIN < "$SRC/auth_testacct.py" >/dev/null 2>&1 || true
docker exec -i tradingsys-auth python - create $LOGIN < "$SRC/auth_testacct.py" > "$W/acct.json"
PASS=$(python3 -c "import json;print(json.load(open('$W/acct.json'))['passcode'])")
rm -f "$W/acct.json"
RC=0
timeout 400 docker run --rm --name "qa-client-scr-$$" --network host -v "$W:/work" -w /work -e BASE -e OUT=out -e QA_USER=$LOGIN -e QA_PASS="$PASS" \
  mcr.microsoft.com/playwright:v1.49.0-jammy sh -c "[ -d node_modules/playwright ] || npm i --no-save --silent playwright@1.49.0; node scenarios_real.mjs" || RC=$?
docker exec -i tradingsys-auth python - delete $LOGIN < "$SRC/auth_testacct.py" >/dev/null || true
exit $RC
