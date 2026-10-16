# Bản sao công khai (đã lọc)

Đây là ảnh chụp đã lọc của dự án nội bộ `trading-system`. So với bản chạy thật:

- Địa chỉ IP, số tài khoản MT5, email, đường dẫn máy cá nhân được thay bằng placeholder (`<VPS_IP>`, `<BASTION_IP>`, `<HOST_IP>`, `<OWNER_EMAIL>`, `<SECRETS_DIR>`; số tài khoản demo là `100000001`).
- Không có: lịch sử commit, `.env`/khoá/ACL Redis (xem `infra/redis/users.acl.example`), ảnh chụp màn hình QA, tài liệu bảo mật/pentest và tài liệu bàn giao nội bộ.
- Phạm vi: chỉ giám sát chỉ-đọc + paper; không đặt lệnh thật.
