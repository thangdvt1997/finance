# ARCH_AUDIT — đánh giá độc lập kiến trúc / SRE / AppSec (2026-10-11)

Phạm vi: đọc mã trong repo `D:\Work\trading-system` + kiểm tra CHỈ ĐỌC trên VPS <VPS_IP> (docker inspect, redis-cli INFO/XLEN/XINFO, psql SELECT, ufw status, systemctl, Prometheus API). Không sửa, không dừng, không tạo container. Chưa chạy build/test cục bộ. Số liệu "VPS" đo lúc ~14:20 UTC 2026-10-11.
Thang mức độ: P0 = phải sửa trước khi có tiền thật / dữ liệu quan trọng; P1 = sửa trong 30 ngày; P2 = 60 ngày; P3 = tốt-nếu-có. Công sức: S (<1 ngày), M (1-5 ngày), L (>1 tuần).

## 0. Nhận định tổng thể (thẳng thắn)

Hệ thống ở trạng thái "prototype chạy được, kỷ luật kỹ thuật tốt ở tầng ứng dụng, yếu ở tầng vận hành/bảo mật hạ tầng". Điểm mạnh thật: event contract rõ, upsert idempotent, DLQ có lý do, XAUTOCLAIM đã sửa (H1), mt-bridge fail-closed + HMAC + replay + read-only chứng minh được, vai trò DB tách (ts_ro / ts_analytics), trigger bất biến cho `paper_events`, nginx cửa duy nhất có CSP/limit/GET-only, Trivy + Renovate có, QA e2e bằng tay khá sâu (383 unit test / 44 file + bộ e2e). Điểm yếu cốt lõi: (a) một VPS dùng chung, một Redis, một Postgres, không HA, không DR thật; (b) phần lớn container chạy root, không hardening, tất cả dùng chung superuser DB; (c) Redis không mật khẩu; (d) không có CI/CD, không lockfile, deploy bằng tar+ssh từ laptop, VPS không phải git repo; (e) backup chưa từng chạy tự động, cùng ổ đĩa, chưa có off-site, restore-test mới chạy tay; (f) tunnel công khai chỉ có Basic Auth và rate-limit nginx bị "gộp IP".
Điều quan trọng: hệ thống hiện READ-ONLY (không có đường đặt lệnh). Mọi rủi ro bên dưới là "nợ trước giai đoạn execution" — chưa gây thiệt hại tiền, nhưng KHÔNG được đi tiếp sang strategy/execution khi P0/P1 chưa xong.

---
## 1. Độ tin cậy

### R-1 (P0 → trước execution, P1 hiện tại) Một VPS, một Redis, một Postgres, không HA; RPO/RTO chưa định nghĩa
- Bằng chứng: VPS `nvme0n1p2` duy nhất, uptime 82 ngày, RAM 128GB dùng chung với hệ thống "thật" khác (62 container; 19 thuộc tradingsys). Redis 1 instance, AOF `everysec` (`infra/docker-compose.yml:27`), không replica, `maxmemory=0`. Timescale 1 instance, `wal_level=replica`, `archive_mode=off` (VPS psql SHOW) → không PITR; mọi `pg_dump` là điểm khôi phục duy nhất.
- Hệ quả: RPO thực tế = tuổi của dump gần nhất (hiện tối đa 24h nếu timer chạy; xem R-2) cộng ≤1s AOF; RTO = thời gian làm lại host + restore tay (chưa đo, chưa có runbook). Dữ liệu thị trường tái tạo được (Dukascopy backfill), nhưng `account_snapshots`, `alerts`, và sau này `paper_*`/journal lệnh thì KHÔNG tái tạo được.
- Sửa: ghi RPO/RTO thành SLO (đề xuất: dữ liệu tái tạo RPO 24h/RTO 4h; journal lệnh RPO ≤5 phút/RTO 1h). WAL archiving + base backup bằng pgBackRest hoặc WAL-G (S3-compatible, vd Backblaze B2/Cloudflare R2 free-tier) → PITR; Redis chỉ coi là bus tạm (đã đúng), nhưng bật replica/Sentinel chỉ khi có execution. Chuẩn bị `compose` thứ hai trên máy khác (warm standby) cho giai đoạn execution. Công sức: M (pgBackRest) + L (standby). OSS: pgBackRest/WAL-G, restic, Patroni (chỉ khi cần HA thật).

### R-2 (P0) Backup: chưa chạy theo lịch lần nào, cùng ổ đĩa, không off-site, không mã hóa, restore-test không tự động
- Bằng chứng: `/root/trading-system/backups/` chỉ có 4 file `ts-20261011T10*.dump` (10:12–10:24, đều do chạy tay/QA, 520–690KB); `tradingsys-backup.timer` active, lần chạy kế `Mon 03:10 UTC` → CHƯA có lần tự động nào. Script `infra/backup/pg_backup.sh:25` giữ 7 bản; lưu vào `$(dirname $INFRA)/backups` cùng ổ NVMe với `pg-data`. journal 10-11 10:17 có cảnh báo `pg_dump: --data-only ... disable-triggers` (cảnh báo về hypertable circular FK, chấp nhận được nhưng cần xác nhận restore thực sự đủ). `infra/backup/pg_restore_test.sh:48-51` chỉ so `count(*)` 4 bảng (không `bars` theo khoảng, không kiểm checksum, không kiểm hypertable chunk/continuous aggregate, bỏ qua `quotes`, `calendar_events`, `experts`, ...), và chỉ chạy tay. Không có bản sao Redis, `.env`, htpasswd, cấu hình Grafana ngoài `grafana-data` volume.
- Hệ quả: mất ổ/host ⇒ mất dữ liệu + backup cùng lúc; "đã test restore" mới ở mức một lần chạy tay.
- Sửa: (1) đẩy dump + WAL off-site (restic/rclone → R2/B2/máy khác) mã hóa bằng khóa tách khỏi VPS; (2) timer restore-test hằng tuần tự động + so checksum theo bảng (`md5` tổng hợp theo partition thời gian), alert nếu fail hoặc backup cũ >26h (metric `backup_last_success_timestamp` qua node_exporter textfile); (3) sao lưu `.env`/secrets bằng `sops`/`age` (đã có `infra/ops/sops_encrypt_env.sh`) ra ngoài VPS; (4) diễn tập DR đầy đủ 1 lần/quý, ghi thời gian thật vào runbook. Công sức: M. OSS: restic, rclone, pgBackRest, sops+age.

### R-3 (P1) Bus Redis Streams: trim `MAXLEN ~100000` có thể xóa tin CHƯA tiêu thụ, không cảnh báo
- Bằng chứng: `libs/common/src/tscommon/bus.py:33,42` (`maxlen=100_000, approximate=True` trên mọi stream, không xét lag của group). VPS: `md.bars` đang 78.202/100.000 (78%) với lưu lượng ≈5 ev/s nhưng backfill nhiều symbol hoặc storage-writer chết ~vài giờ sẽ chạm trần; Redis `maxmemory-policy noeviction` + `maxmemory=0` ⇒ chỉ có MAXLEN bảo vệ. Khi vượt, XADD trim tin cũ nhất đang nằm trong PEL/lag → mất im lặng (consumer thấy "message đã bị xoá", `bus.py:130` ack bỏ qua).
- Sửa: không trim theo độ dài cho stream có consumer-group; dùng `XTRIM MINID` theo thời gian (vd 7 ngày) chạy ở job riêng SAU khi `lag==0`; cảnh báo `stream_len/maxlen > 0.7`; thêm metric `bus_trimmed_unconsumed`. Công sức: S.

### R-4 (P1) storage-writer: 1 consumer, 1 transaction/sự kiện, tuần tự → ~230 ev/s; retry cứng; "poison by DB" vào DLQ mà không replay
- Bằng chứng: `storage_writer/writer.py:96-108` xử lý tuần tự từng message; `db.py:24-28` một transaction mỗi message, pool tối đa 5 (`db.py:22`) nhưng dùng 1 kết nối; `writer.py:77-94` lỗi DB 3 lần (0.2/0.4s) → dead-letter + ack ⇒ một sự cố Postgres >1s biến sự kiện HỢP LỆ thành DLQ (mất tính tự lành); QA M3 đo ~230 ev/s, p95 burst 20s. Không có công cụ replay DLQ (tìm trong repo: không có `replay_dlq`), `dlq` trim 50.000 (`writer.py:60`).
- Sửa: batch `executemany` trong 1 transaction cho cả lô 100 rồi ack lô (giảm ~10-30x); phân biệt lỗi: lỗi DB tạm thời KHÔNG ack và KHÔNG dead-letter, để lại PEL cho `reclaim` (đã có max_deliveries=5) — chỉ DLQ khi lỗi dữ liệu; viết CLI `dlq-replay --reason ... --since ...` có dry-run; metric `dlq_len`. Công sức: M. OSS: asyncpg `copy_records_to_table`/`unnest`.

### R-5 (P1) Thứ tự & "last-write-wins" không có khóa phiên bản → dữ liệu cũ phát lại ghi đè mới
- Bằng chứng: `mapping.py:96-97` (bars), `142-144` & `150-152` (calendar: `actual=EXCLUDED.actual` — một phát lại sự kiện cũ với `actual=NULL` xóa số liệu thật), `215-216` (snapshot). Không có cột `version`/`event_ts` để chặn ghi cũ. Bus at-least-once + XAUTOCLAIM + nhiều producer (Dukascopy vs MT) làm đảo thứ tự là hiện thực.
- Sửa: `... DO UPDATE ... WHERE EXCLUDED.event_ts >= tbl.event_ts` (hoặc COALESCE cho trường nullable như `actual`); thêm cột `ingested_at`, `event_id`. Công sức: S-M.

### R-6 (P2) Dọn consumer rác & tên consumer cố định
- Bằng chứng: group `storage-writer` còn 4 consumer (VPS XINFO GROUPS) dù `CONSUMER_NAME=storage-writer-1` đã cố định (`main.py:200`); `Bus.prune_idle_consumers` (`bus.py:157`) tồn tại nhưng không được gọi từ writer. alert-service group có 1 consumer (đã sạch). Không nguy hiểm, nhưng làm nhiễu quan sát.
- Sửa: gọi prune sau `reclaim_once` mỗi giờ. Công sức: S.

### R-7 (P2) Alert/ntfy: hàng đợi không giới hạn (H2 trong QA) — chưa thấy sửa trong mã; kênh `crit` có thể bị bão `info` chặn
- Bằng chứng: QA_REPORT H2 (apprise 5,5 s/tin tuần tự, `RATE_LIMIT_PER_MIN=20`). Tôi không tìm thấy hàng đợi ưu tiên trong `alert-service/dispatch.py` khi đọc nhanh; cần kiểm chứng lại sau bản sửa.
- Sửa: hàng đợi ưu tiên theo level + gộp (digest) cho info/warn + giới hạn kích thước hàng đợi (drop-oldest với counter), gửi song song có semaphore. OSS: Alertmanager đã có group/inhibit; dùng ntfy priority. Công sức: S-M.

### R-8 (P1) Upgrade không downtime: không có
- Bằng chứng: `deploy.sh` tar rồi `docker compose up -d --build` trên VPS (1 replica mỗi service; `restart: unless-stopped`); cảnh báo trong SECURITY_SCAN: một `compose up` chỉ với file chính đã 2 lần hạ cấp redis/timescale về image cũ (SECURITY_SCAN.md cuối). Image dùng `latest` tag nội bộ (`tradingsys-*:latest`), không có digest/rollback tag.
- Sửa: gộp compose về một nguồn sự thật (đã đề xuất trong SECURITY_SCAN), tag image theo git SHA, `docker compose up -d --no-deps` từng service với healthcheck (rolling cho service stateless; consumer idempotent nên chồng nhau an toàn), giữ 2 tag trước để rollback. Công sức: S-M.

---
## 2. Bảo mật

### S-1 (P0) Redis không mật khẩu, không ACL; mọi container cùng mạng đều ghi được bus
- Bằng chứng: VPS `CONFIG GET requirepass` = rỗng; `infra/docker-compose.yml:26-27` không `--requirepass`/ACL. `redis://redis:6379/0` trong `x-service` (`:12`). Bất kỳ container nào vào `tradingsys_internal` (web-ui, gatus, dozzle?, một service bị chiếm RCE) có thể: XADD giả sự kiện `account.snapshots`/`alerts.out`, XDEL/FLUSHALL, đọc `dlq`. Sau này bus là kênh tín hiệu → lệnh ⇒ đây là điểm chiếm quyền thị trường.
- Sửa: Redis ACL theo service (collector chỉ `XADD` vào stream của nó; storage-writer `XREADGROUP/XACK/XAUTOCLAIM`; api-gateway read-only), tắt `FLUSHALL/CONFIG/DEBUG`, mật khẩu qua Docker secret/`sops`. Công sức: M.

### S-2 (P0) Tất cả service ghi dữ liệu dùng superuser `ts` của Postgres; web-facing gateway đã dùng `ts_ro` (tốt) nhưng writer/collectors không
- Bằng chứng: `docker-compose.yml:13` (anchor `DATABASE_URL` với `POSTGRES_USER` = `ts`, `rolsuper=t` theo VPS `pg_roles`); storage-writer chạy `DATABASE_URL=postgresql://ts…` (VPS exec). Vai trò `ts_ro` (SELECT trên `bars`, `alerts` – VPS information_schema), `ts_analytics` có tồn tại; chưa có `ts_writer` quyền hẹp (chỉ INSERT/UPDATE trên bảng cụ thể). Một lỗi SQL injection/RCE ở storage-writer = chiếm toàn DB (COPY TO PROGRAM).
- Sửa: tạo `ts_writer` (INSERT/UPDATE/SELECT trên đúng 9 bảng, không DDL, không super); chỉ migration runner dùng `ts`. pg_hba: bỏ `trust` cho 127.0.0.1 trong container nếu có publish port (hiện 5432 không publish; port 5432 lắng nghe trên host là Postgres KHÁC, không phải của tradingsys). Công sức: S-M.

### S-3 (P1) Container hardening không đồng đều: 9/19 container chạy root hoặc không giới hạn, không cap_drop/read_only/limit
- Bằng chứng (VPS docker inspect): storage-writer `user=""` (root, uid=0 xác nhận bằng `id`), expert-collector/news-collector root (không có `USER` trong Dockerfile: `services/storage-writer/Dockerfile`, expert-collector, news-collector), api-gateway/mt-bridge/alert-service/market-collector chạy user thường nhưng `ro=false`, không `cap_drop`, không `no-new-privileges`. Chỉ web-ui, nlp, analytics có `ro=true + cap_drop ALL + no-new-privileges` (nlp còn mem 6GB/pids 256). Không có `mem_limit`/`cpus` cho phần còn lại: một service lỗi rò RAM có thể ảnh hưởng hệ thống khác trên VPS dùng chung 128GB. Không seccomp tuỳ chỉnh (mặc định Docker là chấp nhận được). Dozzle đã restart 10 lần (VPS `RestartCount=10`; log lúc 10:29 trùng lúc agent khác recreate).
- Sửa: đưa vào `x-service` anchor: `user: 10001`, `read_only: true`, `tmpfs: [/tmp]`, `cap_drop: [ALL]`, `security_opt: [no-new-privileges:true]`, `pids_limit`, `mem_limit`, `cpus`; thêm `USER` vào 3 Dockerfile; kiểm bằng `docker bench`/Trivy config. Công sức: S.

### S-4 (P1) Tunnel Cloudflare "quick tunnel" + Basic Auth: một lớp xác thực yếu, rate-limit bị gộp, không MFA, URL không ổn định
- Bằng chứng: `systemctl is-active tradingsys-tunnel` = active, `enabled`, file URL tồn tại; `install_tunnel.sh:23-25` dùng `cloudflared tunnel --url` (quick tunnel, `*.trycloudflare.com`, không SLA, không Access). Nginx `default.conf.template:37-38` Basic Auth duy nhất; `limit_req_zone $binary_remote_addr` (`:4-5`) nhưng KHÔNG có `real_ip_header CF-Connecting-IP`/`set_real_ip_from` (grep rỗng) ⇒ nguồn thấy được = IP nội bộ của cloudflared, tất cả client dùng CHUNG một thùng 15 r/s: kẻ tấn công đoán được URL có thể làm 429 toàn bộ người dùng thật (DoS) và brute-force Basic Auth không bị khoá theo IP. Không fail2ban/khoá tài khoản; mật khẩu htpasswd không biết độ mạnh (chỉ kiểm có file). `X-API-Key` được nginx chèn (`:61,79`) → ai qua Basic Auth là có toàn quyền đọc API, kể cả WebSocket.
- Sửa (theo thứ tự): (1) tắt quick tunnel; dùng Named Tunnel + Cloudflare Access (free ≤50 user: OIDC/Google + MFA, policy theo email) trước nginx — Basic Auth chỉ còn lớp phụ; (2) `real_ip` từ `CF-Connecting-IP` + `limit_req` theo IP thật + `limit_req_zone` riêng cho 401 (`auth_request`/`error_page 401`) hoặc Cloudflare WAF rate limiting rule; (3) nếu tự host: Authelia/Authentik (OIDC + TOTP/WebAuthn) làm `auth_request` cho nginx; (4) rotate API_TOKEN khi đổi người, token đọc-only theo vai (viewer vs admin). Công sức: M. OSS: Cloudflare Access, Authelia, Authentik, oauth2-proxy, fail2ban/CrowdSec.
- Đánh giá "basic auth + API key đủ chưa?": đủ cho một người dùng, dữ liệu công khai, đọc-only; KHÔNG đủ khi có execution/PNL thật/tài khoản MT (số dư, equity, positions lộ qua `/v1/accounts`).

### S-5 (P1) Secret management: `.env` phẳng, backup `.env.bak.*` rải rác, secret trong env container
- Bằng chứng: `/root/trading-system/infra/.env` quyền 0600 (tốt) nhưng có 2 bản `.env.bak.1791713803`, `.env.bak.1791722631` (0600, root) lưu lịch sử mật khẩu cũ; compose truyền secret qua biến môi trường (`docker-compose.yml:129-131,151-153`) ⇒ `docker inspect`/`/proc/<pid>/environ`/Dozzle (đọc `containers/json` qua socket-proxy, `CONTAINERS=1`, `INFO=1`) có thể lộ giá trị env của mọi container cùng host (SECURITY_SCAN §5 đã thừa nhận). `.gitignore` chỉ có `.env` (không `.env.*`, `*.dump`, `backups/`, `htpasswd`, `data/`). Không quét bí mật trong git (không gitleaks/pre-commit); repo hiện có `.git` cục bộ nhưng VPS không phải git repo (xem Q-1).
- Sửa: `.gitignore` bổ sung; gitleaks pre-commit + CI; chuyển secret sang Docker secrets (`/run/secrets`, file) hoặc sops+age giải mã lúc deploy; xóa `.env.bak.*` sau khi xoay; Dozzle tắt hoặc dùng `DOZZLE_FILTER` + không hiển thị env. Công sức: S-M. OSS: gitleaks, sops+age, Infisical/Vault (nếu muốn dài hạn).

### S-6 (P1) mt-bridge: HMAC tùy chọn (mặc định tắt), nonce lưu RAM, khóa theo tài khoản, cảnh báo investor-password chỉ ở mức "warn"
- Bằng chứng: `mtbridge/service.py:131` chỉ kiểm HMAC `if cfg.hmac_secret_env and …`; `infra/mt-bridge/accounts.yaml` KHÔNG khai báo `hmac_secret_env` cho cả 2 tài khoản (grep) ⇒ chỉ còn Bearer token tĩnh + ts-skew ±120 s + nonce RAM (`protocol.py:112-116`, restart ⇒ mất; QA L4). Kẻ có token (bị lộ trong `MQL4/5` EA `.set`/log/screenshot) giả mạo được toàn bộ số dư/equity/nến và kích hoạt/ngụy trang alert. Lưu ý `service.py:156` cảnh báo `trade_allowed` (tốt) nhưng không chặn. Cổng ingest đi qua `127.0.0.1:8490` (compose `:134-135`); EA ở máy khác phải qua tunnel/ssh — chưa có mTLS.
- Sửa: bắt buộc HMAC (fail-closed khi `hmac_secret_env` rỗng cho `transport=agent`), nonce → Redis `SET NX EX 300`, token xoay định kỳ + `kid`; chuyển sang mTLS (nginx/Caddy client-cert) hoặc WireGuard riêng cho EA; thêm sanity-check giá (so với nguồn khác) để phát hiện nguồn bị giả. Công sức: M.

### S-7 (P1) Chuỗi cung ứng: không lockfile, phụ thuộc `>=`, không SBOM, không ký image, image `latest`, base image không ghim digest
- Bằng chứng: `services/*/pyproject.toml` toàn `>=` (vd `httpx>=0.27`, `fastapi>=0.110`, `feedparser>=6.0`), không `requirements.txt`/`uv.lock`/`poetry.lock`; Dockerfile `FROM python:3.12-slim` (không digest), build tại VPS (`pip install` từ PyPI thời điểm build, không kiểm hash) — hai lần build cùng commit có thể khác nhau; SECURITY_SCAN: 44 HIGH chưa vá ở lớp Debian cho mỗi image (không xử lý được) + web-ui CRITICAL libssl (có thể đã được sửa, cần quét lại); 125 image/layer `<none>` digest trên VPS (rác build, tốn đĩa). Renovate cấu hình có (`renovate.json`) nhưng KHÔNG có nơi chạy (không có repo remote/Gitea/GitHub), `enabledManagers` có `github-actions` nhưng không có workflow.
- Sửa: `uv pip compile --generate-hashes` → `requirements.lock` mỗi service; multi-stage build, base `python:3.12-slim@sha256:…` + Renovate; `syft` SBOM + `trivy` trong CI; ký image bằng `cosign` (keyless/OIDC hoặc key riêng) và verify khi deploy; `docker image prune` định kỳ. Công sức: M. OSS: uv, pip-audit, syft, grype/trivy, cosign, Renovate self-hosted.

### S-8 (P2) Mối đe dọa đặc thù
- Prompt-injection qua tin/RSS vào nlp/LLM: ĐÃ giảm thiểu tốt — `nlp/summarize.py:1-6` dùng TextRank trích xuất, không có LLM/tool (grep `anthropic|openai` trong `services/nlp` chỉ trả `summarize.py` docstring). Rủi ro còn lại: khi sau này thêm LLM (PLAN: "LLM chỉ tóm tắt/giải thích") phải có: tách ngữ cảnh không tin cậy, không cho LLM chạm bus lệnh, kiểm schema đầu ra, giới hạn độ dài. P3 hiện tại.
- SSRF qua collector: URL lấy từ cấu hình YAML/danh sách nguồn cố định (rủi ro thấp) nhưng `httpx.AsyncClient(follow_redirects=True)` không giới hạn đích (`news_collector/httpclient.py:36-37`, `expert_collector/httpclient.py:28`, `market_collector/providers/__init__.py:22`): một nguồn bị chiếm có thể 302 → `http://redis:6379/`, `http://timescaledb:5432`, `http://169.254.169.254`, `http://api-gateway:8000`. Không có giới hạn kích thước phản hồi (đọc `r.content` toàn bộ: `httpclient.py:117`) → OOM bằng phản hồi lớn/ gzip bomb. P2. Sửa: transport tùy chỉnh chặn IP riêng/link-local/loopback sau resolve + giới hạn redirect (≤3, cùng eTLD+1), `max_bytes` streaming, `Accept-Encoding` chỉ khi giải nén có giới hạn. S-M. OSS: `httpx` event hooks, `ssrf-protect`-style resolver; mạng `internal` + egress allowlist (iptables/Squid) cho collector.
- ReDoS/parser: 41 lệnh `re.*` trong services; `defusedxml` dùng ở SEC 13F (tốt) nhưng `feedparser.parse(body)` (`news_collector/sources/rss.py:28`, `expert_collector/sources/rss_ideas.py:85`) nhận XML từ internet — feedparser dùng sax không tải DTD ngoài nhưng entity expansion/độ sâu vẫn cần giới hạn kích thước; regex `_SENT` có lookbehind/lookahead tuyến tính (OK). P2: chạy parser trong tiến trình con với `resource.setrlimit`/timeout; thêm `re2` (`google-re2`) cho regex áp lên văn bản không tin cậy.
- EA bị giả mạo / lộ token: xem S-6. Lộ API key: S-4/S-5.
- WebSocket: QA L2 (giữ kết nối chưa xác thực 10 s) và mất sự kiện giữa 2 lần `XREAD $` — nên dùng `last_id`. P3.

### S-9 (P2) CSP, headers, CORS
- Bằng chứng: `services/web-ui/nginx/security-headers.conf` có CSP chặt (`default-src 'none'`, hash cho style), `X-Frame-Options DENY`, `COOP/CORP`, `Permissions-Policy`; thiếu HSTS (do trycloudflare/Access xử lý) và `Cross-Origin-Embedder-Policy`; gateway FastAPI `/docs` và `/openapi.json` công khai (đúng thiết kế nội bộ, nhưng cổng 127.0.0.1:8480 nếu bị mở sẽ lộ). OK ở mức P3.

### S-10 (P2) Mạng
- Bằng chứng: tất cả service chung 1 mạng `tradingsys_internal` (compose `:184-186`) ⇒ collector (đi internet) nói chuyện được với redis/timescaledb/gateway; ports host publish đều `127.0.0.1` (VPS docker ps: 8480, 8490, 8580, 8590, 8591, 8592, 3300) — tốt. UFW của host rất rộng (cho phép nhiều IP "Anywhere" và 80/443 mở cho cả máy), Docker bypass UFW cho published port nhưng ở đây đã bind localhost. Kết quả: bề mặt công khai THỰC của tradingsys = cloudflared (outbound) → nginx. Điều tốt cần giữ.
- Sửa: tách mạng `bus` (redis ↔ producers/consumers), `db` (timescaledb ↔ writer/gateway/analytics), `edge` (nginx ↔ gateway), `egress` (collector có internet) — collector KHÔNG vào mạng `db`. `internal: true` cho `bus`/`db`. Công sức: S-M.

---
## 3. Quan sát (observability)

### O-1 (P2) Metrics tốt, logs/trace thiếu; không OpenTelemetry; `trace_id` có trong Event nhưng không ai dùng
- Bằng chứng: Prometheus 10/10 target up (VPS); 17 luật (`infra/prometheus/rules.yml`) phủ down/lag/pending/DB error/DLQ/disk/RAM; Gatus + ntfy. `libs/common/events.py:19` có `trace_id` nhưng `make_event(..., trace_id=None)` mặc định; không có OTel (grep rỗng). Log: JSON qua `tscommon/logsetup.py` nhưng không tập trung (Dozzle chỉ xem sống, không lưu).
- Sửa: OpenTelemetry SDK + `opentelemetry-instrumentation-fastapi/httpx/asyncpg/redis` → OTLP → Grafana Tempo; Loki + Promtail/Alloy cho log (giữ 14 ngày); propagate `trace_id` (W3C traceparent) trong Event từ collector → writer → alert; dashboard theo luồng. Công sức: M. OSS: OTel, Tempo, Loki, Grafana Alloy, VictoriaMetrics (nếu cần lưu lâu).

### O-2 (P1) Chưa có SLO/SLI chính thức; cảnh báo thiếu "độ tươi dữ liệu" theo symbol và theo nguồn
- Bằng chứng: `NoNewBars` (`rules.yml:45-50`) chỉ kiểm tổng; QA M6 phát hiện USDJPY thiếu 10-09 và XAUUSD thiếu 3 ngày mà KHÔNG có alert nào (`mc_backfill_running=0`, log 503). Cảnh báo `MtAccountDisconnected` đang FIRING cho `demo-mt4-01` từ 11:11 UTC (VPS Prometheus `/alerts`) >3 giờ: không ai xử lý ⇒ báo động chết (alert fatigue / hoặc EA demo tắt). `alertmanager.yml` một receiver duy nhất, `repeat_interval: 4h`, không phân tuyến theo severity, không silences/maintenance window, không "dead man's switch".
- Sửa: SLI = (độ tươi theo symbol-timeframe, tỉ lệ sự kiện vào DLQ, độ trễ bus→DB p95, độ sẵn sàng gateway); SLO đề xuất: 99% bar M1 mới nhất ≤3 phút trễ trong giờ thị trường; DLQ <0,1%; gateway 99,5%. Luật `max by (symbol)(time()-mc_last_bar_ts{tf="M1"}) > 600` + `market_open` flag; watchdog `vector(1)` đẩy sang kênh ngoài (healthchecks.io/Gatus ngoài host) để phát hiện chính VPS chết; routing: crit → điện thoại (ntfy priority 5/Telegram), warn → digest. Runbook (docs/runbooks/*.md) gắn `runbook_url` vào annotation: hiện chưa có thư mục runbook. Công sức: S-M. OSS: Sloth/Pyrra (SLO), healthchecks.io self-hosted, Alertmanager.

---
## 4. Dữ liệu

### D-1 (P1) Không có compression/retention/continuous aggregate; bảng `bars` lưu M1 ở mọi khung "vật lý"
- Bằng chứng: VPS `timescaledb_information.hypertables`: `bars` (26 chunk, `compression_enabled=f`), `quotes`, `account_snapshots` — không bật nén; `jobs` chỉ có 2 job hệ thống (không có `policy_compression/retention/refresh_continuous_aggregate`). DB hiện 30MB nên chưa đau, nhưng `quotes`/`account_snapshots` (5.044 hàng/ngày, chưa kể tick) sẽ phình theo số symbol/tài khoản. `bars` PK `(symbol, tf, ts_open, source)` (`schema.sql:8`) chứa M1..D1 đều lưu vật lý (tăng ghi 6 lần) thay vì dựng bằng continuous aggregate từ M1. `chunk` tạo cả cho "500 ngày trước" do QA ghi dữ liệu lệch (chunk rỗng vẫn tồn tại).
- Sửa: `ALTER TABLE bars SET (timescaledb.compress, timescaledb.compress_segmentby='symbol,tf,source')` + `add_compression_policy('bars','7 days')`; retention `quotes` 30–90 ngày, `account_snapshots` giữ vô hạn nhưng nén + downsample bằng continuous aggregate theo giờ; M5..D1 là continuous aggregate từ M1 (đã có `analytics` cũng đọc), `drop_chunks` cho chunk rỗng lệch năm. Công sức: M. OSS: TimescaleDB native; không cần ClickHouse ở quy mô này.

### D-2 (P1) Kiểu dữ liệu & ràng buộc: tiền/giá dùng `double precision`, hầu như không có CHECK, đơn vị không nhất quán
- Bằng chứng: `schema.sql:4-8` `o,h,l,c double precision`; `account_snapshots.balance/equity/margin double precision` (`:49-52`) → sai số làm tròn trong sổ cái/đối soát; không có CHECK nào ở các bảng dữ liệu (VPS `pg_constraint contype='c'` chỉ thấy ràng buộc catalog Timescale; trong mã chỉ `003_paper.sql:26-27` có CHECK) — QA M1 cho thấy nến `o=5,h=1,l=9` vẫn vào DB trước khi `validate_bar` (mapping) được thêm; ràng buộc nên có ở DB vì còn đường ghi khác (psql, backfill script). `calendar_events.forecast/previous/actual` là `text` (`schema.sql:24-28`); vnstock giá theo nghìn đồng (QA M7); `news_items` PK theo `url` (cùng URL khác fragment trùng: QA L3). Bảng "lab/demo" lẫn vào DB thật: `bars_lab_20261011` (350 hàng), `alerts_demo_20261011`, `bars_vn_20261011` (VPS `pg_stat_user_tables`).
- Sửa: `numeric(18,8)` cho giá/tiền ở bảng sổ cái (account/paper/journal), `double` giữ cho nến phân tích nhưng thêm `CHECK (l<=LEAST(o,c) AND h>=GREATEST(o,c) AND l>0)`, `CHECK (side IN …)`, enum/domain cho `tf`; cột `unit`, `currency`; chuẩn hóa URL (bỏ fragment, utm); DB riêng `ts_lab` cho dữ liệu thử; dọn 3 bảng lab sau khi xác nhận với chủ. Công sức: M.

### D-3 (P1) Migration không có công cụ; đánh số trùng; initdb chỉ chạy 001
- Bằng chứng: `infra/db/migrations/` có `002_analytics.sql` + `002_news_enrichment.sql`, `003_paper.sql` + `003_calendar_extra.sql`; compose chỉ mount `001` vào `docker-entrypoint-initdb.d` (`docker-compose.yml:49`), còn lại áp bằng script tay (`create_analytics_role.sh:17`, `create_paper_role.sh:18`). Trên VPS vắng các bảng `paper_*` (chưa áp) và không có bảng lịch sử migration, nên không thể biết DB đang ở phiên bản nào.
- Sửa: dùng công cụ migration có bảng `schema_migrations` (sqitch/dbmate/Atlas/Flyway/Alembic), chạy bằng job một lần với role `ts_migrator`, kiểm tra trong CI trên Timescale tạm; đánh số tuần tự duy nhất. Công sức: S-M. OSS: dbmate (nhẹ nhất), Atlas.

### D-4 (P2) Chất lượng/lineage, múi giờ, đối soát
- Tốt: kiểm chất lượng sâu trong QA (OHLC hợp lệ 21.170 nến 0 vi phạm; lệch tối đa 0,031% so với ECB; căn UTC đúng; tách DST). Thiếu: lineage — `bars.source` chỉ có tên nguồn, không có `ingest_run_id`/phiên bản collector/`event_id` (chỉ news & alerts có `event_id`); khi hai nguồn cùng symbol/tf (dukascopy vs mt5) không có quy tắc "nguồn chủ" (golden source) và không đối soát tự động giữa chúng; `server_tz: Europe/Athens` trong accounts.yaml (EA tính theo giờ máy chủ broker) — nhận định đúng nhưng cần test DST tự động quanh 2 mốc chuyển giờ Mỹ/Âu (không đồng thời: ~3 tuần mỗi năm lệch); D1 theo UTC khác D1 broker (QA L1); đồng hồ: không có kiểm tra drift NTP của host/EA (ts-skew ±120 s dựa vào đồng hồ bridge).
- Sửa: bảng `data_sources(priority, tz, unit, ...)`, `view bars_golden`, job đối soát hằng ngày (Dukascopy vs MT5 vs ECB) ghi `recon_results` + alert khi lệch >X; `chrony`/metric `node_timex_offset_seconds` alert >100 ms; thêm test DST. Công sức: M.

---
## 5. Chất lượng mã

### Q-1 (P0 cho giai đoạn execution; P1 hiện tại) Không có CI/CD; deploy từ laptop bằng `tar|ssh`; VPS không phải git repo
- Bằng chứng: không có `.github/`, `.gitea/`, `.pre-commit-config.yaml`, `Makefile`; `deploy.sh:5-8` đóng gói cả thư mục (loại trừ `.venv`, `.git`) rồi ghi đè `/root/trading-system` (VPS `git status` → "not a git repository"): không biết VPS đang chạy commit nào, không rollback, không audit ai deploy gì; `.pytest_cache`, `*.egg-info`, `.venv` nằm lẫn trong thư mục dự án (`libs/common/.pytest_cache`, `services/*/src/*.egg-info`). Renovate/Trivy chạy rời (`infra/ops/trivy_scan.sh` bằng tay). Test e2e (`tests/e2e/`) phụ thuộc VPS thật và gửi thông báo thật (tác dụng phụ QA §6).
- Sửa: Gitea (self-host, đã có hạ tầng khác) hoặc GitHub Actions: pipeline `lint (ruff) → type (pyright/mypy) → unit (pytest + fakeredis) → build (buildx, cache) → trivy fs/image + gitleaks + pip-audit → SBOM+cosign → deploy (tag SHA, `compose up -d --no-deps`, healthcheck, tự rollback)`; e2e chạy trên Timescale/Redis tạm (service container), không đụng ntfy thật (đặt `APPRISE_URLS` rỗng khi test); pre-commit: ruff, gitleaks, check-yaml, detect-private-key; Renovate self-hosted chạy trong Gitea Actions. Công sức: M-L. OSS: Gitea Actions/Woodpecker CI, ruff, pyright, pre-commit, gitleaks, Renovate, trivy, syft, cosign.

### Q-2 (P2) Kiểm thử: nhiều nhưng chưa đo độ phủ; không kiểm kiểu/lint
- Bằng chứng: ~383 hàm test / 44 file (grep), có e2e và static scan "không có mã đặt lệnh" (tốt, đáng giữ trong CI); `pyproject.toml` không có `pytest-cov`, `ruff`, `mypy/pyright`; `libs/common` chỉ 2 file test cho bus/log/risk_windows. Không test chịu lỗi cho các nhánh khó: Postgres chết giữa lô, Redis failover, đồng hồ lùi, DST. Test dùng `fakeredis` (không mô phỏng `XAUTOCLAIM` đúng mọi trường hợp: sự cố H1 chỉ phát hiện nhờ e2e thật).
- Sửa: bật coverage gate (ví dụ ≥80% cho `storage_writer`, `mt-bridge`, `tscommon`), property-based test (hypothesis) cho `mapping.py`/`protocol.py`, test hợp đồng (JSON Schema từ pydantic → so với `docs/CONTRACTS.md`), chaos test tự động (Toxiproxy) trong CI hằng đêm. Công sức: M.

### Q-3 (P2) Cấu trúc, trùng lặp, cấu hình
- Bằng chứng: mỗi service tự có `httpclient.py` riêng (news, expert, market `providers/__init__`), `retry.py`, `ratelimit.py`, kiểm tra host cooldown — logic gần giống 3 bản; `tscommon/risk_windows.py` và `api-gateway/risk_windows.py` (146 dòng) song trùng tên/chức năng; `STREAMS` ở `bus.py:11` vs `MAPPERS` ở storage-writer vs hằng số trong consumer khác (3 nguồn sự thật); mẫu `Dockerfile` copy-paste 11 bản (không multi-stage, build nặng 150–400MB mỗi image); config qua biến môi trường lẻ tẻ (`os.getenv` trong `main.py:200-203`, `service.py:43-49`) thay vì pydantic Settings thống nhất; `docs/CONTRACTS.md` 60 dòng viết tay có nguy cơ lệch so với pydantic.
- Sửa: đưa `PoliteClient` (rate limit, ETag, cooldown, SSRF guard, size cap) vào `tscommon.http`; sinh `CONTRACTS.md` từ model; base image dùng chung (`tradingsys-base`) + lockfile; một `Settings` mỗi service; `docs/runbooks/`, ADR (`docs/adr/`) cho các quyết định (Redis vs NATS, Timescale vs ClickHouse). Công sức: M.

### Q-4 (P3) IaC: compose + shell, chưa mô tả máy chủ
- Bằng chứng: host-level (ufw, systemd timer/tunnel, node_exporter allow) nằm trong `infra/host/*.sh` thủ công; `COMPOSE_FILE` đặt trong `.env` trên VPS (SECURITY_SCAN) chứ không trong repo. Sửa: Ansible role nhỏ (hoặc cloud-init) cho host; `COMPOSE_FILE` vào `.env.example`; một compose "profile" thay cho 3 file. Công sức: M.

---
## 6. Hiệu năng / khả năng mở rộng

- Giới hạn hiện tại (đo trong QA §4 + đọc mã): ghi DB ≈230 sự kiện/s tổng (1 consumer, 1 giao dịch/sự kiện: `writer.py:96-108`, `db.py:24-28`); đọc API p95 9–74 ms; WS ~3 ms; DB 30MB, Redis 33MB. Lưu lượng thực <5 ev/s ⇒ dư ~45x. Số symbol hiện ≈6-8 (EURUSD,GBPUSD,USDJPY,XAUUSD + vài mã VN) × 6 tf.
- Nút thắt khi lớn: (1) storage-writer tuần tự (sửa bằng batch — R-4, nâng lên ~3.000–10.000 ev/s mà KHÔNG cần đổi công nghệ); (2) `bars` lưu M1..D1 vật lý (D-1); (3) `quotes` tick/giây × symbol nếu mở rộng MT live (hiện publish chỉ khi đổi giá: `service.py:96-98`); (4) mô hình đọc `analytics` gọi `ts_ro` quét tối đa theo symbol; (5) bộ nhớ Redis do stream không tuổi thọ (R-3).
- Khi nào thêm công nghệ: giữ Redis Streams + Timescale đến khi (a) >2.000 ev/s bền vững hoặc cần nhiều consumer-group độc lập có replay dài (≥7 ngày) / retention theo thời gian → NATS JetStream (một binary, subject-based, replay theo thời gian, dễ cluster 3 node); (b) >~1–2 tỉ hàng nến/tick hoặc truy vấn phân tích cột nặng, đa symbol (backtest quy mô lớn) → ClickHouse (đọc từ Timescale/Parquet; KHÔNG thay Postgres cho sổ lệnh); (c) cần chịu lỗi nút DB → Patroni/pgBackRest + replica đọc (cho gateway/analytics), PgBouncer trước Postgres khi >100 kết nối; (d) nhiều tiến trình ghi → partition `bars` thêm chiều space `symbol` (hash) cho Timescale khi >100 symbol. Chưa cần ngay: P3.

---
## 7. Chuẩn bị cho giai đoạn strategy/execution

Hiện trạng tốt làm nền: không có đường đặt lệnh trong mã (QA static scan: 239 file, 0 ký hiệu đặt lệnh), `mt-bridge` read-only, `paper-trader` ghi chỉ bảng `paper_*` bằng role `ts_paper` (`docker-compose.tools.yml:174,192`), trigger bất biến `paper_events/fills/equity` (`003_paper.sql:114-118`), kill-switch có endpoint admin (`paper_trader/app.py:225,235`). Nhưng đây là bản MÔ PHỎNG; chưa phải kiến trúc an toàn cho tiền thật. Yêu cầu bắt buộc trước khi cho phép bất kỳ lệnh thật:

### X-1 (P0 trước execution) Ranh giới an toàn & tách mạng
- Ba vùng tách hẳn: (A) Data (hiện tại), (B) Strategy/Signal (chỉ đọc A, chỉ đề xuất), (C) Execution/OMS + broker (vùng riêng: máy/VM/VPS riêng hoặc ít nhất mạng Docker `internal: true` + egress chỉ tới broker). Không có service nào ở A hoặc B được nối trực tiếp tới C; giao tiếp một chiều qua hàng đợi "order proposals" có chữ ký (Ed25519) và schema nghiêm.
- Hiện tại mọi thứ trong 1 mạng bridge, một Redis, một DB, một VPS dùng chung với các hệ thống khác ⇒ không đáp ứng. Luồng lệnh PHẢI dùng Redis/Postgres riêng (hoặc NATS với account riêng) với ACL/role riêng; EA/MT terminal chạy trong VM riêng; secret broker (investor→trade password) chỉ ở vùng C, lưu bằng Vault/sops, không nằm trong `.env` chung.

### X-2 (P0) Risk engine + kill-switch ĐỘC LẬP
- Kill-switch hiện là chức năng nội bộ của paper-trader (`app.py:225-235`), cùng tiến trình/DB với chiến lược. Cần: tiến trình riêng, đọc trạng thái độc lập (equity từ broker, không từ DB nội bộ), có quyền hủy mọi lệnh chờ + đóng vị thế qua kênh riêng; "dead-man": nếu risk engine không gia hạn lease (Redis `SET key EX 15`) trong N giây, OMS từ chối mọi lệnh mới (fail-closed); kill bằng 3 đường (API, file cờ trên host, nút vật lý/Telegram có MFA). Giới hạn cứng: max lot, max exposure, max daily loss, max orders/phút, whitelist symbol, cửa sổ tin tức (`risk_windows` đã có — tận dụng).
- Thử nghiệm kill-switch hằng tuần trên demo, đo thời gian hiệu lực (<2 s).

### X-3 (P0) Idempotency + audit trail bất biến + đối soát
- OMS: `client_order_id` do OMS sinh, lưu TRƯỚC khi gửi (write-ahead), khóa duy nhất; retry không tạo lệnh trùng; trạng thái lệnh là state machine có chuyển hợp lệ cố định; đối soát vị thế/số dư với broker mỗi N giây, lệch ⇒ halt.
- Audit: bảng append-only + chuỗi hash (mỗi dòng chứa `prev_hash`), role không có UPDATE/DELETE, `REVOKE TRUNCATE`; xuất định kỳ ra lưu trữ WORM (S3 Object Lock/R2 + retention) và ký; trigger `paper_block_mutation` (`003_paper.sql:114`) là mẫu tốt — nhưng superuser `ts` vẫn bỏ qua được (S-2), nên cần role riêng và lưu ngoài host. OSS: pgAudit, immudb (tùy chọn), OpenTimestamps (tùy chọn).

### X-4 (P1) 4-eyes + quản lý thay đổi
- Mọi thay đổi chiến lược/tham số rủi ro/danh sách tài khoản: PR bắt buộc 2 người duyệt (hoặc người + CI tự động), tham số ghi vào DB kèm `approved_by` ≠ `proposed_by`, hiệu lực sau độ trễ (cooldown) trừ giảm rủi ro. Triển khai bằng nhánh bảo vệ trên Gitea/GitHub + CODEOWNERS; kích hoạt "live" yêu cầu 2 token độc lập (mô phỏng 2-person rule) và MFA (WebAuthn qua Authentik/Authelia).
- Tiền đề pháp lý (G1–G3 trong PLAN.md) vẫn là cổng chặn: chưa xong thì không đi tiếp.

---
## 8. Bảng tổng hợp phát hiện

| ID | Mức | Phát hiện | Công sức | Công cụ |
|---|---|---|---|---|
| S-1 | P0 | Redis không mật khẩu/ACL, bus mở cho mọi container | M | Redis ACL, Docker secrets |
| S-2 | P0 | Mọi service ghi bằng superuser `ts`; không có `ts_writer` | S-M | Postgres roles |
| R-2 | P0 | Backup chưa từng chạy theo lịch, cùng ổ, không off-site, restore-test thủ công | M | restic, pgBackRest, sops/age |
| R-1 | P0* | 1 VPS/1 Redis/1 PG, không PITR, RPO/RTO chưa định nghĩa (*P0 trước execution) | M-L | WAL-G/pgBackRest, standby |
| Q-1 | P0* | Không CI/CD, deploy tar|ssh, VPS không phải git repo, không rollback | M-L | Gitea Actions, cosign |
| X-1/2/3 | P0* | Chưa có ranh giới vùng, kill-switch độc lập, audit chuỗi hash/WORM | L | Vault, pgAudit, WORM |
| S-4 | P1 | Quick tunnel + Basic Auth; rate-limit gộp IP (thiếu real_ip); không MFA | M | Cloudflare Access/Authelia |
| S-3 | P1 | 9/19 container root / không read_only / không limit | S | compose anchor |
| S-5 | P1 | Secret trong env + `.env.bak.*`, không quét secret | S-M | gitleaks, sops, Docker secrets |
| S-6 | P1 | mt-bridge HMAC mặc định tắt, nonce RAM, không mTLS | M | HMAC bắt buộc, mTLS/WireGuard |
| S-7 | P1 | Không lockfile/SBOM/ký image, base image không ghim | M | uv, syft, trivy, cosign |
| R-3 | P1 | MAXLEN trim có thể xóa tin chưa tiêu thụ (md.bars 78%) | S | XTRIM MINID |
| R-4 | P1 | Writer tuần tự 230 ev/s; lỗi DB tạm → DLQ; chưa có replay | M | batch executemany |
| R-5 | P1 | Last-write-wins không khóa phiên bản (calendar `actual` bị xóa) | S-M | `WHERE event_ts >=` |
| D-1 | P1 | Không nén/retention/continuous aggregate | M | Timescale policies |
| D-2 | P1 | `double` cho tiền, ít CHECK, bảng lab lẫn DB thật | M | numeric, CHECK, DB riêng |
| D-3 | P1 | Migration không công cụ, đánh số trùng | S-M | dbmate/Atlas |
| O-2 | P1 | Chưa có SLO; alert `MtAccountDisconnected` firing >3h; thiếu freshness/symbol, watchdog ngoài | S-M | Sloth, healthchecks |
| R-8 | P1 | Deploy gây gián đoạn, image `latest`, 2 lần bị hạ cấp image | S-M | tag SHA, rollback |
| O-1 | P2 | Không OTel/log tập trung; `trace_id` không dùng | M | OTel, Tempo, Loki |
| S-8 | P2 | SSRF redirect/không giới hạn kích thước; parser XML/regex | S-M | transport guard, re2 |
| S-10 | P2 | 1 mạng chung cho mọi service | S-M | network segmentation |
| R-6/R-7 | P2 | Consumer rác; hàng đợi alert không ưu tiên | S | prune, ntfy priority |
| Q-2/Q-3 | P2 | Không coverage/lint/type; httpclient trùng 3 bản; Dockerfile lặp | M | pytest-cov, ruff, pyright |
| D-4 | P2 | Không lineage/golden source/đối soát tự động; NTP không giám sát | M | recon job, chrony |

---
## 9. Roadmap 30/60/90 ngày

**0–30 ngày (nền tảng an toàn; mục tiêu: không còn P0 hiện tại)**
1. Redis `requirepass` + ACL theo service; Postgres `ts_writer` (và chỉ migrator dùng `ts`) — S-1, S-2.
2. Backup: off-site mã hóa (restic→R2/B2), alert "backup cũ >26h", restore-test tự động hằng tuần, diễn tập khôi phục 1 lần, ghi RTO/RPO thật — R-2/R-1.
3. Chuyển quick tunnel → Named Tunnel + Cloudflare Access (MFA), `real_ip` + rate-limit theo IP thật — S-4.
4. Hardening compose (`x-service`: user, read_only, cap_drop, no-new-privileges, mem/cpu/pids) + `USER` 3 Dockerfile — S-3.
5. `XTRIM MINID` thay MAXLEN, batch writer, không DLQ lỗi DB tạm thời, CLI replay DLQ — R-3/R-4. Guard phiên bản (calendar/bars) — R-5.
6. Khởi tạo git remote (Gitea) + CI tối thiểu: ruff + pytest + gitleaks + trivy; VPS deploy từ tag SHA (không tar từ laptop) — Q-1; `.gitignore` bổ sung; xóa `.env.bak.*` sau xoay secret.
7. Xử lý alert `MtAccountDisconnected` (xác nhận EA demo-mt4-01 bị tắt hay lỗi), thêm freshness-per-symbol alert + watchdog ngoài.

**31–60 ngày (độ bền & quan sát)**
1. HMAC bắt buộc + nonce Redis + xoay token mt-bridge; WireGuard/mTLS cho EA — S-6.
2. Lockfile có hash, SBOM, cosign, base image digest, Renovate chạy thật — S-7.
3. Timescale: nén `bars`, retention `quotes`, continuous aggregate M5..D1, drop chunk lệch; migration tool (dbmate) + dọn bảng lab; CHECK constraints; `numeric` cho sổ cái — D-1/D-2/D-3.
4. OpenTelemetry (traces) + Loki (logs) + SLO dashboard; runbook cho 10 alert chính — O-1/O-2.
5. Tách mạng bus/db/edge/egress; SSRF guard + size cap trong `PoliteClient` dùng chung — S-10/S-8/Q-3.
6. WAL archiving/PITR (pgBackRest) — R-1.

**61–90 ngày (sẵn sàng cho strategy/paper-live; execution chỉ sau cổng pháp lý G1–G3)**
1. Vùng execution riêng (VM/VPS riêng, Redis/DB riêng), proposal ký số, risk engine + kill-switch độc lập với lease dead-man, OMS idempotent write-ahead + đối soát broker — X-1/2/3.
2. Audit trail chuỗi hash + WORM off-host; role không UPDATE/DELETE; xác minh định kỳ chuỗi hash — X-3.
3. 4-eyes qua nhánh bảo vệ + MFA (Authentik/Authelia WebAuthn); thay đổi tham số rủi ro có độ trễ — X-4.
4. Warm standby (compose thứ hai + replica PG), chaos test hằng đêm trong CI, diễn tập DR đầy đủ lần 2 — R-1/Q-2.
5. Đánh giá lại NATS/ClickHouse theo số liệu tải thật (không làm trước) — mục 6.

---
## 10. Điểm số trưởng thành (1 = ad-hoc … 5 = tối ưu hóa/đo lường)

Cột "Gốc" = đánh giá 2026-10-11; cột "Nay" = sau các vòng hardening đến 2026-10-12 (tự đánh giá, dựa trên bằng chứng kiểm trên VPS; trục 7 không đổi vì chưa đụng execution).

| Trục | Gốc | Nay | Thay đổi chính |
|---|---|---|---|
| 1. Độ tin cậy | 2.5 | 3.0 | PITR/WAL + restore-test tự động, release/rollback, giới hạn tài nguyên mọi container, log xoay vòng; còn 1 node, backup chưa off-site |
| 2. Bảo mật | 2.0 | 3.4 | Redis ACL, role DB hẹp, 100% container không root/read-only/cap_drop (ngoại lệ ghi rõ), secret tách theo service, mạng tách backend/ops/frontend/egress; còn quick tunnel+Basic Auth, ts_app quyền rộng, chưa ký image |
| 3. Quan sát | 3.0 | 4.2 | exporter Postgres/Redis/cAdvisor/backup, 61 luật, SLO + burn-rate, 4 dashboard, trace Jaeger; thiếu log lưu dài/probe từ ngoài |
| 4. Dữ liệu | 2.5 | 3.2 | nén, retention quotes, continuous aggregate, độ tươi theo nguồn; còn `double` cho tiền, chưa có migration tool |
| 5. Chất lượng mã | 2.5 | 3.4 | lockfile có hash 14/15 service + base digest, ruff sạch, CI VPS chạy thật (pytest 14 package, trivy, SBOM); chưa remote/CI tự động, chưa type-check/coverage |
| 6. Hiệu năng/mở rộng | 3.0 | 3.0 | không đổi |
| 7. Sẵn sàng execution | 1.5 | 1.5 | không đổi |

Trung bình ≈ 3.1/5 (từ 2.4). Đủ cho "trạm dữ liệu + paper"; chưa đủ cho tiền thật.

---
## 11. Giới hạn của lần đánh giá này
Không chạy test/build cục bộ (theo quy tắc); không dùng container `audit-`; không đọc giá trị secret (chỉ kiểm có/không, quyền file, tiền tố user DB). Chưa kiểm chứng: độ mạnh mật khẩu htpasswd, hành vi `alert-service/dispatch.py` sau bản sửa H2, nội dung `services/web-ui` đã triển khai so với repo (L5 trong QA), các thành phần `paper-trader`/`nlp` chạy thực tế (nlp có container, paper-trader chưa triển khai: không có bảng `paper_*` trong DB).

---
## 12. Rà soát bảo mật cuối (pentest nội bộ) — 2026-10-14
Phạm vi: phân quyền/IDOR (808 kiểm tra e2e `test_pentest_authz.py`), tunnel/nginx từ ngoài, secret, CVE/hardening, AI/LLM, quét tĩnh không-đặt-lệnh. Chi tiết: `docs/SECURITY_SCAN.md`, `docs/HARDENING.md` §6, `docs/AUTH.md`.

### 12.1 Đã sửa trong vòng này
| Mức | Phát hiện | Trạng thái |
|---|---|---|
| P1 | cAdvisor (root) mount `/var/run` (docker.sock) + `/` + `/var/lib/docker` -> bỏ qua proxy chỉ-GET | SỬA (chỉ `/sys` + `/var/lib/docker/image` `:ro`) |
| P1 | `API_TOKEN` dùng chung lộ trong log gateway | XOAY, quét lại sạch |
| P2 | cache gateway trước authorize, chung khoá vai trò phụ (auditor đọc cache client) | SỬA + test |
| P2 | mật khẩu web cũ trong htpasswd/file rõ; 17 `.env.bak*`; tài khoản test chưa đổi mật khẩu | SỬA / DỌN |
| P2 | redis-cache còn redis:7 (6 CRITICAL), cAdvisor/Jaeger/exporter có CRITICAL | NÂNG: CRITICAL toàn hệ thống 20 -> 3 |
| P3 | public_path tin URI thô; open-redirect login; `/v1/stream` thiếu Origin; journal/accounts bị miễn; NLP tự tải model không ghim; lọt tiêm prompt biến thể (9/20 -> 0/20) | SỬA + test |

### 12.2 Còn mở (ưu tiên)
| Mức | Mô tả | Hướng xử lý |
|---|---|---|
| P1 (trước khi có tiền thật) | Một VPS/Redis/Postgres, backup chưa off-site (R-1/R-2) | xem roadmap §9 |
| P2 | docker-socket-proxy cho phép inspect (`Env` mọi container host, gồm hệ thống khác) cho Dozzle/cAdvisor | tắt Dozzle khi không dùng; secret `*_FILE`; proxy lọc theo nhãn |
| P2 | mạng ops/backend: gọi thẳng service nội bộ không xác thực (alert-rules tin `X-Owner-*`; gateway chỉ cần API key) | mTLS/Bearer theo service hoặc NetworkPolicy theo cặp service |
| P2 | Redis `ts_app` rộng (`~* &*`), 11 service dùng chung; credential dùng chung `ts_ro`/`API_TOKEN` | ACL theo stream từng service (selector `%R~/%W~`) |
| P2 | quick tunnel Cloudflare (URL đổi, không Access/MFA ở biên) | tunnel có tên + Cloudflare Access/WebAuthn |
| P3 | 44 HIGH Debian chưa vá (mỗi image Python); 3 CRITICAL timescaledb ở binary phụ | chờ Debian / base distroless; xoá gosu/tune/parallel-copy trong Dockerfile riêng |
| P3 | CSRF token dùng chung theo giờ; khoá tạm 15 phút có thể bị lạm dụng; 2FA master chưa bắt buộc cho mọi thao tác nhạy cảm | token theo phiên; khoá theo IP+tài khoản; bắt buộc TOTP |
| P3 | image chưa ký (cosign); LLM briefing: blacklist chỉ là lớp phụ (phòng thủ chính là kiến trúc + hậu kiểm) | ký image trong CI |
| P3 | header CSP/XFO trùng ở `/auth/login` (nginx + auth) | tinh gọn |

### 12.3 Điểm trưởng thành (cập nhật)
| Trục | 10-12 | Nay (10-14) | Ghi chú |
|---|---|---|---|
| 1. Độ tin cậy | 3.0 | 3.0 | không đổi |
| 2. Bảo mật | 3.4 | 4.1 | pentest 808 kiểm tra 0 FAIL, 5 lỗ đã sửa, CRITICAL 20 -> 3, secret xoay, tunnel/biên kiểm từ ngoài sạch; trừ điểm: mạng nội bộ chưa xác thực theo service, `ts_app` rộng, quick tunnel, proxy inspect |
| 3. Quan sát | 4.2 | 4.2 | Prometheus 25/25, cAdvisor vẫn đủ metric sau thu hẹp mount |
| 4. Dữ liệu | 3.2 | 3.2 | |
| 5. Chất lượng mã | 3.4 | 3.6 | +11 test briefing, +808 kiểm tra pentest, SBOM 20 image |
| 6. Hiệu năng/mở rộng | 3.0 | 3.0 | |
| 7. Sẵn sàng execution | 1.5 | 1.5 | không đổi (read-only + paper; quét tĩnh 0 mã đặt lệnh ngoài tests) |
Trung bình ≈ 3.2/5 (bảo mật 4.1 là mức cao nhất đạt được với 1 VPS + quick tunnel; vượt 4.5 cần Access/mTLS nội bộ + ACL theo service + off-site).
