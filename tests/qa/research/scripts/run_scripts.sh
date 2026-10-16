#!/usr/bin/env bash
# QA research: kiem ke + TEST moi script/tool (infra/ops, infra/backup, infra/db|host|perf, mt-agent/lab*, data/mtlab-hist, tests/*).
# Chay tren VPS:   bash tests/qa/research/scripts/run_scripts.sh [--md] [--only S-026,S-028]
# - Moi lenh chay `nice -n 19 timeout`; KHONG deploy/restart/xoa; script nguy hiem chi chay trong SANDBOX tmp (+ docker gia lap qua PATH).
# - Ket qua cuoi: bang ID | ket qua | ghi chu; thoat 0 neu khong co FAIL. --md in them bang Markdown (dung cho FUNCTION_INVENTORY).
# - Khong in/ghi secret (chi so sanh gian tiep bang grep -qF).
set -u
R="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
HERE="$R/tests/qa/research/scripts"
MD=0; ONLY=""
while [ $# -gt 0 ]; do case "$1" in --md) MD=1;; --only) ONLY="$2"; shift;; esac; shift; done
W="$(mktemp -d "${TMPDIR:-/tmp}/qa-scripts.XXXXXX")"; trap 'rm -rf "$W"' EXIT
RES="$W/res.tsv"; : > "$RES"
LOADMAX="${LOADMAX:-70}"
res()  { printf '%s\t%s\t%s\n' "$1" "$2" "$3" >> "$RES"; }          # ID  PASS|FAIL|SKIP|STATIC  ghi-chu
want() { [ -z "$ONLY" ] || case ",$ONLY," in *",$1,"*) return 0;; *) return 1;; esac; }
run()  { OUT=$(nice -n 19 timeout "${TMO:-90}" "$@" 2>&1); RC=$?; }  # -> $OUT $RC
# ok ID "nhan" '<bieu thuc bash dung $RC/$OUT>'
ok()   { local id=$1 lbl=$2; shift 2; if eval "$*"; then res "$id" PASS "$lbl"; else res "$id" FAIL "$lbl (rc=${RC:-?} out=$(printf '%s' "${OUT:-}" | tr '\n' ' ' | cut -c1-160))"; fi; }
skip() { res "$1" SKIP "$2"; }
loadok() { [ "$(cut -d. -f1 /proc/loadavg)" -le "$LOADMAX" ]; }
sha()  { sha256sum "$1" 2>/dev/null | cut -d' ' -f1; }

# ---------- docker gia lap (PATH) de test script nguy hiem ----------
STUB="$W/stub"; mkdir -p "$STUB"; CALLS="$W/docker.calls"; : > "$CALLS"
cat > "$STUB/docker" <<'EOF'
#!/bin/bash
echo "$*" >> "${DOCKER_CALLS:-/dev/null}"
case "$*" in
  "images --format {{.Repository}}") echo tradingsys-foo; exit 0;;
  "images --format {{.Tag}} tradingsys-foo") printf '%s\n' latest rel-a rel-b rel-c rel-d; exit 0;;
  *pg_dump*) [ -n "${STUB_DUMP_FAIL:-}" ] && exit 1; head -c 4096 /dev/urandom; exit 0;;
  *pg_restore*" -l"*) cat >/dev/null; seq 1 50; exit 0;;
  *pg_basebackup*) head -c 2048 /dev/urandom; exit 0;;
  "ps "*) exit 0;;
  inspect*) echo "docker inspect: requires at least 1 argument" >&2; exit 1;;
  *ghcr.io/astral-sh/ruff*) echo "ruff FAIL" ; exit 1;;
  "exec "*notify*|"exec -i -e SEV="*) exit "${STUB_NOTIFY_RC:-1}";;
  *) exit 0;;
esac
EOF
chmod +x "$STUB/docker"
export DOCKER_CALLS="$CALLS"
withstub() { PATH="$STUB:$PATH" "$@"; }
mk_infra() {  # mk_infra DIR  -> DIR/infra/{ops,backup,...} ban sao scripts that + .env gia
  local d=$1; mkdir -p "$d/infra/ops" "$d/infra/backup" "$d/infra/web-ui/auth" "$d/infra/redis" "$d/infra/env" "$d/infra/mt-bridge" "$d/logs"
  cp "$R"/infra/ops/*.sh "$R"/infra/ops/*.manifest "$d/infra/ops/" 2>/dev/null; cp "$R"/infra/backup/*.sh "$d/infra/backup/"
  printf 'API_TOKEN=oldtoken\nINTERNAL_TOKEN=oldint\nLOG_LEVEL=info\nSTORAGE_X=1\nPOSTGRES_PASSWORD=pgsecret\nMT_FOO=1\n' > "$d/infra/.env"; chmod 600 "$d/infra/.env"
  printf 'admin:$apr1$x$y\n' > "$d/infra/web-ui/auth/htpasswd"
}

# ======================= 0. QUET TINH moi script =======================
INV="$HERE/inventory.tsv"
node_ok=0; command -v node >/dev/null && node_ok=1
static_one() {  # static_one ID file -> ghi STATIC/FAIL
  local id=$1 f=$2 e
  case "$f" in
    *.sh|*.sh.bak*) e=$(bash -n "$f" 2>&1) || { res "$id" FAIL "bash -n loi: $(basename "$f"): ${e:0:120}"; return; } ;;
    *.py) e=$(python3 -I -c 'import sys;compile(open(sys.argv[1],"rb").read(),sys.argv[1],"exec")' "$f" 2>&1) || { res "$id" FAIL "py compile loi: $(basename "$f"): ${e:0:120}"; return; } ;;
    *.yaml|*.yml|*.disabled|*.manifest) case "$f" in *.manifest) ;; *) e=$(python3 -I -c 'import sys,yaml;list(yaml.safe_load_all(open(sys.argv[1])))' "$f" 2>&1) || { res "$id" FAIL "yaml loi: $(basename "$f"): ${e:0:120}"; return; };; esac ;;
    *.mjs) [ $node_ok = 1 ] && { e=$(node --check "$f" 2>&1) || { res "$id" FAIL "node --check loi: $(basename "$f")"; return; }; } ;;
    *.sql) [ -s "$f" ] || { res "$id" FAIL "sql rong: $f"; return; } ;;
  esac
  [ -s "$f" ] || [ "${f##*.}" = lock ] || { res "$id" FAIL "file 0 byte: $f"; return; }
  res "$id" STATIC "$(basename "$f")"
}
while IFS='|' read -r id path dep desc; do
  case "$id" in ''|'#'*) continue;; esac
  want "$id" || continue
  n=0; for pat in $path; do for f in $R/$pat; do [ -e "$f" ] || continue; n=$((n+1)); static_one "$id" "$f"; done; done
  [ $n -gt 0 ] || res "$id" FAIL "khong tim thay file: $path"
done < "$INV"

# ======================= 1. TEST CHUC NANG =======================
# ---- S-016 gen_mt_hmac.sh
if want S-016; then d="$W/t16"; mk_infra "$d"; run sh "$d/infra/ops/gen_mt_hmac.sh"; a=$(sha "$d/infra/.env")
  ok S-016 "them 2 bien HMAC 64-hex, khong in gia tri" '[ $RC = 0 ] && grep -qE "^MT_HMAC_DEMO_MT4_01=[0-9a-f]{64}$" "$d/infra/.env" && grep -qE "^MT_HMAC_DEMO_MT5_01=[0-9a-f]{64}$" "$d/infra/.env" && ! grep -qE "[0-9a-f]{64}" <<<"$OUT"'
  run sh "$d/infra/ops/gen_mt_hmac.sh"; ok S-016 "idempotent (chay lai khong doi .env)" '[ $RC = 0 ] && [ "$(sha "$d/infra/.env")" = "$a" ]'; fi
# ---- S-017 gen_service_env.sh
if want S-017; then d="$W/t17"; mk_infra "$d"; run bash "$d/infra/ops/gen_service_env.sh"; a=$(sha "$d/infra/env/storage-writer.env")
  ok S-017 "sinh env theo allowlist (LOG_LEVEL,STORAGE_X co; POSTGRES_PASSWORD khong), 0600" '[ $RC = 0 ] && grep -q "^STORAGE_X=1" "$d/infra/env/storage-writer.env" && grep -q "^LOG_LEVEL=" "$d/infra/env/storage-writer.env" && ! grep -rq POSTGRES_PASSWORD "$d/infra/env/" && [ "$(stat -c %a "$d/infra/env/storage-writer.env")" = 600 ]'
  run bash "$d/infra/ops/gen_service_env.sh"; ok S-017 "idempotent" '[ $RC = 0 ] && [ "$(sha "$d/infra/env/storage-writer.env")" = "$a" ]'
  run bash "$d/infra/ops/gen_service_env.sh" --report; ok S-017 "--report liet ke bien khong service nao nhan" '[ $RC = 0 ] && grep -q POSTGRES_PASSWORD <<<"$OUT"'
  rm -f "$d/infra/.env"; run bash "$d/infra/ops/gen_service_env.sh"; ok S-017 "thieu .env -> rc1" '[ $RC = 1 ]'; fi
# ---- S-018 gen_vapid.sh (nhanh da co khoa; nhanh sinh khoa test qua docker gia lap + BAK sandbox)
if want S-018; then d="$W/t18"; mk_infra "$d"; printf 'VAPID_PRIVATE_KEY=a\nVAPID_PUBLIC_KEY=b\nPUSH_ENC_KEY=c\n' >> "$d/infra/.env"; a=$(sha "$d/infra/.env")
  run bash "$d/infra/ops/gen_vapid.sh"; ok S-018 "da co khoa -> giu nguyen .env, rc0" '[ $RC = 0 ] && [ "$(sha "$d/infra/.env")" = "$a" ]'
  d2="$W/t18b"; mk_infra "$d2"; cat > "$STUB/docker.vapid" <<'EOF'
EOF
  OUT=$(BAK="$W/bak18" PATH="$STUB:$PATH" nice -n 19 timeout 30 bash -c '
    docker(){ printf "VAPID_PRIVATE_KEY=p\nVAPID_PUBLIC_KEY=q\nPUSH_ENC_KEY=r\n"; }; export -f docker; bash "$0"' "$d2/infra/ops/gen_vapid.sh" 2>&1); RC=$?
  ok S-018 "sinh khoa (docker gia lap): nap 3 bien + VAPID_SUBJECT, backup .env, rc0" '[ $RC = 0 ] && grep -q "^VAPID_PRIVATE_KEY=p" "$d2/infra/.env" && grep -q "^VAPID_SUBJECT=" "$d2/infra/.env" && ! grep -q "=p$" <<<"$OUT"'; fi
# ---- S-019 hardening_audit.sh
if want S-019; then run sh "$R/infra/ops/hardening_audit.sh"; ok S-019 "chay that (doc-chi): rc0 co bang + muc VI PHAM" '[ $RC = 0 ] && grep -q "VI PHẠM" <<<"$OUT" && grep -q "|u=" <<<"$OUT"'
  OUT=$(PATH="$STUB:$PATH" nice -n 19 timeout 30 sh "$R/infra/ops/hardening_audit.sh" 2>&1); RC=$?
  ok S-019 "khong co container -> khong in loi 'requires at least 1 argument' (xargs -r)" '! grep -q "requires at least 1" <<<"$OUT"'; fi
# ---- S-022 notify.sh
if want S-022; then run env ALERT_CONTAINER=khong-ton-tai sh "$R/infra/ops/notify.sh" warning "tieu de" "noi dung"; ok S-022 "container khong ton tai: rc0 (loi gui khong lam hong script goi) + canh bao stderr" '[ $RC = 0 ] && grep -q "không gửi được" <<<"$OUT"'; fi
# ---- S-026 release.sh
if want S-026; then d="$W/t26"; mkdir -p "$d/r" "$d/rel"; echo x > "$d/a.tgz"
  run env TS_ROOT="$d/r" REL_DIR="$d/rel" sh "$R/infra/ops/release.sh" current; ok S-026 "current khi chua co .release = none" '[ "$OUT" = none ]'
  run env TS_ROOT="$d/r" REL_DIR="$d/rel" sh "$R/infra/ops/release.sh" record v1 h1 "ghi chu 1" "$d/a.tgz"; ok S-026 "record v1" '[ $RC = 0 ] && grep -q "^version=v1" "$d/r/.release" && [ -f "$d/rel/ts-v1.tgz" ] && [ -f "$d/rel/v1.release" ]'
  run env TS_ROOT="$d/r" REL_DIR="$d/rel" sh "$R/infra/ops/release.sh" record v2 h2 "n2" "$d/a.tgz"; ok S-026 "record v2 -> previous=v1" '[ $RC = 0 ] && grep -q "^previous=v1" "$d/r/.release" && grep -q "^version=v2" "$d/r/.release"'
  for v in v3 v4; do KEEP_RELEASES=2 TS_ROOT="$d/r" REL_DIR="$d/rel" sh "$R/infra/ops/release.sh" record $v h "n" "$d/a.tgz" >/dev/null; sleep 1; touch "$d/rel/ts-$v.tgz"; done
  ok S-026 "retention KEEP=2 giu 2 tarball moi nhat" '[ "$(ls "$d"/rel/ts-*.tgz | wc -l)" = 2 ]'
  run env TS_ROOT="$d/r" REL_DIR="$d/rel" sh "$R/infra/ops/release.sh" record v9 h9 "khong co tgz" "$d/khong-co.tgz"
  ok S-026 "record voi tarball khong ton tai -> tu choi (rc!=0) va KHONG ghi release" '[ $RC != 0 ] && ! grep -q "^version=v9" "$d/r/.release"'
  run env TS_ROOT="$d/r" REL_DIR="$d/rel" sh "$R/infra/ops/release.sh" bogus; ok S-026 "lenh la -> rc2 + usage" '[ $RC = 2 ]'
  : > "$CALLS"; run env TS_ROOT="$d/r" REL_DIR="$d/rel" KEEP_IMAGE_RELEASES=3 PATH="$STUB:$PATH" sh "$R/infra/ops/release.sh" snapshot
  ok S-026 "snapshot (docker gia lap): tag rel-<ver> + xoa tag cu vuot KEEP_IMG" '[ $RC = 0 ] && grep -q "^tag tradingsys-foo:latest tradingsys-foo:rel-" "$CALLS" && grep -q "^rmi tradingsys-foo:rel-a" "$CALLS" && ! grep -q "^rmi tradingsys-foo:rel-d" "$CALLS"'; fi
# ---- S-027 rollback.sh
if want S-027; then d="$W/t27"; mkdir -p "$d/r/infra" "$d/rel" "$d/pk"; echo OLD > "$d/pk/marker.txt"; tar czf "$d/rel/ts-v1.tgz" -C "$d/pk" marker.txt; echo NEW > "$d/r/marker.txt"
  printf 'version=v2\nprevious=v1\n' > "$d/r/.release"; : > "$CALLS"
  run env TS_ROOT="$d/r" REL_DIR="$d/rel" PATH="$STUB:$PATH" sh "$R/infra/ops/rollback.sh"
  ok S-027 "rollback v2->v1: giai nen ma, retag image, ghi .release, KHONG recreate khi thieu SERVICES" '[ $RC = 0 ] && [ "$(cat "$d/r/marker.txt")" = OLD ] && grep -q "^version=v1" "$d/r/.release" && grep -q "^previous=v2" "$d/r/.release" && grep -q "^tag tradingsys-foo:rel-v1 tradingsys-foo:latest" "$CALLS" && ! grep -q "compose" "$CALLS"'
  : > "$CALLS"; run env TS_ROOT="$d/r" REL_DIR="$d/rel" SERVICES="foo" PATH="$STUB:$PATH" sh "$R/infra/ops/rollback.sh" v1
  ok S-027 "SERVICES=foo -> compose up -d --no-build --no-deps foo" '[ $RC = 0 ] && grep -q "compose -p tradingsys --env-file .env up -d --no-build --no-deps foo" "$CALLS"'
  run env TS_ROOT="$d/r" REL_DIR="$d/rel" sh "$R/infra/ops/rollback.sh" v-khong-co; ok S-027 "ban khong ton tai -> rc1, khong doi gi" '[ $RC = 1 ] && grep -q "^version=v1" "$d/r/.release"'
  ok S-027 "copy tam khong dung ten co dinh /tmp/ts-rollback.sh (chong ghi de/symlink)" '! grep -q "cp \"\$0\" /tmp/ts-rollback.sh" "$R/infra/ops/rollback.sh"'; fi
# ---- S-028 rotate_secret.sh
if want S-028; then d="$W/t28"; mk_infra "$d"; E="$d/infra/.env"; S="$d/infra/ops/rotate_secret.sh"; B="$W/bak28"; old=$(sed -n 's/^API_TOKEN=//p' "$E")
  run env BAK="$B" bash "$S"; ok S-028 "khong doi so -> usage rc2" '[ $RC = 2 ]'
  run env BAK="$B" bash "$S" POSTGRES_PASSWORD; ok S-028 "bien ngoai ALLOW -> rc3, khong sua" '[ $RC = 3 ] && grep -q "^POSTGRES_PASSWORD=pgsecret$" "$E"'
  run env BAK="$B" bash "$S" NOPE_TOKEN; ok S-028 "bien khong ALLOW (NOPE_TOKEN) -> rc3" '[ $RC = 3 ]'
  run env BAK="$B" bash "$S" BACKFILL_TOKEN; ok S-028 "bien co trong ALLOW nhung chua co trong .env, khong INIT -> rc4" '[ $RC = 4 ]'
  run env BAK="$B" bash "$S" API_TOKEN; nv=$(sed -n 's/^API_TOKEN=//p' "$E")
  ok S-028 "xoay API_TOKEN: doi gia tri (48 hex), khong in gia tri, giu dong khac, .env 0600, co ban sao luu" '[ $RC = 0 ] && [ "$nv" != "$old" ] && [[ "$nv" =~ ^[0-9a-f]{48}$ ]] && ! grep -qF "$nv" <<<"$OUT" && grep -q "^LOG_LEVEL=info" "$E" && [ "$(stat -c %a "$E")" = 600 ] && [ "$(ls "$B"/env-*.bak | wc -l)" -ge 1 ]'
  run env BAK="$B" bash "$S" INTERNAL_TOKEN; ok S-028 "INTERNAL_TOKEN: gia tri cu chuyen sang INTERNAL_TOKEN_PREV" '[ $RC = 0 ] && grep -q "^INTERNAL_TOKEN_PREV=oldint$" "$E"'
  run env BAK="$B" INIT=1 BYTES=32 bash "$S" BACKFILL_TOKEN; ok S-028 "INIT=1 tao bien moi (64 hex)" '[ $RC = 0 ] && grep -qE "^BACKFILL_TOKEN=[0-9a-f]{64}$" "$E"'
  sleep 1; run env BAK="$B" bash "$S" API_TOKEN >/dev/null; sleep 1; run env BAK="$B" bash "$S" API_TOKEN >/dev/null
  run env BAK="$B" bash "$S" --prune-bak 1; ok S-028 "--prune-bak 1 khi KHONG co infra/.env.bak.*: rc0 va con dung 1 ban" '[ $RC = 0 ] && [ "$(ls "$B"/env-*.bak | wc -l)" = 1 ]'
  cp "$E" "$d/infra/.env.bak.1"; run env BAK="$B" bash "$S" --prune-bak 1; ok S-028 "--prune-bak xoa infra/.env.bak.* con sot" '[ $RC = 0 ] && [ ! -e "$d/infra/.env.bak.1" ]'
  run env BAK="$B" bash "$S" --htpasswd-disable; ok S-028 "--htpasswd-disable thay hash, giu user" '[ $RC = 0 ] && grep -qF "admin:\$apr1\$" "$d/infra/web-ui/auth/htpasswd" && ! grep -qF "x\$y" "$d/infra/web-ui/auth/htpasswd"'; fi
# ---- S-023 redis_acl_render.sh
if want S-023; then d="$W/t23"; mk_infra "$d"; S="$d/infra/ops/redis_acl_render.sh"
  run env BAK="$W/bak23" bash "$S"; a=$(sha "$d/infra/redis/users.acl"); e1=$(sha "$d/infra/.env"); pw=$(sed -n 's/^REDIS_APP_PASSWORD=//p' "$d/infra/.env")
  ok S-023 "sinh users.acl + users-cache.acl, them mat khau vao .env, default off, khong chua mat khau ro" '[ $RC = 0 ] && grep -q "^user default off" "$d/infra/redis/users.acl" && [ -n "$pw" ] && ! grep -qF "$pw" "$d/infra/redis/users.acl" && [ -s "$d/infra/redis/users-cache.acl" ] && grep -q "^user ts_svc_" "$d/infra/redis/users.acl"'
  run env BAK="$W/bak23" bash "$S"; ok S-023 "idempotent (acl + .env khong doi lan 2)" '[ $RC = 0 ] && [ "$(sha "$d/infra/redis/users.acl")" = "$a" ] && [ "$(sha "$d/infra/.env")" = "$e1" ]'
  if loadok; then TMO=240 run bash "$R/infra/ops/redis_acl_render.sh" --check; ok S-023 "--check tren redis that (ACL DRYRUN, khong ghi): OK" '[ $RC = 0 ] && grep -q "ACL check: OK" <<<"$OUT"'; else skip S-023 "--check tren redis that bo qua: load cao"; fi; fi
# ---- S-032 sops_encrypt_env.sh
if want S-032; then run env SOPS_AGE_KEY_FILE="$W/k.txt" bash "$R/infra/ops/sops_encrypt_env.sh"; ok S-032 "khong doi so -> usage rc1" '[ $RC = 1 ]'
  run env SOPS_AGE_KEY_FILE="$W/k.txt" bash "$R/infra/ops/sops_encrypt_env.sh" encrypt /khong/co; ok S-032 "encrypt file khong ton tai -> rc1" '[ $RC = 1 ] && grep -q "Không thấy" <<<"$OUT"'
  command -v sops >/dev/null || skip S-032 "encrypt/decrypt/init that: sops+age chua cai tren VPS (chua dung, 'CHUA bat buoc')"; fi
# ---- S-033 top_cves.py
if want S-033; then d="$W/t33"; mkdir -p "$d"; python3 - "$d" <<'PY'
import json,sys
v=lambda i,s,p,iv,fx=None:{"VulnerabilityID":i,"Severity":s,"PkgName":p,"InstalledVersion":iv,**({"FixedVersion":fx} if fx else {})}
json.dump({"Results":[{"Vulnerabilities":[v("CVE-1","HIGH","a","1","2"),v("CVE-2","CRITICAL","b","1"),v("CVE-3","CRITICAL","c","1","9"),v("CVE-4","HIGH","a","1","2")]}]},open(sys.argv[1]+"/img1.json","w"))
json.dump({"Results":None},open(sys.argv[1]+"/img2.json","w"))
PY
  run python3 "$R/infra/ops/top_cves.py" "$d" 3; ok S-033 "CRITICAL truoc HIGH, co ban va truoc chua va; gom CVE trung; Results=null khong loi" '[ $RC = 0 ] && [ "$(grep -n CRITICAL <<<"$OUT" | head -1 | cut -d: -f1)" -lt "$(grep -n HIGH <<<"$OUT" | head -1 | cut -d: -f1)" ] && grep -q "c 1 -> fix 9" <<<"$OUT" && grep -q "(2 CVE" <<<"$OUT" && grep -q "## img2" <<<"$OUT"'
  run python3 "$R/infra/ops/top_cves.py"; ok S-033 "thieu doi so: bao loi (rc!=0), khong treo" '[ $RC != 0 ]'; fi
# ---- S-007 bt_summary.py
if want S-007; then d="$W/t7"; mkdir -p "$d/l"; python3 - "$d/l" <<'PY'
import sys, numpy as np, pandas as pd
r=np.random.default_rng(1)
for s,n in (("dev",300),("val",120),("test",150)):
    pd.DataFrame({"R_net":r.normal(-.1,1,n),"R_gross":r.normal(0,1,n),"kb":r.choice(["KB-1","KB-2"],n)}).to_csv(f"{sys.argv[1]}/ledger_{s}.csv.gz",index=False)
PY
  run python3 "$R/infra/ops/bt_summary.py" "$d/l" "$d/o1.json"; run python3 "$R/infra/ops/bt_summary.py" "$d/l" "$d/o2.json"
  ok S-007 "sinh summary.json hop le (4 hang, by_kb), tai lap (cung input -> cung output)" '[ $RC = 0 ] && python3 -c "import json,sys;j=json.load(open(sys.argv[1]));assert len(j[\"rows\"])==4 and set(j[\"by_kb\"])=={\"dev_val\",\"test\"}" "$d/o1.json" && [ "$(sha "$d/o1.json")" = "$(sha "$d/o2.json")" ]'
  [ -d "$R/data/research/patterns/backtest/final/ledger" ] && res S-007 PASS "du lieu ledger that con" || skip S-007 "PHAN CHUA PHU: chay tren ledger that - thu muc data/research/patterns/backtest/final/ledger khong con tren VPS (backtest da dung); chi test bang ledger tong hop"; fi
# ---- S-012 feed_latency.py
if want S-012; then TMO=60 run python3 "$R/infra/ops/feed_latency.py" 2; ok S-012 "do p50/p95 fx + metal (cua so 2s) rc0" '[ $RC = 0 ] && grep -q "^fx: n=" <<<"$OUT" && grep -q "^metal: n=" <<<"$OUT"'
  ok S-012 "metal do CUNG cua so voi fx (khong snapshot lien tiep)" '! grep -q "if cls == \"fx\": time.sleep" "$R/infra/ops/feed_latency.py"'; fi
# ---- S-015 gen_assets_mt5.py
if want S-015; then d="$W/t15"; mkdir -p "$d/libs/common/src/tscommon" "$d/infra/mt-bridge"
  run python3 "$R/infra/ops/gen_assets_mt5.py" --csv /root/mtlab/out/symbols.csv --out-dir "$d"; a=$(sha "$d/libs/common/src/tscommon/assets_mt5.yaml")
  run python3 "$R/infra/ops/gen_assets_mt5.py" --csv /root/mtlab/out/symbols.csv --out-dir "$d"
  ok S-015 "sinh assets_mt5.yaml + feed_symbols.txt tu symbols.csv that, idempotent, yaml hop le" '[ $RC = 0 ] && [ "$(sha "$d/libs/common/src/tscommon/assets_mt5.yaml")" = "$a" ] && python3 -c "import yaml,sys;d=yaml.safe_load(open(sys.argv[1]));assert d[\"symbols\"][\"forex\"]" "$d/libs/common/src/tscommon/assets_mt5.yaml"'
  ok S-015 "dong bo voi file dang commit trong repo (khong lech)" 'diff -q "$d/libs/common/src/tscommon/assets_mt5.yaml" "$R/libs/common/src/tscommon/assets_mt5.yaml" >/dev/null && diff -q "$d/infra/mt-bridge/feed_symbols.txt" "$R/infra/mt-bridge/feed_symbols.txt" >/dev/null'; fi
# ---- S-020 lock_deps.py (uv gia lap)
if want S-020; then d="$W/t20"; mkdir -p "$d/root/libs/common" "$d/root/services/foo" "$d/out" "$d/bin"
  printf '[project]\nname="tscommon"\nversion="1"\ndependencies=["pydantic>=2","tscommon-x"]\n' > "$d/root/libs/common/pyproject.toml"
  printf '[project]\nname="foo"\nversion="1"\ndependencies=["httpx","pydantic>=2"]\n' > "$d/root/services/foo/pyproject.toml"
  printf '#!/bin/sh\nwhile [ $# -gt 0 ]; do [ "$1" = -o ] && o=$2; shift; done; printf "httpx==1 \\\\\\n    --hash=sha256:aa\\n" > "$o"\n' > "$d/bin/uv"; chmod +x "$d/bin/uv"
  if python3 -c "import tomllib" 2>/dev/null; then run env PATH="$d/bin:$PATH" python3 "$R/infra/ops/lock_deps.py" "$d/root" "$d/out" foo
  else TMO=120 run docker run --rm --network none --user "$(id -u):$(id -g)" -v "$d:/w" -v "$R/infra/ops:/ops:ro" python:3.12-slim sh -c "PATH=/w/bin:\$PATH python /ops/lock_deps.py /w/root /w/out foo"; fi
  ok S-020 "gop dep common+service, bo tscommon*, sap xep, goi uv pip compile --generate-hashes (uv gia lap)" '[ $RC = 0 ] && [ "$(cat "$d/out/foo.in")" = "$(printf "httpx\npydantic>=2")" ] && [ -s "$d/out/foo.requirements.lock" ]'
  command -v uv >/dev/null && echo "uv co san (khong goi mang that trong test)" >/dev/null; fi
# ---- S-021 lock_deps.sh (docker gia lap)
if want S-021; then : > "$CALLS"; run env PATH="$STUB:$PATH" TS_ROOT="$R" sh "$R/infra/ops/lock_deps.sh" foo; ok S-021 "goi docker run python:3.12-slim chay lock_deps.py voi service chi dinh (docker gia lap; khong pip that)" '[ $RC = 0 ] && grep -q "python:3.12-slim" "$CALLS" && grep -q "lock_deps.py /src /out foo" "$CALLS"'; fi
# ---- S-036 deploy.sh (tren VPS -> deploy_local.sh): dich tham so
if want S-036; then d="$W/t36"; mkdir -p "$d/infra/ops"; cp "$R/deploy.sh" "$d/"
  printf '#!/bin/bash\necho "ARGS:$*"\n' > "$d/infra/ops/deploy_local.sh"
  [ -d /d/Work ] && skip S-036 "may co /d/Work (laptop)" || {
  run bash "$d/deploy.sh" "up -d --build mt-bridge"; ok S-036 "'up -d --build mt-bridge' -> mt-bridge" '[ "$OUT" = "ARGS:mt-bridge" ]'
  run bash "$d/deploy.sh" "up -d --no-deps a b"; ok S-036 "'up -d --no-deps a b' -> a b" '[ "$OUT" = "ARGS:a b" ]'
  run bash "$d/deploy.sh" api-gateway auth; ok S-036 "nhieu doi so giu nguyen" '[ "$OUT" = "ARGS:api-gateway auth" ]'
  run bash "$d/deploy.sh" --all --exclude x; ok S-036 "--all --exclude chuyen tiep" '[ "$OUT" = "ARGS:--all --exclude x" ]'; }; fi
# ---- S-011 deploy_local.sh
if want S-011; then S="$R/infra/ops/deploy_local.sh"
  run bash "$S" --help; ok S-011 "--help rc0" '[ $RC = 0 ] && grep -q "deploy_local" <<<"$OUT"'
  run bash "$S" --bogus; ok S-011 "tuy chon la -> rc2" '[ $RC = 2 ]'
  if flock -n /tmp/tradingsys-deploy.lock true 2>/dev/null; then   # kiem tra tham so nam SAU khoa deploy: khoa ban (phien khac dang deploy) => timeout, khong phai loi script
  run bash "$S" --check; ok S-011 "khong chi dinh service -> rc1" '[ $RC = 1 ] && grep -q "chưa chỉ định" <<<"$OUT"'
  run bash "$S" --check dich-vu-ao; ok S-011 "service khong co trong compose -> rc1" '[ $RC = 1 ] && grep -q "không có trong compose" <<<"$OUT"'
  else skip S-011 "kiem tra tham so (--check khong service / service ao): khoa deploy dang ban boi phien khac"; fi
  if flock -n /tmp/tradingsys-deploy.lock true 2>/dev/null && loadok; then TMO=300 run bash "$S" --check --skip-tests auth; ok S-011 "--check --skip-tests auth (dry-run: compose config + 0-byte/conflict/JSON/YAML/compile py3.12 + bash -n): rc0" '[ $RC = 0 ] && grep -q "kiểm tra OK" <<<"$OUT"'
  else skip S-011 "--check that: deploy khac dang giu khoa hoac load cao"; fi
  skip S-011 "PHAN CHUA PHU: build/up/healthy/rollback/smoke-gate/ghi release that (khong deploy). Da doc ma: rollback_svc, FORCE_SMOKE_FAIL, kiem tarball gzip -t"; fi
# ---- S-009 ci_vps.sh : ruff loi phai lam CI do
if want S-009; then d="$W/t9"; mkdir -p "$d/infra/ops" "$d/tests/e2e"; printf '#!/bin/sh\necho "=== x"; echo "1 passed"\n' > "$d/infra/ops/run_tests.sh"; : > "$d/tests/e2e/static_readonly_scan.py"
  run env PATH="$STUB:$PATH" TS_ROOT="$d" CI_OUT="$d/ci" bash "$R/infra/ops/ci_vps.sh" quick; ok S-009 "ruff that bai (docker gia lap) -> CI thoat !=0" '[ $RC != 0 ]'
  skip S-009 "PHAN CHUA PHU: chay that ruff/pytest 15 package/trivy/syft (qua nang; chi kiem logic thoat)"; fi
# ---- S-029 / S-030 run_tests / run_rt_tests
if want S-029; then ok S-029 "khong sao chep data/ (52GB) vao container: run_rt_tests dung tar --exclude nhu run_tests" 'grep -q -- "--exclude=./data" "$R/infra/ops/run_rt_tests.sh"'
  skip S-029 "PHAN CHUA PHU: chay pytest api-gateway that (pip install qua mang, nang)"; fi
if want S-030; then if loadok; then TMO=420 run sh "$R/infra/ops/run_tests.sh" common; ok S-030 "pytest libs/common trong container tam (that): rc0 + 'passed'" '[ $RC = 0 ] && grep -q passed <<<"$OUT"'; else skip S-030 "load cao"; fi; fi
# ---- S-031 smoke.sh
if want S-031; then ok S-031 "phu thuoc ton tai: s_smoke.mjs, s_user.py, auth_testacct.py, anh playwright" '[ -f "$R/tests/qa/s_smoke.mjs" ] && [ -f "$R/tests/qa/s_user.py" ] && [ -f "$R/services/client-ui/qa/auth_testacct.py" ] && docker image inspect mcr.microsoft.com/playwright:v1.49.0-jammy >/dev/null 2>&1'
  if [ "${RUN_SMOKE:-0}" = 1 ]; then TMO=500 run bash "$R/infra/ops/smoke.sh"; ok S-031 "smoke.sh chay that (RUN_SMOKE=1): rc0 'SMOKE XANH', tai khoan thu da xoa" '[ $RC = 0 ] && grep -q "SMOKE XANH" <<<"$OUT"'
  else skip S-031 "chay that (tao tai khoan thu + Playwright 3 vai, ~2-3 phut, khoa flock rieng): bat bang RUN_SMOKE=1; lan 2026-10-16 07:38 UTC: XANH 233 kiem tra/0 loi"; fi; fi
# ---- S-034 trivy_scan.sh
if want S-034; then skip S-034 "chay that: quet moi image (docker save + trivy, nang, keo image). Da kiem bash -n va doc ma; top_cves.py (S-033) test rieng"; fi
# ---- S-001 auth_bootstrap_master.sh
if want S-001; then S="$R/infra/ops/auth_bootstrap_master.sh"
  run bash "$S" --name 'Bad!'; ok S-001 "ten master sai (chu hoa/ky tu la) -> rc2" '[ $RC = 2 ]'
  run bash "$S" --bogus; ok S-001 "doi so la -> rc2" '[ $RC = 2 ]'
  skip S-001 "PHAN CHUA PHU: bootstrap/--reset that (tao/doi mat khau master, ghi <SECRETS_DIR>) - khong chay tren he thong that"; fi
# ---- S-005 backup_offsite.sh
if want S-005; then d="$W/t5"; mkdir -p "$d/b" "$d/dest" "$d/st"; for i in 1 2 3; do echo "dump$i" > "$d/b/ts-2026101${i}T000000Z.dump.enc"; (cd "$d/b" && sha256sum "ts-2026101${i}T000000Z.dump.enc" > "ts-2026101${i}T000000Z.dump.enc.sha256"); done; echo c > "$d/b/ts-config-20261013T000000Z.tar.gz.enc"
  E="env BACKUP_DIR=$d/b STATE_DIR=$d/st OFFSITE_LOG=$d/log OFFSITE_KEEP=2 RCLONE_CONFIG=$d/rc.conf"
  run $E bash "$R/infra/ops/backup_offsite.sh"; ok S-005 "chua cau hinh DEST -> DRY-RUN rc0, status disabled, liet ke file" '[ $RC = 0 ] && grep -q "DRY-RUN" <<<"$OUT" && grep -q "^disabled" "$d/st/offsite.status"'
  run $E OFFSITE_DEST="$d/dest" bash "$R/infra/ops/backup_offsite.sh"; ok S-005 "co DEST nhung chua --apply -> van dry-run, khong copy" '[ $RC = 0 ] && [ -z "$(ls "$d/dest")" ]'
  if command -v rclone >/dev/null; then echo old > "$d/dest/ts-20200101T000000Z.dump.enc"
    run $E OFFSITE_DEST="$d/dest" bash "$R/infra/ops/backup_offsite.sh" --apply; ok S-005 "--apply (rclone local): copy 2 ban moi + sha256 + config, kiem checksum, status ok, xoa ban cu o dich" '[ $RC = 0 ] && [ -f "$d/dest/ts-20261013T000000Z.dump.enc" ] && [ -f "$d/dest/ts-20261012T000000Z.dump.enc.sha256" ] && [ ! -e "$d/dest/ts-20261011T000000Z.dump.enc" ] && [ ! -e "$d/dest/ts-20200101T000000Z.dump.enc" ] && grep -q "^ok" "$d/st/offsite.status"'
    run $E OFFSITE_DEST="$d/dest" bash "$R/infra/ops/backup_offsite.sh" --apply; ok S-005 "idempotent (chay lai rc0)" '[ $RC = 0 ]'
    echo corrupt > "$d/b/ts-20261013T000000Z.dump.enc"; run $E OFFSITE_DEST="$d/dest" bash "$R/infra/ops/backup_offsite.sh" --apply; ok S-005 "sha256 cuc bo sai -> khong day, rc1, status failed" '[ $RC = 1 ] && grep -q "^failed" "$d/st/offsite.status"'
  else skip S-005 "rclone khong co"; fi
  run $E OFFSITE_KEEP=abc bash "$R/infra/ops/backup_offsite.sh"; ok S-005 "OFFSITE_KEEP khong phai so -> rc1" '[ $RC = 1 ]'
  skip S-005 "PHAN CHUA PHU: mode rsync/ssh (khong co dich ssh)"; fi
# ---- S-040 backup_watch.sh
if want S-040; then d="$W/t40"; mk_infra "$d"; st="$d/st"; mkdir -p "$st"; now=$(date +%s); echo "$now" > "$st/backup.last_success"; echo "$now" > "$st/restore_test.last_success"
  : > "$CALLS"; run env STATE_DIR="$st" PATH="$STUB:$PATH" bash "$d/infra/backup/backup_watch.sh"; ok S-040 "moi + khong loi -> khong canh bao, ghi backup.prom, rc0" '[ $RC = 0 ] && ! grep -q "exec" "$CALLS" && grep -q "^ts_backup_last_success_timestamp $now" "$st/backup.prom"'
  echo $((now-30*3600)) > "$st/backup.last_success"; echo "failed 1 x" > "$st/restore_test.last_failure"; : > "$CALLS"; run env STATE_DIR="$st" PATH="$STUB:$PATH" bash "$d/infra/backup/backup_watch.sh"
  ok S-040 "backup >26h + restore-test loi -> 2 canh bao qua notify, prom co last_run_failed=1, rc0" '[ $RC = 0 ] && [ "$(grep -c "^exec" "$CALLS")" -ge 2 ] && grep -q "ts_restore_test_last_run_failed 1" "$st/backup.prom"'; fi
# ---- S-041 offsite.sh
if want S-041; then d="$W/t41"; mkdir -p "$d/bk" "$d/st" "$d/dest" "$d/ops"; cp "$R/infra/backup/offsite.sh" "$d/ops/"; echo x > "$d/bk/ts-20261014T000000Z.dump.enc"; echo y > "$d/bk/other.txt"
  run env STATE_DIR="$d/st" bash "$d/ops/offsite.sh" "$d/bk"; ok S-041 "chua cau hinh -> status disabled, rc0" '[ $RC = 0 ] && grep -q "^disabled" "$d/st/offsite.status"'
  run env STATE_DIR="$d/st" bash "$d/ops/offsite.sh"; ok S-041 "thieu doi so -> rc!=0" '[ $RC != 0 ]'
  command -v rclone >/dev/null && { run env STATE_DIR="$d/st" BACKUP_RCLONE_REMOTE="$d/dest" RCLONE_CONFIG="$d/rc" bash "$d/ops/offsite.sh" "$d/bk"; ok S-041 "rclone copy chi *.enc (khong other.txt), status ok" '[ $RC = 0 ] && [ -f "$d/dest/ts-20261014T000000Z.dump.enc" ] && [ ! -e "$d/dest/other.txt" ] && grep -q "^ok" "$d/st/offsite.status"'; }; fi
# ---- S-043 pg_backup.sh (docker gia lap + sandbox)
if want S-043; then d="$W/t43"; mk_infra "$d"; K="$W/k43"; E="env BACKUP_DIR=$d/bk STATE_DIR=$d/st BACKUP_KEY=$K KEEP=2 PATH=$STUB:$PATH ALERT_CONTAINER=khong-co"
  run $E bash "$d/infra/backup/pg_backup.sh"; f=$(cat "$d/st/backup.last_file" 2>/dev/null)
  ok S-043 "dump (gia lap) -> ma hoa AES + sha256 + goi cau hinh ma hoa + state last_success; sinh khoa 0600 neu thieu" '[ $RC = 0 ] && [ -s "$f" ] && (cd "$d/bk" && sha256sum -c "$(basename "$f").sha256" >/dev/null) && ls "$d"/bk/ts-config-*.tar.gz.enc >/dev/null && [ -s "$d/st/backup.last_success" ] && [ "$(stat -c %a "$K")" = 600 ]'
  ok S-043 "giai ma bang khoa duoc, noi dung la dump (4096B), goi cau hinh giai ma ra .env" 'openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass file:$K -in "$f" | wc -c | grep -q 4096 && openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass file:$K -in "$(ls "$d"/bk/ts-config-*.tar.gz.enc | head -1)" | tar tzf - | grep -q infra/.env'
  for i in 1 2 3; do sleep 1; run $E bash "$d/infra/backup/pg_backup.sh" >/dev/null; done
  ok S-043 "retention KEEP=2 (dump va config)" '[ "$(ls "$d"/bk/ts-2*.dump.enc | wc -l)" = 2 ] && [ "$(ls "$d"/bk/ts-config-*.enc | wc -l)" = 2 ]'
  run env BACKUP_DIR="$d/bk" STATE_DIR="$d/st" BACKUP_KEY="$K" KEEP=2 PATH="$STUB:$PATH" STUB_DUMP_FAIL=1 ALERT_CONTAINER=khong-co bash "$d/infra/backup/pg_backup.sh"
  ok S-043 "pg_dump loi -> rc1, ghi backup.last_failure, khong de file .tmp" '[ $RC = 1 ] && [ -e "$d/st/backup.last_failure" ] && ! ls "$d"/bk/*.tmp >/dev/null 2>&1'
  skip S-043 "PHAN CHUA PHU: pg_dump that tren timescaledb (lon, dang co timer 03:10 UTC); xac minh pg_restore -l that"; fi
# ---- S-044 pg_basebackup.sh
if want S-044; then d="$W/t44"; mk_infra "$d"; K="$W/k44"; echo secretkeytest > "$K"; mkdir -p "$d/wal"; touch -d '2020-01-01' "$d/wal/old.gz"
  E="env BACKUP_DIR=$d/bk STATE_DIR=$d/st BACKUP_KEY=$K WAL_DIR=$d/wal PATH=$STUB:$PATH ALERT_CONTAINER=khong-co"
  for i in 1 2 3; do run $E bash "$d/infra/backup/pg_basebackup.sh"; sleep 1; done; touch "$d/wal/new.gz"
  ok S-044 "base backup (gia lap) ma hoa, giu 2 ban moi nhat, WAL cu hon base cu nhat bi xoa, WAL moi giu" '[ $RC = 0 ] && [ "$(ls "$d"/bk/base/base-*.enc | wc -l)" = 2 ] && [ ! -e "$d/wal/old.gz" ] && [ -e "$d/wal/new.gz" ] && [ -s "$d/st/basebackup.last_success" ]'
  run env BACKUP_DIR="$d/bk" STATE_DIR="$d/st" BACKUP_KEY="$K" WAL_DIR="$d/wal" PATH="$STUB:$PATH" ALERT_CONTAINER=khong-co bash -c 'docker(){ return 1; }; export -f docker; exec bash "$0"' "$d/infra/backup/pg_basebackup.sh"
  ok S-044 "pg_basebackup loi -> rc1, khong de .tmp" '[ $RC != 0 ] && ! ls "$d"/bk/base/*.tmp >/dev/null 2>&1'; fi
# ---- S-045 pg_restore_test.sh
if want S-045; then ok S-045 "tinh tuoi dump tu ten file: bieu thuc sed+date hop le (khong bi hong ky tu dieu khien)" 'eval "$(grep "^DT=" "$R/infra/backup/pg_restore_test.sh" | sed "s/; DAGE=.*//")" 2>/dev/null; F=ts-20261014T031000Z.dump.enc; eval "$(grep "^DT=" "$R/infra/backup/pg_restore_test.sh" | sed "s/; DAGE=.*//")"; [ "$DT" = "20261014 03:10:00" ] && date -u -d "$DT" +%s >/dev/null'
  skip S-045 "PHAN CHUA PHU: restore that vao DB tam restore_test (nang, timer hang tuan; khong chay tren DB that)"; fi
# ---- S-046 pitr_restore_test.sh
if want S-046; then skip S-046 "dung container postgres tam tu base backup + WAL (nang, can khoa that); chi kiem tinh + doc ma"; fi
# ---- S-100.. infra/db, host
if want S-100; then run bash "$R/infra/db/apply_migration.sh"; ok S-100 "thieu doi so -> rc!=0 va nhac cach dung" '[ $RC != 0 ] && grep -q "cần đường dẫn" <<<"$OUT"'
  run bash "$R/infra/db/apply_migration.sh" /khong/co/file.sql; ok S-100 "file khong ton tai -> rc!=0, khong ap gi" '[ $RC != 0 ]'
  skip S-100 "PHAN CHUA PHU: ap migration that (thay doi DB)"; fi
if want S-101; then skip S-101 "14 script create_*_role.sh: tao/doi role Postgres + ghi .env (thay doi DB that); chi kiem bash -n + doc ma (idempotent theo mo ta); da chay luc dung role"; fi
if want S-103; then d="$W/t103"; mkdir -p "$d/data"; echo 'x https://abc-def.trycloudflare.com y' > "$d/data/tunnel.log"; run env TS_ROOT="$d" sh "$R/infra/host/tunnel_url.sh"
  ok S-103 "lay URL trycloudflare ghi data/tunnel_url.txt, rc0" '[ $RC = 0 ] && [ "$(cat "$d/data/tunnel_url.txt")" = "https://abc-def.trycloudflare.com" ]'
  echo none > "$d/data/tunnel.log"; run env TS_ROOT="$d" sh "$R/infra/host/tunnel_url.sh"; ok S-103 "khong co URL -> rc1" '[ $RC = 1 ]'; fi
if want S-102; then skip S-102 "install_backup_timer.sh / install_tunnel.sh / ufw_allow_node_exporter.sh can root + systemd/ufw (thay doi may); chi kiem bash -n + doc ma"; fi
# ---- lab/lab-feed scripts
if want S-050; then run bash "$R/mt-agent/lab/chk.sh"; ok S-050 "chk.sh (doc-chi) rc0, co /accounts + streams + khong in token" '[ $RC = 0 ] && grep -q "redis streams" <<<"$OUT" && ! grep -qF "$(sed -n "s/^BRIDGE_ADMIN_TOKEN=//p" "$R/infra/.env")" <<<"$OUT"'; fi
if want S-051; then run bash "$R/mt-agent/lab/chk2.sh"; ok S-051 "chk2.sh (doc-chi) rc0, co cac muc, khong in mat khau redis" '[ $RC = 0 ] && grep -q "\[account_snapshots\]" <<<"$OUT" && ! grep -qF "$(sed -n "s/^REDIS_ADMIN_PASSWORD=//p" "$R/infra/.env")" <<<"$OUT"'; fi
for id in S-052 S-053 S-055 S-069; do want $id && skip $id "script cho LAPTOP (cd /d/Work..., node sftp/ssh qua bastion) - khong dung tren VPS; DEPRECATED tren VPS, giu lai cho phien laptop"; done
want S-054 && skip S-054 "xoay token that + build/recreate mt-bridge + sua .env bang sed -i (mat ACL, ghi ban sao .env vao /root/mtlab/out) - nguy hiem; dung rotate_secret.sh. LEGACY"
want S-056 && skip S-056 "docker run importer tren du lieu that (ghi parquet/DB); can SYM that"
want S-057 && skip S-057 "chay trong container auth, tao/xoa tai khoan MT that - nguy hiem; chi kiem compile"
if want S-060; then d="$W/t60"; mkdir -p "$d"; python3 - "$d" <<'PY'
import sys; p=sys.argv[1]
open(p+"/a.ini","wb").write(b"\xff\xfe"+"[Charts]\r\nMaxBars=1\r\n[Experts]\r\nWebRequest=0\r\nKeep=1\r\n".encode("utf-16-le"))
PY
  run python3 "$R/mt-agent/lab-feed/scripts/patch_ini.py" "$d/a.ini" Experts WebRequest=1 "WebRequestUrl=http://bridge.lab" AllowLiveTrading=0; a=$(sha "$d/a.ini")
  run python3 "$R/mt-agent/lab-feed/scripts/patch_ini.py" "$d/a.ini" Experts WebRequest=1 "WebRequestUrl=http://bridge.lab" AllowLiveTrading=0; b=$(sha "$d/a.ini")
  run python3 "$R/mt-agent/lab-feed/scripts/patch_ini.py" "$d/new.ini" Charts MaxBars=5000
  ok S-060 "patch_ini.py: sua UTF-16 giu phan con lai, them khoa thieu, idempotent, tao file moi" '[ "$a" = "$b" ] && python3 - "$d/a.ini" "$d/new.ini" <<PY2
import sys
t=open(sys.argv[1],"rb").read(); assert t[:2]==b"\xff\xfe"; s=t[2:].decode("utf-16-le")
assert "WebRequest=1" in s and "Keep=1" in s and "AllowLiveTrading=0" in s and "MaxBars=1" in s
assert s.count("[Experts]")==1 and s.count("WebRequest=1")==1
n=open(sys.argv[2],"rb").read()[2:].decode("utf-16-le"); assert "[Charts]" in n and "MaxBars=5000" in n
PY2'; fi
if want S-061; then d="$W/t61"; mkdir -p "$d"; printf 'x\r\n<window>\r\n</window>\r\n' > "$d/c.chr"; printf 'A=1\r\nB=2\r\n' > "$d/s.set"
  run python3 "$R/mt-agent/lab-feed/scripts/patch_chr.py" "$d/c.chr" "$d/s.set"; a=$(sha "$d/c.chr"); run python3 "$R/mt-agent/lab-feed/scripts/patch_chr.py" "$d/c.chr" "$d/s.set"
  ok S-061 "patch_chr.py: chen khoi <expert> truoc <window>, idempotent (chay lai khong nhan doi)" '[ "$(sha "$d/c.chr")" = "$a" ] && [ "$(grep -c "<expert>" "$d/c.chr")" = 1 ] && grep -q "A=1" "$d/c.chr"'
  run python3 "$R/mt-agent/lab-feed/scripts/patch_chr.py" "$d/c.chr" "$d/s.set" --strip; ok S-061 "--strip go khoi expert" '! grep -q "<expert>" "$d/c.chr"'; fi
if want S-062; then d="$W/t62"; mkdir -p "$d"; python3 - "$d" <<'PY' &
import socket,sys,threading
s=socket.socket(); s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1); s.bind(("127.0.0.1",18771)); s.listen(5)
def h(c):
    d=c.recv(100); c.sendall(b"echo:"+d); c.close()
s.settimeout(8)
try:
    while True:
        c,_=s.accept(); threading.Thread(target=h,args=(c,)).start()
except Exception: pass
PY
  sleep 1; (timeout 6 python3 "$R/mt-agent/lab-feed/scripts/tcp-fwd.py" 127.0.0.1 18772 127.0.0.1 18771 &) ; sleep 1.5
  OUT=$(printf hello | timeout 4 python3 -c "
import socket;s=socket.create_connection(('127.0.0.1',18772),3);s.sendall(b'hello');print(s.recv(100).decode())" 2>&1); RC=$?
  ok S-062 "tcp-fwd.py chuyen tiep TCP 127.0.0.1:18772 -> echo-server (hai chieu)" '[ $RC = 0 ] && grep -q "echo:hello" <<<"$OUT"'; wait 2>/dev/null; fi
if want S-063; then d="$W/t63"; mkdir -p "$d"; printf 'TOK=tk\nHM=hm\n' > "$d/e.env"
  python3 - <<'PY' > "$d/srv.py"
print('''
import http.server,json,hmac,hashlib,time
seen=set(); SECRET=b"hm"
class H(http.server.BaseHTTPRequestHandler):
    def log_message(self,*a): pass
    def do_POST(self):
        raw=self.rfile.read(int(self.headers["Content-Length"])); sig=self.headers.get("X-MT-Sig"); b=json.loads(raw)
        if not sig: return self._r(401)
        exp=hmac.new(SECRET,f"{b['ts']}.{b['nonce']}.".encode()+raw,hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig,exp): return self._r(401)
        if b["nonce"] in seen: return self._r(409)
        seen.add(b["nonce"]); self._r(200)
    def _r(self,c): self.send_response(c); self.send_header("Content-Length","0"); self.end_headers()
s=http.server.HTTPServer(("127.0.0.1",18773),H); s.timeout=10
import sys
for _ in range(12): s.handle_request()
''')
PY
  (timeout 15 python3 "$d/srv.py" &) ; sleep 1; run python3 "$R/mt-agent/lab-feed/scripts/hmac_check.py" http://127.0.0.1:18773 acc mt5 "$d/e.env" TOK HM
  ok S-063 "hmac_check.py voi bridge gia lap: 5 kich ban (401/401/401/200/409) rc0, khong in secret" '[ $RC = 0 ] && [ "$(grep -c OK <<<"$OUT")" = 5 ] && ! grep -q "hm" <<<"${OUT//chu_ky/}"'; fi
if want S-064; then : > "$CALLS"; run env ENV_FILE= PATH="$STUB:$PATH" bash "$R/mt-agent/lab-feed/scripts/run-feed.sh"; ok S-064 "run-feed.sh thieu ENV_FILE -> rc!=0 va KHONG xoa container feed (kiem tra truoc khi docker rm)" '[ $RC != 0 ] && ! grep -q "^rm -f mtlab-mt5-feed" "$CALLS"'
  : > "$CALLS"; echo X=1 > "$W/feed.env"; run env ENV_FILE="$W/feed.env" PATH="$STUB:$PATH" bash "$R/mt-agent/lab-feed/scripts/run-feed.sh"; ok S-064 "co ENV_FILE -> docker rm -f + docker run (--restart unless-stopped, mang tradingsys_internal) (docker gia lap)" '[ $RC = 0 ] && grep -q "^run -d --name mtlab-mt5-feed --restart unless-stopped" "$CALLS" && grep -q "network tradingsys_internal" "$CALLS"'; fi
for id in S-065 S-066 S-067 S-068; do want $id && skip $id "chay duoc chi trong container Wine/Xvfb cua terminal MT (xdotool, wine, toa do man hinh 1280x800) - khong co tren host; da kiem bash -n/compile + doc ma"; done
if want S-078; then ok S-078 "start-term.sh.bak-20261014 la ban sao luu cu, khong duoc goi boi script nao" '! grep -rq "start-term.sh.bak" "$R/mt-agent" "$R/infra" --include=*.sh --include=*.yml --include=*.py'; fi
# ---- data/mtlab-hist
if want S-090; then ok S-090 "driver.sh da het tac dung: queue rong, done.txt co ket qua; driver_q.sh thay the" '[ ! -s "$R/data/mtlab-hist/queue.txt" ] && [ -s "$R/data/mtlab-hist/done.txt" ]'; skip S-090 "chay that: docker restart terminal hist + nap DB - khong chay"; fi
if want S-091; then skip S-091 "driver_q.sh: hang doi nhieu terminal (docker restart mtlab-mt5-hist*) - khong chay; queue rong nen khong con viec"; fi
if want S-092; then skip S-092 "loadguard.sh: vong lap vo han dung container mtlab-mt5-hist7..4 khi load>40 - khong chay"; fi
if want S-093; then ok S-093 "takeover.sh co chot an toan (khong kill PID cung 61755/61756 khi chay lai)" 'grep -q "DEPRECATED" "$R/data/mtlab-hist/takeover.sh" && grep -q "exit" <(sed -n 1,6p "$R/data/mtlab-hist/takeover.sh")'; fi
if want S-094; then skip S-094 "runimp.sh (hist): docker run importer tren du lieu that - can SYM"; fi
if want S-095; then run timeout 20 bash "$R/data/mtlab-hist/st.sh"; if grep -q "No such container\|is not running" <<<"$OUT"; then skip S-095 "container mtlab-mt5-hist khong chay (terminal hist da tat): st.sh khong co doi tuong - deprecated cung driver"; else ok S-095 "st.sh (doc-chi) chay" '[ $RC = 0 ]'; fi; fi
if want S-096; then run docker exec tradingsys-data-keeper python -m data_keeper.histload --help; ok S-096 "histload.py --help (trong container data-keeper) rc0" '[ $RC = 0 ] && grep -qi "usage" <<<"$OUT"'; fi
# ---- ops: backfill + class_demo + sql + gatus + manifests
if want S-002; then TMO=240 run bash -c "docker run --rm -v $R/infra/ops:/ops:ro --entrypoint python tradingsys-analytics:latest -m unittest discover -s /ops/tests 2>&1 | tail -4"; ok S-035 "unittest resample_utc (H4/D1 UTC) trong image analytics" 'grep -q "OK" <<<"$OUT"'
  if loadok; then TMO=240 run python3 "$R/infra/ops/backfill_canon_hist.py" --dry-run --symbols US500 --years 1 --tfs H1; ok S-002 "--dry-run US500 1 nam H1: rc0, khong ghi DB" '[ $RC = 0 ]'; else skip S-002 "load cao"; fi; fi
if want S-004; then if loadok; then TMO=240 run python3 "$R/infra/ops/backfill_mt5hist.py" --symbols EURGBP --dry-run; ok S-004 "--dry-run EURGBP: rc0" '[ $RC = 0 ]'; else skip S-004 "load cao"; fi; fi
want S-003 && skip S-003 "can BACKFILL_TOKEN + market-collector (goi nha cung cap ngoai, ghi bars that); chi kiem compile"
want S-006 && skip S-006 "bt_art.sh: docker run pe-research tren du lieu backtest (da DUNG theo CLAUDE.md, du lieu ledger khong con); chi kiem bash -n. DEPRECATED (backtest dung)"
want S-010 && skip S-010 "class_demo.py: chay trong api-gateway, tao job quet/walk-forward that + goi LLM (nang, co trang thai); chi kiem compile"
if want S-008; then d="$W/t8"; run bash -c "docker exec -i -e PGOPTIONS='-c statement_timeout=60000 -c default_transaction_read_only=on' tradingsys-timescaledb-1 psql -U ts -d ts -v ON_ERROR_STOP=1 -X -f - < '$R/infra/ops/check_hist.sql' | head -40"; ok S-008 "check_hist.sql chay doc-chi (read_only transaction) khong loi SQL" '! grep -qi "^ERROR\|psql:" <<<"$OUT"'; fi
if want S-013; then python3 -I - "$R" > "$W/gatus.out" 2>&1 <<'PY'; RC=$?; OUT=$(cat "$W/gatus.out")
import sys,glob,yaml,re
R=sys.argv[1]; svc=set()
for f in glob.glob(R+"/infra/docker-compose*.yml"):
    svc|=set((yaml.safe_load(open(f)) or {}).get("services",{}))
bad=[];names={}
for f in sorted(glob.glob(R+"/infra/ops/gatus.yaml")+glob.glob(R+"/infra/ops/gatus.d/*.yaml")):
    d=yaml.safe_load(open(f)) or {}
    for e in d.get("endpoints",[]) or []:
        for k in ("name","url","conditions"):
            if k not in e: bad.append(f"{f}: thieu {k} ({e.get('name')})")
        n=(e.get("group"),e.get("name"))
        if n in names: bad.append(f"trung ten {n}")
        names[n]=1
        m=re.match(r"^\w+://([a-z0-9-]+)[:/]",e.get("url",""))
        if m and m.group(1) not in svc and m.group(1) not in ("localhost","127"): bad.append(f"{f}: host {m.group(1)} khong phai service compose ({e['name']})")
print("endpoints",len(names)); print("\n".join(bad)); sys.exit(1 if bad else 0)
PY
  ok S-013 "gatus.yaml + gatus.d/*.yaml: yaml hop le, endpoint co name/url/conditions, host la service compose, khong trung ten" '[ $RC = 0 ]'; fi
if want S-024; then python3 -I - "$R" > "$W/m.out" 2>&1 <<'PY'; RC=$?; OUT=$(cat "$W/m.out")
import sys,glob,yaml,re
R=sys.argv[1]; svc=set()
for f in glob.glob(R+"/infra/docker-compose*.yml"):
    svc|=set((yaml.safe_load(open(f)) or {}).get("services",{}))
bad=[]
for mf,name in (("service_env.manifest","env"),("redis_acl_services.manifest","acl")):
    for l in open(f"{R}/infra/ops/{mf}"):
        l=l.rstrip("\r\n")
        if not l or l.startswith("#"): continue
        m=re.match(r"^([a-z0-9-]+):\s*(.*)$",l)
        if not m: bad.append(f"{mf}: dong khong hop le: {l[:60]}"); continue
        if m.group(1) not in svc: bad.append(f"{mf}: service {m.group(1)} khong co trong compose")
        if name=="acl" and m.group(2).count("(")!=m.group(2).count(")"): bad.append(f"{mf}: ngoac khong can: {m.group(1)}")
print("\n".join(bad)); sys.exit(1 if bad else 0)
PY
  ok S-024 "redis_acl_services.manifest + service_env.manifest: cu phap, service ton tai trong compose, ngoac can" '[ $RC = 0 ]'; fi
# ---- tests/e2e, tests/qa, perf: chi tinh
want S-110 && skip S-110 "infra/perf/ab_*.sh: do A/B mot lan (container perf-gw-before/after khong con) -> DEPRECATED; run_bench/run_pageload/run_ws_load can /root/qa-e2e + k6/Playwright (nang) - da kiem bash -n"
want S-120 && skip S-120 "tests/e2e/*: bo test e2e/pentest do agent ts chay (pytest trong container, can tai khoan thu); deploy.sh cua thu muc nay la cho laptop. Chi kiem tinh o day"
want S-121 && skip S-121 "tests/qa/*: cong cu cua cac agent QA khac (Playwright/k6), da chay trong cac vong QA; chi kiem tinh o day"

# ======================= 1b. SCRIPT MOI (2026-10-16: sau 7e8277d) =======================
# ---- S-130 digest.sh + digest.py (sandbox TS_ROOT, LLM gia khong ton tai => xuat ban khong-LLM)
if want S-130; then d="$W/t130"; mkdir -p "$d/docs/handoff" "$d/infra/ops"; (cd "$d" && git init -q && git config user.email q@q && git config user.name q && echo x > a && git add a && git commit -qm t1); cp "$R/infra/ops/status_brief.sh" "$d/infra/ops/"
  run env TS_ROOT="$d" LA_LLM_URL=http://127.0.0.1:1 DIGEST_LLM_TIMEOUT=2 python3 "$R/infra/ops/digest.py"
  ok S-130 "digest.py (sandbox, LLM chet): rc0, sinh DIGEST.md 'khong-LLM', co state" '[ $RC = 0 ] && grep -q "không-LLM" "$d/docs/handoff/DIGEST.md" && [ -s "$d/data/la/digest_state.json" ]'
  run env TS_ROOT="$d" DIGEST_MAXLOAD=0 LA_LLM_URL=http://127.0.0.1:1 python3 "$R/infra/ops/digest.py"; ok S-130 "digest.py khi load > DIGEST_MAXLOAD: khong crash (rc0)" '[ $RC = 0 ]'
  ok S-130 "digest.sh dung flock + nice + timeout, ghi log vao data/la" 'grep -q "flock -n" "$R/infra/ops/digest.sh" && grep -q "nice -n 19" "$R/infra/ops/digest.sh" && grep -q "timeout" "$R/infra/ops/digest.sh"'; fi
# ---- S-131 tokens_report.py
if want S-131; then d="$W/t131"; mkdir -p "$d/docs/handoff" "$d/data/la"; run env TS_ROOT="$d" TOKENS_PROM="$d/t.prom" python3 "$R/infra/ops/tokens_report.py"
  ok S-131 "tokens_report.py (sandbox): rc0, sinh TOKENS.md + file .prom" '[ $RC = 0 ] && [ -s "$d/docs/handoff/TOKENS.md" ] && [ -s "$d/t.prom" ]'; fi
# ---- S-132 feed_e2e.py (doc-chi: docker exec vao gateway lay /metrics, cua so 1 s)
if want S-132; then if loadok && docker ps --format '{{.Names}}' | grep -q '^tradingsys-api-gateway-1$'; then TMO=60 run python3 "$R/infra/ops/feed_e2e.py" 1
  ok S-132 "feed_e2e.py 1 s (doc-chi): rc0, in 4 nhan tick->hub / bus->hub / tick->queue / hub->browser" '[ $RC = 0 ] && [ "$(grep -cE "^(tick->hub|bus->hub|tick->queue|hub->browser)" <<<"$OUT")" = 4 ]'; else skip S-132 "gateway khong chay hoac load cao"; fi; fi
# ---- S-133 la (local agent CLI) + la_lib.tools (sandbox) + la_bench
if want S-133; then run python3 "$R/infra/ops/la" --help; ok S-133 "la --help liet ke cac lenh con, rc0" '[ $RC = 0 ] && grep -q "fix-lint" <<<"$OUT" && grep -q "issue-fix" <<<"$OUT"'
  run python3 "$R/infra/ops/la" --dry-run commit-msg; ok S-133 "la --dry-run commit-msg: khong goi LLM, rc0" '[ $RC = 0 ] && grep -q "dry-run" <<<"$OUT"'
  run python3 "$R/infra/ops/la" --dry-run stats; ok S-133 "la stats (doc data/la): rc0" '[ $RC = 0 ]'
  d="$W/t133"; mkdir -p "$d"; run python3 -I - "$R/infra/ops" "$d" <<'PY'
import sys, pathlib
sys.path.insert(0, sys.argv[1]); from la_lib import tools
d = pathlib.Path(sys.argv[2]); t = tools.Tools(d, d)
t.write_file("x.txt", "hi")
assert "hi" in t.read_file("x.txt")
for p in ("../evil.txt", "/etc/passwd"):
    try: t.read_file(p); sys.exit("doc ngoai repo khong bi chan: " + p)
    except ValueError: pass
try: t.write_file("../evil.txt", "x"); sys.exit("ghi ngoai repo khong bi chan")
except ValueError: pass
print("OK")
PY
  ok S-133 "la_lib.tools: doc/ghi trong worktree OK; chan ../ va duong dan tuyet doi ngoai repo" '[ $RC = 0 ] && grep -q "^OK" <<<"$OUT" && [ ! -e "$W/evil.txt" ]'; fi
# ---- S-135 llm_node.sh (render vao thu muc tam; KHONG add/remove/reload)
if want S-135; then d="$W/t135"; mkdir -p "$d"; printf 'n1|sv-x|ssh|127.0.0.1:18080|1\n' > "$d/nodes.list"
  run env LLM_DIR="$d" LLM_NODES_FILE="$d/nodes.list" LLM_UPSTREAM_OUT="$d/up.conf" bash "$R/infra/ops/llm_node.sh" render; ok S-135 "render: sinh upstream.nodes.conf trong thu muc tam, rc0" '[ $RC = 0 ] && [ -s "$d/up.conf" ] && grep -q "127.0.0.1:18080" "$d/up.conf"'
  run env LLM_DIR="$d" LLM_NODES_FILE="$d/nodes.list" bash "$R/infra/ops/llm_node.sh" list; ok S-135 "list: in node n1, rc0" '[ $RC = 0 ] && grep -q n1 <<<"$OUT"'
  run bash "$R/infra/ops/llm_node.sh" --dry-run add; ok S-135 "add thieu host -> rc!=0" '[ $RC != 0 ]'
  run bash "$R/infra/ops/llm_node.sh" --dry-run bogus; ok S-135 "lenh la -> rc!=0" '[ $RC != 0 ]'; fi
# ---- S-136 guard.sh
if want S-136; then run sh "$R/infra/local-llm/guard.sh" echo guardok; ok S-136 "load thap -> chay lenh (rc0)" '[ $RC = 0 ] && grep -q guardok <<<"$OUT"'
  run env LLM_MAX_LOAD=0 sh "$R/infra/local-llm/guard.sh" echo guardok; ok S-136 "load > nguong -> tu choi rc75, khong chay" '[ $RC = 75 ] && ! grep -q "^guardok" <<<"$OUT"'; fi
# ---- S-137 merge_old_bars_chunks.sh (docker gia: khong chunk -> khong goi merge_chunks)
if want S-137; then : > "$CALLS"; run env PATH="$STUB:$PATH" bash "$R/infra/ops/merge_old_bars_chunks.sh" 2010 2011; ok S-137 "docker gia, 0 chunk: rc0 va KHONG goi merge_chunks" '[ $RC = 0 ] && ! grep -q merge_chunks "$CALLS"'
  run env PATH="$STUB:$PATH" bash "$R/infra/ops/merge_old_bars_chunks.sh"; ok S-137 "thieu tham so -> rc!=0" '[ $RC != 0 ]'; fi
# ---- S-138 status_brief.sh (doc-chi)
if want S-138; then TMO=60 run bash "$R/infra/ops/status_brief.sh"; ok S-138 "status_brief.sh: rc0, dong t=... load=... up=..., issues open=" '[ $RC = 0 ] && grep -qE "^t=.* load=.* up=" <<<"$OUT" && grep -q "issues open=" <<<"$OUT"'; fi
# ---- S-139 local-llm config + jaeger + dashboard
if want S-139; then ok S-139 "local-llm/config.yaml, jaeger/config.yaml hop le; dashboard local-llm.json la JSON" 'python3 -I -c "import yaml,json,sys;[yaml.safe_load(open(sys.argv[1]+f)) for f in (\"/infra/local-llm/config.yaml\",\"/infra/jaeger/config.yaml\")];json.load(open(sys.argv[1]+\"/infra/grafana/dashboards/local-llm.json\"))" "$R"'; fi
# ---- S-141 EA scripts MQL5 (tinh)
if want S-141; then ok S-141 "EA Scripts MQL5 (FeedProbe, MTAgentDealFixture, MTAgentExport, MTAgentRange) co OnStart" 'for f in FeedProbe MTAgentDealFixture MTAgentExport MTAgentRange; do grep -q "OnStart" "$R/mt-agent/lab-feed/ea/MQL5/Scripts/$f.mq5" || exit 1; done'; fi

# ======================= 2. TONG HOP =======================
python3 - "$RES" "$INV" "$MD" <<'PY'
import sys, collections
res = collections.defaultdict(list)
for l in open(sys.argv[1], encoding="utf-8"):
    i, st, note = (l.rstrip("\n").split("\t") + ["", ""])[:3]
    res[i].append((st, note))
inv = []
for l in open(sys.argv[2], encoding="utf-8"):
    if l.strip() and not l.startswith("#"):
        p = l.rstrip("\n").split("|")
        inv.append((p[0], p[1], p[2], p[3]))
rows = []; cnt = collections.Counter()
for i, path, dep, desc in inv:
    r = res.get(i, [])
    if not r: continue
    fails = [n for s, n in r if s == "FAIL"]
    passes = [n for s, n in r if s == "PASS"]
    skips = [n for s, n in r if s == "SKIP"]
    nstatic = sum(1 for s, n in r if s == "STATIC")
    if fails: v = "FAIL"
    elif passes: v = "PASS"
    elif skips: v = "BỎ QUA"
    else: v = "PASS(tĩnh)" if nstatic else "?"
    if v == "PASS" and skips: v = "PASS*"          # co phan chua phu
    cnt[v] += 1
    note = "; ".join(fails[:3]) if fails else ("; ".join(skips[:2]) if skips else "")
    rows.append((i, v, dep, path, f"{len(passes)}p/{len(fails)}f/{nstatic}t", note))
print(f"{'ID':6} {'KẾT QUẢ':11} {'NHÃN':10} {'ĐỐI TƯỢNG':58} {'TEST':9} GHI CHÚ")
for r in rows: print(f"{r[0]:6} {r[1]:11} {r[2]:10} {r[3][:58]:58} {r[4]:9} {r[5][:150]}")
tot = len(rows)
print(f"\nTỔNG {tot} mục: " + ", ".join(f"{k}={v}" for k, v in sorted(cnt.items())) + "   (PASS*: pass nhưng có phần chưa phủ; xem BỎ QUA/ghi chú; test chi tiết:",
      sum(1 for v in res.values() for s, _ in v if s in ("PASS", "FAIL")), "kiểm chứng)")
if sys.argv[3] == "1":
    print("\n| ID | Kết quả | Nhãn | Đối tượng | Chi tiết test | Ghi chú |\n|---|---|---|---|---|---|")
    for r in rows: print(f"| {r[0]} | {r[1]} | {r[2]} | `{r[3]}` | {r[4]} | {r[5].replace('|','/')} |")
sys.exit(1 if cnt.get("FAIL") else 0)
PY
exit $?
