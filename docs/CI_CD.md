# CI/CD (không cần git server) — 2026-10-11

## Hiện trạng
- Deploy: `./deploy.sh "<lệnh compose>"` từ laptop lên VPS (`/root/trading-system`), ghi release (`.release`, giữ 5 tarball, tag image `rel-<VER>`), rollback bằng `infra/ops/rollback.sh`. Xem `infra/README.md`.
- Lockfile có hash: `services/<svc>/requirements.lock` cho 14/15 service Python (storage-writer, market-collector, news-collector, expert-collector, mt-bridge, alert-service, api-gateway, analytics, alert-rules, paper-trader, nlp, risk-monitor, reporter, vn-market; journal theo mẫu khi có). Sinh lại: `sh infra/ops/lock_deps.sh <svc>...` trên VPS (uv trong container tạm), chép về repo bằng `sftp-get`. Dockerfile cài `pip install --only-binary=:all: --require-hashes -r requirements.lock` rồi `--no-deps` cho `libs/common` và service; base image ghim digest `python:3.12-slim@sha256:...`; web-ui ghim digest cho `node:22-alpine` và `nginx-unprivileged:stable-alpine` (npm: `package-lock.json` + `npm ci`). Từ 2026-10-12 cả 7 service còn lại (paper-trader, nlp, analytics, risk-monitor, reporter + web-ui) đã chuyển theo mẫu.
- Pre-commit: `.pre-commit-config.yaml` (check-yaml, detect-private-key, ruff, gitleaks, shellcheck); `ruff.toml` lint lỗi thật. `.gitignore` bổ sung `.env.*`, `*.dump*`, `backups/`, `wal-archive/`, `data/`, htpasswd, `*.key`, `.release`.
- GitHub Actions (`.github/workflows/ci.yml`): ruff + gitleaks, pytest theo từng package, quét tĩnh "không có mã đặt lệnh", build image + trivy fs + SBOM CycloneDX (syft). Chạy khi có remote GitHub.
- CI trên VPS (không cần remote): `sh infra/ops/ci_vps.sh [quick]` = ruff + pytest (container tạm) + static read-only scan + trivy fs + SBOM syft cho image đang chạy (`/var/tmp/tradingsys-ci/sbom-*.cdx.json`). `infra/ops/trivy_scan.sh` quét image đang chạy; `infra/ops/run_tests.sh` chạy pytest chọn lọc.

## Quy trình đề xuất
1. Sửa code + test: `./deploy.sh ""` rồi `sh infra/ops/run_tests.sh <pkg>` trên VPS.
2. `sh infra/ops/ci_vps.sh quick`.
3. `./deploy.sh "up -d --build --no-deps <svc>"` từng service, kiểm healthcheck.
4. e2e: `bash tests/e2e/deploy.sh` rồi `cd /root/qa-e2e && sh run_remote.sh test_flow.py` (+ `cleanup.py`).
5. Lỗi thì `infra/ops/rollback.sh`.
Lộ trình: tạo remote (Gitea/GitHub), Renovate chạy thật, ký image cosign, tag theo SHA.

## Phụ lục — Đăng nhập mạnh cho web-ui (đề xuất, chưa triển khai)
Hiện (từ 2026-10-12): đăng nhập phiên do service `auth` (argon2id, TOTP tuỳ chọn, `auth_request`) + giới hạn đăng nhập sai theo IP thật (CF-Connecting-IP); Basic Auth chỉ là dự phòng. Các phương án dưới đây là lớp bổ sung phía ngoài (SSO/MFA), chưa triển khai. Khuyến nghị theo thứ tự:
1. Cloudflare Named Tunnel + Cloudflare Access (miễn phí đến 50 user, MFA/OIDC): tạo tunnel có tên (cần tài khoản Cloudflare), policy theo email; giữ Basic Auth làm lớp phụ. Thay `install_tunnel.sh` (quick tunnel) bằng `cloudflared tunnel run <tên>` dùng token.
2. Tự host: Authelia (OIDC/TOTP/WebAuthn) làm `auth_request` cho nginx: thêm container `authelia` (mạng internal) và trong `default.conf.template` đổi `location = /_auth` thành `proxy_pass http://authelia:9091/api/authz/auth-request`; hoặc Caddy (`forward_auth authelia:9091`) làm cổng TLS phía trước nginx.
3. Token đọc-only theo vai (viewer/admin) cho gateway; xoay `API_TOKEN` khi đổi người.
