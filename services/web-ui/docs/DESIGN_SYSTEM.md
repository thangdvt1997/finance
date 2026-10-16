# Design system — Trạm thị trường (web-ui)

Trang xem trực tiếp: `#/design` (Storybook-lite nội bộ, dùng chính component thật, đổi giao diện/màu nhấn ở `#/cai-dat` để kiểm tra mọi biến thể).
Nguyên tắc: **chuyên nghiệp, dày thông tin nhưng dễ đọc, nhất quán, truy cập được (WCAG 2.2 AA)**, tiếng Việt, không hiển thị tên nguồn dữ liệu (`docs/UI_NO_SOURCES.md`), không có thao tác giao dịch.

## 1. Token (đặt trong `app/src/index.css`, biến thể trong `app/src/ux/ux.css`)

| Token | Tối | Sáng | Dùng cho |
|---|---|---|---|
| `--bg` / `--panel` / `--panel2` | `#090d13` / `#0e141c` / `#131b26` | `#edf0f4` / `#fff` / `#f4f6f9` | nền trang / khung / ô nhập, hàng hover |
| `--line` / `--line2` | `#1d2836` / `#2a3a4e` | `#dbe1e9` / `#c3ccd8` | viền mảnh / viền rõ |
| `--fg` / `--muted` / `--faint` | `#d6dfeb` / `#8191a5` / `#7788a0` | `#0f1b2a` / `#4a5a6f` / `#5a697e` | chữ chính / phụ / chú thích (đều ≥ 4,5:1 trên `--panel`) |
| `--up` / `--down` | `#2bd08f` / `#ff5c7a` | `#066f49` / `#b9243f` | tăng / giảm (đổi theo Cài đặt) |
| `--accent` (+`-fg`, `-bg`) | `#f0b84f` | `#8c5409` | nhấn: nút chính, mục đang chọn, liên kết (đổi theo Cài đặt) |
| `--info` / `--warn` | `#5aa9ff` / `#f0b84f` | `#1a62bd` / `#8c5409` | thông tin / cảnh báo |

Quy tắc: **không viết màu cứng trong component** (trừ huy hiệu số đỏ `.ux-badge`, bản xem trước trong Cài đặt). Tailwind map token: `text-muted`, `bg-panel`, `border-line`, `text-up`... Chữ trên nền nhấn dùng `--accent-fg`.

Biến thể do người dùng chọn, áp bằng thuộc tính trên `<html>` (`ux/settings.js` → `applyAll`; `public/theme-init.js` áp trước khi vẽ để không nháy):
`data-theme` (sáng/tối, “tự động” = theo thiết bị) · `data-accent` (amber, blue, green, violet, rose, cyan; mỗi màu có giá trị riêng cho sáng/tối, đã kiểm tương phản) · `data-updown` (`vn` xanh tăng/đỏ giảm, `asia` đỏ tăng/xanh giảm, `cb` xanh dương/cam + ký hiệu ▲▼ cho người mù màu) · `data-density` (comfortable/compact) · `data-fs` (90/100/110/125 %, dùng `zoom`) · `data-contrast` (normal/high) · `data-motion` (system/reduce).

## 2. Chữ
Inter (UI, có tiếng Việt) + JetBrains Mono (số liệu, class `.num`, tabular). Thang: 19px/600 tiêu đề trang (`PageHead`) · 14px/600 hộp thoại · 13.5px nội dung · 12.5px nút/bảng/tiêu đề khung · 11.5px nhãn/chú thích · 10.5px nhóm điều hướng (hoa). Không dùng cỡ < 10.5px.

## 3. Khoảng cách, bo góc, tương tác
Thang 4px: 4 · 8 (`gap-2`) · 12 (`gap-3`, khoảng cách giữa khung và lề) · 16 (padding trang `lg:p-4`) · 24. Bo góc: 4 chip nhỏ · 6 nút/ô nhập · 8 khung · 10 menu/tour · 99 viên thuốc. Mục tiêu chạm ≥ 44px trên màn cảm ứng (`@media (pointer: coarse)` đã áp cho `.btn`, `.field`, `.seg`, menu); vùng chạm tối thiểu 24px ở mọi nơi (WCAG 2.5.8). Focus: `outline 2px var(--accent)`, offset 2px (tương phản cao: 3px). Không dùng `transition: all`.

## 4. Thành phần dùng chung

| Thành phần | Mã | Ghi chú |
|---|---|---|
| `Panel`, `PageHead`, `Stat`, `Chip`, `Seg`, `Sparkline`, `ImpactDots`, `Disclaimer` | `components/ui.jsx` | `Stat` tự gắn tooltip thuật ngữ theo nhãn (xem §6) |
| `Freshness`, `LatestFresh` | `components/ui.jsx` | huy hiệu độ tươi duy nhất: màu + biểu tượng + chữ; xám khi thị trường nghỉ; **không tên nguồn** |
| `Async` | `components/ui.jsx` | loading (dòng/`variant="table"`/`"chart"`) → lỗi (`ErrorState`) → rỗng (`EmptyState`) → dữ liệu |
| `EmptyState`, `ErrorState`, `TableSkeleton`, `ChartSkeleton`, `ConnectionBanner` | `components/ux/States.jsx` | §5 |
| `Dialog` (modal/drawer) | `components/dialog.jsx` | role=dialog, aria-modal, bẫy focus, Esc, trả focus |
| `Term`, `InfoTip` | `components/ux/Term.jsx` | tooltip thuật ngữ, tải lười nội dung |
| `Toaster` + `toast()`/`notify()` | `components/ux/Toaster.jsx`, `ux/bus.js` | một đường duy nhất cho toast/âm/thông báo trình duyệt |
| `CommandPalette`, `Cheatsheet` | `components/ux/` | Ctrl-K, `?` |
| `PageTools` | `components/ux/PageTools.jsx` | xuất/in/chia sẻ/đánh dấu |
| Bảng | `table.tbl` (index.css) / TanStack Table | tiêu đề cột sticky, số căn phải `.r` + `.num` |

## 5. Trạng thái chuẩn
- **Đang tải**: skeleton giữ đúng kích thước nội dung (không giật bố cục): `Skeleton` (dòng), `TableSkeleton`, `ChartSkeleton`. Không dùng spinner trần.
- **Rỗng**: `EmptyState` luôn nói *vì sao* và *việc nên làm* (nút/liên kết hành động).
- **Lỗi**: `ErrorState` chẩn đoán theo mã (ngoại tuyến, 0, 401, 403, 404, 429, 5xx), nút **Thử lại**, “Chi tiết kỹ thuật” (mục, mã, thời điểm, trang) sao chép được, liên kết sang trang Hệ thống.
- **Mất kết nối realtime/ngoại tuyến**: `ConnectionBanner` (chờ 4 giây để tránh nháy), tự nối lại với backoff, nút “Nối lại ngay”; số liệu giữ nguyên và huy hiệu độ tươi tự chuyển vàng/đỏ.
- **Độ tươi**: luôn qua `Freshness` (ngưỡng trong `lib/freshness.js`).

## 6. Hệ thống UX (thư mục `app/src/ux/`, `components/ux/`)
- `settings.js` — kho Cài đặt: lưu `localStorage["ts-ux"]` ngay + đồng bộ `PUT /user/prefs` (`prefs.ux`, alert-rules giữ các khoá đã biết; bản có `t` mới hơn thắng). `fmtconfig.js` giữ múi giờ/kiểu ngày/số/tiền; `lib/format.js` đọc từ đó (formatter dựng lười, làm mới khi đổi; trang dựng lại nhờ `key` ở App).
- `bus.js` — `toast({tone,title,body,href})`, `notify({key,cat,sev,title,body,href})` (chống trùng theo `key`, lưu 200 mục/14 ngày). `NotifyBridge` gom WebSocket + `/alerts` + trạng thái kết nối + lỗi truy vấn. `sound.js` âm báo WebAudio (không tệp).
- `commands.js` — lệnh Ctrl-K + `parseIntents` (“cảnh báo eurusd 1.0850”, “eurusd h4”) + `registerCommandProvider(fn)` để trang khác đăng ký thêm lệnh (Terminal dùng để chuyển workspace/thêm widget). `Cheatsheet.registerShortcuts(tiêu đề, hàng)` thêm nhóm phím tắt.
- `glossary.js` (thuật ngữ + FAQ), `termkeys.js` (bảng tra nhẹ nhãn → id; nội dung tải lười): thêm thuật ngữ = thêm 1 mục vào `GLOSSARY` (và alias vào `termkeys.js` nếu muốn `Stat` tự gắn). Dùng thủ công: `<Term id="margin-level">Margin level</Term>` hoặc `<InfoTip id="var" />`. Tắt tự gắn: `<Stat term={false} …/>`.
- `exporters.js` — CSV (UTF-8 BOM), **XLSX thật** (zip STORE tự viết), TSV/HTML để dán, PNG (html-to-image, nhúng phông tự), in; `PageTools` quét `<table>` thật trong `<main>`. In: `@media print` trong `ux.css` (nền trắng, bỏ điều hướng, mở rộng vùng cuộn, tiêu đề in có thời điểm + địa chỉ).
- `urlstate.js` — trạng thái trong địa chỉ `#/trang?khoá=giá trị` (`useHashQuery`); biểu đồ đã có `#/thi-truong/EURUSD?tf=H4`. Chia sẻ liên kết = sao chép `location.href`.
- `recent.js` — trang/mã gần đây + đánh dấu (localStorage theo thiết bị).
- `UxRoot` — gắn một lần: áp cài đặt, đồng bộ prefs, toast, cầu thông báo, tour (tải lười), thông báo chuyển trang cho trình đọc màn hình, mũi tên ↑↓/Home/End trong bảng, biến vùng cuộn thành vùng truy cập được bằng bàn phím.

## 7. Trang mới
Tạo `pages/<Tên>.jsx` có `export const meta = { path, label, group, icon, order, roles, keywords }` (xem `docs/WIDGETS.md`); trang tự vào thanh điều hướng, Ctrl-K, phím tắt `g`. Dùng `PageHead` + `Panel` + `Async`; mọi số tiền/giá/ngày qua `lib/format.js`; mọi nhãn thuật ngữ qua `Stat`/`Term`.

## 8. Trợ năng (checklist trước khi merge)
Landmark: `header`, `nav[aria-label]`, `main#main` (focus khi đổi trang), liên kết “Bỏ qua điều hướng” · mọi nút icon có `aria-label` chứa chữ nhìn thấy (WCAG 2.5.3) · không chỉ dùng màu (biểu tượng/chữ kèm theo) · `aria-live` chỉ cho nhãn trạng thái ngắn và toast (giá chạy KHÔNG đọc) · vùng cuộn có `tabindex=0` + tên · bảng có `th` và tên · tương phản chữ ≥ 4,5:1 ở **cả hai giao diện và mọi màu nhấn** · tôn trọng `prefers-reduced-motion` + cài đặt “Giảm chuyển động”. Kiểm bằng axe-core (WCAG 2.0–2.2 A/AA) trên bản live: xem `docs/research/UI_QA.md`.

## 9. Ngân sách hiệu năng
Bundle chính ≤ 250 KB gzip (hiện ~104 KB) · trang/ECharts/lightweight-charts là chunk riêng (nạp khi cần) · hộp thoại Ctrl-K/phím tắt/thông báo/tour/xuất tệp nạp lười và được nạp sẵn lúc rảnh · phông chỉ nạp bộ chữ cần dùng (latin, vietnamese) · tài nguyên băm tên `immutable` 1 năm, shell `no-cache`, gzip (nginx) · mục tiêu LCP < 2,5 s trên mạng nhanh (đo thực: < 0,7 s).

## 10. Quản trị đội tài khoản (master/support/analyst/auditor)
Tệp: `app/src/fleet.css` (tiền tố `fl-`, dùng token màu của §1), `components/fleet/bits.jsx` (mẫu dùng chung), `lib/fleetApi.js` (truyền tải + lỗi), `lib/fleetQueries.js` (hook dữ liệu + `usePerm`).
- **Màu trạng thái không là tín hiệu duy nhất**: `CompStatus` (xanh/vàng/đỏ/xám = trong hạn mức/sát ngưỡng/vi phạm/chưa có dữ liệu, kèm biểu tượng + chữ + nhãn "cũ" khi stale), `Pill` (tone ok|warn|bad|info|mute + biểu tượng), `UsageBar` (thanh tiến độ có vạch ngưỡng vàng 70% và 100%, `role=progressbar`, kèm số % và "dư địa còn lại"). Xanh = `--up`, vàng = `--accent`, đỏ = `--down`.
- **KPI bấm = lọc**: `.fl-kpi` (nút `aria-pressed`), viền trái theo sắc thái; bộ lọc nằm trong địa chỉ (`#/doi-tai-khoan?ea=offline`) để chia sẻ/Quay lại.
- **Bí mật hiển thị MỘT lần**: `SecretPanel` (cảnh báo to, chép từng giá trị, tải tệp, PHẢI tick "đã lưu" mới đóng, `useLeaveGuard` chặn tải lại). Không bao giờ ghi vào localStorage/sessionStorage/URL.
- **Xác nhận 2 bước nguy hiểm**: gõ đúng cụm máy chủ cấp (`XAC NHAN <n>`) — `BulkDialog`; hoặc gõ số tài khoản — `ConfirmDialog` (clients).
- **Quyền**: `GBtn` (nút bị khoá kèm lý do trong `title` và chữ cho trình đọc màn hình), `usePerm().reason(perm,{master})`. UI chỉ phản ánh; máy chủ là lớp bảo mật thật.
- **Chưa khả dụng**: `Unavailable` (route/dịch vụ chưa có -> không crash, có nút kiểm tra lại). Lỗi `totp_required` -> `ErrLine` kèm nút mở trình hướng dẫn TOTP (`openTotpWizard()`).
- **In khổ A4** (thẻ onboarding): `#fl-print` được gắn vào `<body>` khi in (`body.fl-printing`), 2 thẻ/trang, đen trắng, `@page A4`.
- **Banner xem-như-khách** `.fl-va`: dính dưới thanh trên, đếm ngược tới `expires_at`, hết hạn tự thoát; mọi thao tác ghi bị chặn trong `fx()` (lib/fleetApi.js).
