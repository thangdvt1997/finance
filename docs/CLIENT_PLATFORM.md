# CLIENT_PLATFORM — kiến trúc master/client (hợp đồng chung cho mọi agent)

Hệ thống này là ỨNG DỤNG MASTER hỗ trợ/điều khiển các CLIENT = tài khoản MT4/MT5 (mỗi client là một tài khoản MT, định danh bằng nền tảng + số tài khoản + máy chủ broker). Giai đoạn này: MONITOR/HỖ TRỢ (read-only). Điều khiển/giao dịch thêm sau (qua service riêng, có cổng pháp lý G1-G3). Không hiển thị tên nguồn dữ liệu trên UI/báo cáo/thông báo (docs/UI_NO_SOURCES.md).

## Vai trò
- `master`: quản trị viên (người vận hành). Thấy mọi client, quản lý client/tài khoản, cấp mã, xem sức khoẻ hệ thống. (đã chuyển sang đăng nhập phiên + TOTP tuỳ chọn từ 2026-10-12; basic-auth chỉ còn dự phòng, xem docs/AUTH.md.)
- `client`: chủ tài khoản MT. Đăng nhập bằng ID MT (nền tảng + số tài khoản) + mật khẩu cổng (passcode do master cấp hoặc tự đặt sau khi ghép cặp). CHỈ thấy dữ liệu của tài khoản MÌNH + dữ liệu thị trường/tin/lịch dùng chung. TUYỆT ĐỐI không thu mật khẩu giao dịch/investor MT của client qua web.

## Định danh
`account_id` = `<platform>:<login>` ví dụ `mt5:12345678` (platform ∈ mt4|mt5; server broker lưu kèm trong `mt_accounts.server`). Khoá đăng nhập: platform + login (+ server nếu trùng số).

## Bảng (role DB riêng `ts_auth`, migration + script tạo role theo mẫu analytics/journal)
- `mt_accounts(account_id pk, platform, login bigint, server, label, client_id, status[pending|active|suspended], ea_token_hash, ea_hmac_secret_enc, pairing_code_hash, pairing_expires_at, created_at, last_seen_at, notes)`
- `portal_users(user_id uuid pk, role[master|client], login_key unique, display_name, password_hash(argon2id), totp_secret_enc null, status, failed_attempts, locked_until, must_change_password, created_at, last_login_at)`; client↔account: `user_accounts(user_id, account_id)`.
- `portal_sessions(session_id pk, user_id, created_at, expires_at, last_seen_at, ip, user_agent, revoked)`
- `audit_log(id, ts, actor_user_id, action, target, ip, detail jsonb)` (hash-chain tuỳ chọn)

## Dịch vụ `auth` (FastAPI, OSS: argon2-cffi, pyotp tuỳ chọn)
- `POST /auth/login {platform, login, secret, server?}` → cookie phiên HttpOnly+Secure+SameSite=Strict (id ngẫu nhiên 256 bit, lưu băm), rate limit theo IP+tài khoản, khoá tạm, thông báo lỗi chung, audit.
- `POST /auth/logout`, `GET /auth/me` → `{user_id, role, display_name, accounts:[account_id...]}`, `POST /auth/change-password`, `POST /auth/pair {platform, login, pairing_code, new_password}` (lần đầu: mã ghép cặp hiển thị trong log Experts của EA hoặc do master cấp).
- Master (role=master): CRUD client/tài khoản, cấp lại passcode, xoay EA token/HMAC, đình chỉ/kích hoạt, xem audit/phiên, ép đăng xuất.
- `GET /auth/verify` cho nginx `auth_request` (trả 200 + header `X-User-Id`, `X-Role`, `X-Accounts`) → nginx đặt header tin cậy xuống api-gateway (gateway chỉ tin header từ nginx nội bộ; chặn client tự đặt header).
- mt-bridge xác thực EA bằng token lấy từ DB `mt_accounts` (băm, cache ngắn) thay vì accounts.yaml tĩnh; tài khoản mới tự xuất hiện khi master tạo.

## Phạm vi dữ liệu (gateway áp dụng bắt buộc)
- Công khai cho mọi người dùng đã đăng nhập: giá/nến/chỉ báo, tin, lịch, cửa sổ rủi ro, chứng khoán VN, crypto, bản tin.
- Theo tài khoản (lọc bằng `account_id ∈ accounts` của phiên; master thấy tất cả): account snapshots/vị thế/lệnh, risk, journal (+ghi chú), cảnh báo cá nhân (alert-rules), báo cáo, paper (chỉ master).
- Chỉ master: hệ thống, quản trị client, paper-trading toàn cục, nguồn/hạ tầng.
- Mọi endpoint theo tài khoản phải kiểm tra quyền; test chống IDOR (client A không đọc được B).

## Ứng dụng
- `services/client-ui` (mới): PWA mobile-first cho CLIENT, đường dẫn `/c/`, dùng chung design system; trang: Đăng nhập (ID MT), Tài khoản (equity/balance/margin, vị thế, lệnh chờ), Rủi ro, Nhật ký, Thị trường (watchlist + biểu đồ + TA), Tin & Lịch (+cửa sổ rủi ro), Cảnh báo của tôi, Hồ sơ/đổi mật khẩu/phiên.
- `web-ui` (master): thêm trang 'Khách hàng' (fleet): danh sách tài khoản, trạng thái EA (kết nối/độ trễ/lần cuối), cấp mã ghép cặp, xoay token, đình chỉ, nhật ký đăng nhập, xem như khách hàng (impersonate chỉ-đọc, có audit).
- Không có chức năng đặt lệnh ở bất kỳ UI nào.

## Vận hành EA + cấp phát tài khoản động (mt-bridge ↔ auth) — HỢP ĐỒNG NỘI BỘ
Chủ sở hữu: `services/mt-bridge` + `mt-agent/` (bridge là CLIENT của auth; auth KHÔNG đọc/ghi DB của bridge, bridge KHÔNG đọc DB của auth).

**Luồng provisioning**: master tạo `mt_accounts` (status `pending`, sinh `ea_token` + `hmac_secret` + `pairing_code`) → client cài EA (README `mt-agent/`), nhập `PairCode` (hoặc `Token`+`HmacSecret` do master giao) → EA gọi `POST /ingest/v1/register` → bridge hỏi auth → EA nhận credential (1 lần) hoặc trạng thái → EA gửi snapshot ký HMAC → bridge xác thực theo bản ghi của auth → tài khoản hiện trên master (`GET /accounts` của bridge + sự kiện `mt.account_status`) và client UI (dữ liệu `account.snapshots`).

**Quyết định**: bridge gọi HTTP nội bộ của auth (không đọc DB chéo service) bằng token dịch vụ; cache RAM TTL 15 giây (`BRIDGE_AUTH_TTL_S`) + thu hồi tức thì qua `POST bridge:8000/internal/invalidate`; auth tạm chết → dùng cache tối đa 10 phút (stale-if-error) rồi fail-closed (503/401). Tài khoản YAML (`infra/mt-bridge/accounts.yaml`) vẫn chạy song song (dynamic ưu tiên khi trùng `account_id`).

**Auth phải cung cấp** (mạng `ops`/`backend`, header `Authorization: Bearer <BRIDGE_AUTH_TOKEN>` = cùng giá trị ở `AUTH_INTERNAL_TOKEN`; chỉ mt-bridge gọi; KHÔNG qua nginx công khai). `account_id` có thể chứa `:` → URL-encode (`mt5%3A12345678`):
- `GET /internal/mt-accounts` → `{"rev": int, "accounts": [Record...]}` (toàn bộ, ≤ vài nghìn; bridge poll mỗi ~10 giây).
- `GET /internal/mt-accounts/{account_id}` → `Record` | 404 (bridge gọi khi gặp tài khoản chưa có trong cache → master vừa tạo là hiện ngay).
- `Record = {account_id, platform(mt4|mt5), status(pending|active|suspended), ea_token_hash, hmac_secret, require_hmac(bool, mặc định true), rev, config?}`:
  - `ea_token_hash` = `sha256(token).hexdigest()` (token ngẫu nhiên ≥128 bit, hiển thị cho master/EA ĐÚNG 1 LẦN).
  - `hmac_secret` = secret DẠNG RÕ (bridge cần để tính HMAC; auth giải mã `ea_hmac_secret_enc` khi trả; endpoint chỉ cho service token). `require_hmac` mặc định TRUE cho tài khoản mới.
  - `config` (tuỳ chọn): chỉ các khoá `symbol_prefix, symbol_suffix, symbol_aliases, watch_symbols, timeframes, server_tz, server_utc_offset_hours, rules` (không cho đặt token/transport).
  - giá trị `status` lạ → bridge coi là `suspended` (fail-closed).
- `POST /internal/mt-accounts/register` body `{platform, login, server, company, build, ea, pair_code, remote_addr}` → `{status: pending|active|suspended|rejected|unknown, account_id?, message?, pairing_code?, token?, hmac_secret?}`. `pair_code` đúng + khớp (platform, login) → trả `token`+`hmac_secret` MỚI (1 lần, vô hiệu hoá mã), chuyển tài khoản `active` (master cấp mã = đã duyệt) hoặc giữ `pending` nếu chính sách yêu cầu duyệt; `pair_code` rỗng + tự đăng ký BẬT → tạo `pending` + trả `pairing_code` để EA hiển thị (client nhập ở `/auth/pair`); sai mã → `rejected`. HTTP 429 → bridge báo `rate_limited`. Auth tự giới hạn tốc độ/khoá mã theo (platform, login). Bridge KHÔNG lưu/log `token`/`hmac_secret` trong phản hồi này.
- `POST /internal/mt-accounts/seen` body `{items:[{account_id, status(online|degraded|offline), reason, pending, last_seen_at, latency_ms, skew_s, ea_version, build, broker, server, remote_addr}]}` (gộp lô, mỗi tài khoản ≤1 lần/30 giây hoặc khi đổi trạng thái) → auth cập nhật `mt_accounts.last_seen_at` (+ cột sức khoẻ nếu muốn) để master hiển thị 'sức khoẻ EA'.
- `POST /internal/mt-accounts/audit` body `{account_id, action, detail}` (vd `ea_rejected_suspended`, tối đa 1/5 phút/tài khoản) → ghi `audit_log`.
- Auth gọi bridge sau MỖI thay đổi (xoay token/HMAC, đình chỉ/kích hoạt, xoá): `POST http://mt-bridge:8000/internal/invalidate` `{account_id}` + `Authorization: Bearer <BRIDGE_AUTH_TOKEN>` → hiệu lực ở request kế tiếp (không chờ TTL).

**Mã trả cho EA** (`POST /ingest/v1`): 200 ok; **202 `pending`** (đã xác thực nhưng chưa được duyệt: KHÔNG nhận dữ liệu, EA đợi 30 giây); 401 token/HMAC/ts sai hoặc thu hồi (đồng nhất, không lộ sự tồn tại); **403 `suspended`** (+ audit); 409 replay; 422 schema; 429 giới hạn tốc độ (`Retry-After`); 503 auth chưa sẵn sàng. `POST /ingest/v1/register`: 200 (`active|pending`) / 403 (`rejected|suspended`) / 404 / 429 / 502; phản hồi `Cache-Control: no-store`.

**Sự kiện `mt.account_status`** (bus; chỉ khi đổi trạng thái): payload `{account_id, platform, status(online|degraded|offline), reason, pending, ts, last_seen_at, latency_ms, ea_version, build, broker, server}` — KHÔNG có địa chỉ IP (IP chỉ gửi cho auth qua `/seen`, master xem).

**HMAC**: bật mặc định cho mọi tài khoản động (`require_hmac=true`); YAML: `require_hmac: true|false` theo tài khoản (hoặc `MT_REQUIRE_HMAC=1` toàn cục); `X-MT-Sig = hex(HMAC_SHA256(secret, "{ts}.{nonce}." + body))`. EA 1.1 (MQL4+MQL5) ký đã kiểm chứng trong lab (0 lỗi biên dịch).

**Vận hành EA (tóm tắt, chi tiết `mt-agent/README.md`)**: client KHÔNG nhập mật khẩu giao dịch/investor ở bất kỳ đâu (EA không cần đăng nhập; terminal dùng tài khoản của chính client). Chỉ cần: tải EA, thêm URL vào Allow WebRequest, nhập `BridgeUrl` + `PairCode` (hoặc `Token`+`HmacSecret`). EA in mã ghép cặp/trạng thái ở tab Experts và `Comment()` trên chart (không in token/HMAC). Giới hạn tốc độ: 5 req/giây/tài khoản (burst 20), khoá tạm theo (IP, tài khoản) khi xác thực sai liên tục.

## Cập nhật 2026-10-12 (auth đã triển khai — chi tiết `docs/AUTH.md`)
- Đăng nhập phiên đang chạy; basic-auth chỉ còn là dự phòng (`AUTH_BASIC_FALLBACK=1`, mặc định tắt). Migration `011_auth.sql`, role `ts_auth` (+ `ts_mtauth` đọc hẹp cho mt-bridge).
- `/auth/login` nhận `platform` ∈ master|mt4|mt5 (master: `login`=tên). `X-Accounts` = danh sách account_id (`*` không dùng cho client). Gateway: `GET /v1/me`, mặc định từ chối cho role client (whitelist `CLIENT_ALLOW`), `/user/rules|prefs` chỉ master cho tới khi alert-rules có owner.
- Quy ước mt-bridge: pairing_code_hash = sha256(chữ hoa, chỉ chữ-số), ea_token_hash = sha256, ea_hmac_secret_enc = Fernet(AUTH_SECRET_KEY).
- Vỏ tĩnh client-ui `/c/` công khai ở nginx (`AUTH_PUBLIC_PREFIXES`); dữ liệu luôn sau `/api` có phiên.

## Cập nhật 2026-10-12 (provisioning nội bộ đã nối end-to-end)
- Auth đã cung cấp đủ `/internal/mt-accounts*` (list/get/register/seen/audit) + gọi `mt-bridge /internal/invalidate`; token dịch vụ `BRIDGE_AUTH_TOKEN` (env của cả auth và mt-bridge), `BRIDGE_AUTH_URL=http://auth:8000`. Kích hoạt tài khoản = duyệt. Chi tiết + rủi ro: `docs/AUTH.md` mục 6; e2e: `tests/e2e/test_provisioning.py`.

## Cập nhật 2026-10-12 (backend cho ứng dụng client: cảnh báo cá nhân, lệnh chờ, tiền tệ, Web Push)
Migration `infra/db/migrations/013_client_backend.sql` (áp bằng `bash infra/db/apply_migration.sh migrations/013_client_backend.sql`). Chi tiết vận hành: `services/alert-rules/README.md`.
- **Cảnh báo cá nhân theo chủ sở hữu**: `alert_rules.owner_user_id` (+`account_id`), `alert_rule_events.owner_user_id`. Gateway mở `/v1/user/rules` (CRUD, preview), `/v1/user/rule-events`, `/v1/user/push*` cho role client; gateway dựng `X-Owner-Role/X-Owner-User/X-Owner-Accounts` từ header tin cậy của nginx (KHÔNG chuyển tiếp từ client) và alert-rules lọc mọi truy vấn theo chủ sở hữu (không khớp = 404, không oracle). Client: tối đa 20 quy tắc, điều kiện `account` BẮT BUỘC gắn tài khoản của chính họ (422 nếu khác; áp cả preview), kênh chỉ `app`/`push` (không ntfy/telegram toàn cục), cooldown >= 5 phút, quy tắc gắn tài khoản không còn thuộc họ bị tự tắt. Kích hoạt quy tắc cá nhân KHÔNG phát `alerts.out` (không lộ qua ntfy/telegram của người vận hành): chỉ ghi `alert_rule_events` theo chủ (app đọc `/v1/user/rule-events`) + Web Push chung. master thấy/sửa mọi quy tắc (không đổi chủ). `/v1/user/prefs` vẫn chỉ master.
- **Lệnh chờ**: bảng `account_orders`; `/v1/accounts` trả thêm `orders[]` (đang mở) mỗi tài khoản; `GET /v1/accounts/{id}/orders?status=open|removed|all&limit=` (client chỉ tài khoản của mình, 403 đồng nhất).
- **Tiền tệ**: `account_snapshots.currency` -> `/v1/accounts|overview[].currency` (UI không được cộng gộp tài khoản khác tiền tệ).
- **Web Push (VAPID tự host, miễn phí)**: module trong alert-rules (`webpush.py`); bảng `push_subscriptions` (endpoint + khoá mã hoá Fernet, chỉ role `ts_userconf`; `ts_ro` bị thu hồi). API client: `GET /v1/user/push` (bật/tắt, public key, số thiết bị), `POST /v1/user/push/subscribe|unsubscribe|test`. Nội dung push chung ("Cảnh báo mới" + liên kết `/c/#/thong-bao`), không số dư/tên tài khoản/tên nguồn. Giới hạn: 5 thiết bị/người, 20 push/giờ/người, endpoint chỉ https tới dịch vụ push đã biết (chống SSRF), 404/410 hoặc 5 lỗi liên tiếp -> xoá. Bật: `bash infra/ops/gen_vapid.sh` (sinh khoá vào infra/.env, không in) rồi `./deploy.sh "up -d --no-deps alert-rules"`.


## Control plane (tương lai)
Thiết kế mặt phẳng điều khiển an toàn (bậc L0-L4, kênh lệnh EA kéo + chữ ký Ed25519, risk engine, kill-switch 4 tầng, consent/opt-in của client, STRIDE, lộ trình) ở `docs/CONTROL_PLANE_DESIGN.md`. Chỉ là THIẾT KẾ: hệ thống vẫn READ-ONLY, mọi bậc từ L2 trở lên cần cổng pháp lý G1-G3 + luật sư. Quy tắc bất biến: không lưu mật khẩu giao dịch/investor; giới hạn do client đặt có hiệu lực cao nhất; LLM không ra lệnh.

## Cập nhật 2026-10-12: giới hạn/thông báo/prefs/ticket
Migration `infra/db/migrations/015_client_limits.sql` (role `ts_userconf`; `ts_ro` bị thu hồi). Chi tiết hợp đồng + vận hành: `services/alert-rules/README.md`. Gateway `/v1/user/*` + nginx client-ui whitelist đã mở:
- `GET|PUT /user/limits` (+`GET /user/limits/history`): giới hạn/mục tiêu do client đặt, SIẾT áp ngay, NỚI/XOÁ chờ 24 giờ (`pending_value`/`pending_effective_at`), tiến độ `progress{level ok|warn|danger|hit|unknown}`; nhắc mốc 70/90/100% qua thông báo `limit` + Web Push chung. Chỉ nhắc, không chặn lệnh; giới hạn của client có hiệu lực cao nhất (CONTROL_PLANE_DESIGN).
- `GET /user/notifications`, `POST /user/notifications/read`; phát từ service khác: `POST alert-rules:8000/internal/notifications` (nội bộ, không qua gateway).
- `GET|PUT /user/client-prefs` (rev lạc quan, 409, <=8KB, khoá whitelist), `GET /user/push/devices`, `DELETE /user/push/devices/{id}`.
- `POST|GET /user/tickets` (client), `PUT /user/tickets/{id}` chỉ master -> thông báo `support` cho chủ. Chống spam 5/giờ/người + gộp trùng.
- Kiểm thử: pytest alert-rules (`test_client_api.py`) + api-gateway (`test_authz.py`), e2e `services/client-ui/qa/e2e_client_api.sh` (2 tài khoản thử A/B, tự xoá).
