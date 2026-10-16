#!/bin/sh
# QA màn Phương pháp (master, mock). Dùng: sh run_ai_methods.sh  -> ảnh trong /tmp/qa-ui-meth/out
set -e
SRC="$(cd "$(dirname "$0")" && pwd)"; W=/tmp/qa-ui-meth; mkdir -p "$W"; chmod 700 "$W"; cp "$SRC"/ai_methods.mjs "$W"/
QU=qa-ui-meth; BASEU="${BASE:-http://127.0.0.1:8580}"
docker exec -i tradingsys-auth python - delete $QU < "$SRC/master_user.py" >/dev/null 2>&1 || true
docker exec -i tradingsys-auth python - create $QU < "$SRC/master_user.py" > "$W/pw.txt"; PASS=$(cat "$W/pw.txt")
RC=0
timeout 560 docker run --rm --name "qa-meth-$$" --network host -v "$W:/work" -w /work -e BASE="$BASEU" -e OUT=out -e SIZES="${SIZES:-}" -e SHOT="${SHOT:-1}" -e QA_USER=$QU -e QA_PASS="$PASS" \
  mcr.microsoft.com/playwright:v1.49.0-jammy sh -c "[ -d node_modules/axe-core ] && [ -d node_modules/playwright ] || npm i --no-save --silent playwright@1.49.0 axe-core@4.10.2; node ai_methods.mjs" || RC=$?
docker exec -i tradingsys-auth python - delete $QU < "$SRC/master_user.py" || true
rm -f "$W/pw.txt"
exit $RC
