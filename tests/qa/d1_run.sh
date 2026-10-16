#!/bin/sh
# D1: chạy kịch bản d1_*.mjs (mặc định d1_pages.mjs) với master thử qa_stab_d1 (tự tạo, tự xoá). Ảnh lỗi: /tmp/qa-d1/out
set -e
SRC="$(cd "$(dirname "$0")" && pwd)"; MU="$SRC/../../services/web-ui/qa/master_user.py"
NAME=qa-stab-d1; W=/tmp/qa-d1
mkdir -p "$W" && chmod 700 "$W" && cp "$SRC"/d1_*.mjs "$W"/
docker exec -i tradingsys-auth python - delete $NAME < "$MU" >/dev/null 2>&1 || true
docker exec -i tradingsys-auth python - create $NAME < "$MU" > "$W/pw.txt"; chmod 600 "$W/pw.txt"
flock -w 900 /tmp/tradingsys-deploy.lock true || true   # đợi deploy khác xong (tránh nhiễu 502/chunk 500)
RC=0
timeout 1800 docker run --rm --name "$NAME-pw" --network host -v "$W:/work" -w /work -e BASE="${BASE:-http://127.0.0.1:8580}" -e OUT=out-$$ -e ONLY -e RES -e COMBO -e QA_USER=$NAME \
  mcr.microsoft.com/playwright:v1.49.0-jammy sh -c "[ -d node_modules/playwright ] || npm i --no-save --silent playwright@1.49.0; QA_PASS=\$(cat pw.txt) node ${1:-d1_pages.mjs}" || RC=$?
docker exec -i tradingsys-auth python - delete $NAME < "$MU" || true
rm -f "$W/pw.txt"; docker run --rm -v "$W:/w" alpine chown -R $(id -u):$(id -g) /w/out-$$ 2>/dev/null || true
exit $RC
