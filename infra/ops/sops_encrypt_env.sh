#!/usr/bin/env bash
# Mã hóa/giải mã infra/.env bằng SOPS + age để có thể lưu bản mã hóa (.env.enc) trong git. CHƯA bắt buộc dùng.
# Dùng:
#   ./sops_encrypt_env.sh init            # tạo khóa age (~/.config/sops/age/keys.txt) + in public key; in hướng dẫn
#   ./sops_encrypt_env.sh encrypt [.env]  # -> .env.enc (dotenv, chỉ giá trị được mã hóa)
#   ./sops_encrypt_env.sh decrypt [.env.enc] [.env]   # giải mã ra file chmod 600
# Cần: sops (https://github.com/getsops/sops/releases) + age. Nếu thiếu: chạy qua container (đặt USE_DOCKER=1).
# Khóa riêng (keys.txt) KHÔNG bao giờ commit; sao lưu ở nơi riêng (password manager). .gitignore đã loại .env.
set -euo pipefail
cd "$(dirname "$0")/.."
KEYFILE="${SOPS_AGE_KEY_FILE:-$HOME/.config/sops/age/keys.txt}"
export SOPS_AGE_KEY_FILE="$KEYFILE"

run() {  # run sops|age-keygen ...
  if [ "${USE_DOCKER:-0}" = 1 ]; then
    case "$1" in
      sops) shift; docker run --rm -v "$PWD:/w" -w /w -v "$(dirname "$KEYFILE"):/k" -e SOPS_AGE_KEY_FILE=/k/$(basename "$KEYFILE") ghcr.io/getsops/sops:v3.10.2-alpine sops "$@";;
      age-keygen) shift; docker run --rm -v "$(dirname "$KEYFILE"):/k" filosottile/age age-keygen "$@";;
    esac
  else command "$@"; fi
}
pubkey() { grep -m1 -o 'age1[0-9a-z]*' "$KEYFILE"; }

case "${1:-}" in
  init)
    mkdir -p "$(dirname "$KEYFILE")"; chmod 700 "$(dirname "$KEYFILE")"
    [ -f "$KEYFILE" ] && { echo "Đã có khóa: $KEYFILE"; } || { run age-keygen -o "$KEYFILE"; chmod 600 "$KEYFILE"; }
    echo "Public key: $(pubkey)"
    echo "Ghi vào infra/.sops.yaml:  creation_rules: [{path_regex: '\.env\.enc$', age: '$(pubkey)'}]"
    ;;
  encrypt)
    in="${2:-.env}"; [ -f "$in" ] || { echo "Không thấy $in"; exit 1; }
    run sops --encrypt --age "$(pubkey)" --input-type dotenv --output-type dotenv "$in" > .env.enc
    echo "Đã tạo infra/.env.enc (có thể commit). Giữ .env gốc ngoài git."
    ;;
  decrypt)
    in="${2:-.env.enc}"; out="${3:-.env}"
    umask 077
    run sops --decrypt --input-type dotenv --output-type dotenv "$in" > "$out"; chmod 600 "$out"
    echo "Đã giải mã -> $out (chmod 600)"
    ;;
  *) sed -n 2,9p "$0"; exit 1;;
esac
