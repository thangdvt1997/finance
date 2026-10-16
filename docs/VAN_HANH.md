# Vận hành hệ thống (tradingsys)

Dành cho người quản trị. Hệ thống chạy bằng Docker Compose (project `tradingsys`) trên VPS **<VPS_IP>** (VPS dùng chung với hệ thống khác — chỉ thao tác trên container/volume có tiền tố `tradingsys`). Hướng dẫn người dùng cuối: [HUONG_DAN_SU_DUNG.md](HUONG_DAN_SU_DUNG.md).

## 0. Nguyên tắc an toàn (đọc trước)
- **READ-ONLY**: hệ thống không có đường đặt/sửa/đóng lệnh. Đừng thêm. Có test chặn (`static_readonly_scan.py`, `test_no_trading_code_anywhere`).
- **Không tiền thật**: mô phỏng dùng vốn ảo; tài khoản MT dùng mật khẩu **investor** (chỉ đọc). Chưa vượt qua cổng pháp lý G1–G3 trong `PLAN.md` thì không được chuyển sang tiền thật.
- **Cổng pháp lý**: forex cho cá nhân tại Việt Nam chưa có sàn được cấp phép (Nghị định 340/2025 có phạt nặng); robot chứng khoán cần xác nhận bằng văn bản với công ty chứng khoán. Hỏi luật sư trước khi giao dịch thật.
- **Máy chủ dùng chung**: không `docker system prune`, không `docker stop $(docker ps -q)`, không đụng container không có tiền tố `tradingsys`.
- **Bí mật** (`infra/.env`, `/root/.tradingsys-backup.key`, mật khẩu web) không đưa vào git/chat/log.
- Không chạy build/test nặng trên laptop; chạy trên VPS.

Mọi lệnh compose trên VPS (đã đặt `COMPOSE_FILE` trong `infra/.env` gồm 3 file, **không bao giờ bỏ bớt file** — thiếu `docker-compose.ops.yml` sẽ làm redis/timescaledb bị tạo lại sai phiên bản):
```bash
ssh root@<VPS_IP>
cd /root/trading-system/infra
docker compose -p tradingsys --env-file .env ps
```

## 1. Truy cập các công cụ quản trị (SSH tunnel)
Mọi cổng chỉ bind `127.0.0.1` trên VPS, truy cập bằng tunnel SSH từ máy bạn:
```bash
ssh -L 8580:127.0.0.1:8580 -L 3300:127.0.0.1:3300 -L 8590:127.0.0.1:8590 -L 8591:127.0.0.1:8591 -L 8592:127.0.0.1:8592 -L 16686:127.0.0.1:16686 root@<VPS_IP>
```
| Địa chỉ trên máy bạn | Công cụ |
|---|---|
| http://127.0.0.1:8580 | Website (web-ui) — người dùng thường vào bằng link Cloudflare tunnel (xem mục 6) |
| http://127.0.0.1:3300 | Grafana (dashboard; cổng host 3300 do `GRAFANA_PORT=3300` trên VPS, trong container là 3000) |
| http://127.0.0.1:8590 | Gatus (trang kiểm tra sống/chết) |
| http://127.0.0.1:8591 | Dozzle (xem log) |
| http://127.0.0.1:8592 | ntfy (thông báo, topic `tradingsys-alerts`) |
| http://127.0.0.1:16686 | Jaeger (trace của api-gateway) |

(Trong môi trường làm việc hiện tại, SSH đi qua bastion `<BASTION_IP>` — dùng `SSH_JUMP`/`ProxyJump` nếu VPN không ổn định.)

## 2. Xem log (Dozzle)
1. Mở tunnel rồi vào http://127.0.0.1:8591.
2. Bên trái là danh sách container `tradingsys-*`. Bấm một container để xem log trực tiếp; ô tìm kiếm hỗ trợ chuỗi và regex; chọn nhiều container cùng lúc để xem chung.
3. Tìm theo mã sự kiện: mỗi dòng log của service có `trace_id` của sự kiện.
4. Mỗi container giữ tối đa ~30 MB log (10 MB × 3 file) — log cũ hơn vài ngày sẽ mất.
Cách khác (dòng lệnh): `docker logs --since 30m tradingsys-storage-writer-1 | tail -100`.
Dozzle chỉ đọc (qua `docker-socket-proxy`, không có shell/hành động).

## 3. Kiểm tra sức khoẻ
Thứ tự nhanh nhất:
1. **Trang "Hệ thống" trên website**: tất cả service chấm xanh, "độ mới của dữ liệu" bình thường theo từng nguồn (FX/chứng khoán nghỉ cuối tuần là bình thường; crypto phải luôn mới).
2. **Gatus** (:8590): mọi dòng xanh. Gatus gọi `/healthz` mỗi 30 giây và tự gửi cảnh báo về alert-service nếu lỗi.
3. **Grafana** (:3300 trên VPS, tài khoản `admin`, mật khẩu = `GRAFANA_ADMIN_PASSWORD` trong `.env`). Dashboard: `ts-platform-health` (service up, lag, DLQ), `ts-slo` (SLO & độ tươi dữ liệu, sao lưu/phục hồi), `ts-resources` (CPU/RAM container, Postgres, Redis, host), market-overview.
4. Dòng lệnh: `docker ps --format '{{.Names}} {{.Status}}' | grep tradingsys` — mọi container phải `(healthy)`.
5. Hàng đợi lỗi (DLQ): `docker exec tradingsys-redis-1 redis-cli --user ts_admin --no-auth-warning XLEN dlq` — nên ≈ 0. Xem nội dung: `... XRANGE dlq - + COUNT 5`. Mỗi bản ghi có `reason`.
6. Kiểm bảo mật container: `sh infra/ops/hardening_audit.sh` (chỉ docker-socket-proxy bị đánh dấu là ngoại lệ có chủ đích).
7. Kiểm tra dữ liệu/QA đầy đủ: mục 14.

SLO mục tiêu (xem `docs/SLO.md`): API sẵn có 99,5%; độ trễ API 95% ≤ 500 ms; độ tươi dữ liệu 99%; bus không tồn đọng 99,9%.

## 4. Deploy và rollback
**Cách chính (từ 2026-10-14): chạy TRỰC TIẾP trên VPS** — mã nguồn ở `/root/trading-system` là git repo (nguồn sự thật), không còn upload tarball:
```bash
cd /root/trading-system
bash infra/ops/deploy_local.sh api-gateway auth                 # deploy vài service (tuần tự)
bash infra/ops/deploy_local.sh --all --exclude pattern-engine   # mọi service (bỏ qua một số)
bash infra/ops/deploy_local.sh --check web-ui                   # chỉ kiểm tra, không build
./deploy.sh api-gateway                                         # trên VPS deploy.sh tự gọi deploy_local.sh
./deploy.sh "up -d --build mt-bridge"                           # cú pháp cũ vẫn được (tự tách tên service)
```
Tuỳ chọn: `--skip-tests`, `--no-record` (không ghi release), `--keep-going` (service lỗi → rollback service đó rồi làm tiếp), `--timeout SEC` (mặc định 240 s/chờ healthy; briefing-llm/nlp/timescaledb ×3), `--note "mô tả"`.

`deploy_local.sh` làm theo thứ tự (dừng ngay khi có lỗi, không đụng container):
0. Script tự chạy từ bản sao tạm trong /tmp (sửa/commit deploy_local.sh lúc đang deploy không làm hỏng lượt đang chạy).
1. Khoá `/tmp/tradingsys-deploy.lock` (flock) — nhiều agent/người deploy cùng lúc sẽ xếp hàng.
2. `docker compose -p tradingsys --env-file .env config` (`infra/.env` đặt COMPOSE_FILE + COMPOSE_PROJECT_NAME=tradingsys; nếu tự gõ lệnh compose trong `infra/` vẫn nên thêm `-p tradingsys` vì file compose có `name: trading-system`).
3. Kiểm tra trong `libs/common`, `infra`, `services/<svc>`: file 0 byte (nghi cắt khi đồng bộ), conflict marker, JSON/YAML sai cú pháp, `bash -n` cho deploy.sh + infra/ops/*.sh, compile Python bằng **Python 3.12** (container `python:3.12-slim`), rồi pytest (`infra/ops/run_tests.sh <svc>` nếu service có `tests/`).
4. `bash infra/ops/gen_service_env.sh`; `sh infra/ops/release.sh snapshot` (gắn tag `tradingsys-*:rel-<phiên bản hiện tại>`).
5. Từng service: `docker compose build <svc>` → `up -d --no-build --no-deps <svc>` → chờ `healthy` (service không có healthcheck: chạy ổn định ≥15 s).
6. Service lỗi (build lỗi: image cũ vẫn chạy; không healthy: retag `rel-<bản trước>` → `latest` + `up -d --no-build --no-deps`) → **không ghi release**, thoát mã 1.
7. Tất cả OK → đóng gói `git ls-files` thành tarball, `release.sh record` ghi `.release` + `/root/trading-system-releases/ts-<VER>.tgz`.

`VER = <UTC>-<git short sha>[-dirty]` (`-dirty` = còn thay đổi chưa commit). Nên commit trước khi deploy.
Lưu ý: biến `${POSTGRES_PATTERN_PASSWORD:?}` chưa có trong `.env` thì compose từ chối mọi lệnh — deploy_local tự đặt placeholder và bỏ qua pattern-engine (chạy `infra/db/create_pattern_role.sh` để bật).

**Nhánh laptop (cũ, hạn chế dùng)**: `./deploy.sh "up -d --build --no-deps <svc>"` từ `/d/Work/trading-system` đóng gói + upload qua bastion. Đã thêm: kiểm sha256 + `gzip -t` tarball trên VPS **trước** khi giải nén/ghi release (upload bị cắt → huỷ, mã 3), sau giải nén khôi phục ACL mask cho user `cc`. Cảnh báo: tar đè lên cây git trên VPS — sẽ ghi đè thay đổi chưa commit trên VPS.

Kiểm tra sau deploy: `docker ps --filter label=com.docker.compose.project=tradingsys` (healthy), trang Hệ thống, Gatus, và `cd /root/qa-e2e && sh run_remote.sh test_flow.py` (mục 14).

**Rollback** (trên VPS):
```bash
cd /root/trading-system
sh infra/ops/release.sh list           # xem danh sách phiên bản
sh infra/ops/release.sh current
docker images tradingsys-<svc> --format '{{.Tag}} {{.ID}}'      # các tag rel-* còn giữ (3 bản mới nhất/ image)
# Chỉ 1 service, giữ nguyên mã nguồn (nhanh nhất):
docker tag tradingsys-<svc>:rel-<VER> tradingsys-<svc>:latest
cd infra && docker compose -p tradingsys --env-file .env up -d --no-build --no-deps <svc>
# Code + image về release trước (giải nén tarball đè cây làm việc; sau đó `git status` để xem/khôi phục):
SERVICES="news-collector api-gateway" sh infra/ops/rollback.sh [VER]
```
Ưu tiên rollback mã bằng git (`git revert <commit>` rồi `deploy_local.sh <svc>`). Thay đổi lược đồ DB (migration) không tự rollback — kiểm tra trước khi quay lui. Service dùng image dựng sẵn (redis, prometheus, gatus...) không có tag `rel-*`: rollback = sửa lại tag image trong compose rồi deploy lại.

## 5. Sao lưu và khôi phục (tóm tắt `DR_RUNBOOK.md`)
Tự động (systemd timer trên VPS):
| Timer | Lịch | Làm gì |
|---|---|---|
| `tradingsys-backup` | 03:10 UTC mỗi ngày | `pg_dump` mã hoá AES-256 + gói cấu hình mã hoá, kiểm tra giải mã, giữ 14 bản (`/root/trading-system/backups`) |
| `tradingsys-basebackup` | Chủ nhật 02:30 | base backup vật lý (PITR) |
| `tradingsys-restoretest` | Chủ nhật 04:30 | khôi phục thử dump + diễn tập PITR vào DB tạm |
| `tradingsys-backupwatch` | mỗi giờ | báo động nếu backup >26 giờ, restore-test >8 ngày, off-site cũ |
WAL archiving bật (RPO về lý thuyết ≤ 5 phút nhưng **chỉ khi WAL được đẩy ra ngoài máy** — hiện chưa).

**VIỆC BẠN PHẢI LÀM (chưa xong)**
1. Sao chép khoá mã hoá ra ngoài VPS: `scp root@<VPS_IP>:/root/.tradingsys-backup.key .` rồi cất trong trình quản lý mật khẩu. **Mất khoá = mất toàn bộ backup.**
2. Cấu hình off-site (`rclone` tới R2/B2/S3/SFTP…): xem `DR_RUNBOOK.md` mục 3. Hiện backup nằm cùng ổ đĩa với dữ liệu, không chịu được mất VPS.

Khôi phục:
- *Xoá/ghi sai dữ liệu* → PITR (`DR_RUNBOOK.md` mục 4.1): dừng service ghi → giải mã base → đặt `recovery_target_time` → thử bằng `infra/backup/pitr_restore_test.sh 'YYYY-MM-DD HH:MM:SS+00'` → thay volume.
- *Mất DB/host* → khôi phục từ dump (mục 4.2): dựng máy mới + `deploy.sh`, giải mã `ts-config-*.tar.gz.enc` lấy `.env`, `pg_restore`, chạy lại `infra/db/create_*_role.sh`, sinh lại `redis/users.acl` và `infra/env/*`.
- Dữ liệu thị trường mất có thể backfill từ nguồn (Dukascopy, Yahoo, ccxt); **quote thô >30 ngày bị xoá theo chính sách** (còn `quotes_1m`); `bars` được nén sau 30 ngày (không xoá).
- Redis chỉ là bus tạm; mất Redis không mất dữ liệu đã ghi DB.
- Dữ liệu nghiên cứu `data/research/patterns/` (gồm `mt5/` nến native MT5) **không** nằm trong backup tự động và không vào git; tái tạo được (fetch lại / xuất lại từ terminal MT5 lab). Raw `.bin` MT5 nén `zstd -19 --rm` sau khi parquet kiểm xong — xem `docs/research/PATTERN_DATA.md` mục MT5.
Diễn tập thật mỗi quý và ghi vào bảng nhật ký ở cuối `DR_RUNBOOK.md`.

## 6. Đổi mật khẩu
**Website (đăng nhập phiên do service `auth`, từ 2026-10-12)**: mật khẩu master ban đầu ở `<SECRETS_DIR>/auth_master_admin.txt` (đổi bắt buộc ở lần đăng nhập đầu); quên mật khẩu: `bash infra/ops/auth_bootstrap_master.sh --reset`; chi tiết `docs/AUTH.md` mục 4. Đổi mật khẩu client/master phụ: do master làm trong giao diện (Khách hàng / Vai trò & nhân sự).

**Website — đường dự phòng Basic Auth (mặc định TẮT, chỉ bật khẩn cấp bằng `AUTH_BASIC_FALLBACK=1`)**: trên VPS
```bash
cd /root/trading-system
bash services/web-ui/scripts/make-htpasswd.sh admin        # đổi mật khẩu 'admin' (mật khẩu ngẫu nhiên in ra MỘT lần)
bash services/web-ui/scripts/make-htpasswd.sh them_nguoi   # thêm người dùng khác
```
File ghi vào `infra/web-ui/auth/htpasswd`; không cần restart. Muốn xoá người dùng: sửa file, xoá dòng tương ứng.

**Grafana**: đổi `GRAFANA_ADMIN_PASSWORD` trong `.env` **và** trong giao diện Grafana (Profile → Change password; biến môi trường chỉ có tác dụng ở lần khởi tạo đầu tiên).

**Cơ sở dữ liệu / Redis / token API**: các mật khẩu `POSTGRES_*_PASSWORD`, `REDIS_*_PASSWORD`, `API_TOKEN` nằm ở `infra/.env`. Quy trình chung: sửa `.env` → `bash infra/ops/gen_service_env.sh` → với Redis chạy `DEFAULT_OFF=1 bash infra/ops/redis_acl_render.sh` → với role Postgres chạy lại `infra/db/create_<role>_role.sh` → recreate service dùng nó (`up -d --no-deps <svc>`, từng cái một). Sau đó thử lại `test_flow.py`. Nếu một mật khẩu từng bị lộ (in vào log/chat) hãy đổi nó ngay.

**Link đường hầm Cloudflare**: không phải mật khẩu nhưng thay đổi: `cat /root/trading-system/data/tunnel_url.txt`; khởi động lại `systemctl restart tradingsys-tunnel`. Chỉ bật đường hầm khi đăng nhập phiên (`auth`) đang chạy.

## 7. Thêm khoá API miễn phí (từng bước)
Mọi nguồn dưới đây miễn phí; thiếu khoá thì nguồn đó tự tắt gọn và trang "Hệ thống" hiện "Cần khoá". Cách chung:
1. Đăng ký trên trang nhà cung cấp, lấy khoá.
2. Trên VPS mở `infra/.env` (quyền 600) và điền vào biến tương ứng (không in ra màn hình/log).
3. Nạp lại service: `cd /root/trading-system/infra && docker compose -p tradingsys --env-file .env up -d --no-deps market-collector` (hoặc `news-collector`).
4. Kiểm tra trang Hệ thống: nguồn chuyển từ "Cần khoá" sang "Hoạt động"; xem log bằng Dozzle nếu không.

| Nguồn | Dùng cho | Biến trong `.env` | Đăng ký | Service nạp lại |
|---|---|---|---|---|
| Twelve Data | giá nhiều loại tài sản (8 req/phút, 800/ngày) | `TWELVEDATA_API_KEY` | twelvedata.com/register | market-collector |
| OANDA practice | FX đối chiếu Dukascopy | `OANDA_PRACTICE_TOKEN` | tài khoản practice → My Hub → Manage API Access | market-collector |
| TrueFX | FX đối chiếu (HTTP không mã hoá — dùng tài khoản riêng) | `TRUEFX_USER`, `TRUEFX_PASS` | truefx.com (Register) | market-collector |
| Alpaca | ETF/cổ phiếu Mỹ (thay Yahoo, hợp pháp hơn) | `ALPACA_KEY`, `ALPACA_SECRET` | app.alpaca.markets/signup (Paper/Free) | market-collector |
| Tiingo | ETF/cổ phiếu Mỹ | `TIINGO_TOKEN` | tiingo.com/account/api/token | market-collector |
| Marketaux | tin có gắn mã (100 req/ngày) | `MARKETAUX_TOKEN` | marketaux.com/register | news-collector |
| FRED | số "actual" cho lịch kinh tế | `FRED_API_KEY` | fred.stlouisfed.org/docs/api/api_key.html | news-collector |
| Telegram bot | thông báo đẩy | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | @BotFather (tạo bot) rồi nhắn bot, lấy chat id | alert-service |

Ghi chú:
- Alpaca/Tiingo, khi bật, **tự thắng Yahoo** theo thứ tự ưu tiên nguồn (`DATA_SOURCE_PRIORITY.md`, quy tắc: tên `source` đứng đầu bảng chữ cái thắng khi trùng nến). Đừng đặt tên nguồn mới đứng sau `yahoo_daily` nếu muốn nó thắng.
- Yahoo (`yahoo_daily`) là API không chính thức, chỉ dùng cá nhân, có thể bị chặn; tắt bằng cách bỏ khỏi `PROVIDERS` hoặc đặt `ALLOW_RISKY_PROVIDERS=false`.
- Thông báo đẩy: mặc định đang đi qua **ntfy nội bộ + Apprise** (`APPRISE_URLS` đã đặt). Muốn nhận trên điện thoại, cần địa chỉ ntfy truy cập được từ ngoài hoặc Telegram. Telegram chỉ có lệnh đọc (`/status`, `/last_alerts`) và chỉ trả lời đúng `TELEGRAM_CHAT_ID`.
- Danh sách nguồn có thể bị **ẩn tên** ở API/web (tính năng `HIDE_SOURCES`) — trang Hệ thống vẫn hiện trạng thái.

## 8. Thêm tài khoản MT (EA, token, HMAC)
Kiến trúc: terminal MT4/MT5 chạy EA **chỉ đọc** (`mt-agent/`) → HTTPS POST `/ingest/v1` tới `mt-bridge`. EA không có hàm giao dịch, không nhận lệnh, không mở cổng.
1. **Khai báo tài khoản**: sửa `infra/mt-bridge/accounts.yaml` thêm khối mới (mẫu: `demo-mt4-01`): `account_id`, `platform` (mt4/mt5), `transport: agent`, `token_env: MT_TOKEN_<TÊN>`, `hmac_secret_env: MT_HMAC_<TÊN>`, `server_tz` (múi giờ máy chủ broker, ví dụ `Europe/Athens`), `watch_symbols`, `timeframes`, `rules` (heartbeat, drawdown, margin, `expected_magics`).
2. **Sinh token (≥ 32 ký tự ngẫu nhiên)**: thêm vào `infra/.env` dòng `MT_TOKEN_<TÊN>=$(openssl rand -hex 32)` (dùng `printf '\nMT_TOKEN_X=%s\n' "$(openssl rand -hex 32)" >> infra/.env`). **Sinh HMAC**: `sh infra/ops/gen_mt_hmac.sh MT_HMAC_<TÊN>` (ghi vào `.env`, không in). Đọc giá trị để dán vào EA: `grep MT_HMAC_<TÊN> infra/.env` (coi như mật khẩu).
3. Thêm hai biến này vào danh sách cho phép của `mt-bridge` trong `infra/ops/service_env.manifest` (dòng `mt-bridge`), rồi `bash infra/ops/gen_service_env.sh`.
4. Áp dụng: `./deploy.sh "up -d --no-deps mt-bridge"` (từ laptop) hoặc recreate trên VPS. Kiểm tra `/healthz`.
5. **Cài EA vào terminal** (mỗi terminal = 1 tài khoản, thư mục cài riêng/portable): chép `mt-agent/Include/MTAgent/` vào `<Data Folder>/MQL4|MQL5/Include/`, chép EA vào `Experts/`, biên dịch (F7). *Tools → Options → Expert Advisors → Allow WebRequest* thêm URL gốc của bridge (HTTPS, MT4 chỉ cho cổng 80/443, URL phải có dấu chấm). Kéo EA vào **một** chart; điền `BridgeUrl`, `AccountId`, `Token`, `HmacSecret`, `Symbols` (tên theo broker, vd `EURUSD.m`), `Timeframes`, `HistoryDays` (mặc định 365 ngày lịch sử cho Nhật ký).
6. **Đăng nhập terminal bằng mật khẩu investor** (chỉ đọc). Nếu nhập mật khẩu giao dịch, hệ thống cảnh báo bảo mật (`trade_allowed=true`).
7. Kiểm tra: góc chart hiện `status=ok`; trang Tài khoản hiện tài khoản; nếu 401 → kiểm tra đồng hồ máy (lệch >120 giây bị từ chối), token, chữ ký HMAC.
8. Bắt buộc HMAC cho mọi tài khoản: sau khi mọi EA đã cập nhật đặt `MT_REQUIRE_HMAC=1` (hiện `demo-mt5-01` chưa bật HMAC, chờ EA MT5 mới).
9. Thu hồi: đổi token trong `.env` rồi recreate `mt-bridge`; token lộ thì coi như đã bị chiếm.
Lưu ý: bridge phải nằm sau **TLS** (token đi trong header). Kiểm tra điều khoản broker về EA/VPS trước khi dùng tài khoản thật. Cổng `127.0.0.1:8490` của mt-bridge và `GET /accounts` cần `BRIDGE_ADMIN_TOKEN` (đã đặt; trống thì bị từ chối).

## 9. Thêm phương pháp giao dịch vào paper-trader
Paper-trader chỉ mô phỏng; plugin chỉ trả **mục tiêu tỷ trọng**, không ra lệnh. Quy trình:
1. Viết `services/paper-trader/strategies/my_method.py` (thư mục này được mount `:ro` vào `/cfg/strategies`):
```python
from paper_trader.strategy import Strategy, StrategyContext, register
from paper_trader.models import Targets

@register("my_method")
class MyMethod(Strategy):
    @property
    def required_history(self): return 100                  # thiếu lịch sử -> 'warming_up'
    def targets(self, ctx: StrategyContext) -> Targets:
        c = ctx.history["EURUSD"]["c"]                       # DataFrame o,h,l,c,v — chỉ nến ĐÃ ĐÓNG
        return Targets(weights={"EURUSD": 1.0 if c.iloc[-1] > c.mean() else 0.0}, kind="conviction")  # hoặc kind="weight"
```
2. Thêm khối tài khoản vào `services/paper-trader/paper.example.yaml` (được mount thành `/cfg/paper.yaml`): `id`, `strategy: my_method`, `params`, `universe`, `rebalance`, `risk` (whitelist, đòn bẩy, kill-switch…), `benchmark: bh_fx`, vốn ảo và tiền tệ cơ sở.
3. (Nên) tạo strategy card `cards/my_method.yaml` ghi giả thuyết, tham số khoá, kết quả backtest (cả mục không đạt) và tiêu chí xét duyệt; đổi cấu hình sau này sẽ tạo phiên bản mới và **đồng hồ giai đoạn tính lại từ đầu**.
4. `./deploy.sh "up -d --build --no-deps paper-trader"`. Kiểm tra trang Mô phỏng: tài khoản mới ở trạng thái "warming up" rồi bắt đầu mô phỏng từ nến đã đóng gần nhất. Tài khoản mới nên có nhãn rõ nếu chỉ là replay (`start_at` trong quá khứ → REPLAY).
5. Quy trình khuyến nghị: backtest trung thực (có chi phí, walk-forward) → paper ≥ 12 tuần so với benchmark/backtest → chỉ khi đó mới xét bước tiếp theo và các cổng pháp lý. Đừng chỉnh tham số khi đang chạy paper (làm mất ý nghĩa thống kê).
Reset kill-switch/halt (quản trị, KHÔNG qua gateway): gọi trực tiếp paper-trader với `PAPER_ADMIN_TOKEN`, `POST /paper/accounts/{id}/kill-switch/reset|halt`.

## 10. Xử lý sự cố thường gặp
| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Không vào được website | Link tunnel đã đổi / dịch vụ tunnel chết | `cat /root/trading-system/data/tunnel_url.txt`; `systemctl restart tradingsys-tunnel` |
| Website 401 mãi | Sai mật khẩu hoặc bị khoá tạm (5 lần sai → 15 phút) | Đợi; quên mật khẩu master: `auth_bootstrap_master.sh --reset` (Basic Auth `make-htpasswd.sh` chỉ áp dụng khi bật dự phòng) |
| Trang báo 502 ở một mục (Mô phỏng/Rủi ro/Nhật ký/Báo cáo) | Service tương ứng đang khởi động lại hoặc gateway không nối được mạng `ops` | `docker ps` tìm container không healthy; `docker compose ... up -d --no-deps <svc>`; kiểm tra mạng: `docker inspect <ctr> --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}'` |
| Giá đứng yên (ngoại hối/vàng) | Cuối tuần / chưa mở cửa lại Chủ nhật 21:00 UTC | Bình thường; Dukascopy trễ ~1 giờ sau giờ mở |
| Giá đứng yên (crypto) trong giờ bình thường | market-collector lỗi/bị chặn IP | Xem log market-collector (Dozzle); `up -d --no-deps market-collector` |
| Một mã crypto thiếu nến phút (ví dụ TON) | Sàn thanh khoản mỏng không trả nến rỗng | Chấp nhận; dùng khung lớn |
| Nến VN/US không mới | Yahoo bị chặn hoặc ngoài giờ cập nhật (22:30 UTC) | Xem log; kiểm `ALLOW_RISKY_PROVIDERS`; cân nhắc Alpaca/Tiingo |
| `vn-market` báo cũ (>5 ngày, cảnh báo `VnMarketStale`) | VNDirect đổi API/chặn, hoặc ngày lễ dài | Xem log vn-market; `VN_INGEST=true`; thử lại sau; xem `docs/VN_MARKET.md` |
| Tin trùng/thiếu | Feed đổi định dạng/URL | Log news-collector; test `news/khong-trung-url` |
| Lịch kinh tế không có "thực tế" sau công bố | `actual` đến trễ hoặc cần `FRED_API_KEY` | Đợi vài chục phút; thêm khoá FRED (mục 7) |
| Cảnh báo ntfy dồn dập | Backlog alert-service (gửi nối tiếp) hoặc test tạo cảnh báo | Xem `alerts:recent`; hạ giới hạn `RATE_LIMIT_PER_MIN`; không chạy test tải alert trên môi trường thật |
| `dlq` tăng | Sự kiện sai định dạng | `XRANGE dlq - + COUNT 5`: đọc `reason`; sửa nguồn phát; xoá bản ghi test bằng `cleanup.py` |
| `mt-bridge`: 401 | Token/HMAC sai hoặc đồng hồ lệch >120 s | Kiểm tra `.env`, đồng bộ giờ (NTP) trên máy chạy MT |
| `mt-bridge`: 409 | Gửi lại cùng nonce (replay) | EA tự đổi nonce; thường do chạy 2 EA cùng tài khoản |
| "Tài khoản mất kết nối" | EA/terminal tắt hoặc mạng | Mở lại terminal; cảnh báo chỉ báo cho tài khoản đã gửi trong 24 giờ qua |
| Paper "chain đứt" (cảnh báo nghiêm trọng) | Bản ghi journal bị sửa/xoá | **Dừng, không sửa tay.** Khôi phục từ backup (mục 5), điều tra ai có quyền ghi bảng `paper_*` |
| Redis không lên sau recreate | Compose chỉ dùng 1 file → redis 7-alpine không đọc được AOF 8.x | Luôn dùng đủ 3 file (kiểm `COMPOSE_FILE` trong `.env`) |
| Redis nạp `users.acl` lỗi | Dòng chú thích `#` trong file | Chạy lại `redis_acl_render.sh` (bản mới không sinh chú thích) |
| DB "tuple decompression limit exceeded" khi DELETE | Chunk `bars` đã nén | `SET timescaledb.max_tuples_decompressed_per_dml_transaction = 0;` trong phiên thao tác |
| Container hết RAM / bị kill | Giới hạn `mem_limit` | Xem Grafana `ts-resources`; tăng giới hạn trong compose cho đúng service |
| Đĩa đầy | WAL/backup/log | `df -h`; xem `backups/`, `wal-archive/`; log đã giới hạn 30 MB/container |
| Trace/Jaeger trống | Lấy mẫu 25%, lưu RAM, restart mất | Bình thường |

Khi không rõ: (1) trang Hệ thống, (2) Gatus, (3) Dozzle log của service nghi ngờ, (4) `docker inspect <ctr> --format '{{.State.Health.Status}}'`.

## 11. Checklist hằng ngày (≈ 3 phút)
- [ ] Trang Hệ thống: mọi service xanh; không cảnh báo nghiêm trọng mới ở trang Cảnh báo.
- [ ] Báo cáo ngày (06:30 VN) đã sinh, trạng thái `ok` (không `degraded`).
- [ ] Gatus toàn xanh; Grafana `ts-slo` không có burn-rate đỏ.
- [ ] `XLEN dlq` ≈ 0.
- [ ] Độ mới dữ liệu: crypto < vài phút; VN `lag_days` 0–1; tin tức mới trong giờ gần đây.

## 12. Checklist hằng tuần
- [ ] Báo cáo tuần (Chủ nhật 19:00) đọc xong; mục rủi ro/stress nổi bật.
- [ ] Kết quả `tradingsys-restoretest` (Chủ nhật 04:30) thành công (`/var/lib/tradingsys-backup/restore_test.last_success` mới; không có cảnh báo `RestoreTestTooOld`).
- [ ] Sao lưu: file mới nhất trong `backups/` có ngày hôm qua/hôm nay; **khoá backup đã được cất ngoài VPS**; off-site (nếu đã cấu hình) có ngày mới.
- [ ] Dung lượng đĩa/volume (`df -h`, `docker system df` — chỉ để xem), Grafana `ts-resources`.
- [ ] Mô phỏng: `GET /v1/paper/verify` (trang Chất lượng) báo chuỗi nguyên vẹn; không có cảnh báo suy giảm đỏ.
- [ ] Chạy QA dữ liệu (mục 14) và đọc kết quả; sau thứ Ba kiểm tra riêng lịch kinh tế đã có `actual`.
- [ ] Nhật ký giao dịch: review tuần và ghi chú.
- [ ] Cập nhật phụ thuộc/CVE: `infra/ops/trivy_scan.sh` hoặc xem PR Renovate nếu đã bật; quý một lần diễn tập DR.

## 13. Cảnh báo an toàn (nhắc lại)
1. Hệ thống **không đặt lệnh**, mọi truy cập MT là **investor (chỉ đọc)**.
2. **Không tiền thật** cho tới khi có xác nhận pháp lý (G1–G3), backtest có chi phí + walk-forward, paper đủ dài, kill-switch đã thử thật, giới hạn lỗ/vị thế, sao lưu có diễn tập.
3. Kết quả mô phỏng và mọi chỉ báo **không phải khuyến nghị đầu tư**; mẫu ngắn (như 12 tuần) không cho phép kết luận.
4. LLM (nếu dùng) chỉ tóm tắt tin, **không có quyền ra lệnh**.
5. Không mở cổng Redis/DB/Grafana ra Internet; mọi cổng bind `127.0.0.1`; web-ui luôn sau đăng nhập phiên (`auth_request`); không tắt `cap_drop`, `read_only` của container.
6. Dữ liệu từ nguồn không chính thức (Yahoo, vnstock/VNDirect) chỉ dùng cá nhân, có thể ngừng bất cứ lúc nào.

## 14. Chạy kiểm thử chất lượng (QA)
Chạy từ laptop (đẩy bộ test lên VPS) rồi chạy **trên VPS** (không chạy trên laptop):
```bash
bash tests/e2e/deploy.sh
ssh root@<VPS_IP> "cd /root/qa-e2e && sh run_remote.sh test_flow.py"            # luồng bus→DB→API, DLQ, auth, WebSocket
ssh root@<VPS_IP> "cd /root/qa-e2e && sh run_remote.sh test_data_quality.py"     # chất lượng dữ liệu thật (chỉ đọc)
ssh root@<VPS_IP> "cd /root/qa-e2e && sh run_remote.sh test_mt_bridge.py"        # mt-bridge + chứng minh không có đường đặt lệnh
ssh root@<VPS_IP> "cd /root/qa-e2e && sh run_remote.sh test_new_components.py"   # crypto, VN, lịch, paper chain, risk, journal, reporter (chỉ đọc)
ssh root@<VPS_IP> "cd /root/qa-e2e && sh run_remote.sh cleanup.py"               # dọn dữ liệu test (luôn chạy sau test_flow / orphan)
```
Mặc định an toàn; **đừng** bật `QA_N_ALERT` hoặc `QA_MT_LIVE=1` (sẽ gửi cảnh báo thật tới ntfy). Đừng chạy song song hai bộ test (dùng chung symbol `QAUSD` và DLQ). Kết quả tổng hợp ở [QA_REPORT.md](QA_REPORT.md).

## 15. Quản trị đội tài khoản (master) — nhóm, luật, sự cố, vai trò phụ (2026-10-12)
Chi tiết kỹ thuật: `docs/FLEET_MGMT.md`; bảo mật: `docs/AUTH.md` mục 7.
- **Nhóm/tag/views**: gom tài khoản theo nhóm (một tài khoản thuộc nhiều nhóm), gắn tag, lưu bộ lọc. Thao tác hàng loạt (đình chỉ/kích hoạt/tag/nhóm/xoay token/HMAC, tối đa 200) luôn qua 2 bước: xem trước -> gõ `XAC NHAN <n>`; mỗi tài khoản + bản ghi `bulk_executed` vào audit.
- **TOTP**: master PHẢI bật TOTP trước khi dùng thao tác nhạy cảm mới (bulk, import CSV, nhân sự, xem-như-khách). Mất thiết bị 2FA: `bash infra/ops/auth_bootstrap_master.sh --reset`.
- **Nhập CSV**: cột `platform,login,server,label,group,tags,notes`, tối đa 200 dòng; xem trước báo lỗi từng dòng; commit trả passcode/mã ghép cặp/EA token/HMAC MỘT lần (in/lưu ngay; server không giữ).
- **Luật rủi ro** (mẫu cấu hình được, KHÔNG có "luật nhà cái" cứng): tạo mẫu -> gán theo nhóm/tag/tài khoản/tất cả. Engine ở `risk-monitor` chạy mỗi chu kỳ (60s), ghi xanh/vàng/đỏ + dư địa vào bảng tuân thủ; vàng ≥ `warn_usage_pct` (mặc định 70%), đỏ ≥ 100%. Kiểm: `GET risk-monitor:8000/risk/rules/status`. Tắt engine: bỏ `FLEET_INTERNAL_TOKEN` khỏi env risk-monitor + recreate.
- **Sự cố**: tự mở từ luật/ngân sách/mất EA (khoảng lặng 15 phút + ân hạn theo chính sách nhóm; >=10 tài khoản và >=60% cùng mất EA => 1 sự cố "mất kết nối hàng loạt"); nhận/giao/tạm hoãn/đóng; tự đóng khi hết điều kiện.
- **Vai trò phụ**: `POST /auth/admin/staff` (support/analyst/auditor + nhóm được xem). Không giao nhóm = không thấy gì. Đổi quyền => buộc đăng nhập lại.
- **Khách opt-in push** luật rủi ro: khách tự bật ở Thông báo; master không bật hộ.
- Rollback nhanh: `infra/ops/rollback.sh`; dữ liệu nằm trong các bảng migration `014_fleet.sql` (additive, không phá cũ).

## 16. Bảng cổng / container / volume / timer hiện tại (chốt 2026-10-14)
**Cổng publish (đều `127.0.0.1` trên VPS, truy cập qua SSH tunnel; người dùng ngoài vào bằng Cloudflare quick tunnel -> web-ui, URL ở `data/tunnel_url.txt`)**
| Cổng host | Container | Ghi chú |
|---|---|---|
| 8580 | `web-ui` | website master (nginx + auth_request) — đích của tunnel |
| 8581 | `client-ui` | cổng khách (`CLIENT_PORT`) |
| 8480 | `api-gateway` | REST/WS (`GATEWAY_PORT`) |
| 8490 | `mt-bridge` | nhận EA (mt-agent) |
| 3300 | `grafana` | 6 dashboard (cache-latency, market-overview, platform-health, realtime, slo, resources) |
| 8590 / 8591 / 8592 | `gatus` / `dozzle` / `ntfy` | status / log / thông báo |
| 16686 | `jaeger` | trace |
Không publish: redis, redis-cache, timescaledb, prometheus (9090), alertmanager (9093), các service Python (8000 nội bộ), exporter.

**36 container (project `tradingsys`)**: lõi `redis redis-cache timescaledb storage-writer market-collector news-collector expert-collector mt-bridge api-gateway web-ui client-ui`; nghiệp vụ `alert-service alert-rules risk-monitor reporter auth journal track-record analytics paper-trader nlp vn-market briefing briefing-llm`; giám sát `prometheus alertmanager grafana gatus postgres-exporter redis-exporter textfile-exporter cadvisor jaeger ntfy`; công cụ `dozzle docker-socket-proxy`. Mạng: `tradingsys_backend|ops|frontend|internal|socketproxy`.

**Volume**: `pg-data` (1,5 GB, DB), `redis-data`, `prom-data` (≈1 GB, giữ 30 ngày), `grafana-data`, `gatus-data`, `ntfy-cache`, `alertmanager-data`, `reports-data`, `mc-data`, `nlp-models`, `briefing-models` (≈32 GB, mô hình LLM — phần lớn dung lượng stack), `trivy-cache` (1,6 GB, tái tạo được). Ngoài volume: `/root/trading-system/backups` (≈400 MB), `/root/trading-system/wal-archive` (≈3 GB, tỉa mỗi tuần theo base backup), `/root/trading-system-releases` (5 tarball).

**systemd** (`systemctl list-timers 'tradingsys*'`): `tradingsys-backup.timer` (03:10 UTC hằng ngày), `tradingsys-basebackup.timer` (CN 02:30), `tradingsys-restoretest.timer` (CN 04:30), `tradingsys-backupwatch.timer` (hằng giờ :17) và dịch vụ `tradingsys-tunnel.service` (cloudflared quick tunnel, tự chạy lại; URL ghi `data/tunnel_url.txt`, đổi mỗi lần restart tunnel).

**URL cố định (Named Tunnel) — hướng dẫn, cần một domain bạn sở hữu trên Cloudflare**: (1) `cloudflared tunnel login` (chọn zone), (2) `cloudflared tunnel create tradingsys`, (3) `cloudflared tunnel route dns tradingsys app.<domain-của-bạn>`, (4) tạo `/etc/cloudflared/config.yml` với `tunnel: <UUID>`, `credentials-file`, `ingress: [{hostname: app.<domain>, service: http://127.0.0.1:8580}, {service: http_status:404}]`, (5) đổi `ExecStart` của `tradingsys-tunnel.service` thành `cloudflared tunnel --no-autoupdate run tradingsys`, `systemctl daemon-reload && systemctl restart tradingsys-tunnel`. Giữ web-ui basic-auth/đăng nhập bật; có thể thêm Cloudflare Access (miễn phí ≤50 người) phía trước. Không cần sửa code.

**Việc kiểm tra định kỳ sau vòng hoàn thiện**: mục tiêu Prometheus 25/25 up; 76+ luật hợp lệ; Gatus ≥33 endpoint; Grafana 122 truy vấn panel không lỗi (kiểm bằng `/api/ds/query` với admin). Cảnh báo thử: `amtool alert add alertname=KiemTraDinhKy severity=info ...` trong container alertmanager (đi qua alert-service -> bảng `alerts` + ntfy, dedupe theo nhóm).

**Lỗi hay gặp: bind-mount file bị cũ.** `deploy.sh` giải nén tarball ghi đè file (inode mới) nên container chỉ mount **một file** (prometheus.yml, rules_*.yml, gatus.yaml...) vẫn thấy bản cũ cho tới khi recreate. Sau khi sửa các file đó: `deploy.sh "up -d --no-deps --force-recreate <service>"` (prometheus/gatus), rồi so `md5sum` host với `docker exec <c> md5sum <path>`.

## 17. Feed toàn bộ cặp (126 forex + 10 kim loại + 26 chỉ số)
- Đường đi: EA market-feed (account `mt5:<login>-feed`, read-only) -> mt-bridge `/ingest/v1` -> bus `md.quotes` -> storage-writer (bảng `quotes`) -> hub `/v1/rt` (topic `q:<SYMBOL>`) -> UI. Hợp đồng: `docs/handoff/FEED_ALL_contract.md`.
- Kiểm tra nhanh: Grafana `ts-feed-all`; Prometheus `feed:symbols_active`, `feed:tick_rate`, `feed:latency_p95_seconds`; Gatus `feed-all-fx`; e2e: `sh /root/qa-e2e/run_remote.sh test_feed_all.py` (SKIP = thị trường đóng / feed chưa live).
- Sự cố: (1) `FeedFxNoQuotes`/`FeedEaOffline`: kiểm `docker ps` mt-agent/lab MT5, log EA (terminal Wine), `mtbridge_account_connected{account=~".*-feed"}`; khởi động lại terminal theo `mt-agent/LAB.md` (không đụng EA 7 mã cũ). (2) `FeedSymbolsSilentHigh`: exotic tick thưa là bình thường; xem danh sách symbol im ở dashboard. (3) Trễ cao: tải terminal/VPS (cAdvisor), hàng đợi EA, 429 từ bridge. (4) Rollback feed mới: tắt EA feed (không ảnh hưởng EA cũ/canon 7 mã); luật tự im vì metric biến mất.
- Cuối tuần/ngày lễ không có cảnh báo (lịch phiên trong `rules_feed.yml`); nếu broker đổi giờ DST, kiểm lại mốc 22:00 UTC (mùa đông có thể 23:00).

### 17.1 Ưu tiên tốc độ giá realtime — CPU & độ trễ (2026-10-15)
- **CPU bền vững**: `cpus: 32` + `cpu_shares: 4096` cho `mt-bridge, storage-writer, api-gateway, redis` qua `infra/docker-compose.perf.yml` (đã thêm vào `COMPOSE_FILE` trong `infra/.env`; ghi đè `cpus` của anchor `x-svc`). Không mất khi `docker compose up -d`/deploy. Kiểm tra: `docker inspect <ct> --format '{{.HostConfig.NanoCpus}} {{.HostConfig.CpuShares}}'` (32000000000 4096). Rollback: bỏ `:docker-compose.perf.yml` khỏi COMPOSE_FILE rồi `up -d`; image dự phòng `tradingsys-rollback/<svc>:pre-feedall`.
- **mtlab-mt5-feed** (docker run, ngoài compose): tạo bằng `mt-agent/lab-feed/scripts/run-feed.sh` (cpus 32, cpu-shares 4096; ENV_FILE do root cấp, không để secret trong repo). **mtlab-mt5**: `mt-agent/lab-feed/compose.perf.yml` (ghi đè cho /root/mtlab/docker-compose.yml, cần root).
- **Giảm trễ**: EA feed ScanMs 40→20, FlushMs 250→100, MaxMsgPerSec 4→10 (mặc định trong `start-feed.sh`, ghi đè bằng env FEED_SCAN_MS/FEED_FLUSH_MS/FEED_MSG_PER_SEC); bridge `BRIDGE_RATE_PER_S` 5→20, `BRIDGE_RATE_BURST` 20→60; EA gửi thời điểm tick theo mili-giây (`time` = giây.mmm, `QuoteIn.time: float`) để đo/sắp xếp không bị làm tròn giây.
- **Đo**: `python3 infra/ops/feed_latency.py [giây]` (p50/p95/p99 từ histogram `mtbridge_feed_latency_seconds`, chỉ đọc).

## 18. data-keeper / trang Dữ liệu
Trang `#/du-lieu` (master): bảng phủ dữ liệu, nút "Kiểm tra lại" (20 giây/lần). Kill-switch `DATA_KEEPER_ENABLED`; tắt LLM: `DATA_KEEPER_LLM_ENABLED=0` (vẫn có báo cáo mẫu). Mã im lặng vì thị trường đóng là bình thường. Xem `docs/DATA_KEEPER.md`.

## 19. Cổng chất lượng (smoke + tự rollback) — 2026-10-15
**Quy ước (bắt buộc):** không commit thay đổi giao diện/API khi chưa có kết quả smoke xanh (hoặc ảnh QA) đi kèm; mọi deploy đi qua `infra/ops/deploy_local.sh` (bọc `flock /tmp/tradingsys-deploy.lock`).
- **Smoke đầu-cuối** `bash infra/ops/smoke.sh` (~2-3 phút, thoát 0 = xanh, 1 = đỏ, 2 = hỏng hạ tầng smoke). Tạo tài khoản thử `qa_stab_s_m` (master), `qa_stab_s_e` (chuyên gia), client thử `999007711` -> Playwright trong container tạm -> mở mọi mục điều hướng master + 12 trang client, gọi API chính, kiểm tra: không lỗi console/pageerror, không 4xx/5xx/mất kết nối (403 của chuyên gia và 404 "chưa có dữ liệu" của client thử là hợp lệ), không lộ tên nguồn dữ liệu, không NaN/undefined, chuyên gia bị 403 ở `/auth/admin/*`, ẩn danh bị 401. Tài khoản thử luôn bị xoá khi xong (trap). Chịu deploy giữa chừng: chờ web-ui/client-ui tối đa 90s, đăng nhập/mở trang có retry; máy quá tải thì cắt theo ngân sách thời gian (`SMOKE_DEADLINE`, mặc định 140s) và ghi chú số trang bỏ qua. Mã: `tests/qa/s_smoke.mjs`, `tests/qa/s_user.py`.
- **Tự rollback**: `deploy_local.sh` chạy smoke sau khi mọi service healthy; đỏ -> thử lại 1 lần sau 20s -> vẫn đỏ thì rollback MỌI service vừa deploy về image `rel-<bản trước>`, KHÔNG ghi `.release`, thoát 1. Kiểm cơ chế bằng `FORCE_SMOKE_FAIL=1 bash infra/ops/deploy_local.sh --skip-tests --no-record <svc ít rủi ro>`.
- **Khẩn cấp**: `--skip-smoke` bỏ cổng (script ghi CẢNH BÁO); phải chạy smoke tay ngay sau đó.
- **Tarball release**: trước khi ghi `.release`, `deploy_local.sh` kiểm `gzip -t` + số file trong tar; hỏng/cắt -> không ghi release (`deploy.sh` cũ đã kiểm sha256+gzip trên VPS).
- Đọc lỗi: dòng `FAIL <trang>: ...` trong đầu ra; log đầy đủ ở `/tmp/qa-s-smoke/out.txt`.

## LLM local, digest và đo token (2026-10-15)
- LLM local + CLI `la` (giảm token Claude cho việc cơ học): xem [LOCAL_LLM.md](LOCAL_LLM.md). Quy tắc tiết kiệm token: mục tương ứng trong CLAUDE.md.
- `docs/handoff/DIGEST.md`: tóm tắt thay đổi tự sinh mỗi 30 phút (crontab của user cc -> `infra/ops/digest.sh`, nice 19, flock, bỏ qua nếu load > 60; LLM lỗi thì xuất bản không-LLM; lịch sử xoay vòng 24 bản ở `docs/handoff/digest_history/`). Log: `data/la/digest.log`. Biến: `LA_LLM_URL`, `DIGEST_MAXLOAD`.
- `docs/handoff/TOKENS.md`: token Claude (đo từ `~/.claude` log) và local (`data/la/tokens.jsonl`) theo ngày/phiên/model + tỉ lệ; `infra/ops/tokens_report.py` cũng ghi metric textfile `data/la/tokens.prom` (ts_claude_tokens_today, ts_local_tokens_today, ts_local_token_ratio). Để Prometheus thấy: root cần copy/symlink tệp này vào thư mục textfile-exporter `/var/lib/tradingsys-backup/` (user cc không ghi được) hoặc đặt `TOKENS_PROM`.

### 19b. Cổng deploy nhanh (2026-10-16)
- `infra/ops/deploy_local.sh`: khoá THEO TỪNG SERVICE (`/tmp/tradingsys_deploy_<svc>.lock`) — service khác nhau deploy song song, cùng service xếp hàng. KHÔNG bọc `flock` toàn cục ngoài lệnh (mất song song; script cảnh báo).
- Gộp: yêu cầu cùng service tới liên tiếp trong 60 s (`--debounce`) được đợi yên rồi gộp; yêu cầu xếp hàng mà lần build trước (bắt đầu sau khi nó tới) đã xanh thì bỏ qua ("GỘP").
- Smoke NHANH theo service (`infra/ops/smoke_quick.sh <svc>...`, 10-60 s) là cổng chặn + tự rollback (về `pre-<VER>`); smoke ĐẦY ĐỦ (`smoke.sh`) chạy NỀN tối đa 1 lần/15 phút (`smoke_full_bg.sh`, chỉ cảnh báo; trạng thái ở `/tmp/tradingsys-deploy-state/`), hoặc ép bằng `--smoke-full`.
- Build dùng cache lớp Docker; cuối mỗi lần in `TIMING` từng bước, lưu `/tmp/tradingsys-deploy-state/timings.log`.
- Tự chữa: nếu ACL `infra/env` bị đặt lại (user cc mất quyền đọc) script sửa bằng container tạm.
