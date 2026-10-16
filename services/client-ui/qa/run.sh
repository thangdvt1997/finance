#!/bin/sh
# Chạy kiểm thử Playwright trong container tạm qa-client-* TRÊN VPS (không chạy trên laptop).
# Dùng (trên VPS):  sh /root/trading-system/services/client-ui/qa/run.sh [shots.mjs|e2e.mjs]   (biến môi trường BASE, ONLY, THEMES... truyền qua)
# Kết quả: /tmp/qa-client/out  (+ /tmp/qa-client/out.tgz)
set -e
SRC="$(cd "$(dirname "$0")" && pwd)"
W=${QA_W:-/tmp/qa-client}
mkdir -p "$W" && rm -rf "$W/out" && cp "$SRC"/*.mjs "$W"/
SCRIPT="${1:-shots.mjs}"
docker run --rm --name "qa-client-$$" --network host -v "$W:/work" -w /work \
  -e BASE -e ONLY -e THEMES -e OUT=out -e QA_USER -e QA_PASS -e QA_PLATFORM -e QA_PAIR -e MASTER_USER -e MASTER_PASS \
  mcr.microsoft.com/playwright:v1.49.0-jammy sh -c "[ -d node_modules/playwright ] || npm i --no-save --silent playwright@1.49.0; node $SCRIPT" || RC=$?
[ -d "$W/out" ] && (cd "$W" && tar czf out.tgz out)
exit ${RC:-0}
