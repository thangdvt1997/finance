# infra

Hạ tầng chạy toàn bộ nền tảng bằng Docker Compose: Redis (AOF), TimescaleDB, Prometheus, Grafana + các service (hiện 36 container, xem `docs/KIEN_TRUC.md`; nội dung cũ: 15 service; xem `docs/HARDENING.md`, `docs/OBSERVABILITY.md`). Thực tế dùng 3 file compose (`COMPOSE_FILE=docker-compose.yml:docker-compose.ops.yml:docker-compose.tools.yml` trong `.env`).

## Cấu trúc
- `docker-compose.yml` – lõi stack. Mạng (từ 2026-10-12): `backend` (DB/Redis, internal), `ops` (HTTP nội bộ + metrics, internal), `frontend` (cổng publish), `internal` (đường ra internet + mt-agent lab), `socketproxy`; chỉ publish Grafana (`GRAFANA_PORT`, mặc định 3000) và api-gateway (`GATEWAY_PORT`, mặc định 8080), cả hai bind `127.0.0.1` theo mặc định. Redis/DB/Prometheus KHÔNG publish.
- `db/schema.sql` – schema, tự chạy ở lần khởi tạo DB đầu tiên; `db/migrations/*.sql` – migration bổ sung (hiện có `001_alerts_event_id`, cần cho storage-writer). Migration mới: thêm file và mount thêm vào compose, hoặc chạy tay `docker compose exec -T timescaledb psql -U ts -d ts < file.sql` (các file đều idempotent).
- `prometheus/prometheus.yml` – scrape `/metrics` của 18 service Python + exporter (port 8000 nội bộ; 7 service là số lúc đầu).
- `grafana/provisioning` – datasource Prometheus (`prom`) + TimescaleDB (`pg`); `grafana/dashboards` – "Platform health", "Market overview".
- `backup/pg_backup.sh` – pg_dump định kỳ, giữ 14 ngày.
- `.env.example` – danh sách biến môi trường.

## Chạy local (cần Docker)
```bash
cd infra
cp .env.example .env      # đổi POSTGRES_PASSWORD, GRAFANA_ADMIN_PASSWORD, API_TOKEN
docker compose config -q  # kiểm tra cú pháp
docker compose up -d --build
docker compose ps
# Grafana: http://localhost:3000
```
Mỗi service được build từ `services/<name>/Dockerfile` với context là thư mục gốc repo (Dockerfile phải `COPY libs/common` — xem mẫu `services/storage-writer/Dockerfile`).

Sau khi sửa schema trên DB đã có dữ liệu: init script KHÔNG chạy lại; hãy áp migration bằng tay.

## Triển khai lên VPS Linux <VPS_IP> (hướng dẫn BAN ĐẦU — nay ĐÃ deploy tại /root/trading-system; dùng `./deploy.sh` thay vì lệnh `docker compose` trực tiếp, xem docs/VAN_HANH.md mục 4)
1. Cài Docker Engine + compose plugin (`curl -fsSL https://get.docker.com | sh`), tạo user không root thuộc nhóm `docker`.
2. Lấy mã nguồn: `git clone <repo> /opt/trading-system` (hoặc rsync). `cd /opt/trading-system/infra && cp .env.example .env`, điền mật khẩu mạnh (`openssl rand -base64 24`). `chmod 600 .env`.
3. Firewall (ufw): chỉ mở SSH + 443 nếu có reverse proxy; KHÔNG mở 3000/8080/5432/6379/9090 ra internet. Giữ `GRAFANA_BIND`/`GATEWAY_BIND`=127.0.0.1 và truy cập qua SSH tunnel (`ssh -L 3000:localhost:3000 user@<VPS_IP>`) hoặc đặt Caddy/nginx + TLS phía trước.
   Lưu ý: Docker publish port bỏ qua ufw nếu bind 0.0.0.0, nên cứ bind 127.0.0.1.
4. `docker compose up -d --build`; kiểm tra `docker compose ps`, `docker compose logs -f storage-writer`.
5. Backup: `crontab -e` -> `0 3 * * * /opt/trading-system/infra/backup/pg_backup.sh >> /var/log/ts-backup.log 2>&1`. Nên rsync thư mục `/var/backups/trading-system` sang máy khác. Thử khôi phục định kỳ.
6. Cập nhật: `git pull && docker compose up -d --build`. Rollback: checkout tag cũ rồi up lại. Dữ liệu nằm trong volume `pg-data`, `redis-data`.
7. Theo dõi: dashboard "Platform health" (service up, lag, lỗi, dlq). Stream `dlq` chứa event lỗi: `docker compose exec redis redis-cli XRANGE dlq - + COUNT 10`.

## Ghi chú vận hành
- Redis dùng `noeviction` + AOF everysec; stream bị cắt ở ~100k entry/stream (Bus.maxlen) nên bộ nhớ có giới hạn.
- Image Postgres: `timescale/timescaledb:latest-pg16`; nên pin version cụ thể khi lên production.

## Vận hành (ops)
- **Alerting**: `docker-compose.ops.yml` thêm Alertmanager + luật `prometheus/rules.yml` (service down, lag/pending, không có md.bars, lỗi DB/Redis, dlq, disk/RAM host qua node_exporter có sẵn). Chạy: `docker compose -p tradingsys --env-file .env -f docker-compose.yml -f docker-compose.ops.yml up -d` (hoặc `COMPOSE_FILE=docker-compose.yml:docker-compose.ops.yml` trong `.env`). Đường đi: Prometheus -> Alertmanager -> `alert-service /webhook/alertmanager` -> `alerts.out` -> Telegram + bảng `alerts`. Scrape node_exporter cần `host/ufw_allow_node_exporter.sh` (ufw INPUT DROP).
- **Backup**: `backup/pg_backup.sh` (pg_dump -Fc từ container, giữ 7 bản ở `<repo>/backups`, chmod 700/600), timer `tradingsys-backup.timer` 03:10 UTC (`host/install_backup_timer.sh`). Thử khôi phục vào DB tạm: `backup/pg_restore_test.sh`. Redis: AOF trong volume `redis-data` (bus tạm).
- **Truy cập từ xa**: `host/install_tunnel.sh` cài unit `tradingsys-tunnel.service` (cloudflared quick tunnel -> `TUNNEL_TARGET`, mặc định web-ui `127.0.0.1:8580`, URL ghi vào `data/tunnel_url.txt`). Mặc định KHÔNG bật; chỉ `--start` khi web-ui đã có basic auth.
- **DB read-only**: `db/create_readonly_role.sh` tạo role `ts_ro` (SELECT only, read_only mặc định, statement_timeout 15s) và thêm `POSTGRES_RO_PASSWORD` vào `.env`. api-gateway chỉ SELECT nên nên dùng `DATABASE_URL: postgresql://ts_ro:${POSTGRES_RO_PASSWORD}@timescaledb:5432/${POSTGRES_DB:-ts}`.
- **Bảo mật**: không port nào của stack bind 0.0.0.0 (chỉ 127.0.0.1: grafana, gateway, mt-bridge); Redis có ACL theo user (`ts_app`, `ts_gateway`, `ts_admin`, `ts_cache`, `ts_metrics`; từ 2026-10-12, xem docs/HARDENING.md) và chỉ ở mạng `backend` (internal); `.env` chmod 600.

## Công cụ OSS vận hành (OSS_REUSE quick wins, 2026-10-11)
Bật bằng `COMPOSE_FILE=docker-compose.yml:docker-compose.ops.yml:docker-compose.tools.yml` trong `infra/.env` (đã đặt trên VPS) hoặc `-f` cả 3 file. Mọi cổng chỉ bind `127.0.0.1` (biến `OPS_BIND`); truy cập qua SSH tunnel: `ssh -L 8590:127.0.0.1:8590 -L 8591:127.0.0.1:8591 -L 8592:127.0.0.1:8592 <vps>`.

| Cổng host | Container | Mô tả |
|---|---|---|
| 8590 | `tradingsys-gatus` | Gatus: kiểm `/healthz` 7 service + web-ui + TCP Redis/Timescale + Prometheus/Alertmanager/Grafana (`ops/gatus.yaml`, `ops/gatus.d/*.yaml`); `/metrics` Prometheus; cảnh báo -> `alert-service /webhook/alertmanager`. Tên khác `gatus` (hệ thống khác trên host). |
| 8591 | `tradingsys-dozzle` | Dozzle xem log; chỉ nói chuyện với `tradingsys-docker-socket-proxy` (docker.sock `:ro`, chỉ GET containers/events/info/version; POST/exec/images bị chặn), lọc `label=com.docker.compose.project=tradingsys`, tắt actions/shell. |
| 8592 | `tradingsys-ntfy` | ntfy nội bộ, topic `tradingsys-alerts`, kênh dự phòng qua Apprise (`APPRISE_URLS=ntfy://ntfy:80/tradingsys-alerts` trong `.env`). Xem tin: `curl 127.0.0.1:8592/tradingsys-alerts/json?poll=1&since=all`. |

- **Apprise**: alert-service đọc `APPRISE_URLS` (phẩy phân tách; Telegram/ntfy/Slack/Discord/email), xem `services/alert-service/README.md`.
- **Quét CVE**: `ops/trivy_scan.sh` (container `aquasec/trivy`), báo cáo `docs/SECURITY_SCAN.md`. **Renovate**: `renovate.json` ở gốc repo; bật bằng cách cài GitHub App "Renovate" (miễn phí) cho repo hoặc chạy self-host `docker run --rm -e RENOVATE_TOKEN=... -e RENOVATE_REPOSITORIES=<org/repo> renovate/renovate`; PR đầu tiên là "Configure Renovate"/Dependency Dashboard.
- **SOPS+age** (chưa bắt buộc): `ops/sops_encrypt_env.sh init|encrypt|decrypt`; khóa riêng không commit.
- **Nâng phiên bản** image nằm trong `docker-compose.ops.yml` (override), không sửa compose chính. Lưu ý: `up` chỉ với `docker-compose.yml` sẽ ĐẢO NGƯỢC nâng cấp (compose tạo lại container theo image cũ); luôn dùng `COMPOSE_FILE` như trên.


## Hardening vòng 3 (2026-10-11) — tóm tắt vận hành
Chi tiết kỹ thuật: `docs/CONTRACTS.md` (mục "Hardening vòng 3"), DR: `docs/DR_RUNBOOK.md`, CI: `docs/CI_CD.md`.
- **Release & rollback**: `./deploy.sh "<lệnh compose>"` (từ laptop) ghi `/root/trading-system/.release` (version, hash, thời gian, bản trước), giữ 5 tarball ở `/root/trading-system-releases/` và gắn tag image `tradingsys-*:rel-<VER-trước>`. Rollback: `sh infra/ops/rollback.sh [VER]` rồi `SERVICES="svc..." sh infra/ops/rollback.sh` (hoặc `docker compose ... up -d --no-build --no-deps <svc>`). `sh infra/ops/release.sh list|current`.
- **Backup**: timer `tradingsys-backup` (03:10 UTC; dump `-Fc` MÃ HOÁ openssl AES-256, khoá `/root/.tradingsys-backup.key` — PHẢI sao ra ngoài VPS), `tradingsys-basebackup` (CN 02:30, base backup vật lý), `tradingsys-restoretest` (CN 04:30: restore-test sâu + diễn tập PITR), `tradingsys-backupwatch` (mỗi giờ: cảnh báo nếu backup >26h/restore-test >8 ngày/off-site cũ). WAL archiving bật (`archive_mode=on`, `/root/trading-system/wal-archive`, `archive_timeout=300`). Off-site: điền `infra/backup/offsite.env` (xem `.example`). Cài/cập nhật timer: `sudo bash infra/host/install_backup_timer.sh`.
- **Redis**: ACL (user riêng, `default` tắt) — `infra/ops/redis_acl_render.sh`; `redis-cli` thủ công: `docker exec tradingsys-redis-1 redis-cli --user ts_admin --no-auth-warning ...` (container có sẵn `REDISCLI_AUTH`). Redis `maxmemory 4gb` (noeviction).
- **DB role**: `infra/db/create_writer_role.sh` (ts_writer). **Container**: compose anchor `x-service` có `read_only`, `cap_drop ALL`, `no-new-privileges`, `pids_limit 256`, `mem_limit 1g`, `cpus 2`; user 10001 cho storage-writer/news/expert; market-collector dùng volume `mc-data` (`HOME=/data/home`).
- **web-ui nginx**: `real_ip` từ `CF-Connecting-IP` (tin các dải docker/loopback), xác thực qua `auth_request` tới server nội bộ `:8081` với giới hạn đăng nhập sai ~10/phút/IP (403 khi vượt), thêm HSTS/COEP. Authelia/Caddy: xem `docs/CI_CD.md` phụ lục "Đăng nhập mạnh".
- **Test/CI**: `sh infra/ops/run_tests.sh common storage-writer ...` (pytest trong container, trên VPS); `sh infra/ops/ci_vps.sh [quick]` (ruff + pytest + quét tĩnh + trivy + SBOM syft); lockfile có hash `services/*/requirements.lock` (`infra/ops/lock_deps.sh`).
- **Cảnh báo giả**: `MtAccountDisconnected` chỉ báo tài khoản đã gửi dữ liệu trong 24h qua.

## Vòng 4 (2026-10-12): hardening nốt, tách secret/mạng, observability, retention
Tài liệu chi tiết: `docs/HARDENING.md` (container/secret/mạng, ngoại lệ), `docs/OBSERVABILITY.md` + `docs/SLO.md` (exporter, dashboard, luật burn-rate, trace), `docs/DATA_RETENTION.md` (nén/retention/cagg), `docs/DR_RUNBOOK.md`.
- **Container**: 100% container tradingsys không root (trừ docker-socket-proxy/cadvisor/textfile-exporter, ghi lý do), read-only FS, cap_drop ALL, giới hạn mem/cpu/pids, log xoay vòng. Kiểm: `sh infra/ops/hardening_audit.sh`.
- **Secret**: `infra/ops/service_env.manifest` + `bash infra/ops/gen_service_env.sh [--report]` -> `infra/env/<svc>.env` (0600). `deploy.sh` tự gọi. Không còn `env_file: .env` toàn bộ.
- **Mạng**: xem bảng trong `docs/HARDENING.md`. Container tạm (e2e, restore test) phải `docker network connect tradingsys_backend|ops|...` tương ứng (xem `tests/e2e/run_remote.sh`). Tên mạng thật: `tradingsys_backend`, `tradingsys_ops`, `tradingsys_frontend`, `tradingsys_internal`.
- **Giám sát mới** (docker-compose.ops.yml): `postgres-exporter` (role `ts_monitor`: `bash infra/db/create_monitor_role.sh`), `redis-exporter` (ACL `ts_metrics`: `DEFAULT_OFF=1 bash infra/ops/redis_acl_render.sh`), `textfile-exporter` (backup), `cadvisor`, `jaeger` (UI `127.0.0.1:16686`). Luật: `prometheus/rules_slo.yml` (40 luật). Dashboard sinh bằng `python infra/grafana/gen_dashboards.py`. Gatus: `ops/gatus.d/platform.yaml`.
- **Retention/nén**: `bash infra/db/apply_migration.sh migrations/009_retention_compression.sql` (đã áp).
- **Lockfile**: mọi service Python (trừ journal) có `requirements.lock`; Dockerfile `--require-hashes --only-binary` + base digest. Sinh lại: `sh infra/ops/lock_deps.sh <svc>`.
- **CI VPS**: `sh infra/ops/ci_vps.sh` (ruff + pytest 14 package + quét tĩnh + trivy + SBOM). Kết quả gần nhất: `docs/SECURITY_SCAN.md`.

## Vòng hoàn thiện (2026-10-14): bảng vận hành hiện tại
Bảng cổng/container/volume/timer đầy đủ: `docs/VAN_HANH.md` mục 16. Tóm tắt:
- Cổng host (127.0.0.1): web-ui 8580, client-ui 8581, api-gateway 8480, mt-bridge 8490, grafana 3300, gatus 8590, dozzle 8591, ntfy 8592, jaeger 16686. 36 container, 5 mạng `tradingsys_{backend,ops,frontend,internal,socketproxy}`.
- Timer: `tradingsys-backup` (03:10 UTC), `-basebackup` (CN 02:30), `-restoretest` (CN 04:30), `-backupwatch` (hằng giờ); `tradingsys-tunnel.service` (quick tunnel, URL ở `data/tunnel_url.txt`).
- Dọn dữ liệu thử: `db/cleanup_test_data_20261014.sql` (sao lưu vào schema `archive`, hậu tố `_cleanup_20261014`, rồi xoá; giữ `mt5:99000001`, `master:admin`, sổ cái bất biến).
- Gatus: thêm `ops/gatus.d/platform_extra.yaml` (client-ui, track-record, briefing-llm, jaeger, textfile-exporter, redis-cache). Prometheus: nhóm luật `tradingsys-ops-extra` (ContainerCrashLoop, HostDiskFillingFast).
- Lưu ý: file cấu hình mount **riêng lẻ** (prometheus.yml, rules_*.yml, gatus.yaml) cần recreate container sau deploy (xem VAN_HANH mục 16).
