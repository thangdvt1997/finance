#!/usr/bin/env bash
# ai-pool-teardown.sh — gỡ pool llama.cpp (5 node theo data/ai-pool/nodes.json) khi xong việc / trước TTL (expires_at).
# MẶC ĐỊNH CHỈ IN KẾ HOẠCH (không kết nối). Thực thi cần --yes. Kiểm sau gỡ: --verify (chỉ đọc).
#
# Dùng: ai-pool-teardown.sh [--yes | --verify] [--only <tên-node>]... [--nodes <file>]
#
# Truy cập node: SSH (BatchMode, không mật khẩu). Đích SSH của node <name> lấy theo thứ tự:
#   1) biến môi trường AI_POOL_SSH_<NAME> (NAME = tên node, '-' -> '_', in hoa), vd AI_POOL_SSH_SV_37=root@<HOST_IP>
#   2) tệp data/ai-pool/ssh_targets (dòng "name user@host", # = chú thích; KHÔNG chứa khoá)
#   3) mặc định root@<ip trong nodes.json>
# Khoá: dùng ssh-agent/~/.ssh/config có sẵn; hoặc AI_POOL_SSH_KEY=<đường dẫn khoá> (chỉ truyền cho ssh -i, không in).
# (Lúc viết, VPS này KHÔNG có khoá/alias SSH tới node: pool do laptop điều phối triển khai -> chạy script từ máy có truy cập.)
#
# Chỉ dọn tài nguyên của pool:
#   - container tên bắt đầu ai-pool-llm (vd ai-pool-llm, ai-pool-llm-code); KHÔNG đụng ai-pool-lb
#   - quy tắc iptables có comment chứa "ai-pool" (INPUT/DOCKER-USER, v4+v6)
#   - thư mục /opt/ai-pool (model, KEEP_UNTIL, script)
# Không đụng gì khác. Quy tắc iptables KHÔNG có comment "ai-pool" mà mở cổng 18080/18081 chỉ được IN CẢNH BÁO để xem tay.
# Sau gỡ KHÔNG tự sửa nodes.json: chỉ in gợi ý đặt "status":"removed" để router tự loại node.
set -euo pipefail

MODE=plan; ONLY=()
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; ROOT="$(cd "$HERE/../.." && pwd)"
NODES="${AI_POOL_NODES:-$ROOT/data/ai-pool/nodes.json}"
TARGETS="${AI_POOL_SSH_TARGETS:-$ROOT/data/ai-pool/ssh_targets}"
SSH_BIN="${AI_POOL_SSH_BIN:-ssh}"   # cho phép giả lập khi test
while (($#)); do case "$1" in
  --yes) MODE=run;; --verify) MODE=verify;; --dry-run) MODE=plan;;
  --only) ONLY+=("${2:?thiếu tên node}"); shift;;
  --nodes) NODES="${2:?thiếu tệp}"; shift;;
  -h|--help) sed -n '2,20p' "$0"; exit 0;;
  *) echo "tham số lạ: $1" >&2; exit 2;; esac; shift; done
[[ -f "$NODES" ]] || { echo "không thấy $NODES" >&2; exit 2; }

log(){ printf '[ai-pool-teardown] %s\n' "$*" >&2; }

# name ip port -> mỗi dòng, validate chặt (chống chèn lệnh)
mapfile -t ROWS < <(python3 -I - "$NODES" <<'PY'
import json,re,sys
for n in json.load(open(sys.argv[1])):
    name,ip,port=str(n.get("name","")),str(n.get("ip","")),str(n.get("port",18080))
    if not(re.fullmatch(r"[A-Za-z0-9_.-]+",name) and re.fullmatch(r"[0-9a-fA-F:.]+",ip) and re.fullmatch(r"\d{2,5}",port)):
        sys.exit("node không hợp lệ: %r"%(n,))
    print(name,ip,port)
PY
)
(( ${#ROWS[@]} )) || { echo "nodes.json rỗng" >&2; exit 2; }

target_of(){ # name ip
  local v="AI_POOL_SSH_$(echo "$1" | tr 'a-z-' 'A-Z_')" t=""
  t="${!v:-}"
  [[ -z "$t" && -f "$TARGETS" ]] && t="$(awk -v n="$1" '$1==n{print $2}' "$TARGETS" | head -1)"
  echo "${t:-root@$2}"
}
sshc(){ local o=(-o BatchMode=yes -o ConnectTimeout=15 -o StrictHostKeyChecking=accept-new)
  [[ -n "${AI_POOL_SSH_KEY:-}" ]] && o+=(-i "$AI_POOL_SSH_KEY"); "$SSH_BIN" "${o[@]}" "$@"; }

# Script chạy trên node. $1 = run|verify, $2 = cổng
remote_script(){ cat <<'REMOTE'
set -u
MODE="$1"; PORT="$2"
SUDO=""; [ "$(id -u)" -ne 0 ] && SUDO="sudo -n"
fail=0
cont(){ docker ps -a --format '{{.ID}} {{.Names}}' 2>/dev/null | awk '$2 ~ /^ai-pool-llm/ {print $1}'; }
rules(){ for ipt in iptables ip6tables; do command -v $ipt >/dev/null 2>&1 || continue
  $SUDO $ipt-save 2>/dev/null | grep -E -- '^-A .*--comment "?[^" ]*ai-pool' | sed "s/^/$ipt /"; done; }
if [ "$MODE" = run ]; then
  for id in $(cont); do docker rm -f "$id" >/dev/null 2>&1 && echo "đã xoá container $id"; done
  rules | while read -r ipt _ rest; do
    # -A CHAIN ... -> -D CHAIN ...  (giữ nguyên dấu nháy comment qua eval có kiểm soát)
    eval "$SUDO $ipt -D ${rest#* }" 2>/dev/null && echo "đã xoá rule $ipt: $rest"
  done
  [ -d /opt/ai-pool ] && { $SUDO rm -rf --one-file-system /opt/ai-pool && echo "đã xoá /opt/ai-pool"; }
fi
# verify (chạy cả sau run)
c="$(cont | wc -l)"; r="$(rules | wc -l)"
[ "$c" -eq 0 ] || { echo "CÒN container ai-pool: $c"; fail=1; }
[ "$r" -eq 0 ] || { echo "CÒN rule iptables comment ai-pool: $r"; fail=1; }
[ ! -e /opt/ai-pool ] || { echo "CÒN /opt/ai-pool"; fail=1; }
if command -v ss >/dev/null 2>&1 && ss -ltn 2>/dev/null | awk -v p=":$PORT" '$4 ~ p"$"{f=1} END{exit !f}'; then echo "CÒN socket nghe cổng $PORT"; fail=1; fi
# rule mở cổng không có comment pool: chỉ cảnh báo
w="$( for ipt in iptables ip6tables; do command -v $ipt >/dev/null 2>&1 && $SUDO $ipt-save 2>/dev/null | grep -E -- "--dport $PORT( |$)" | grep -v ai-pool; done | wc -l)"
[ "$w" -eq 0 ] || echo "CẢNH BÁO: $w rule khác nhắc cổng $PORT (không comment ai-pool) — xem tay, script không xoá"
[ "$fail" -eq 0 ] && echo "SẠCH" || exit 1
REMOTE
}

rc=0
for row in "${ROWS[@]}"; do
  read -r name ip port <<<"$row"
  if ((${#ONLY[@]})); then m=0; for o in "${ONLY[@]}"; do [[ "$o" == "$name" ]] && m=1; done; ((m)) || continue; fi
  tgt="$(target_of "$name" "$ip")"
  case "$MODE" in
  plan)
    log "[$name] $tgt (cổng $port) — KẾ HOẠCH (không kết nối):"
    echo "  1. docker rm -f mọi container tên ^ai-pool-llm (vd ai-pool-llm)"
    echo "  2. iptables/ip6tables -D mọi rule có comment 'ai-pool'"
    echo "  3. rm -rf /opt/ai-pool (model, KEEP_UNTIL, script)"
    echo "  4. kiểm: không còn container/rule/thư mục, không socket nghe $port"
    ;;
  run|verify)
    log "[$name] $tgt — ${MODE}"
    if remote_script | sshc "$tgt" bash -s -- "$([[ $MODE == run ]] && echo run || echo verify)" "$port"; then
      log "[$name] OK"
      if [[ $MODE == verify ]] && command -v curl >/dev/null 2>&1; then
        if curl -s -o /dev/null --max-time 5 "http://$ip:$port/health"; then log "[$name] CÒN: cổng $port từ ngoài vẫn trả lời"; rc=1; else log "[$name] cổng $port đóng (từ máy này)"; fi
      fi
    else log "[$name] THẤT BẠI/CÒN SÓT"; rc=1; fi;;
  esac
done
if [[ $MODE == plan ]]; then
  log "Chưa làm gì. Thực thi: $0 --yes ; kiểm: $0 --verify"
else
  log "Gợi ý (KHÔNG tự làm): đặt \"status\":\"removed\" cho các node đã gỡ trong $NODES (hoặc xoá khỏi danh sách) để router tự loại node chết."
fi
exit $rc
