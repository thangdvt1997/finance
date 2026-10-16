#!/bin/sh
# QA biểu đồ trong MÔI TRƯỜNG CÔ LẬP (không đụng container web-ui đang chạy của stack, không cần đăng nhập):
#   build SPA từ mã đã đồng bộ -> nginx tạm qa-ui-b-web (CSP y hệt web-ui, /api -> api-gateway kèm API key chỉ nằm trong file 0600) -> Playwright dùng chung netns.
#   sh /root/trading-system/services/web-ui/qa/run-b-iso.sh [chart.mjs]     kết quả: /tmp/qa-ui-b/out (+ out.tgz). Dọn: container + file cấu hình.
set -e
SRC="$(cd "$(dirname "$0")" && pwd)"
W=/tmp/qa-ui-b
mkdir -p "$W/site" && chmod 700 "$W" && rm -rf "$W/out" && cp "$SRC"/chart*.mjs "$W"/
sh /root/qa-ui-b/build.sh 4 >/dev/null
rm -rf "$W/site/dist" && cp -r /tmp/qa-ui-b-build/dist "$W/site/dist"
KEY=$(grep '^API_TOKEN=' /root/trading-system/infra/.env | head -1 | cut -d= -f2-)
CSP=$(grep 'Content-Security-Policy' "$SRC/../nginx/security-headers.conf" | head -1)
umask 077
cat > "$W/site/default.conf" <<CONF
server {
  listen 8080;
  root /usr/share/nginx/html;
  index index.html;
  $CSP
  add_header Cross-Origin-Resource-Policy "same-origin" always;
  location /api/ {
    proxy_pass http://api-gateway:8000/;
    proxy_set_header X-API-Key "$KEY";
    proxy_set_header Host \$http_host;
    proxy_http_version 1.1;
    proxy_set_header Upgrade \$http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_read_timeout 120s;
  }
  location / { try_files \$uri \$uri/ /index.html; }
}
CONF
chmod 644 "$W/site/default.conf"   # nginx (uid 101) cần đọc; tệp bị xoá ngay sau khi chạy
docker rm -f qa-ui-b-web >/dev/null 2>&1 || true
docker run -d --name qa-ui-b-web --network tradingsys_backend --memory 256m \
  -v "$W/site/dist:/usr/share/nginx/html:ro" -v "$W/site/default.conf:/etc/nginx/conf.d/default.conf:ro" \
  nginxinc/nginx-unprivileged:stable-alpine >/dev/null
sleep 2
docker ps --filter name=qa-ui-b-web --format '{{.Status}}' | grep -q Up || { docker logs qa-ui-b-web 2>&1 | tail -5; exit 1; }
SCRIPT="${1:-chart.mjs}"
RC=0
timeout 1200 docker run --rm --name "qa-ui-b-$$" --network container:qa-ui-b-web -v "$W:/work" -w /work -e BASE=http://127.0.0.1:8080 -e OUT=out -e ONLY -e QA_USER= \
  mcr.microsoft.com/playwright:v1.49.0-jammy sh -c "[ -d node_modules/playwright ] || npm i --no-save --silent playwright@1.49.0; node $SCRIPT" || RC=$?
docker rm -f qa-ui-b-web >/dev/null 2>&1 || true
rm -f "$W/site/default.conf"
[ -d "$W/out" ] && (cd "$W" && tar czf out.tgz out)
exit $RC
