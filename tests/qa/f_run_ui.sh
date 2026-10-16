#!/bin/sh
# Chay QA giao dien AI Training Class tren backend that. Dung: sh tests/qa/f_run_ui.sh [master|expert] [width] ; anh -> /tmp/qa-ui-f/out
ROLE="${1:-master}"; WID="${2:-1440}"
SRC="$(cd "$(dirname "$0")" && pwd)"; W=/tmp/qa-ui-f; mkdir -p "$W"; chmod 700 "$W"; cp "$SRC"/f_classroom_ui.mjs "$W"/
QU="qa_stab_f_$ROLE"; BASEU="${BASE:-http://127.0.0.1:8580}"
docker exec -i tradingsys-auth python - delete $QU < "$SRC/s_user.py" >/dev/null 2>&1 || true
docker exec -i tradingsys-auth python - create $QU $ROLE < "$SRC/s_user.py" > "$W/pw.txt" || exit 3
PASS=$(cat "$W/pw.txt"); RC=0
timeout 1500 docker run --rm --name "qa-f-$$" --network host -v "$W:/work" -w /work -e BASE="$BASEU" -e OUT=out -e ROLE="$ROLE" -e W="$WID" -e H="${H:-950}" -e QA_USER=$QU -e QA_PASS="$PASS" \
  mcr.microsoft.com/playwright:v1.49.0-jammy sh -c "[ -d node_modules/playwright ] || npm i --no-save --silent playwright@1.49.0; node f_classroom_ui.mjs" || RC=$?
docker exec -i tradingsys-auth python - delete $QU < "$SRC/s_user.py" || true
rm -f "$W/pw.txt"; exit $RC
