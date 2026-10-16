#!/usr/bin/env bash
# Quét CVE HIGH/CRITICAL cho mọi image của stack compose project `tradingsys` + image nền (python:3.12-slim).
# Chạy bằng container aquasec/trivy (không cài gì lên host). Mỗi image được `docker save` ra file tạm rồi quét
# (KHÔNG mount docker.sock vào container quét). Cache DB ở volume `tradingsys-trivy-cache`.
# Dùng:  ./trivy_scan.sh [thư_mục_báo_cáo]     (mặc định /var/tmp/tradingsys-trivy)
# Kết quả: <dir>/<image>.json + <dir>/summary.txt (bảng gọn). Thoát 0 dù có CVE (chỉ báo cáo).
set -euo pipefail
TRIVY_IMAGE="${TRIVY_IMAGE:-aquasec/trivy:0.75.0}"
PROJECT="${COMPOSE_PROJECT_NAME:-tradingsys}"
OUT="${1:-/var/tmp/tradingsys-trivy}"
EXTRA_IMAGES="${EXTRA_IMAGES:-python:3.12-slim}"
mkdir -p "$OUT"; chmod 700 "$OUT"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT

mapfile -t IMAGES < <({ docker ps -a --filter "label=com.docker.compose.project=${PROJECT}" --format '{{.Image}}' | sed -E 's#^([^:@]+)$#\1:latest#'
                        docker images --format '{{.Repository}}:{{.Tag}}' | grep -E "^${PROJECT}-" || true
                        for i in $EXTRA_IMAGES; do echo "$i"; done; } | grep -v '<none>' | sort -u)
echo "Quét ${#IMAGES[@]} image bằng ${TRIVY_IMAGE}"
docker volume create tradingsys-trivy-cache >/dev/null
rm -f "$OUT"/*.json "$OUT/summary.txt"
for img in "${IMAGES[@]}"; do
  safe="$(echo "$img" | tr '/:@' '___')"
  docker image inspect "$img" >/dev/null 2>&1 || docker pull -q "$img" >/dev/null
  docker save "$img" -o "$TMP/$safe.tar"
  docker run --rm -v tradingsys-trivy-cache:/root/.cache -v "$TMP:/in:ro" -v "$OUT:/out" "$TRIVY_IMAGE" \
    image --quiet --input "/in/$safe.tar" --scanners vuln --severity HIGH,CRITICAL --ignore-unfixed=false \
    --format json --output "/out/$safe.json" >/dev/null 2>"$TMP/err" || { echo "LỖI quét $img: $(tail -2 "$TMP/err")"; }
  rm -f "$TMP/$safe.tar"
  echo "  xong: $img"
done
python3 - "$OUT" > "$OUT/summary.txt" <<'PY'
import json, glob, os, sys
out = sys.argv[1]
print(f"{'IMAGE':58} {'OS':18} {'CRIT':>4} {'HIGH':>4} {'FIXABLE':>7}")
for f in sorted(glob.glob(os.path.join(out, "*.json"))):
    try:
        d = json.load(open(f))
    except Exception:
        continue
    name = os.path.basename(f)[:-5]  # tên file = image đã đổi / : @ thành _
    os_ = (d.get("Metadata", {}).get("OS") or {})
    c = h = fx = 0
    for r in d.get("Results") or []:
        for v in r.get("Vulnerabilities") or []:
            if v["Severity"] == "CRITICAL": c += 1
            elif v["Severity"] == "HIGH": h += 1
            if v.get("FixedVersion"): fx += 1
    print(f"{name[:58]:58} {(os_.get('Family','?')+' '+os_.get('Name',''))[:18]:18} {c:>4} {h:>4} {fx:>7}")
PY
cat "$OUT/summary.txt"
