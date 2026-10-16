# web-ui

Website theo dõi hệ thống (chỉ đọc): giá/nến realtime, tin tức, lịch kinh tế, chuyên gia uy tín, tài khoản MT4/MT5 (READ-ONLY), cảnh báo, trạng thái hệ thống. Giao diện tiếng Việt, giờ Asia/Ho_Chi_Minh, tối mặc định (có nút đổi sáng; lựa chọn được nhớ), responsive 375px đến desktop.

```
Trình duyệt ──đăng nhập phiên (auth_request → service auth)──> nginx (web-ui:8080) ──/api/*  + X-API-Key (chèn phía server)──> api-gateway:8000 ──> DB / Redis / Prometheus
                               └─ file tĩnh (SPA đã build)        └─ /api/v1/stream (WebSocket)
```

## Chạy trên server (docker compose)
```bash
cd infra
# 1) [CHỈ cho đường dự phòng Basic Auth, AUTH_BASIC_FALLBACK=1] mật khẩu htpasswd (sinh ngẫu nhiên, in ra đúng 1 lần). Đăng nhập thường ngày dùng service auth: xem docs/AUTH.md
../services/web-ui/scripts/make-htpasswd.sh admin        # ghi infra/web-ui/auth/htpasswd
# 2) .env cần API_TOKEN (1 token, không CSV); tuỳ chọn WEB_PORT/WEB_BIND/PROMETHEUS_URL (xem .env.example)
docker compose -p tradingsys --env-file .env up -d --build web-ui api-gateway
# 3) truy cập: http://127.0.0.1:8580  (SSH tunnel:  ssh -L 8580:127.0.0.1:8580 user@vps)  hoặc reverse proxy TLS
```
Port chỉ bind `127.0.0.1` (`WEB_BIND`). Muốn mở ra Internet: đặt sau reverse proxy có **TLS** (basic auth gửi mật khẩu dạng base64). Chưa có `htpasswd` thì nginx từ chối mọi request (fail-closed) và log cảnh báo.
Cập nhật API gateway (thêm `/v1/system`, `/v1/symbols`, `/v1/equity-history`) cần build lại `api-gateway`.

## Bảo mật
- nginx là cổng duy nhất: đăng nhập phiên bắt buộc qua `auth_request` (từ 2026-10-12; Basic Auth chỉ còn là dự phòng khi `AUTH_BASIC_FALLBACK=1`; trừ `/healthz` nội bộ và các tiền tố công khai tối thiểu trong docs/AUTH.md), **chỉ GET/HEAD**, NGOẠI LỆ duy nhất là whitelist ghi cấu hình cảnh báo + prefs (`POST /api/v1/user/rules[/preview|/<id>/preview]`, `PUT|DELETE /api/v1/user/rules/<id>`, `PUT /api/v1/user/prefs`; bảo vệ: Origin==Host, Sec-Fetch-Site, X-CSRF-Token, JSON<=16KB, 30 ghi/phút/IP; mọi route/method khác 405, KHÔNG có route đặt lệnh), `limit_req` 15 req/s/IP cho API, `limit_conn` 10 WebSocket/IP.
- `X-API-Key` do nginx chèn từ env `API_KEY` (= `API_TOKEN`), đè mọi header cùng tên từ client, bỏ `Cookie`/`Authorization` trước khi chuyển xuống gateway. Khoá **không** có trong JS/HTML/trình duyệt.
- Chỉ proxy `/api/v1/*`; `/docs`, `/metrics`, `/readyz` của gateway không lộ ra.
- CSP chặt (`default-src 'none'`, script/style/font/img/connect = `'self'`; riêng 1 hash cho `<style>` nội tuyến của lightweight-charts), `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy: no-referrer`, `Permissions-Policy` tắt cảm biến. Container nginx không đặc quyền (uid 101), `read_only`, `cap_drop: ALL`.
- Nâng phiên bản `lightweight-charts` có thể đổi hash CSP: mở console, nếu thấy lỗi `style-src ... sha256-...` thì cập nhật hash trong `nginx/security-headers.conf`.

## Phát triển (không cần Docker)
```powershell
cd services/web-ui/app ; npm ci ; npm run build            # tạo app/dist
cd ../../.. ; .venv\Scripts\python services\web-ui\dev\mock_server.py     # http://127.0.0.1:8590
# tuỳ chọn:  --empty (thử trạng thái trống)  --fail news,calendar (thử trạng thái lỗi 503)  --no-csp
# hot reload:  cd services/web-ui/app ; npm run dev   (Vite 5173, proxy /api -> 8590)
```
`dev/mock_server.py` chạy **chính api-gateway** với `InMemoryRepo` + fakeredis và dữ liệu giả sát định dạng thật, nên JSON giống production. Nó gắn thêm đúng CSP của nginx để bắt lỗi CSP sớm.

## Terminal (workspace nhiều tab, widget kéo-thả)
Trang chính `#/terminal`: workspace tuỳ biến (Tổng quan, Forex, Crypto, Chứng khoán VN, Tin & Lịch + tự tạo), lưới 24 cột kéo-thả/đổi cỡ (`react-grid-layout`, MIT), khoá bố cục, nhân bản, nhập/xuất JSON, kênh màu liên kết mã giữa các widget, toàn màn hình/trình chiếu xoay workspace (Esc thoát), lưu theo người dùng ở máy chủ (`/v1/user/prefs`, khoá `tm`) + localStorage dự phòng. Phím tắt: `Alt+1..9` đổi workspace, `g` rồi `t` mở Terminal, Ctrl-K gõ tên workspace/widget.
**Thêm widget/trang = thả 1 tệp** (`app/src/widgets/<tên>.jsx`, `app/src/pages/<Tên>.jsx` có `export const meta`), không sửa `App.jsx`. Hợp đồng đầy đủ: `docs/WIDGETS.md`. Plugin build `app/vite-plugin-ts-meta.js` đọc `meta` để sidebar/danh mục có metadata đồng bộ mà vẫn tách bundle.

## Cấu trúc
```
app/src/pages/        15 trang (gồm Journal = "Nhật ký") (Analytics = "Phân tích": heatmap trạng thái, screener, chi tiết chỉ báo trên nến, tương quan, phiên; Overview, Market, News, Calendar, Experts, Accounts, Alerts, System)
app/src/components/   ui.jsx (Panel, Async = loading/empty/error, Chip...), charts.jsx (nến + ECharts), table.jsx, topbar.jsx
app/src/lib/          api.js, stream.js (1 WebSocket dùng chung), queries.js (TanStack Query), format.js (múi giờ VN), session.js
nginx/                default.conf.template, security-headers.conf, 10-check-auth.sh
scripts/make-htpasswd.sh    dev/mock_server.py    docs/*.png (ảnh chụp trên dữ liệu giả)
```

## Ảnh chụp (docs/, dữ liệu giả)
`01-tong-quan-desktop` bảng giá, bản đồ nhiệt, đếm ngược sự kiện HIGH, tin nóng, tín hiệu, tài khoản · `02-thi-truong-*` nến + volume realtime (tối/sáng) · `03-tin-tuc` · `04-lich-kinh-te` · `05-chuyen-gia` (cờ cảnh báo tham khảo) · `06-tai-khoan` equity + vị thế (READ-ONLY) · `08-he-thong` · `09/10-*-mobile` 375px · `13-phan-tich-desktop`, `14-phan-tich-mobile` (trang Phân tích; cần snapshot từ service analytics, mock server tự tính bằng chính engine) · `11-trang-thai-rong` · `12-trang-thai-loi`.

## Lưu ý vận hành
- Realtime: `/api/v1/stream` đẩy `md.quotes`, `md.bars`, v.v.; trình duyệt tự nối lại (backoff 2s..30s). Nếu `Mất kết nối` kéo dài, kiểm tra `docker logs` của web-ui và `WS_MAX_CONNECTIONS` của gateway.
- `/v1/system`: đặt `PROMETHEUS_URL=http://prometheus:9090` cho gateway để biết service nào ngừng; không đặt thì chỉ suy ra từ sự kiện cuối trên bus (service im lặng > 15 phút = ngừng).
- Dữ liệu chuyên gia chỉ để tham khảo, không phải khuyến nghị đầu tư (hiện cố định trên trang Chuyên gia và thanh bên).

## Cảnh báo người dùng, danh sách theo dõi, PWA
- Trang **Cảnh báo** (quy tắc của tôi: giá/%/RSI-EMA/cửa sổ tin/sentiment/margin MT, AND/OR, hết hạn, một lần/lặp, kênh ntfy/log/telegram, lịch sử kích hoạt) và **Danh sách theo dõi** (nhiều nhóm, lưu server trong `user_prefs`) gọi `/api/v1/user/*` -> service `alert-rules`.
- **Ctrl/Cmd-K**: nhảy trang/mã; phím tắt `g`+chữ, `/`, `?`, `t`, `[`. Huy hiệu nguồn + tuổi dữ liệu trên các bảng giá/số liệu (`Freshness`).
- **PWA**: `manifest.webmanifest`, `sw.js` (chỉ cache `/assets/*`, shell, icon; KHÔNG cache `/api/*`, WebSocket, 401/403, non-GET). Cần HTTPS (hoặc localhost) để cài trên điện thoại; trang HTTP-IP bỏ qua đăng ký SW êm.

## Trang Nhật ký (`#/nhat-ky`, phím tắt `g` rồi `j`)
Nhật ký giao dịch trên lịch sử lệnh ĐÃ ĐÓNG (không gồm floating) của tài khoản MT (EA agent gửi deal) và paper; gọi `/api/v1/journal/*` (service `journal` qua gateway). Bộ lọc (tài khoản, 7/30/90 ngày/tất cả/tuỳ chọn, symbol, EA, hướng) được nhớ trong localStorage (`journal.v1`). Tài khoản có nguồn `sim:*` gắn nhãn **MÔ PHỎNG**, fixture lab gắn **FIXTURE**.
- Tổng quan: hàng KPI, đường vốn + drawdown (điểm nạp/rút), lịch heatmap theo ngày (bấm ô để lọc bảng lệnh), phân bố R, thống kê theo giờ/thứ/phiên/symbol/hướng/EA, đóng góp EA, chuỗi/thời gian giữ/chi phí.
- Lệnh: bảng sắp xếp + phân trang phía server, lọc kết quả/tag/vi phạm; bấm dòng mở ngăn chi tiết, sửa tag/ghi chú/đánh giá.
- Kỷ luật: điểm 0-100, quy tắc vi phạm, so sánh P/L sạch/vi phạm, chỉnh ngưỡng; MAE/MFE (chỉ tải khi mở, xấp xỉ từ nến).
- Review tuần: chọn tuần, so với tuần trước, nhận xét tự động, ghi chú tuần.
Đường GHI duy nhất: `PUT|DELETE /api/v1/journal/<tk>/notes/<deal|week|day>/<ref>` (ghi chú/tag; `apiWrite` + CSRF như trang Cảnh báo). Không có thao tác đặt/sửa/đóng lệnh. Nginx cần build lại image `web-ui` để nhận location `/api/v1/journal/`. Mã: `pages/Journal.jsx`, `components/journal.jsx`, `components/journalDeals.jsx`; không thêm thư viện mới.

## Quy tắc: không hiển thị tên nguồn dữ liệu

Giao diện chỉ hiển thị NỘI DUNG (giá, tin, lịch, tín hiệu, chuyên gia), không in tên nguồn/nhà cung cấp/sàn. Huy hiệu độ mới chỉ ghi "N phút trước".
Văn bản do máy chủ sinh đi qua `clean()`/`scrub()` (`app/src/lib/format.js`). Kiểm tra tránh tái phát (chạy trên VPS):
`docker run --rm -v $PWD:/w:ro node:22-alpine node /w/scripts/lint-sources.cjs [--dist]`. Ghi công thư viện OSS nằm ở THIRD_PARTY.md.

## Thông tin thị trường (Market Intelligence)
Trang + widget (mỗi view vừa là trang vừa là widget Terminal): `#/suc-manh-tien-te` (sức mạnh 8 tiền tệ H1/H4/D1, heatmap 28 cặp, tỷ giá chéo), `#/ban-do-nhiet` (crypto / ETF toàn cầu / ngành Mỹ / hàng hoá / forex / cổ phiếu / ngành VN), `#/movers`, `#/tuong-quan-rui-ro` (tương quan tương tác + lăn, ATR%, beta, phân phối lợi suất), `#/phien-giao-dich` (biên độ theo phiên + giờ mở cửa/ngày lễ), `#/nhip-thi-truong` (Market Pulse), `#/vi-the-lon` (vị thế đầu cơ lớn hàng tuần + đồng thuận chuyên gia), `#/tin-tuc` (terminal tin tức WebSocket) và `#/lich` (lịch kinh tế chuyên nghiệp). Dữ liệu từ `/v1/intel/*`; mô tả và giới hạn dữ liệu: `docs/MARKET_INTEL.md` (repo gốc). Mã: `src/components/intel/*`, `src/lib/intel*.js`, `src/lib/calendarPro.js`, `src/lib/marketHours.js`; QA tự động: `qa/run-c.sh intel.mjs|intel-flow.mjs`.

## Biểu đồ chuyên nghiệp (trang Thị trường + widget `chart`)
`components/chart/ChartWorkspace.jsx` (dùng trong `pages/Market.jsx` và `widgets/chart.jsx`): nhiều biểu đồ **1 / 2 dọc / 2 ngang / 2×2 / 1+3 / 3×2**, mỗi ô độc lập (mã, khung, chỉ báo, kiểu) hoặc liên kết theo **nhóm màu** (đổi mã đồng bộ; tuỳ chọn đồng bộ khung), đồng bộ **crosshair** và **vùng thời gian**.
- **Loại biểu đồ**: nến, nến rỗng, Heikin-Ashi, thanh OHLC, đường, vùng, Baseline, cột + **Renko, Range bars, Line Break, Kagi, Point & Figure** (tính phía trình duyệt từ OHLC → xấp xỉ, ghi chú trong bảng Hiển thị).
- **Công cụ vẽ** (nhóm trên thanh trái, phím tắt Alt+chữ kiểu TradingView): đường xu hướng/tia/kéo dài/ngang/dọc/mũi tên/kênh/**kênh hồi quy**/**Pitchfork Andrews**, Fibonacci thoái lui/mở rộng/**cung**/**vùng thời gian**/**Gann fan**/**projection**, chữ nhật/**tam giác**/**vùng cung-cầu**/**sóng Elliott (0-5, ABC)**, **nhãn văn bản/ghi chú**, thước đo, **anchored VWAP**, **volume profile** (phân bổ đều khối lượng nến theo biên độ → xấp xỉ). Khoá/ẩn/đổi tên/đổi màu/xoá qua **Danh sách đối tượng**, Undo/Redo (Ctrl+Z / Ctrl+Shift+Z), nhân bản (Ctrl+D).
- **Lưu bản vẽ**: theo (mã, khung) vào `user_prefs.chart.draw` (máy chủ, qua `lib/prefs.js`) + bản sao `localStorage` (`ts-draw2:*`); máy chủ lỗi thì dùng cục bộ. Ngân sách ~4,8KB trong 16KB prefs chung (quá thì bỏ bản vẽ cũ nhất khỏi máy chủ).
- **Mẫu (template)**: chỉ báo + kiểu + giao diện/lớp phủ (+ bố cục tuỳ chọn), lưu `user_prefs.chart.tpl`, nhập/xuất JSON.
- **Lớp phủ**: vùng phiên Tokyo/London/New York/VN + đường mở/đóng phiên, đường đóng cửa trước / mở cửa ngày, sự kiện lịch **HIGH** (`/v1/calendar`) và tin quan trọng (`/v1/news`, |sắc thái| ≥ 0,35) trên trục thời gian, **đường cảnh báo giá** (bấm/kéo → `POST/PUT /v1/user/rules`; CHỈ cảnh báo, không đặt lệnh).
- **So sánh nhiều mã** (chồng %), **Spread A−B**, **Tỉ lệ A/B**, pane **tương quan** Pearson lăn; **đa khung (MTF)** M15/H1/H4/D1; **Replay** (chọn nến bắt đầu, bước, phát 1–25 nến/giây, tua).
- **Hiệu năng**: chỉ báo tính trong **Web Worker** (`indWorker.js`), tải thêm lịch sử khi kéo trái (phân trang `/v1/bars?to=`, tới 20.000 nến), cập nhật realtime bằng `series.update()` (không dựng lại).
- Ảnh chụp PNG (có tiêu đề) + sao chép clipboard, toàn màn hình (Shift+F), tuỳ biến màu nến/lưới/thang giá trái-phải/log/%.
- QA trên VPS (không chạy ở laptop): `sh /root/trading-system/services/web-ui/qa/run-b-iso.sh` (nginx tạm + Playwright, ảnh + `results.json` trong `/tmp/qa-ui-b/out`).

## Hệ thống UX xuyên suốt (Agent E)
Cài đặt (`#/cai-dat`: giao diện sáng/tối/tự động, màu nhấn, mật độ, cỡ chữ, tương phản, múi giờ, kiểu ngày/số/tiền, màu tăng-giảm, âm báo, thông báo trình duyệt; lưu `localStorage` + `user_prefs.ux`), Trung tâm thông báo (chuông), Ctrl-K đời mới (trang/mã/tin/thuật ngữ/lệnh + cú pháp “cảnh báo eurusd 1.0850”), tour lần đầu, tooltip thuật ngữ (`Term`/`Stat` tự gắn), Trợ giúp (`#/tro-giup`: thuật ngữ, FAQ, ghi chú phiên bản), Giới thiệu (`#/gioi-thieu`: ghi công OSS), Design system (`#/design`), trạng thái chuẩn (skeleton/rỗng/lỗi/mất kết nối), Công cụ trang (xuất CSV/Excel/PNG, in/PDF, sao chép bảng/liên kết, đánh dấu). Mã: `app/src/ux/`, `app/src/components/ux/`, `pages/{Settings,Help,About,Design}.jsx`. Tài liệu: `docs/DESIGN_SYSTEM.md`. Backend: `alert-rules` giữ khoá `ux` trong `/prefs` (models.Prefs).


## Quản trị đội tài khoản — giao diện MASTER (docs/FLEET_MGMT.md)
Nhóm điều hướng **Quản trị đội** (trang tự đăng ký, nạp lười; chỉ ĐỌC/QUẢN TRỊ — KHÔNG có đường đặt lệnh, mọi màn hình có nhãn “Chỉ-đọc · không có đặt lệnh”). Vai trò từ `/auth/me` (`role`, `perms[]`, `scope`, `totp_setup_required`); trang khai báo `meta.perm` để vai trò phụ (support/analyst/auditor) chỉ thấy đúng menu; nút ghi bị khoá kèm lý do (`GBtn`/`usePerm`) — **máy chủ vẫn là lớp bảo mật thật**.
| Trang | Hash | Ai | Nội dung |
|---|---|---|---|
| Đội tài khoản `pages/Fleet.jsx` | `#/doi-tai-khoan` (`g` rồi `f`) | master, support, analyst (`fleet.read`) | Command center: KPI bấm=lọc, bảng (lọc nhóm/tag/trạng thái/EA/tuân thủ/tìm, sắp xếp, phân trang) + thẻ trên mobile, chip nhóm/tag, **Saved views**, chọn nhiều → **thao tác hàng loạt 2 bước** (`XAC NHAN <n>`, secret xoay hiển thị một lần), **Nhập CSV → xem trước từng dòng → thẻ onboarding (in A4 / tải CSV)**, quản lý nhóm (+ thành viên + chính sách cảnh báo), **hồ sơ khách** (tab Tổng quan · Rủi ro & luật · Ghi chú CRM · Kiểm toán) kế thừa mọi thao tác của trang Khách hàng cũ (mã ghép cặp, xoay token, passcode, đình chỉ, tạo tài khoản), **Xem như khách** |
| Sự cố `pages/Incidents.jsx` | `#/su-co` (phím `i`) | master, support (`incident.read`) | Hộp sự cố Mới/Đã nhận/Tạm hoãn/Đã đóng, giao/snooze/ghi chú/đóng, hàng loạt, gộp theo nguyên nhân; huy hiệu số sự cố mở ở thanh bên (poll 45 giây, tạm dừng khi tab ẩn) |
| Luật & tuân thủ `pages/Rules.jsx` | `#/luat` | master, analyst (`compliance.read`) | Mẫu luật (daily_loss, max_drawdown, margin_level, best_day, max_trades_day) + mẫu gợi ý + gán theo nhóm/tag/tài khoản/tất cả; banner cố định “luật nhà cái khác nhau”; bảng tuân thủ toàn đội |
| Báo cáo khách `pages/ClientReports.jsx` | `#/bao-cao-khach` | master, analyst (`report.read`) | Tạo/phát hành/thu hồi báo cáo theo tài khoản, lịch; hiện “chưa khả dụng” khi route backend chưa có |
| Vai trò & nhân sự `pages/Roles.jsx` | `#/vai-tro` | master | Ma trận quyền, tạo nhân sự (mật khẩu một lần), đổi vai trò/phạm vi nhóm, đình chỉ/kích hoạt/thu hồi phiên |
| Phiên & thiết bị `pages/SessionsDevices.jsx` | `#/phien-thiet-bi` | mọi vai trò phụ | Thiết bị/IP/lần cuối, thu hồi từng phiên, đăng xuất mọi nơi, trạng thái TOTP (khác `pages/Sessions.jsx` = phiên thị trường) |
| Nhật ký kiểm toán `pages/AuditTrail.jsx` | `#/kiem-toan` | master, auditor (`audit.read`) | Lọc/xuất CSV/kiểm chuỗi băm |

**Bảo mật phiên (mọi trang):** `components/fleet/FleetRoot.jsx` (gắn ở `App.jsx`, nạp lười) hiển thị (1) banner **Xem như khách** dính phía dưới thanh trên (đếm ngược tới `expires_at`, nút Kết thúc, hết hạn tự thoát; mọi thao tác ghi bị chặn ngay trong `fx()` của `lib/fleetApi.js`), (2) banner **TOTP bắt buộc** cho master (`totp_setup_required`, không tắt được) + trình hướng dẫn `TotpWizard.jsx` (tạo secret → QR vẽ trong trình duyệt bằng `qrcode-generator` MIT, tệp `src/vendor/` nạp lười → mã 6 số). Lỗi `403 totp_required` ở thao tác nhạy cảm → `ErrLine` kèm nút “Bật TOTP ngay”.
**Secret:** passcode/mã ghép cặp/token EA/HMAC chỉ hiển thị MỘT lần (`SecretPanel`: chép, tải, tick “đã lưu” mới đóng, chặn tải lại); không bao giờ ghi vào localStorage/sessionStorage/URL.
**Kiến trúc:** `lib/fleetApi.js` (truyền tải, lỗi → `FleetError`, KHÔNG dữ liệu minh hoạ), `lib/fleetQueries.js` (hook + `usePerm`), `lib/fleetFilters.js` (bộ lọc trong địa chỉ), `components/fleet/*`, `fleet.css` (lớp `fl-*`). Thêm trang cho nhóm này = thả `pages/<Tên>.jsx` có `meta` (`group: "Quản trị đội"`, `perm`).
**QA trực quan (trên VPS, không chạy ở laptop):** `sh /root/trading-system/services/web-ui/qa/fleet-pw.sh <kịch-bản.mjs> <tag>` (master thử `qa-fleet-<tag>` + container Playwright tạm, dọn sau; thư viện `qa/fleet-lib.mjs`); kiểm build không deploy: `qa/fleet-build-check.sh`. Kịch bản: `fleet-fleet.mjs` (Đội tài khoản/TOTP/CSV/hàng loạt/xem-như-khách), `fleet-rules.mjs`, `fleet-incidents.mjs`, `fleet-staff.mjs` (cả kiểm thử vai trò), `fleet-reports.mjs`. Ảnh: `docs/fleet/`.

## Trang Kịch bản (`#/kich-ban`, master)
Tín hiệu kịch bản Sell KB-1..KB-4 (đang hình thành / sẵn sàng / đã kích hoạt, bộ lọc mã/khung/KB), ngăn chi tiết (ảnh phóng to, checklist, dòng thời gian, mức Entry/SL/TP, nến + đường giá + marker), lịch sử + kết quả PAPER (ô số liệu, cảnh báo mẫu nhỏ n<30, đường R luỹ kế, phân rã, sổ cái hash-chain), thư viện ví dụ, mô tả KB. Chỉ đọc, gọi `/api/v1/patterns/*` (hợp đồng: `docs/handoff/SCAN_status.md`). Mã: `app/src/pages/Scenarios.jsx` + `scenarios.css` (class `sc-`). Ảnh PNG `/api/v1/patterns/(media|examples)/*.png` có location nginx riêng (đặt trước regex ảnh tĩnh). QA: `sh qa/run_scenarios.sh` (`MOCK=1` = dữ liệu mẫu chặn trong Playwright, không vào bundle); ảnh `docs/scenarios-*.png`.
