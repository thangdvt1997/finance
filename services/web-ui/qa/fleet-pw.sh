#!/bin/sh
# QA trực quan trang quản trị đội tài khoản: container Playwright tạm trên VPS (không chạy ở laptop).
#   sh /root/trading-system/services/web-ui/qa/fleet-pw.sh <tên-kịch-bản.mjs> <tag>      ví dụ:  sh .../fleet-pw.sh fleet-rules.mjs rules
# Tạo master thử `qa-fleet-<tag>` (qua DB), chạy kịch bản với QA_USER/QA_PASS, thu ảnh vào /tmp/qa-fleet-<tag>/out (+ out.tgz), rồi XOÁ master thử.
# Mặc định chạy trên web-ui đang chạy (http://127.0.0.1:8580): cần đã deploy bản mới (deploy.sh "up -d --build --no-deps web-ui").
set -e
SRC="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="${1:?cần tên kịch bản .mjs trong qa/}"; TAG="${2:-x}"
NAME="qa-fleet-$TAG"; W="/tmp/$NAME"
mkdir -p "$W" && chmod 700 "$W" && rm -rf "$W/out" && cp "$SRC"/*.mjs "$W"/
docker exec -i tradingsys-auth python - delete $NAME < "$SRC/master_user.py" >/dev/null 2>&1 || true
docker exec -i tradingsys-auth python - create $NAME < "$SRC/master_user.py" > "$W/pw.txt"
chmod 600 "$W/pw.txt"
RC=0
timeout 600 docker run --rm --name "$NAME-pw" --network host -v "$W:/work" -w /work -e BASE="${BASE:-http://127.0.0.1:8580}" -e OUT=out -e ONLY -e QA_USER=$NAME \
  mcr.microsoft.com/playwright:v1.49.0-jammy sh -c "[ -d node_modules/playwright ] || npm i --no-save --silent playwright@1.49.0; QA_PASS=\$(cat pw.txt) node $SCRIPT" || RC=$?
docker exec -i tradingsys-auth python - delete $NAME < "$SRC/master_user.py" || true
rm -f "$W/pw.txt"
[ -d "$W/out" ] && (cd "$W" && tar czf out.tgz out)
exit $RC
