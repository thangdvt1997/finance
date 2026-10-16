#!/usr/bin/env bash
# llm_node.sh — thêm/bớt node llama.cpp phụ (Tier A: sv-51, sv-45, sv-02, sv-56) cho LB local-llm.
# CHỈ chạy khi cần (laptop điều phối / phiên có SSH tới node). Mặc định KHÔNG làm gì ở máy khác nếu --dry-run.
#
# Dùng:  llm_node.sh [--dry-run] add|remove|status <host>      <host> = alias SSH hoặc user@host (ví dụ sv-51)
#        llm_node.sh [--dry-run] list | render | tunnels | reload     (chạy trên máy chạy LB = VPS trading)
#
# Ràng buộc an toàn (người dùng đã cho phép Tier A):
#  - chỉ MỘT container tên tsllm-node (+ volume tsllm-node-models); cpus=8, mem 24g, cpu_shares=64 (thấp), nice 19 (--cpuset không ép);
#  - KHÔNG publish ra internet: cổng gắn 127.0.0.1:${PORT} trên node; LB tới node qua (a) WireGuard: NODE_ENDPOINT=<ip-wg>:PORT
#    nếu node có wg (NODE_MODE=wg, bind vào IP wg), hoặc (b) tunnel SSH `ssh -L` từ máy LB (NODE_MODE=ssh, mặc định);
#  - image pin sha như infra/docker-compose.tools.yml; model tải từ HuggingFace (miễn phí) + kiểm sha256 (LFS oid từ HF API,
#    hoặc ghim sẵn ở infra/local-llm/models.sha256); sai sha => xoá tệp, dừng;
#  - remove: dừng + xoá container, volume model, tệp tạm, bỏ khỏi danh sách; không đụng gì khác trên node;
#  - không ghi secret; không dùng sudo (cần docker chạy được cho user SSH).
set -euo pipefail

DRY=0; [[ "${1:-}" == "--dry-run" ]] && { DRY=1; shift; }
CMD="${1:-}"; HOST="${2:-}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LLMDIR="${LLM_DIR:-$HERE/../local-llm}"
NODES="${LLM_NODES_FILE:-$LLMDIR/nodes.list}"          # name|ssh_target|mode|endpoint|weight  (# = chú thích)
OUT_UPSTREAM="${LLM_UPSTREAM_OUT:-$LLMDIR/upstream.nodes.conf}"   # được nginx của local-llm include
SHA_FILE="${LLM_SHA_FILE:-$LLMDIR/models.sha256}"      # "<sha256>  <tên-tệp>" (ghim, ưu tiên hơn HF API)

IMAGE="${LLM_IMAGE:-ghcr.io/ggml-org/llama.cpp:server@sha256:fc9b506e89c1a1cfdd7bc056480f54dc657c1c04d76839a08642dc280b8ed2f6}"
HF_REPO="${LLM_HF_REPO:-unsloth/Qwen3-30B-A3B-Instruct-2507-GGUF}"
MODEL_FILE="${LLM_MODEL_FILE:-Qwen3-30B-A3B-Instruct-2507-Q4_K_M.gguf}"
ALIAS="${LLM_ALIAS:-general}"
CTX="${LLM_CTX:-8192}"; THREADS="${LLM_THREADS:-8}"; PARALLEL="${LLM_PARALLEL:-1}"
PORT="${LLM_NODE_PORT:-8080}"
CNAME=tsllm-node; VOL=tsllm-node-models
TUN_BIND="${LLM_TUNNEL_BIND:-172.17.0.1}"              # IP docker0 của máy LB: container nginx tới được, ngoài mạng thì không
TUN_BASE="${LLM_TUNNEL_BASE:-18100}"
CTRL_DIR="${LLM_CTRL_DIR:-/run/user/$(id -u)/llm-tunnels}"
TIER_A=(sv-51 sv-45 sv-02 sv-56)

log(){ printf '[llm_node] %s\n' "$*" >&2; }
die(){ log "LỖI: $*"; exit 1; }
run(){ if (( DRY )); then printf '[dry-run] %s\n' "$*" >&2; else "$@"; fi; }
rsh(){ # rsh <host> <script-từ-stdin>
  if (( DRY )); then printf '[dry-run] ssh %s bash -s <<<\n' "$1" >&2; sed 's/^/[dry-run]   | /' >&2; else
    ssh -o BatchMode=yes -o ConnectTimeout=15 -o StrictHostKeyChecking=accept-new "$1" bash -s; fi; }

check_host(){
  [[ -n "$HOST" ]] || die "thiếu <host>"
  [[ "$HOST" =~ ^[A-Za-z0-9_.@-]+$ ]] || die "host không hợp lệ"
  local h="${HOST##*@}" ok=0 t
  for t in "${TIER_A[@]}"; do [[ "$h" == "$t"* || "${LLM_ALLOW_ANY:-0}" == 1 ]] && ok=1; done
  (( ok )) || die "$h không thuộc Tier A (${TIER_A[*]}); đặt LLM_ALLOW_ANY=1 nếu người dùng cho phép máy khác"
}
node_name(){ echo "${HOST##*@}" | tr -c 'A-Za-z0-9\n' '_'; }

expected_sha(){ # in sha256 mong đợi: ghim > HF API
  local s=""
  [[ -f "$SHA_FILE" ]] && s="$(awk -v f="$MODEL_FILE" '$2==f{print $1}' "$SHA_FILE" | head -1)"
  if [[ -z "$s" ]]; then
    if (( DRY )); then echo "<sha256-lay-tu-HF-API:$HF_REPO/$MODEL_FILE>"; return; fi
    s="$(curl -fsS --max-time 30 "https://huggingface.co/api/models/$HF_REPO/tree/main" |
      python3 -I -c 'import json,sys;f=sys.argv[1]
for e in json.load(sys.stdin):
    if e.get("path")==f: print((e.get("lfs") or {}).get("oid",""))' "$MODEL_FILE")"
  fi
  [[ "$s" =~ ^[0-9a-f]{64}$ ]] || die "không lấy được sha256 hợp lệ cho $MODEL_FILE"
  echo "$s"
}

cmd_add(){
  check_host
  local sha name mode bind
  sha="$(expected_sha)"; name="$(node_name)"; mode="${NODE_MODE:-ssh}"
  case "$mode" in
    ssh) bind=127.0.0.1;;
    wg)  bind="${NODE_WG_IP:?đặt NODE_WG_IP (IP WireGuard của node) khi NODE_MODE=wg}";;
    *) die "NODE_MODE phải là ssh|wg";;
  esac
  log "add $HOST (mode=$mode, bind=$bind:$PORT, model=$MODEL_FILE)"
  rsh "$HOST" <<REMOTE
set -euo pipefail
command -v docker >/dev/null || { echo "node thiếu docker" >&2; exit 2; }
free_gb=\$(df -BG --output=avail /var/lib/docker 2>/dev/null | tail -1 | tr -dc 0-9); [ "\${free_gb:-0}" -ge 40 ] || { echo "ổ trống < 40 GB" >&2; exit 3; }
mem_gb=\$(awk '/MemAvailable/{printf "%d",\$2/1048576}' /proc/meminfo); [ "\$mem_gb" -ge 26 ] || { echo "RAM khả dụng < 26 GB (\$mem_gb)" >&2; exit 4; }
docker rm -f $CNAME >/dev/null 2>&1 || true
docker volume create $VOL >/dev/null
# tải + kiểm sha256 trong container tạm (curl image nhỏ, chỉ mount volume model)
docker run --rm -v $VOL:/m --cpus 2 --memory 512m curlimages/curl:8.10.1 sh -c '
  set -e; f=/m/$MODEL_FILE
  if [ -f "\$f" ]; then echo "model có sẵn"; else curl -fL --retry 3 -C - -o "\$f.part" "https://huggingface.co/$HF_REPO/resolve/main/$MODEL_FILE"; mv "\$f.part" "\$f"; fi'
got=\$(docker run --rm -v $VOL:/m alpine:3.20 sha256sum /m/$MODEL_FILE | cut -d' ' -f1)
if [ "\$got" != "$sha" ]; then echo "SAI sha256 (\$got != $sha) -> xoá" >&2; docker run --rm -v $VOL:/m alpine:3.20 rm -f /m/$MODEL_FILE; exit 5; fi
docker pull "$IMAGE" >/dev/null
docker run -d --name $CNAME --restart unless-stopped \\
  --cpus 8 --memory 24g --memory-swap 24g --cpu-shares 64 --pids-limit 128 \\
  --cap-drop ALL --security-opt no-new-privileges:true --read-only --tmpfs /tmp \\
  --label tradingsys.llm-node=1 -v $VOL:/models:ro \\
  -p $bind:$PORT:8080 \\
  --entrypoint nice "$IMAGE" -n 19 /app/llama-server --model /models/$MODEL_FILE --host 0.0.0.0 --port 8080 \\
  --threads $THREADS --ctx-size $CTX --parallel $PARALLEL --no-webui --no-warmup --alias $ALIAS --metrics
for i in \$(seq 1 60); do curl -fsS http://$bind:$PORT/health >/dev/null 2>&1 && { echo "node sẵn sàng"; exit 0; }; sleep 5; done
echo "node không healthy sau 5 phút" >&2; docker logs --tail 20 $CNAME >&2; exit 6
REMOTE
  register "$name" "$HOST" "$mode" "${NODE_ENDPOINT:-}" "${NODE_WEIGHT:-1}" "$bind"
  cmd_render; cmd_tunnels; cmd_reload
}

cmd_remove(){
  check_host; local name; name="$(node_name)"
  log "remove $HOST"
  rsh "$HOST" <<REMOTE
set -u
docker rm -f $CNAME >/dev/null 2>&1 || true
docker volume rm -f $VOL >/dev/null 2>&1 || true
docker ps -a --filter label=tradingsys.llm-node=1 -q | grep -q . && { echo "còn container nhãn llm-node" >&2; exit 1; }
echo "đã dọn container+volume trên node"
REMOTE
  unregister "$name"; kill_tunnel "$name"; cmd_render; cmd_reload
}

cmd_status(){
  check_host
  rsh "$HOST" <<REMOTE
docker ps -a --filter name=^$CNAME\$ --format '{{.Names}} {{.Status}}' || true
docker stats --no-stream --format 'cpu={{.CPUPerc}} mem={{.MemUsage}}' $CNAME 2>/dev/null || true
curl -fsS http://127.0.0.1:$PORT/health 2>/dev/null || echo "health: không trả lời trên 127.0.0.1 (có thể bind IP wg)"
uptime
REMOTE
}

# ---- danh sách node (name|ssh_target|mode|endpoint|weight|bind) ----
register(){ # name host mode endpoint weight bind
  local name="$1" host="$2" mode="$3" ep="$4" w="$5" bind="$6"
  if [[ -z "$ep" ]]; then
    if [[ "$mode" == wg ]]; then ep="$bind:$PORT"; else ep="$TUN_BIND:$(tun_port "$name")"; fi
  fi
  (( DRY )) && { log "[dry-run] ghi $NODES: $name|$host|$mode|$ep|$w"; return; }
  mkdir -p "$(dirname "$NODES")"; touch "$NODES"
  grep -v "^$name|" "$NODES" > "$NODES.tmp" || true
  echo "$name|$host|$mode|$ep|$w" >> "$NODES.tmp"; mv "$NODES.tmp" "$NODES"
}
unregister(){ (( DRY )) && { log "[dry-run] bỏ $1 khỏi $NODES"; return; }
  [[ -f "$NODES" ]] && { grep -v "^$1|" "$NODES" > "$NODES.tmp" || true; mv "$NODES.tmp" "$NODES"; }; }
tun_port(){ # cổng tunnel ổn định theo thứ tự tên trong danh sách
  local n="$1" i=0 x
  if [[ -f "$NODES" ]]; then while IFS='|' read -r x _; do [[ -z "$x" || "$x" == \#* ]] && continue
    [[ "$x" == "$n" ]] && { echo $((TUN_BASE+i)); return; }; i=$((i+1)); done < "$NODES"; fi
  echo $((TUN_BASE+i))
}
cmd_list(){ [[ -f "$NODES" ]] && grep -v '^#' "$NODES" || echo "(chưa có node phụ)"; }

# sinh upstream nginx: nút chính local-llm luôn có; node phụ weight thấp + backup chia tải; fail_timeout để loại node chết
cmd_render(){
  local body="# SINH TỰ ĐỘNG bởi infra/ops/llm_node.sh render — KHÔNG sửa tay (sửa $NODES)\n"
  local n h m ep w
  if [[ -f "$NODES" ]]; then
    while IFS='|' read -r n h m ep w; do [[ -z "$n" || "$n" == \#* ]] && continue
      body+="server $ep weight=${w:-1} max_fails=2 fail_timeout=30s;  # $n ($m)\n"; done < "$NODES"
  fi
  if (( DRY )); then printf '[dry-run] %s ->\n%b' "$OUT_UPSTREAM" "$body" >&2; return; fi
  printf '%b' "$body" > "$OUT_UPSTREAM.tmp"; mv "$OUT_UPSTREAM.tmp" "$OUT_UPSTREAM"; log "đã render $OUT_UPSTREAM"
  render_swap
}
# Bản cho llama-swap (L1 dùng llama-swap, infra/local-llm/config.yaml): mỗi node phụ = 1 model trỏ proxy tới node.
# CHƯA kiểm với llama-swap thật: dán vào mục `models:` (hoặc dùng cơ chế peers nếu bản llama-swap hỗ trợ) rồi reload/restart llama-swap.
render_swap(){
  local y="# SINH TỰ ĐỘNG bởi llm_node.sh render (llama-swap) — models trỏ proxy tới node phụ\nmodels:\n" n h m ep w
  [[ -f "$NODES" ]] || return 0
  while IFS='|' read -r n h m ep w; do [[ -z "$n" || "$n" == \#* ]] && continue
    y+="  general-$n:\n    proxy: http://$ep\n    cmd: sleep infinity\n    checkEndpoint: /health\n    ttl: 0\n"; done < "$NODES"
  printf '%b' "$y" > "${OUT_UPSTREAM%.conf}.llama-swap.yaml"
}

# tunnel SSH (chạy trên máy LB). Mỗi node: ssh -N -L TUN_BIND:cổng:127.0.0.1:PORT, ControlPersist, tự thử lại bằng ServerAlive
kill_tunnel(){ (( DRY )) && { log "[dry-run] đóng tunnel $1"; return; }
  [[ -S "$CTRL_DIR/$1" ]] && ssh -S "$CTRL_DIR/$1" -O exit x 2>/dev/null || true; }
cmd_tunnels(){
  [[ -f "$NODES" ]] || return 0
  local n h m ep w lp
  (( DRY )) || mkdir -p "$CTRL_DIR"
  while IFS='|' read -r n h m ep w; do [[ -z "$n" || "$n" == \#* || "$m" != ssh ]] && continue
    lp="${ep##*:}"
    if (( ! DRY )) && ssh -S "$CTRL_DIR/$n" -O check x 2>/dev/null; then continue; fi
    run ssh -f -N -M -S "$CTRL_DIR/$n" -o ExitOnForwardFailure=yes -o ServerAliveInterval=15 -o ServerAliveCountMax=3 \
      -o BatchMode=yes -L "$TUN_BIND:$lp:127.0.0.1:$PORT" "$h"
  done < "$NODES"
}
# reload nginx của local-llm không downtime (L1 đặt tên container qua LLM_LB_CONTAINER)
cmd_reload(){
  local c="${LLM_LB_CONTAINER:-tradingsys-local-llm}"
  if (( DRY )); then log "[dry-run] docker exec $c nginx -t && nginx -s reload"; return; fi
  if docker ps --format '{{.Names}}' | grep -qx "$c"; then
    docker exec "$c" nginx -t && docker exec "$c" nginx -s reload && log "đã reload $c"
  else log "chưa có container LB $c (L1 chưa dựng?) — bỏ qua reload"; fi
}

case "$CMD" in
  add) cmd_add;; remove) cmd_remove;; status) cmd_status;;
  list) cmd_list;; render) cmd_render;; tunnels) cmd_tunnels;; reload) cmd_reload;;
  *) sed -n '2,6p' "$0"; exit 1;;
esac
