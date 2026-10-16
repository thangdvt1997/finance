#!/usr/bin/env bash
# Sinh khoá Web Push (VAPID P-256) + khoá mã hoá đăng ký (Fernet) và NẠP VÀO infra/.env nếu chưa có (idempotent). KHÔNG in khoá ra màn hình/log.
# Cần image alert-rules đã build (có pywebpush):  ./deploy.sh "build alert-rules"  rồi chạy script này TRÊN VPS (cd /root/trading-system/infra).
# Sau đó: docker compose -p tradingsys --env-file .env up -d --no-deps alert-rules   (hoặc deploy.sh "up -d --no-deps alert-rules")
# Đổi khoá VAPID = mọi đăng ký push cũ mất hiệu lực (thiết bị phải đăng ký lại). Mất PUSH_ENC_KEY = đăng ký không giải mã được (tự bị dọn).
set -euo pipefail
cd "$(dirname "$0")/.."
has() { grep -qE "^$1=.+" .env; }
if has VAPID_PRIVATE_KEY && has VAPID_PUBLIC_KEY && has PUSH_ENC_KEY; then echo "đã có khoá Web Push trong .env (giữ nguyên)"; exit 0; fi
IMG="${ALERT_RULES_IMAGE:-tradingsys-alert-rules}"
OUT="$(docker run --rm --entrypoint python "$IMG" -m alert_rules.genkeys)"
BAK="${BAK:-<SECRETS_DIR>-bak}"
if ! { [ -d "$BAK" ] && [ -w "$BAK" ]; } && ! mkdir -p "$BAK" 2>/dev/null; then BAK="$HOME/.tradingsys-secrets-bak"; fi   # chay bang user cc: thu muc root khong ghi duoc
mkdir -p "$BAK"; chmod 700 "$BAK"
cp .env "$BAK/env-$(date +%s).bak"; chmod 600 "$BAK"/env-*.bak
sed -i '/^VAPID_PRIVATE_KEY=/d;/^VAPID_PUBLIC_KEY=/d;/^PUSH_ENC_KEY=/d' .env
printf '\n%s\n' "$OUT" >> .env
has VAPID_SUBJECT || printf 'VAPID_SUBJECT=%s\n' "${VAPID_SUBJECT:-mailto:admin@localhost}" >> .env
echo "ok: đã nạp VAPID_PRIVATE_KEY/VAPID_PUBLIC_KEY/PUSH_ENC_KEY vào .env (không hiển thị). Đặt VAPID_SUBJECT=mailto:<email của bạn> nếu muốn."
