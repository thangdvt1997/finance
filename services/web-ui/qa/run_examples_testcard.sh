#!/bin/sh
# Build harness (vite, docker node) + chụp ảnh bằng playwright. Ảnh: /tmp/qa-xt-<pid>/out (thư mục do root docker tạo, dọn bằng docker)
set -e
SRC="$(cd "$(dirname "$0")/.." && pwd)"; W=/tmp/qa-xt-$$; mkdir -p "$W/out"
tar --exclude=node_modules --exclude=dist -C "$SRC" -cf - app qa/xt-harness | tar -C "$W" -xf -
cp "$SRC/qa/examples_testcard.mjs" "$W/"; cp -r "$W/qa/xt-harness" "$W/app/xt-harness"; sed -i "s#../../app/src#../src#g" "$W/app/xt-harness/main.jsx"
docker run --rm -v "$W:/w" -w /w/app node:22-alpine sh -c "npm ci --no-audit --no-fund >/dev/null 2>&1 && npx vite build /w/app/xt-harness --config /w/app/vite.config.js --outDir /w/h --base ./ --emptyOutDir 2>&1 | tail -4"
timeout 500 docker run --rm --network host -v "$W:/work" -w /work -e OUT=out -e BASE=http://127.0.0.1:4173 \
  mcr.microsoft.com/playwright:v1.49.0-jammy sh -c "npm i --no-save --silent playwright@1.49.0 && (python3 -m http.server 4173 -d /work/h >/dev/null 2>&1 &) && sleep 1 && node examples_testcard.mjs"
