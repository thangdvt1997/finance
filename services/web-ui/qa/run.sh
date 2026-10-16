#!/bin/sh
# QA Terminal bằng Playwright trong container tạm qa-ui-a-* TRÊN VPS (không chạy trên laptop).
#   sh /root/trading-system/services/web-ui/qa/run.sh [terminal.mjs]    -> ảnh + results.json trong /tmp/qa-ui-a/out
set -e
SRC="$(cd "$(dirname "$0")" && pwd)"
W=/tmp/qa-ui-a
mkdir -p "$W" && chmod 700 "$W" && rm -rf "$W/out" && cp "$SRC"/*.mjs "$W"/
NAME=qa-ui-a
docker exec -i tradingsys-auth python - delete $NAME < "$SRC/master_user.py" >/dev/null 2>&1 || true
docker exec -i tradingsys-auth python - create $NAME < "$SRC/master_user.py" > "$W/pw.txt"
chmod 600 "$W/pw.txt"
SCRIPT="${1:-terminal.mjs}"
RC=0
timeout 420 docker run --rm --name "qa-ui-a-$$" --network host -v "$W:/work" -w /work -e BASE="${BASE:-http://127.0.0.1:8580}" -e OUT=out -e ONLY -e QA_USER=$NAME \
  mcr.microsoft.com/playwright:v1.49.0-jammy sh -c "[ -d node_modules/playwright ] || npm i --no-save --silent playwright@1.49.0; QA_PASS=\$(cat pw.txt) node $SCRIPT" || RC=$?
docker exec -i tradingsys-auth python - delete $NAME < "$SRC/master_user.py" || true
rm -f "$W/pw.txt"
[ -d "$W/out" ] && (cd "$W" && tar czf out.tgz out)
exit $RC
