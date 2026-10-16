#!/bin/sh
# QA-E: ma trận client-ui (Playwright container tạm). Tạo tài khoản thử mt5:99900101 (nhãn QA-E2E-XOA-DI) và XOÁ khi xong. Không in mật khẩu.
SRC="$(cd "$(dirname "$0")" && pwd)"; AT="$SRC/../../services/client-ui/qa/auth_testacct.py"
U=99900101; W=/tmp/qa_stab_eg_client
rm_() { docker exec -i tradingsys-auth python - delete $U < "$AT" >/dev/null 2>&1; }
trap 'rm_; rm -f "$W/pw.txt"' EXIT
rm_; mkdir -p "$W" && chmod 700 "$W" && docker run --rm -v "$W:/w" alpine rm -rf /w/out && cp "$SRC/eg_client_matrix.mjs" "$W/"
docker exec -i tradingsys-auth python - create $U < "$AT" | python3 -c 'import sys,json;print(json.load(sys.stdin)["passcode"])' > "$W/pw.txt"; chmod 600 "$W/pw.txt"
timeout 2400 docker run --rm --name "qa-stab-eg-$$" --network host -v "$W:/work" -w /work -e BASE="${BASE:-http://127.0.0.1:8581/c/}" -e OUT=out -e QA_USER=$U -e VIEWS -e THEMES -e LANGS -e SHOTS \
  mcr.microsoft.com/playwright:v1.49.0-jammy sh -c "[ -d node_modules/playwright ] || npm i --no-save --silent playwright@1.49.0; QA_PASS=\$(cat pw.txt) node eg_client_matrix.mjs"
