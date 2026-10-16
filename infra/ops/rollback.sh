#!/bin/sh
# Rollback tradingsys về release trước (hoặc VER chỉ định). Chạy trên VPS:
#   sh infra/ops/rollback.sh              -> về release ngay trước (trường "previous" của .release)
#   sh infra/ops/rollback.sh VER          -> về VER (xem: release.sh list)
#   SERVICES="api-gateway web-ui" sh infra/ops/rollback.sh   -> chỉ recreate các service này (khuyến nghị; mặc định: không recreate gì, chỉ in lệnh)
# Việc làm: (1) giải nén tarball VER đè lên /root/trading-system (file mới thêm sau đó KHÔNG bị xoá), (2) retag image rel-VER -> latest
# (3) `up -d --no-build --no-deps` cho SERVICES. Chỉ động vào project tradingsys.
set -eu
# tự copy sang /tmp để tar không ghi đè script đang chạy
if [ -z "${_TS_RB:-}" ]; then _RBT=$(mktemp /tmp/ts-rollback.XXXXXX) && cp "$0" "$_RBT" && _TS_RB=1 exec sh "$_RBT" "$@"; fi
ROOT="${TS_ROOT:-/root/trading-system}"
REL_DIR="${REL_DIR:-/root/trading-system-releases}"
CURV=$(sed -n 's/^version=//p' "$ROOT/.release" 2>/dev/null | head -1)
TARGET="${1:-$(sed -n 's/^previous=//p' "$ROOT/.release" | head -1)}"
[ -n "$TARGET" ] && [ "$TARGET" != none ] || { echo "không có release trước" >&2; exit 1; }
[ -f "$REL_DIR/ts-$TARGET.tgz" ] || { echo "thiếu $REL_DIR/ts-$TARGET.tgz (có: $(ls $REL_DIR | tr '\n' ' '))" >&2; exit 1; }
echo "rollback $CURV -> $TARGET"
cd "$ROOT" && tar xzf "$REL_DIR/ts-$TARGET.tgz"
for img in $(docker images --format '{{.Repository}}' | grep '^tradingsys-' | sort -u); do
  if docker image inspect "$img:rel-$TARGET" >/dev/null 2>&1; then docker tag "$img:rel-$TARGET" "$img:latest"; echo "retag $img:rel-$TARGET -> latest"; fi
done
printf 'version=%s\nhash=rollback\ndeployed_at=%s\nprevious=%s\nnote=rollback from %s\ndeployer=%s\n' \
  "$TARGET" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$CURV" "$CURV" "${SUDO_USER:-root}" > "$ROOT/.release"
if [ -n "${SERVICES:-}" ]; then
  cd "$ROOT/infra" && docker compose -p tradingsys --env-file .env up -d --no-build --no-deps $SERVICES
else
  echo "Mã/image đã khôi phục. Áp dụng: SERVICES='<svc...>' sh infra/ops/rollback.sh $TARGET   hoặc  cd infra && docker compose -p tradingsys --env-file .env up -d --no-build --no-deps <svc>"
fi
