#!/bin/bash
# Đồng bộ repo lên VPS <VPS_IP>, GHI PHIÊN BẢN RELEASE, rồi (tuỳ chọn) chạy lệnh compose.
# Dùng: ./deploy.sh "up -d --build mt-bridge"      (đối số rỗng = chỉ đồng bộ + ghi release)
# Mỗi lần deploy: tarball lưu ở /root/trading-system-releases/ts-<VER>.tgz (giữ N=5), ghi /root/trading-system/.release,
# gắn tag image rel-<phiên bản trước> để rollback (infra/ops/rollback.sh). Không cần git server.
# Chạy TRÊN VPS (không có /d/Work): chuyển sang infra/ops/deploy_local.sh (kiểm tra -> build -> healthy -> rollback/ghi release).
#   ./deploy.sh api-gateway auth | ./deploy.sh --all --exclude pattern-engine | ./deploy.sh "up -d --build mt-bridge" (tự tách tên service)
if [ ! -d /d/Work ] && [ -f "$(dirname "$0")/infra/ops/deploy_local.sh" ]; then
  if [ $# -eq 1 ] && case "$1" in up\ *) true;; *) false;; esac; then
    set -- $(printf '%s\n' $1 | grep -v -e '^up$' -e '^-')   # "up -d --build a b" -> a b
  fi
  exec bash "$(dirname "$0")/infra/ops/deploy_local.sh" "$@"
fi
cd /d/Work/trading-system
TGZ=/d/Work/ts-$$.tgz; trap 'rm -f $TGZ' EXIT
export SSH_JUMP=<BASTION_IP> MSYS_NO_PATHCONV=1
T=/d/Work/Work-do/devops/claude-memory/tools
tar --exclude=.venv --exclude=.git --exclude=__pycache__ --exclude='*.pyc' --exclude='*.egg-info' --exclude=.pytest_cache \
    --exclude=infra/.env --exclude='infra/redis/users*.acl' --exclude='services/*/docs/*.jpg' --exclude='services/*/docs/*.png' --exclude='services/*/docs/final' --exclude=node_modules --exclude=dist --exclude='docs/*.png' --exclude=.vite \
    -cf - . | gzip -n > $TGZ
HASH=$(sha256sum $TGZ | cut -c1-12)
VER="$(date -u +%Y%m%dT%H%M%SZ)-${HASH:0:8}"
NOTE="${DEPLOY_NOTE:-${1:-sync}}"
cd $T; node ssh-run.js <VPS_IP> "cat > /root/ts-$HASH.tgz" --stdin-file "$(cygpath -w $TGZ)" | tail -1  # (QA cuối: sftp-put hay ECONNRESET qua bastion -> đẩy bằng stdin)
# kiểm sha256 + gzip trên VPS TRƯỚC khi giải nén/ghi release (upload qua bastion hay bị cắt); sau giải nén khôi phục ACL mask cho user cc
node ssh-run.js <VPS_IP> "set -e; F=/root/ts-$HASH.tgz; [ \"\$(sha256sum \$F | cut -c1-12)\" = $HASH ] && gzip -t \$F || { echo 'UPLOAD HONG (sha256/gzip sai) - huy, khong ghi release' >&2; rm -f \$F; exit 3; }; cd /root/trading-system; [ -f infra/ops/release.sh ] && sh infra/ops/release.sh snapshot || true; tar xzf \$F; tar tzf \$F | tr '\\n' '\\0' | xargs -0 -r setfacl -m m::rwX 2>/dev/null || true; sh infra/ops/release.sh record '$VER' '$HASH' '$NOTE' /root/ts-$HASH.tgz; rm -f /root/ts-$HASH.tgz; cd infra && bash ops/gen_service_env.sh >/dev/null && { [ -z \"$1\" ] || docker compose -p tradingsys --env-file .env $1; }"
echo "release: $VER"
