#!/bin/sh
# QA cuoi: tao tai khoan thu, chay final.mjs trong container Playwright tam, XOA tai khoan thu.
#   sh final.sh master|client <tag>     (env: VPS THEMES LANGS ONLY SHOTS) -> /tmp/qa-final-<tag>/out
set -e
SRC="$(cd "$(dirname "$0")" && pwd)"; APP="${1:?master|client}"; TAG="${2:-x}"
W=/tmp/qa-final-$TAG; mkdir -p $W && chmod 700 $W && rm -rf $W/out && cp "$SRC/final.mjs" $W/
if [ "$APP" = master ]; then
  NAME=qa-final-$TAG
  docker exec -i tradingsys-auth python - delete $NAME < "$SRC/master_user.py" >/dev/null 2>&1 || true
  docker exec -i tradingsys-auth python - create $NAME < "$SRC/master_user.py" > $W/pw.txt
  CLEAN() { docker exec -i tradingsys-auth python - delete $NAME < "$SRC/master_user.py" || true; }
  PORT=8580; U=$NAME
else
  U=$(echo "9990${TAG}" | tr -cd 0-9 | cut -c1-9)
  CA="$SRC/../../client-ui/qa/auth_testacct.py"
  docker exec -i tradingsys-auth python - delete $U < $CA >/dev/null 2>&1 || true
  docker exec -i tradingsys-auth python - create $U < $CA | python3 -c 'import sys,json;print(json.load(sys.stdin)["passcode"])' > $W/pw.txt
  CLEAN() { docker exec -i tradingsys-auth python - delete $U < $CA >/dev/null 2>&1 || true; }
  PORT=8581
fi
chmod 600 $W/pw.txt
trap CLEAN EXIT
timeout ${TMO:-3000} docker run --rm --name "qa-final-$TAG-pw" --network host -v "$W:/work" -w /work -e APP=$APP -e BASE=http://127.0.0.1:$PORT -e OUT=out -e TAG=$TAG -e VPS -e THEMES -e LANGS -e ONLY -e SHOTS -e QA_USER=$U \
  mcr.microsoft.com/playwright:v1.49.0-jammy sh -c "[ -d node_modules/playwright ] || npm i --no-save --silent playwright@1.49.0 axe-core@4.10.2; QA_PASS=\$(cat pw.txt) node final.mjs"
rm -f $W/pw.txt
