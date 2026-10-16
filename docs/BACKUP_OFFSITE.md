# Backup off-site (đích do người dùng cấp)

Script: `infra/ops/backup_offsite.sh` (bổ sung cho `infra/backup/offsite.sh` do `pg_backup.sh` gọi). Chỉ đẩy file ĐÃ MÃ HOÁ (`ts-*.dump.enc`, `.sha256`, `ts-config-*.tar.gz.enc`); không bao giờ đẩy khoá.

## Hành vi
- Mặc định DRY-RUN: chỉ liệt kê file sẽ đẩy. Chạy thật khi có `OFFSITE_DEST` VÀ (`--apply` hoặc `OFFSITE_APPLY=1`).
- Kiểm sha256 cục bộ trước khi đẩy; sau khi đẩy kiểm checksum hai phía (`rclone check --one-way` / `rsync --checksum -n`); lỗi => ghi `offsite.status=failed` (backupwatch cảnh báo).
- Giữ `OFFSITE_KEEP` bản (mặc định 14) ở cả nguồn-được-chọn lẫn đích (xoá bản cũ hơn ở đích). Timeout `OFFSITE_TIMEOUT` (900s). Log: `logs/backup_offsite.log`.
- Cấu hình qua biến môi trường hoặc `infra/ops/backup_offsite.env` (chmod 600, không commit): `OFFSITE_MODE=rclone|rsync`, `OFFSITE_DEST`, `RCLONE_CONFIG`, `OFFSITE_SSH_KEY`, `OFFSITE_KEEP`, `OFFSITE_TIMEOUT`.
- Lập lịch sau khi có đích: thêm sau bước backup 03:10 UTC (vd. timer/cron 03:30: `OFFSITE_APPLY=1 bash infra/ops/backup_offsite.sh`).

## Cách có đích miễn phí
- Cloudflare R2: 10 GB miễn phí, không phí egress (cần thẻ để kích hoạt). Backblaze B2: 10 GB đầu miễn phí. Cả hai dùng `rclone config` (loại S3/B2), đích dạng `remote:bucket/tradingsys`.
- Google Drive/OneDrive 15 GB/5 GB qua rclone (dữ liệu đã mã hoá nên an toàn).
- Máy cá nhân/VPS thứ hai qua rsync/ssh: tạo user hạn chế + khoá ssh riêng chỉ để ghi thư mục backup; `OFFSITE_MODE=rsync OFFSITE_DEST=user@host:/duong/dan`.
- Dung lượng: ≈70 MB/dump x 14 bản ≈ 1 GB + base backup 134 MB — vừa gói miễn phí.

## Sao khoá backup ra ngoài (BẮT BUỘC; mất khoá = mất mọi backup mã hoá)
1. Chỉ người vận hành (root) thực hiện, qua kênh riêng tư; không dán khoá vào chat, git, log, ảnh chụp màn hình chia sẻ.
2. Từ máy cá nhân: `scp root@<VPS>:/root/.tradingsys-backup.key .` rồi lưu vào password manager (mục ghi chú bảo mật/file đính kèm) và một bản in/USB cất két. Đặt `chmod 600` trên máy cá nhân.
3. KHÔNG lưu khoá cùng chỗ với bản backup off-site (đích bị lộ + khoá = lộ dữ liệu).
4. Kiểm: tải 1 bản backup từ đích về máy, giải mã bằng khoá đã sao: `openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass file:<khoá> -in ts-<ts>.dump.enc | pg_restore -l | head`. So sha256 khớp file `.sha256`.
5. Sau khi sao, xoá bản tạm trên máy trung gian. Khi xoay khoá: backup cũ vẫn cần khoá cũ — giữ cả hai.

## Việc cần người dùng
Cấp đích (R2/B2/SFTP...), sao khoá ra ngoài, rồi báo để bật timer.
