# AUTH — đăng nhập master/client và phân quyền (2026-10-12)

Hợp đồng chung: `docs/CLIENT_PLATFORM.md`. Mã: `services/auth/`, `services/api-gateway/src/api_gateway/authz.py`, `services/web-ui/nginx/default.conf.template`.

## 1. Mô hình đe doạ (tóm tắt)
| Mối đe doạ | Biện pháp |
|---|---|
| Dò mật khẩu / dò tài khoản tồn tại | argon2id; lỗi chung "ID hoặc mật khẩu không đúng" (cùng mã + nội dung cho sai/không tồn tại/khoá/đình chỉ); luôn băm giả khi không có user (cân bằng thời gian); khoá tạm 5 lần sai → 15 phút (theo tài khoản, kể cả khoá không tồn tại); giới hạn 30 lần sai/10 phút/IP (429); nginx 20 POST/phút/IP |
| Đánh cắp phiên | cookie `ts_session` HttpOnly + Secure + SameSite=Strict; id 256 bit, DB chỉ lưu sha256; hạn tuyệt đối + idle (master 12h/2h, client 7d/48h); đổi mật khẩu/ghép cặp/reset/đình chỉ thu hồi phiên |
| CSRF | SameSite=Strict + kiểm Origin/Sec-Fetch-Site ở nginx và ở auth; thân JSON bắt buộc |
| Giả mạo danh tính xuống gateway | nginx ĐÈ `X-User-Id/X-Role/X-Accounts` và thêm `X-Auth-Secret` (AUTH_TRUST_SECRET); gateway chỉ tin khi secret khớp (hằng thời gian); có header người dùng mà thiếu/sai secret → 403; vẫn cần `X-API-Key` |
| IDOR | gateway mặc định TỪ CHỐI cho role client (whitelist), kiểm `account_id ∈ accounts` trước khi gọi service, lọc danh sách trả về, lọc WebSocket; 403 đồng nhất (không oracle tồn tại) |
| Lộ bí mật ở DB | passcode argon2id; token EA + mã ghép cặp = sha256; HMAC secret + TOTP secret mã hoá Fernet (`AUTH_SECRET_KEY`); audit không chứa bí mật |
| Sửa/xoá dấu vết | `audit_log` append-only (role `ts_auth` chỉ SELECT/INSERT) + chuỗi băm; `GET /auth/admin/audit/verify` |
| Auth sập | `auth_request` lỗi → 500 (đóng); không bao giờ mở |
Không thu/lưu mật khẩu giao dịch hay investor MT.

## 2. Luồng
- **Master**: `/auth/login` {platform:"master", login:"admin", secret, totp?} → cookie. Lần đầu bắt buộc đổi mật khẩu (`must_change_password`; trước đó mọi `/api` bị 401, chỉ `/auth/*` dùng được). TOTP tuỳ chọn: `POST /auth/totp/setup` → `enable {code}`; mỗi mã chỉ dùng một lần.
- **Client**: master tạo tài khoản MT (`POST /auth/admin/accounts {platform, login, server?, label?}`) → trả MỘT lần: `passcode` (mật khẩu cổng ban đầu), `pairing_code` (hết hạn 7 ngày, một lần), `ea_token`, `hmac_secret`. Client đăng nhập `{platform:"mt5", login:"<số>", secret:<passcode>, server?}` rồi đổi mật khẩu; hoặc `POST /auth/pair {platform, login, pairing_code, new_password}` (mã do master cấp hoặc EA tự đăng ký hiển thị trong log Experts) để tự đặt mật khẩu.
- **nginx**: `auth_request /_auth` → `GET /auth/verify` (nội bộ, không lộ ra ngoài) → 200 + `X-User-Id/X-Role/X-Accounts` hoặc 401. Chưa đăng nhập: `/api/*` và `/auth/admin/*` → 401 JSON; trang → 302 `/auth/login?next=`. Công khai tối thiểu: `/auth/login`, `/auth/static/*`, API `/auth/*` (tự xác thực), `/healthz`, và tiền tố `AUTH_PUBLIC_PREFIXES` (mặc định `/c/,/manifest.webmanifest,/sw.js,/favicon`, vỏ tĩnh client-ui; `/api/` không bao giờ công khai). WebSocket đi qua cùng `auth_request`.
- **Trang đăng nhập dự phòng**: `/auth/login` (do service auth phục vụ, CSP chặt); client-ui/web-ui có thể dùng trang riêng gọi cùng API.
- Quy ước pairing cho mt-bridge: mã chuẩn hoá = chữ hoa, bỏ ký tự không phải chữ-số, băm sha256 hex → `mt_accounts.pairing_code_hash`; token EA = sha256 hex → `ea_token_hash`; `ea_hmac_secret_enc` = Fernet(`AUTH_SECRET_KEY`). Role đọc hẹp `ts_mtauth` (SELECT cột xác thực, UPDATE last_seen/status/pairing/token, INSERT) cho bridge.

## 3. Bảng quyền (gateway `/v1`)
| Nhóm | master / service(API key) | client |
|---|---|---|
| Giá/nến/chỉ báo/phân tích, tin, lịch, chuyên gia, cửa sổ rủi ro, `/vn/*`, `/briefing*`, `/risk/config`, `/user/csrf`, `/me` | có | có (GET) |
| `/accounts`, `/overview`, `/equity-history`, `/risk/accounts[/id]`, `/journal/*` (+ ghi chú/tag PUT/DELETE) | tất cả | chỉ tài khoản của mình (lọc danh sách; id khác → 403) |
| `/system`, `/alerts`, `/data-sources`, `/reports*`, `/paper/*`, `/user/rules|rule-events|prefs` (+ ghi) | có | 403 |
| WebSocket `/v1/stream` | mọi stream | stream thị trường + `account.*` đã lọc theo `account_id`; `alerts.out` bị từ chối |
| `/auth/admin/*` (quản trị client/tài khoản/phiên/audit) | master (service auth tự ép role) | 403 |
Route mới thêm sau: client mặc định bị 403 cho tới khi thêm vào `CLIENT_ALLOW` trong `authz.py` (+ nếu theo tài khoản: thêm kiểm trong `account_from_request`/`filter_payload`).
Cảnh báo cá nhân (`/user/rules|rule-events|push*`): client được dùng, CHỈ trên bản ghi của chính họ (gateway gắn danh tính chủ sở hữu, alert-rules lọc; xem `docs/CLIENT_PLATFORM.md` cập nhật 2026-10-12). `/user/prefs` vẫn chỉ master. Lệnh chờ: `/accounts/{id}/orders` (theo tài khoản).

## 4. Vận hành
- Tạo role/DB/khoá: `bash infra/db/create_auth_role.sh` (migration `011_auth.sql`; sinh `POSTGRES_AUTH_PASSWORD`, `POSTGRES_MTAUTH_PASSWORD`, `AUTH_SECRET_KEY`, `AUTH_TRUST_SECRET` vào `infra/.env`). **Không đổi `AUTH_SECRET_KEY` sau khi đã có dữ liệu mã hoá** (HMAC/TOTP sẽ không giải mã được).
- Bootstrap master: `bash infra/ops/auth_bootstrap_master.sh` → mật khẩu ngẫu nhiên ghi `<SECRETS_DIR>/auth_master_admin.txt` (0600, root; không in log). Đọc: `cat` file đó trên VPS. Đổi ngay ở lần đăng nhập đầu rồi xoá file.
- Quên mật khẩu/mất thiết bị 2FA: `bash infra/ops/auth_bootstrap_master.sh --reset` (mật khẩu mới ngẫu nhiên, tắt TOTP, thu hồi mọi phiên).
- Đường dự phòng basic-auth (htpasswd): mặc định TẮT. Bật khẩn cấp: `AUTH_BASIC_FALLBACK=1` trong `infra/.env` rồi `./deploy.sh "up -d --no-deps web-ui"` (cần `infra/web-ui/auth/htpasswd`; chỉ được tính khi request có header Authorization; được coi là master; giới hạn đoán mật khẩu theo IP).
- Giám sát: Gatus `auth` (`/readyz`), Prometheus `auth:8000/metrics` (`auth_logins_total`). Kiểm toàn vẹn audit: `docker exec tradingsys-auth python -m auth.cli verify-audit`.
- Thu hồi: master `POST /auth/admin/users/{id}/revoke-sessions`, `/auth/admin/sessions/{id}/revoke`; đình chỉ tài khoản `.../accounts/{id}/suspend`.
- Deploy theo thứ tự: gateway (có `AUTH_TRUST_SECRET`) → auth → web-ui. Rollback: `infra/ops/rollback.sh`; hoặc `AUTH_BASIC_FALLBACK=1`.
- Test: `pytest` `services/auth`, `services/api-gateway/tests/test_authz.py`; e2e `tests/e2e/test_auth.py` (134 kiểm tra: đăng nhập, khoá tạm, pairing, TOTP, IDOR qua nginx, WebSocket, audit).

## 5. Rủi ro còn lại
- `prefs` (watchlist/layout) vẫn dùng chung 1 người dùng 'admin' (client lưu prefs trên thiết bị). Quy tắc cá nhân đã có chủ sở hữu; alert-rules tin header phạm vi do gateway gắn (chỉ mạng nội bộ): ai gọi thẳng alert-rules từ mạng backend/ops có thể tự đặt danh tính.
- Cookie `Secure` yêu cầu HTTPS (Cloudflare) hoặc localhost; truy cập HTTP thuần qua IP sẽ không giữ phiên.
- Giới hạn tốc độ/khoá tạm lưu bộ nhớ (1 instance auth; restart xoá bộ đếm IP, khoá theo tài khoản vẫn còn trong DB); kẻ biết ID có thể cố ý khoá tạm tài khoản (DoS nhẹ, 15 phút).
- Phiên được cache 5s trong auth: thu hồi có hiệu lực ≤5s ở tiến trình khác (cùng tiến trình: tức thì).
- Ai giữ `AUTH_TRUST_SECRET` + API key (trong mạng nội bộ) có thể tự đặt danh tính; bí mật chỉ nằm trong env web-ui/gateway.
- Chưa có khoá theo thiết bị/2FA cho client; chưa có khoá lock-file image (`lock_deps.sh`) cho auth.

## 6. API nội bộ cho mt-bridge (đã triển khai 2026-10-12)
Chỉ mạng backend/ops, `Authorization: Bearer <BRIDGE_AUTH_TOKEN>` (cùng giá trị ở mt-bridge `BRIDGE_AUTH_TOKEN` và auth; sinh bởi `create_auth_role.sh`; KHÔNG qua nginx công khai; thiếu/sai token -> 401, chưa cấu hình -> 503). mt-bridge đặt `BRIDGE_AUTH_URL=http://auth:8000` (cùng mạng `backend`/`ops`).
- `GET /internal/mt-accounts` -> `{rev, accounts:[Record]}`; `GET /internal/mt-accounts/{id}` -> Record | 404. `Record = {account_id, platform, status, ea_token_hash, hmac_secret (giải mã Fernet), require_hmac (mặc định true), rev, config}`.
- `POST /internal/mt-accounts/register` (EA qua bridge): `pair_code` đúng (master cấp, tài khoản đã có chủ) -> token + HMAC MỚI một lần, tài khoản `active`; mã sai -> `rejected` (403, giới hạn theo IP + (platform,login)); không mã + chưa có tài khoản -> tự đăng ký `pending` (chưa có chủ) + `pairing_code` để client nhập ở `/auth/pair` (giới hạn 5 tài khoản/giờ/IP, tối đa 500 chưa ghép); sau khi client ghép cặp, EA gọi lại từ CÙNG IP nhận credential một lần (lưu mã hoá `ea_cred_pending_enc`, xoá sau khi giao).
- `POST /internal/mt-accounts/seen` -> cập nhật `last_seen_at` + `ea_status/latency/skew/version/build/broker/remote_addr` (master xem trong `GET /auth/admin/accounts`); `POST /internal/mt-accounts/audit` -> `audit_log` (actor `mt-bridge`).
- auth gọi `POST mt-bridge:8000/internal/invalidate {account_id}` sau: tạo/duyệt/đình chỉ/kích hoạt/xoá, xoay token/HMAC, ghép cặp -> hiệu lực ngay (đã kiểm: 0,01s). **Kích hoạt = master duyệt** (`pending -> active`); `pending` thì bridge trả 202 và không nhận dữ liệu.
- Migration `012_auth_bridge.sql` (rev, require_hmac, config, cột sức khoẻ EA). Test: `tests/e2e/test_provisioning.py` (50 kiểm tra: tạo -> pending 202 -> duyệt -> HMAC -> snapshot -> `/v1/accounts` master + client qua nginx -> xoay token/HMAC -> đình chỉ 403 -> PairCode -> tự đăng ký -> xoá).
- Rủi ro: ai ở mạng backend/ops/frontend biết `BRIDGE_AUTH_TOKEN` đọc được HMAC secret mọi tài khoản; tự đăng ký có thể bị lạm dụng tạo hàng loạt bản ghi pending (đã giới hạn, tắt bằng `AUTH_SELF_REGISTER=0`).

## 7. Quản trị đội tài khoản, vai trò phụ, TOTP bắt buộc (2026-10-12; chi tiết `docs/FLEET_MGMT.md`)
- **Vai trò phụ** `support` (đọc + ghi chú), `analyst` (đọc phân tích/tuân thủ/báo cáo), `auditor` (chỉ audit): MẶC ĐỊNH TỪ CHỐI, phạm vi theo nhóm (`staff_scopes`) hoặc `scope_all`; không nhóm = thấy 0 tài khoản. Đăng nhập `platform:"master"` + tên. `X-Role` xuống gateway = vai trò thật; gateway coi họ là `client` bị thu hẹp (`authz.py`: chỉ GET danh sách trắng, không `/v1/user/*`, auditor chỉ `/v1/me`; ký hiệu nội bộ `staff:<role>` trong tập tài khoản để khoá cache không dùng chung với client thật). Đổi quyền/phạm vi ⇒ thu hồi mọi phiên của người đó. Tạo/sửa nhân sự chỉ master (cần TOTP bật).
- **TOTP**: áp dụng cho mọi vai trò không phải client. Cờ `AUTH_MASTER_TOTP_REQUIRED` (mặc định bật): master chưa bật TOTP vẫn đăng nhập được nhưng `/auth/me.totp_setup_required=true` và các thao tác nhạy cảm MỚI (bulk, import CSV, quản lý nhân sự, xem-như-khách) trả 403 `totp_required` cho tới khi bật. Không khoá chủ hệ thống ra ngoài; thao tác cũ giữ nguyên.
- **Xem như khách**: `POST /auth/admin/view-as {account_id, reason>=8}` → grant hết hạn sau `AUTH_VIEW_AS_MINUTES` (30), audit kèm lý do; UI hiển thị banner đếm ngược. (Hết hạn là cơ chế hiển thị/audit: master vốn đọc được mọi dữ liệu qua API.)
- **Bulk/Import**: xác nhận 2 bước (token 120s, một lần, gắn người thực hiện + băm danh sách; cụm gõ `XAC NHAN <n>`), tối đa 200 tài khoản; import CSV tối đa 200 dòng/200 KB (nginx location riêng, thân ≤256k). Secret chỉ trả MỘT lần, server không lưu.
- **Nội bộ** `FLEET_INTERNAL_TOKEN` (Bearer; chỉ mạng backend/ops): `/internal/fleet/{rules,results,scope-accounts,account/{id}/compliance}` cho risk-monitor/reporter. Chưa cấu hình → 503. Không qua nginx công khai.
- **Khách opt-in push** khi sát/vi phạm luật: `GET|PUT /auth/client/notify` (mặc định tắt; master KHÔNG bật hộ). Test: `tests/e2e/test_fleet.py`, `services/auth/tests/test_fleet.py`, `services/api-gateway/tests/test_authz_staff.py`.

## Pentest phân quyền 2026-10-14 (`tests/e2e/test_pentest_authz.py`, ~808 kiểm tra, chạy `sh /root/qa-e2e/run_remote.sh test_pentest_authz.py`)
Phạm vi: IDOR A→B/C trên mọi route theo tài khoản (web-ui `/api` + client-ui `/c/api`, tham số lặp, hoa/thường, `%2F` `%2e%2e` `%252F` `;` `%00` `//`), giả header (X-User-Id/X-Role/X-Accounts/X-Auth-Secret/X-Owner-*), phiên hết hạn/thu hồi/idle/đình chỉ/buộc đổi mật khẩu,
CSRF (Origin lạ/null/hậu tố, Sec-Fetch-Site, thiếu CSRF token, Content-Type), rate-limit đăng nhập/ghép cặp, leo thang `/auth/admin/*`, mass-assignment, vai trò phụ (support/analyst/auditor), WS/SSE (`/v1/rt`, `/v1/stream`), cache-poisoning (nginx micro-cache + Redis gateway), EA→mt-bridge chéo tenant.
Lỗ hổng đã sửa: (P3) `/v1/journal/accounts/...` bị miễn kiểm tài khoản (authz.py); (P3) `public_path` của auth tin `$request_uri` thô: `/c/%2e%2e/index.html` lấy vỏ master không cần đăng nhập (service.py);
(P3) open-redirect `next=/%09/evil.com` ở trang đăng nhập (web/login.js); (P3) `/v1/stream` không kiểm Origin (CSWSH, app.py); (P2) cache Redis của gateway chạy TRƯỚC `authorize` và dùng chung khoá `c` cho vai trò phụ → auditor đọc được bản cache của client (cache.py, khoá riêng `s.<role>`).
Rủi ro còn mở (theo thiết kế, ghi nhận): gọi thẳng nội bộ từ mạng ops/backend không xác thực (alert-rules tin X-Owner-*, journal/risk-monitor/paper-trader/reporter/briefing không auth; gateway chỉ cần API key = quyền master) — web-ui/client-ui chỉ ở mạng `frontend`
(chỉ tới gateway/auth) nên chiếm web-ui không chạm được các dịch vụ này; token CSRF dùng chung toàn hệ thống (HMAC theo giờ, không theo phiên; vẫn cần Origin + SameSite=Strict); khoá tạm theo tài khoản cho phép kẻ tấn công khoá đăng nhập/ghép cặp của người khác 15 phút;
2FA master chỉ bắt buộc cho view-as; đăng ký push `ON CONFLICT` chuyển chủ khi trùng endpoint (cần biết endpoint bí mật).

### Cập nhật hardening 2026-10-14 (agent SEC, xem HARDENING.md §7)
- ĐÃ ĐÓNG: gọi thẳng alert-rules/journal/risk-monitor/paper-trader/reporter/briefing từ mạng nội bộ -> bắt buộc `X-Internal-Token` (enforce; thiếu/sai -> 401, `/healthz` `/metrics` miễn). alert-rules vẫn chỉ tin `X-Owner-*` khi request đã qua token nội bộ (chỉ gateway có).
- ĐÃ ĐÓNG: token CSRF dùng chung toàn hệ thống -> gắn phiên (`kind|role|user_id|sha256(cookie)`); token của phiên B dùng cho phiên A -> 403. Rollback: `CSRF_BIND=global` (api-gateway).
- CHUẨN BỊ (mặc định TẮT): `AUTH_MASTER_TOTP_ENFORCE=true` buộc master bật TOTP mới dùng được `/api/*` (trừ `/api/v1/me`); `/auth/*` vẫn mở để bật TOTP. Cần người dùng bật TOTP cho master trước rồi mới bật cờ.
- Còn mở: khoá tạm theo tài khoản (DoS nhẹ 15 phút); push `ON CONFLICT` đổi chủ khi trùng endpoint; gateway: API key = quyền master (key không ra trình duyệt).
