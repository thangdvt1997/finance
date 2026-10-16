#!/bin/sh
# QA AI Trading trên VPS. Dùng: sh run_ai_trading.sh [master|client] [mock|real]  -> ảnh trong /tmp/qa-ui-a/out
set -e
ROLE="${1:-master}"; MODE="${2:-mock}"
SRC="$(cd "$(dirname "$0")" && pwd)"; W=/tmp/qa-ui-a; mkdir -p "$W"; chmod 700 "$W"; cp "$SRC"/*.mjs "$W"/
MOCKV=1; [ "$MODE" = real ] && MOCKV=0
if [ "$ROLE" = client ]; then
  LOGIN=99900079; T="$SRC/../../client-ui/qa/auth_testacct.py"; BASEU="${BASE:-http://127.0.0.1:8580}"
  docker exec -i tradingsys-auth python - delete $LOGIN < "$T" >/dev/null 2>&1 || true
  docker exec -i tradingsys-auth python - create $LOGIN < "$T" > "$W/client.json"
  PASS=$(python3 -c "import json;print(json.load(open('$W/client.json'))['passcode'])"); QU=$LOGIN
else
  QU=qa-ui-a; BASEU="${BASE:-http://127.0.0.1:8580}"
  docker exec -i tradingsys-auth python - delete $QU < "$SRC/master_user.py" >/dev/null 2>&1 || true
  docker exec -i tradingsys-auth python - create $QU < "$SRC/master_user.py" > "$W/pw.txt"; PASS=$(cat "$W/pw.txt")
fi
RC=0
timeout 300 docker run --rm --name "qa-ai-$$" --network host -v "$W:/work" -w /work -e BASE="$BASEU" -e OUT=out -e ROLE="$ROLE" -e MOCK=$MOCKV -e QA_USER=$QU -e QA_PASS="$PASS" \
  mcr.microsoft.com/playwright:v1.49.0-jammy sh -c "[ -d node_modules/playwright ] || npm i --no-save --silent playwright@1.49.0; node ai_trading.mjs" || RC=$?
if [ "$ROLE" = client ]; then docker exec -i tradingsys-auth python - delete $LOGIN < "$T" || true; else docker exec -i tradingsys-auth python - delete $QU < "$SRC/master_user.py" || true; fi
rm -f "$W/client.json" "$W/pw.txt"
exit $RC
