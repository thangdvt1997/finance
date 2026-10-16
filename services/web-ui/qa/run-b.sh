#!/bin/sh
# QA biểu đồ chuyên nghiệp (agent B) bằng Playwright trong container tạm qa-ui-b-* TRÊN VPS (không chạy trên laptop).
#   sh /root/trading-system/services/web-ui/qa/run-b.sh [chart.mjs]   -> ảnh + results.json trong /tmp/qa-ui-b/out (+ out.tgz)
# Tạo master THỬ qa-ui-b (mật khẩu ngẫu nhiên chỉ nằm trong file 0600, không in ra) và XOÁ sau khi chạy.
set -e
SRC="$(cd "$(dirname "$0")" && pwd)"
W=/tmp/qa-ui-b
mkdir -p "$W" && chmod 700 "$W" && rm -rf "$W/out" && cp "$SRC"/chart*.mjs "$W"/
NAME=qa-ui-b
docker exec -i tradingsys-auth python - delete $NAME < "$SRC/master_user.py" >/dev/null 2>&1 || true
docker exec -i tradingsys-auth python - create $NAME < "$SRC/master_user.py" > "$W/pw.txt"
chmod 600 "$W/pw.txt"
SCRIPT="${1:-chart.mjs}"
RC=0
timeout 900 docker run --rm --name "qa-ui-b-$$" --network host -v "$W:/work" -w /work -e BASE="${BASE:-http://127.0.0.1:8580}" -e OUT=out -e ONLY -e QA_USER=$NAME \
  mcr.microsoft.com/playwright:v1.49.0-jammy sh -c "[ -d node_modules/playwright ] || npm i --no-save --silent playwright@1.49.0; QA_PASS=\$(cat pw.txt) node $SCRIPT" || RC=$?
docker exec -i tradingsys-auth python - delete $NAME < "$SRC/master_user.py" || true
rm -f "$W/pw.txt"
[ -d "$W/out" ] && (cd "$W" && tar czf out.tgz out)
exit $RC
