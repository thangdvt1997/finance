#!/bin/sh
# IJ-I: tạo master thử qa-stab-ij -> chạy ij_load.py -> xoá. Dùng: ij_run.sh [USERS] [SECONDS]
SRC="$(cd "$(dirname "$0")" && pwd)"; MU="$SRC/../../services/web-ui/qa/master_user.py"; N=qa-stab-ij
docker exec -i tradingsys-auth python - delete $N < "$MU" >/dev/null 2>&1 || true
PW=$(docker exec -i tradingsys-auth python - create $N < "$MU") || exit 2
IJ_USER=$N IJ_PASS=$PW python3 "$SRC/ij_load.py" "${BASE:-http://127.0.0.1:8580}" "${1:-30}" "${2:-90}"; RC=$?
docker exec -i tradingsys-auth python - delete $N < "$MU" >/dev/null 2>&1
exit $RC
