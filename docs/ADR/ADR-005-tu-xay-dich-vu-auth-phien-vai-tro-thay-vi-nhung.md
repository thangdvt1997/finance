# ADR-005: Tự xây dịch vụ auth (phiên + vai trò) thay vì nhúng OSS SSO

**Trạng thái:** Accepted (2026-10-12) - lý do dựng lại từ AUTH.md/CI_CD.md

## Bối cảnh
Cần hai loại người dùng: master và **client đăng nhập bằng ID tài khoản MT** (nền tảng + số tài khoản + passcode do master cấp, ghép cặp với EA), phân quyền theo từng `account_id`, vai trò phụ có phạm vi nhóm, cấp phát token EA/HMAC động cho `mt-bridge`. Ban đầu chỉ có Basic Auth nginx. OSS đã cân nhắc: Authelia (OIDC/TOTP/WebAuthn), Cloudflare Access, oauth2-proxy (`OSS_REUSE.md`, `CI_CD.md`).

## Quyết định
Viết service **`auth`** (FastAPI + argon2-cffi + pyotp + cryptography/Fernet): cookie phiên `ts_session` (HttpOnly/Secure/SameSite=Strict, id 256 bit, DB chỉ lưu sha256), khoá tạm, TOTP tuỳ chọn (bắt buộc cho thao tác nhạy cảm của master), audit append-only có hash-chain. nginx dùng `auth_request` + **đè** `X-User-Id/X-Role/X-Accounts` và thêm `X-Auth-Secret`; gateway tự áp whitelist + lọc theo tài khoản. Basic Auth giữ làm đường dự phòng (`AUTH_BASIC_FALLBACK=1`, mặc định tắt). Các OSS SSO vẫn là phương án nâng cấp lớp ngoài (không thay được mô hình quyền theo tài khoản MT).

## Hệ quả
- (+) Mô hình quyền khớp nghiệp vụ (client gắn tài khoản MT), tích hợp trực tiếp với bridge, test e2e 134 kiểm tra (IDOR, khoá tạm, ghép cặp, TOTP, WebSocket).
- (-) Tự giữ mã bảo mật nhạy cảm; rủi ro còn lại ghi ở `AUTH.md` mục 5 (prefs dùng chung 1 người, rate-limit trong bộ nhớ, `AUTH_TRUST_SECRET` trong mạng nội bộ...).
- Chưa có 2FA/khoá thiết bị cho client.
