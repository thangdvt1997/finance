#!/bin/sh
# QA-E flows client-ui: tạo 2 tài khoản thử (mt5:99900111 passcode, mt5:99900112 ghép cặp), chạy Playwright, LUÔN xoá tài khoản thử.
SRC="$(cd "$(dirname "$0")" && pwd)"; AT="$SRC/../../services/client-ui/qa/auth_testacct.py"
U=99900111; V=99900112; W=/tmp/qa_stab_eg_flows
rm_() { docker exec -i tradingsys-auth python - delete $1 < "$AT" >/dev/null 2>&1; }
trap 'rm_ $U; rm_ $V; rm -f "$W/pw.txt" "$W/pair.txt"' EXIT
rm_ $U; rm_ $V; mkdir -p "$W" && chmod 700 "$W" && docker run --rm -v "$W:/w" alpine rm -rf /w/out && cp "$SRC/eg_client_flows.mjs" "$W/"
docker exec -i tradingsys-auth python - create $U < "$AT" | python3 -c 'import sys,json;print(json.load(sys.stdin)["passcode"])' > "$W/pw.txt"
docker exec -i tradingsys-auth python - create $V < "$AT" | python3 -c 'import sys,json;print(json.load(sys.stdin)["pairing_code"])' > "$W/pair.txt"
chmod 600 "$W/pw.txt" "$W/pair.txt"
timeout 1200 docker run --rm --name "qa-stab-eg-flows-$$" --network host -v "$W:/work" -w /work -e BASE="${BASE:-http://127.0.0.1:8581/c/}" -e OUT=out -e QA_USER=$U -e QA_USER2=$V \
  mcr.microsoft.com/playwright:v1.49.0-jammy sh -c "[ -d node_modules/playwright ] || npm i --no-save --silent playwright@1.49.0; QA_PASS=\$(cat pw.txt) QA_PAIR2=\$(cat pair.txt) node eg_client_flows.mjs"
