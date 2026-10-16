#!/bin/sh
# QA biểu đồ chuyên nghiệp (agent B) bằng Playwright trong container tạm qa_stab_d2-* TRÊN VPS (không chạy trên laptop).
#   sh tests/qa/d2_run.sh [script]
# Tạo master THỬ qa_stab_d2 (mật khẩu ngẫu nhiên chỉ nằm trong file 0600, không in ra) và XOÁ sau khi chạy.
set -e
SRC="$(cd "$(dirname "$0")" && pwd)"; MU=/root/trading-system/services/web-ui/qa/master_user.py
W=/tmp/qa_stab_d2
mkdir -p "$W" && chmod 700 "$W" && docker run --rm -v "$W:/w" alpine rm -rf /w/out; rm -rf "$W/out" && cp "$SRC"/d2_*.mjs /root/trading-system/services/web-ui/qa/chart*.mjs /root/trading-system/services/web-ui/qa/terminal.mjs "$W"/
NAME=qa_stab_d2
docker exec -i tradingsys-auth python - delete $NAME < "$MU" >/dev/null 2>&1 || true
docker exec -i tradingsys-auth python - create $NAME < "$MU" > "$W/pw.txt"
chmod 600 "$W/pw.txt"
SCRIPT="${1:-d2_matrix.mjs}"
RC=0
timeout 900 docker run --rm --name "qa_stab_d2-$$" --network host -v "$W:/work" -w /work -e BASE="${BASE:-http://127.0.0.1:8580}" -e OUT=out -e ONLY -e QA_USER=$NAME \
  mcr.microsoft.com/playwright:v1.49.0-jammy sh -c "[ -d node_modules/playwright ] || npm i --no-save --silent playwright@1.49.0; QA_PASS=\$(cat pw.txt) node $SCRIPT" || RC=$?
docker exec -i tradingsys-auth python - delete $NAME < "$MU" || true
rm -f "$W/pw.txt"
[ -d "$W/out" ] && (cd "$W" && tar czf out.tgz out)
exit $RC
