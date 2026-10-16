#!/bin/sh
# QA vai trò client (tạo tài khoản MT thử bằng services/client-ui/qa/auth_testacct.py, luôn xoá sau khi chạy). Chạy TRÊN VPS.
set -e
SRC="$(cd "$(dirname "$0")" && pwd)"
W=/tmp/qa-ui-a; mkdir -p "$W"; chmod 700 "$W"; cp "$SRC"/*.mjs "$W"/
LOGIN=99900077
T="$SRC/../../client-ui/qa/auth_testacct.py"
docker exec -i tradingsys-auth python - delete $LOGIN < "$T" >/dev/null 2>&1 || true
docker exec -i tradingsys-auth python - create $LOGIN < "$T" > "$W/client.json"
PASS=$(python3 -c "import json;print(json.load(open('$W/client.json'))['passcode'])")
RC=0
timeout 200 docker run --rm --name "qa-ui-a-role-$$" --network host -v "$W:/work" -w /work -e BASE="${BASE:-http://127.0.0.1:8580}" -e OUT=out -e QA_USER=$LOGIN -e QA_PASS="$PASS" \
  mcr.microsoft.com/playwright:v1.49.0-jammy sh -c "[ -d node_modules/playwright ] || npm i --no-save --silent playwright@1.49.0; node role.mjs" || RC=$?
docker exec -i tradingsys-auth python - delete $LOGIN < "$T" || true
rm -f "$W/client.json"
exit $RC
