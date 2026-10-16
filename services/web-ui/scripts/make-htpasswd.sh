#!/usr/bin/env bash
# Tạo/đổi mật khẩu đăng nhập web-ui. Sinh mật khẩu NGẪU NHIÊN, in ra đúng 1 lần (không lưu dạng rõ ở đâu cả).
#   services/web-ui/scripts/make-htpasswd.sh <user> [file]
# Mặc định ghi vào infra/web-ui/auth/htpasswd (compose mount thư mục này vào nginx, chỉ đọc).
# Chạy lại cùng <user> = đổi mật khẩu; user khác = thêm user. Sau khi đổi KHÔNG cần restart (nginx đọc file mỗi request).
set -euo pipefail

user="${1:-}"
if [[ ! "$user" =~ ^[A-Za-z0-9._-]{1,32}$ ]]; then
  echo "Dùng: $0 <user> [đường-dẫn-htpasswd]   (user: chữ/số/._- tối đa 32 ký tự)" >&2
  exit 2
fi
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
file="${2:-$here/../../../infra/web-ui/auth/htpasswd}"
mkdir -p "$(dirname "$file")"

command -v openssl >/dev/null || { echo "Cần openssl" >&2; exit 1; }
pass="$(openssl rand -base64 24 | tr -d '/+=\n' | cut -c1-20)"
hash="$(printf '%s' "$pass" | openssl passwd -apr1 -stdin)"   # định dạng apr1 (MD5-crypt), nginx đọc được

tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT
if [[ -f "$file" ]]; then grep -v "^${user}:" "$file" > "$tmp" || true; fi
printf '%s:%s\n' "$user" "$hash" >> "$tmp"
install -m 644 "$tmp" "$file"   # 644: container chạy uid 101 phải đọc được; file chỉ chứa hash

echo "Đã ghi: $file"
echo "Tài khoản : $user"
echo "Mật khẩu  : $pass"
echo "(Mật khẩu chỉ hiện lần này. Quên thì chạy lại script để đặt mật khẩu mới.)"
