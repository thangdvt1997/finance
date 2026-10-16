# DR_RUNBOOK — sao lưu, khôi phục, PITR (tradingsys)

Cập nhật 2026-10-14 (diễn tập đo RPO/RTO thật, mục 5.1); 2026-10-12 (thêm: nén/retention Timescale, giám sát backup qua Prometheus, mạng tách, env theo service). Phạm vi: dữ liệu TimescaleDB (volume `pg-data`), cấu hình/secret (`infra/.env`, htpasswd, `accounts.yaml`). Redis là bus tạm (mất Redis không mất dữ liệu đã ghi DB; tin chưa ghi sẽ mất — xem RPO).

## 1. Mục tiêu (đề xuất, chờ chủ hệ thống chốt)
| Loại dữ liệu | RPO | RTO | Cơ chế |
|---|---|---|---|
| Dữ liệu thị trường (bars/quotes/news/calendar) — tái tạo được (Dukascopy backfill) | 24h | 4h | dump hằng ngày + backfill |
| `account_snapshots`, `alerts`, `paper_*`, journal (KHÔNG tái tạo) | **≤5 phút** | 1h | base backup + WAL archive (`archive_timeout=300`) — chỉ đạt khi WAL được đẩy off-site (hiện mới cùng ổ, xem mục 6) |
| Cấu hình/secret | 24h | 1h | `ts-config-*.tar.gz.enc` trong cùng gói backup |

Con số RTO là ước lượng; đo thật khi diễn tập (mục 5) và ghi vào nhật ký cuối file.

## 2. Thành phần đã triển khai (VPS <VPS_IP>, /root/trading-system)
- `tradingsys-backup.timer` 03:10 UTC: `infra/backup/pg_backup.sh` tạo `backups/ts-<UTC>.dump.enc` (+`.sha256`) và `ts-config-<UTC>.tar.gz.enc`. Mã hoá `openssl enc -aes-256-cbc -pbkdf2 -iter 200000`, khoá `/root/.tradingsys-backup.key` (0600). Mỗi lần: dump, mã hoá, giải mã + `pg_restore -l` để kiểm tra, sha256, đẩy off-site (nếu cấu hình), giữ 14 bản. Lỗi sẽ gửi cảnh báo `critical` (alert-service, Telegram/ntfy).
- `tradingsys-basebackup.timer` Chủ nhật 02:30: `pg_basebackup` (tar+gzip, mã hoá) vào `backups/base/`; giữ 2 bản, xoá WAL cũ hơn bản cũ nhất.
- WAL archiving: `archive_mode=on`, `archive_command` gzip vào `/root/trading-system/wal-archive/<segment>.gz` (bind `/wal-archive` trong container timescaledb), `archive_timeout=300`.
- `tradingsys-restoretest.timer` Chủ nhật 04:30: `pg_restore_test.sh` (khôi phục dump mới nhất vào DB tạm `restore_test`, so số hàng mọi bảng, md5 lát cắt cũ hơn 3 ngày của bars/quotes/news/calendar/account/alerts/paper, số hypertable) và `pitr_restore_test.sh` (base + WAL vào container tạm không mạng, truy vấn kiểm tra). Lỗi sẽ gửi `critical`.
- `tradingsys-backupwatch.timer` mỗi giờ (phút 17): cảnh báo nếu backup quá 26h, restore-test quá 8 ngày, lần chạy gần nhất lỗi, hoặc off-site đã cấu hình mà quá 50h. Trạng thái ở `/var/lib/tradingsys-backup/` (`backup.last_success`, `restore_test.last_success`, `offsite.status`, `backup.prom`).
- Giám sát (2026-10-12): `backup_watch.sh` ghi `/var/lib/tradingsys-backup/backup.prom` (tuổi backup/restore-test/base backup/PITR/off-site, cờ lần chạy lỗi) -> `textfile-exporter` -> Prometheus; luật `BackupTooOld` (>26h, critical), `BackupJobFailed`, `RestoreTestTooOld` (>8 ngày), `PostgresWalArchiveFailing/Stale` (pg_stat_archiver) trong `infra/prometheus/rules_slo.yml`; dashboard `SLO & độ tươi dữ liệu` có khối "Sao lưu / phục hồi". Đường độc lập thứ hai ngoài timer `backupwatch` (nếu chính timer chết thì luật Prometheus vẫn báo vì timestamp đứng yên).
- Nén/retention (`docs/DATA_RETENTION.md`): `bars` nén sau 30 ngày (không xoá), `quotes` xoá chunk >30 ngày (quote thô KHÔNG khôi phục được sau 30 ngày — chỉ còn `quotes_1m` 1 năm), `account_snapshots` xoá >730 ngày. Dump/WAL tính trên dữ liệu đã nén nên nhỏ hơn; restore bằng `timescaledb_pre_restore()/post_restore()` như cũ, sau đó kiểm tra job còn nguyên: `SELECT job_id, proc_name, hypertable_name FROM timescaledb_information.jobs WHERE job_id >= 1000;` (nếu mất: áp lại `infra/db/migrations/009_retention_compression.sql`).
- Đã kiểm chứng 2026-10-11: dump 1.2MB mã hoá OK; restore-test OK (36656 bars, 1077 news... khớp); PITR từ base + WAL OK (36656 bars, 42 alerts, 1077 news).

## 3. Khoá mã hoá và off-site (VIỆC NGƯỜI DÙNG PHẢI LÀM)
1. Sao chép khoá ra NGOÀI VPS (password manager/két): `scp root@<VPS_IP>:/root/.tradingsys-backup.key .`. Mất khoá là mất toàn bộ backup mã hoá; để khoá chỉ trên VPS thì vô nghĩa khi mất VPS.
2. Off-site (CHƯA cấu hình, cần đích do bạn cung cấp): tạo remote rclone (R2/B2/S3/SFTP...) bằng `rclone config --config /root/.config/tradingsys-rclone.conf`, rồi `cp infra/backup/offsite.env.example infra/backup/offsite.env` và điền `BACKUP_RCLONE_REMOTE=remote:bucket/tradingsys`. Từ đó `pg_backup.sh` tự đẩy dump và gói cấu hình mã hoá; `backupwatch` cảnh báo nếu cũ. Để đạt RPO ≤5 phút cho dữ liệu không tái tạo, thêm job đẩy `wal-archive/` (ví dụ `rclone copy /root/trading-system/wal-archive remote:bucket/wal --max-age 1h` mỗi 5 phút) — chưa bật vì chưa có đích.
3. VPS chỉ có một đĩa NVMe (`/`), nên bản "ngoài ổ" khả thi duy nhất là off-site/máy khác.

## 4. Quy trình khôi phục
### 4.1 Mất dữ liệu logic (xoá nhầm, bug ghi sai) — PITR về thời điểm T
1. Dừng ghi: `docker compose -p tradingsys --env-file .env stop storage-writer paper-trader analytics alert-rules journal vn-market` (các service ghi DB; bus giữ tin 24h).
2. Giải mã base mới nhất trước T: `openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass file:/root/.tradingsys-backup.key -in backups/base/base-<ts>.tar.gz.enc | tar xzf - -C /var/tmp/pitr-data` (thư mục trống, chown 70:70).
3. `touch recovery.signal`; thêm vào `postgresql.auto.conf`: `restore_command='gunzip -c /wal-archive/%f.gz > %p'`, `recovery_target_time='YYYY-MM-DD HH:MM:SS+00'`, `recovery_target_action='promote'`.
4. Kiểm tra trước bằng `infra/backup/pitr_restore_test.sh 'YYYY-MM-DD HH:MM:SS+00'`; nếu dữ liệu đúng, thay volume `pg-data` (đổi tên volume cũ để giữ), `docker compose up -d timescaledb`, rồi bật lại service. Tin mới hơn T còn trong bus sẽ được ghi lại (upsert idempotent).

### 4.2 Mất cả DB hoặc host — từ dump
1. Máy mới: Docker + repo (`deploy.sh`) + `infra/.env` (giải từ `ts-config-*.tar.gz.enc`: `openssl enc -d ... | tar xzf - -C /root/trading-system`).
2. `docker compose up -d timescaledb`; tạo DB trống `ts`, `CREATE EXTENSION timescaledb; SELECT timescaledb_pre_restore();`
3. `openssl enc -d ... -in backups/ts-<ts>.dump.enc | docker exec -i tradingsys-timescaledb-1 pg_restore -U ts -d ts --no-owner`, rồi `SELECT timescaledb_post_restore();`
4. Chạy `infra/db/create_*_role.sh` (ts_ro/ts_writer/ts_analytics/ts_paper/ts_userconf/ts_vn/ts_journal/ts_monitor; mật khẩu lấy từ `.env`), áp migration `infra/db/migrations/009_retention_compression.sql` nếu dump không mang theo job nén/retention, `DEFAULT_OFF=1 bash infra/ops/redis_acl_render.sh` (sinh lại `redis/users.acl` từ `.env`), `bash infra/ops/gen_service_env.sh` (sinh `infra/env/*.env` — `deploy.sh` tự làm), `docker compose up -d`, kiểm tra e2e (`tests/e2e`). Mạng `backend`/`ops`/`frontend` do compose tự tạo (xem `docs/HARDENING.md`).
5. Backfill khoảng trống bằng market-collector (Dukascopy) nếu dump cũ hơn dữ liệu cần.

### 4.3 Rollback phiên bản code
`sh infra/ops/rollback.sh` (về release trước) rồi `SERVICES="<svc> ..." sh infra/ops/rollback.sh`; xem `infra/ops/release.sh list`.

## 5. Diễn tập
- Hằng tuần tự động (restoretest). Hằng quý: diễn tập DR đầy đủ mục 4.2 trên máy khác, ghi thời gian thật.
- Nhật ký:

| Ngày | Kịch bản | RTO đo được | RPO đo được | Ghi chú |
|---|---|---|---|---|
| 2026-10-11 | restore dump + PITR vào DB/container tạm cùng host | khoảng 1-2 phút (dữ liệu 30MB) | n/a | chưa đại diện cho dữ liệu lớn hoặc máy mới |
| 2026-10-12 | restart container timescaledb sau hardening (user 70, read-only, tmpfs) | ~14 giây gián đoạn DB (đo từ log "shut down" tới "ready"); mọi service tự kết nối lại, không mất sự kiện (bus giữ) | 0 | không phải DR thật; chứng minh image/volume chạy được với FS chỉ-đọc |

### 5.1 Diễn tập vòng hoàn thiện 2026-10-14 (đo thật trên VPS, dữ liệu DB 0,9 GB, 1,2 triệu bar)
| Bước | Kết quả đo |
|---|---|
| `tradingsys-backup` (pg_dump -Fc + mã hoá + kiểm giải mã), 3 ngày liền 10-12..10-14 | thành công mỗi ngày 03:10 UTC, ≈15 giây, 52 -> 67 MB mã hoá; còn 10 bản; sha256 khớp |
| `tradingsys-basebackup` chạy tay (lần đầu theo lịch là CN 10-18) | 17 giây, 134 MB mã hoá; WAL archive 933 file / 2,8 GB, `pg_stat_archiver` failed_count=0, lệch <4 phút |
| `tradingsys-restoretest`: dump ts-20261014T031026Z vào DB tạm + so số hàng/md5 mọi bảng | **≈3 phút**, OK (mọi hypertable, hàng restored <= live; chênh lệch chỉ là ghi sau dump; incidents/QA đã xoá khỏi live sau khi dump được tạo) |
| PITR: base mới + WAL vào container tạm không mạng | **≈2 phút 15 giây**, OK (1.200.553 bars, 1.357 alerts, 6.899 news) |
| Rollback image một service (client-ui) về tag `rel-*` + recreate `--no-build --no-deps` | sẵn sàng (healthz 200) sau **11,6 giây**; đưa lại bản mới 3,8 giây; healthy. Tarball release cũ giải nén thử vào thư mục tạm: 1624 file, toàn vẹn |
| Ước lượng **RTO** | mất DB trên cùng host: dump -> DB ≈3 phút + tạo role/migration + `up -d` ≈ **10–15 phút**. Host mới: thêm cài Docker + build image (không có registry) ≈ **30–60 phút** (ước lượng, chưa đo); volume `briefing-models` (≈32 GB mô hình LLM) KHÔNG nằm trong backup, phải tải lại — briefing rơi về dạng template trong lúc chờ |
| **RPO** thực tế | dữ liệu DB: ≤24 giờ nếu chỉ có dump; **≤5 phút** bằng WAL (`archive_timeout=300`) nhưng WAL cùng ổ đĩa => chỉ chịu được lỗi logic, KHÔNG chịu mất host. Cấu hình/secret: ≤24 giờ |
Bản kéo về máy (`D:\Work\Backups\tradingsys`) không kiểm được từ VPS: người vận hành cần tự kiểm tra thư mục này có file mới hằng ngày và thử giải mã 1 bản (cần khoá `/root/.tradingsys-backup.key` đã sao ra ngoài).

## 6. Rủi ro còn lại
- Backup/WAL hiện cùng ổ đĩa với `pg-data` (chưa off-site) nên chưa chịu được mất host. Việc cần: mục 3.
- Quote thô >30 ngày bị xoá theo chính sách (không backup lâu hơn dump 14 ngày) — nếu cần tick dài hạn (backtest), đổi retention trong migration 009 trước khi có nguồn tick thật.
- Redis không sao lưu riêng (bus tạm, AOF everysec). `grafana-data`/`prom-data` không backup (provisioning nằm trong repo).
- `pg_dump` cảnh báo `--disable-triggers` về hypertable (đã kiểm chứng restore đủ dữ liệu); giữ restore-test hằng tuần.
