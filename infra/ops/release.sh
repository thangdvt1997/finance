#!/bin/sh
# Quản lý release trên VPS (chạy bởi deploy.sh). Chỉ động vào tài nguyên tradingsys.
#   release.sh snapshot            gắn tag rel-<VER hiện tại> cho các image tradingsys-*:latest (trước khi build đè)
#   release.sh record VER HASH NOTE  ghi .release + lưu tarball /root/ts.tgz vào kho release, dọn bản cũ, ghi dấu release
#   release.sh list                liệt kê release
#   release.sh current
ROOT="${TS_ROOT:-/root/trading-system}"
REL_DIR="${REL_DIR:-/root/trading-system-releases}"
KEEP="${KEEP_RELEASES:-5}"
KEEP_IMG="${KEEP_IMAGE_RELEASES:-3}"
cur() { [ -f "$ROOT/.release" ] && sed -n 's/^version=//p' "$ROOT/.release" | head -1 || echo none; }
case "$1" in
  snapshot)
    V=$(cur); [ "$V" = none ] && V=pre-versioning
    for img in $(docker images --format '{{.Repository}}' | grep '^tradingsys-' | sort -u); do
      docker image inspect "$img:latest" >/dev/null 2>&1 && docker tag "$img:latest" "$img:rel-$V"
    done
    # giữ KEEP_IMG tag rel-* mới nhất cho mỗi image
    for img in $(docker images --format '{{.Repository}}' | grep '^tradingsys-' | sort -u); do
      docker images --format '{{.Tag}}' "$img" | grep '^rel-' | sort -r | tail -n +$((KEEP_IMG + 1)) | while read t; do docker rmi "$img:$t" >/dev/null 2>&1 || true; done
    done
    echo "snapshot images rel-$V" ;;
  record)
    VER="$2"; HASH="$3"; NOTE="$4"; TGZ="${5:-/root/ts.tgz}"
    mkdir -p "$REL_DIR"; chmod 700 "$REL_DIR"
    [ -f "$TGZ" ] || { echo "release.sh: thieu tarball $TGZ - KHONG ghi release (upload bi cat?)" >&2; exit 3; }
    cp "$TGZ" "$REL_DIR/ts-$VER.tgz"
    PREV=$(cur)
    printf 'version=%s\nhash=%s\ndeployed_at=%s\nprevious=%s\nnote=%s\ndeployer=%s\n' \
      "$VER" "$HASH" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$PREV" "$NOTE" "${SUDO_USER:-root}" > "$ROOT/.release.new.$$" && mv "$ROOT/.release.new.$$" "$ROOT/.release"
    cp "$ROOT/.release" "$REL_DIR/$VER.release"
    ls -1t "$REL_DIR"/ts-*.tgz 2>/dev/null | tail -n +$((KEEP + 1)) | xargs -r rm -f --
    echo "release $VER (prev $PREV) recorded; $(ls -1 "$REL_DIR"/ts-*.tgz | wc -l) tarball giữ" ;;
  list) ls -1t "$REL_DIR"/ts-*.tgz 2>/dev/null; echo "current: $(cur)" ;;
  current) cur ;;
  *) echo "usage: release.sh snapshot|record VER HASH NOTE|list|current" >&2; exit 2 ;;
esac
