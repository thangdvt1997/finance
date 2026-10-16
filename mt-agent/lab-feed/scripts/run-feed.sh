#!/bin/bash
# Tao lai container mtlab-mt5-feed (cpus 32 + cpu_shares 4096: uu tien toc do gia realtime). Chay bang root/cc co docker.
# Dung: ENV_FILE=<env600 co MT_LOGIN,MT_SERVER,MT_PASSWORD(investor),MT_PAIRCODE> ./run-feed.sh   (KHONG ghi secret vao repo)
# Tinh chinh tre: FEED_SCAN_MS (20) FEED_FLUSH_MS (100) FEED_MSG_PER_SEC (10) la env cua container (mac dinh trong start-feed.sh).
set -e
R=/root/trading-system/mt-agent
: "${ENV_FILE:?can ENV_FILE}"   # kiem tra TRUOC khi xoa container dang chay
[ -f "$ENV_FILE" ] || { echo "ENV_FILE khong ton tai: $ENV_FILE" >&2; exit 1; }
docker rm -f mtlab-mt5-feed 2>/dev/null || true
docker run -d --name mtlab-mt5-feed --restart unless-stopped --cpus 32 --cpu-shares 4096 --memory 3g --shm-size 512m \
  --network tradingsys_internal --env-file "${ENV_FILE:?can ENV_FILE}" \
  -v mtlab_feedwine:/wine -v $R/lab-feed/scripts:/mtlab:ro -v /root/mtlab/dl:/dl:ro -v $R/lab-feed/ea:/ea:ro \
  -v $R/MQL5:/feedsrc:ro -v $R/lab-feed/out:/out mtlab-wine:9
