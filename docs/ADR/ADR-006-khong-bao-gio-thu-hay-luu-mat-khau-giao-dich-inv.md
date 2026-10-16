# ADR-006: Không bao giờ thu hay lưu mật khẩu giao dịch/investor của MT

**Trạng thái:** Accepted (2026-10-11)

## Bối cảnh
Giám sát tài khoản MT thường làm bằng cách xin mật khẩu investor để server đăng nhập hộ. Việc đó khiến server giữ bí mật có thể bị lạm dụng và mở rộng hậu quả khi bị xâm nhập.

## Quyết định
Client **không nhập mật khẩu MT vào EA, cổng web hay gửi cho master**. EA chạy trong terminal client đã đăng nhập sẵn và chỉ gửi dữ liệu ra. Hệ thống lưu: passcode cổng (argon2id), token EA và mã ghép cặp (sha256), HMAC secret + TOTP secret (mã hoá Fernet bằng `AUTH_SECRET_KEY`). Nếu EA báo tài khoản **cho phép giao dịch** (không phải investor) hệ thống phát cảnh báo bảo mật.

## Hệ quả
- (+) Lộ DB hoặc server không dẫn tới chiếm tài khoản giao dịch của client.
- (-) Cần client cài và duy trì EA trong terminal; terminal tắt thì mất dữ liệu (hiển thị EA offline).
- Không đổi `AUTH_SECRET_KEY` sau khi đã có dữ liệu mã hoá.
