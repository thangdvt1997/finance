#!/bin/sh
# Chạy trước khi nginx khởi động (docker-entrypoint.d). Không dừng container: thiếu htpasswd => nginx từ chối mọi request (fail-closed).
set -eu
if [ -z "${API_KEY:-}" ]; then
  echo "[web-ui] CẢNH BÁO: API_KEY rỗng (đặt API_TOKEN trong infra/.env) - gateway sẽ trả 401 cho mọi request." >&2
fi
if [ -z "${AUTH_TRUST_SECRET:-}" ]; then
  echo "[web-ui] CẢNH BÁO: AUTH_TRUST_SECRET rỗng - gateway sẽ từ chối (403) mọi request mang danh tính người dùng." >&2
fi
if [ "${AUTH_BASIC_FALLBACK:-0}" = "1" ] && [ ! -s /etc/nginx/auth/htpasswd ]; then
  echo "[web-ui] CẢNH BÁO: chưa có /etc/nginx/auth/htpasswd - mọi request sẽ bị từ chối (500)." >&2
  echo "[web-ui] Tạo mật khẩu: services/web-ui/scripts/make-htpasswd.sh <tên-đăng-nhập>" >&2
fi
exit 0
