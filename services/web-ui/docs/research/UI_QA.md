# QA giao diện web-ui (bản live, dữ liệu thật) — 2026-10-12

Phương pháp: Playwright (chromium 1.49) chạy TRÊN VPS <VPS_IP>, container tạm `qa-ui-*` (đã dọn), truy cập web-ui nội bộ qua mạng docker + basic auth. 14 trang × 5 độ phân giải (1366×768, 1920×1080, 2560×1440, 768×1024, 375×812) × 2 giao diện (tối/sáng) = 140 lượt; mỗi lượt kiểm tra bằng JS: tràn ngang/dọc, chồng panel, chữ bị cắt, tương phản WCAG AA (tính trên từng text node), touch target < 44px (≤768px), cỡ chữ < 11px, trạng thái loading còn sót, console/network lỗi, từ cấm (tên nguồn dữ liệu), thời gian tải. Thêm: Ctrl-K, nhấn Tab (focus), bảng "Thêm" trên mobile. Ảnh: `docs/qa/ui-qa/` (`<trang>-<độ phân giải>-<dark|light>.jpg`, `results.json` là kết quả thô).

Lưu ý: vòng đầu chạy theme sáng bị prefs máy chủ ghi đè về tối → kết quả "sáng" vòng đầu vô hiệu, đã sửa script và chạy lại.

## Bảng lỗi × trang × độ phân giải

| # | Lỗi | Trang / độ phân giải | Mức | Đã sửa |
|---|---|---|---|---|
| 1 | Báo cáo luôn lỗi "Không kết nối được máy chủ": `GET /api/v1/reports` bị nginx 301 sang Host không cổng, CSP chặn | Báo cáo / mọi độ phân giải | Cao | Có: thêm `location = /api/v1/reports` (nginx/default.conf.template) |
| 2 | Tương quan chữ phụ (`--faint`) 2,5–3,3:1; sáng: up/down/accent/info 3,8–4,4:1 | Mọi trang (1366→375, tối + sáng; ~100 lượt) | Cao | Có: token màu mới, kiểm lại ≥ 4,5:1 |
| 3 | Thanh dưới mobile chứa 14 mục cuộn ngang ẩn thanh cuộn, nhãn bị cắt ("Chứng kho…") | Mọi trang / 375, 768 | Cao | Có: 4 mục chính + nút "Thêm" mở bảng tất cả trang theo nhóm |
| 4 | Sidebar phẳng 14 mục, không nhóm; chiều cao 768 làm lẹm nút thu gọn | Mọi trang / 1366×768 | Trung bình | Có: 4 nhóm (Thị trường/Thông tin/Tài khoản/Vận hành), mục 32px, danh sách co giãn |
| 5 | Ctrl-K mặc định chỉ liệt kê 14 mục: cắt mất lệnh (đổi giao diện, tạo cảnh báo) | Mọi trang | Thấp | Có: 16 mục (14 trang + 2 lệnh) |
| 6 | Tiêu đề thẻ tài khoản mô phỏng tràn ra ngoài thẻ, trang cuộn ngang | Mô phỏng / 768, 375 (và main tràn 1366) | Cao | Có |
| 7 | Chip độ mới quá rộng gây cuộn ngang 2px | Tin tức / 375 | Trung bình | Có (`min-width:0`, nowrap ellipsis) |
| 8 | Thẻ tài khoản MT: tên + chip bị cắt ("MT · 1:…") | Tổng quan / 1366 | Trung bình | Có (flex-wrap) |
| 9 | Nhãn trục Equity lặp "1 1 1 0 0 0" khi dữ liệu phẳng | Tài khoản / mọi | Trung bình | Có (pad tối thiểu, 2 số lẻ khi khoảng hẹp) |
| 10 | Số thập phân dài trong cảnh báo ("13.439209756097561 event…") | Tổng quan, Cảnh báo, Hệ thống | Trung bình | Có: `clean()` |
| 11 | Nhãn mã crypto "CRYPTO:AAVEUSDT" bị cắt thành "CRYPT…", thị trường ghi "Forex" | Thị trường, Phân tích, Ctrl-K | Trung bình | Có: `symbolLabel` bỏ tiền tố; `symbolMarket` "Tiền ảo"/"Vĩ mô" |
| 12 | Thẻ chỉ số VN xuống dòng xấu (thay đổi · %, trần/sàn) | Chứng khoán VN / 1366 | Thấp | Có |
| 13 | Định dạng số trộn `1.234` (vi-VN) và `1,234` (en-US) cho cùng loại số đếm | Hệ thống, Chuyên gia, Chỉ báo | Thấp | Có: số đếm → en-US; chỉ VND và trang Chứng khoán VN giữ kiểu Việt Nam (quy ước đã ghi) |
| 14 | Khoảng dữ liệu nhật ký ISO `2026-09-02` lệch với dd/MM nơi khác | Nhật ký | Thấp | Có (dd/MM/yyyy) |
| 15 | Touch target nhỏ (nút icon `.btn`, nút chart, logo mobile 24px, mục ticker 19px) | Mọi trang / 768, 375 | Trung bình | Một phần: `.btn` ≥44px, nút chart 40px, logo 44px, ticker 44px; còn link chữ inline và vài nút chart (xem hạn chế) |
| 16 | Thiếu `touch-action`, `overscroll-behavior` hộp thoại, `text-wrap: balance` tiêu đề, nền `select` | Toàn app | Thấp | Có (CSS cuối index.css) |
| 17 | **Tên nguồn dữ liệu hiển thị khắp nơi** (huy hiệu "frankfurter · 3 ngày trước", cột Nguồn, bộ lọc nguồn tin, lịch, chuyên gia, Hệ thống, ghi chú VN…) | Tổng quan, Thị trường, VN, Tin tức, Lịch, Chuyên gia, Nhật ký, Hệ thống, Ctrl-K | Cao | Có — xem mục dưới |

Không còn: tràn ngang/dọc bất thường (0/140), chồng panel (0/140), lỗi console của app (trừ 502/WS thoáng qua khi một agent khác khởi động lại gateway), ảnh vỡ (0).

## Yêu cầu bổ sung: không hiển thị tên nguồn dữ liệu

- `lib/format.js`: `scrub()`/`clean()`/`expertLabel()` với danh sách từ cấm (`BANNED_SOURCES`); áp cho cảnh báo, tin (tiêu đề/tóm tắt), lịch, chuyên gia, Hệ thống.
- `Freshness`/`LatestFresh` không còn nhận/hiện tên nguồn (chỉ "N phút trước" + trạng thái, tooltip/aria cũng bỏ).
- Tin tức: bỏ chip nguồn và bộ lọc nguồn; thêm liên kết "Đọc bài gốc ↗" (không in tên miền). Tổng quan/VN: bỏ tên nguồn trên thẻ tin.
- Lịch kinh tế: bỏ chip "Nguồn", tooltip nguồn từng ô, đoạn ghi chú nguồn. Chuyên gia: bỏ cột Nguồn; mã `PREFIX:123` → "Tổ chức 123".
- Hệ thống: thay 2 panel nguồn/đối chiếu bằng "Tình trạng dữ liệu" (Dữ liệu giá / Tin tức / Đối chiếu giá: Tốt – Cần cấu hình – Tạm ngưng…), không tên.
- Chứng khoán VN, Nhật ký, Ctrl-K, Paper: bỏ chuỗi/tooltip nêu nguồn.
- Chống tái phát: `scripts/lint-sources.cjs` (quét app/src, tuỳ chọn `--dist`; chạy trên VPS qua node:22 → OK) + quét runtime mỗi trang (innerText, `.sr-only`, title/aria-label/placeholder/alt) trong script QA.
- Kết quả xác nhận trên bản live: 140/140 lượt không có từ cấm; bundle build chỉ chứa danh sách từ cấm đúng một lần (trong `format.js`). Thuộc tính `source` của API vẫn tồn tại nhưng không render. Ghi công OSS giữ ở THIRD_PARTY.md.

## Điểm từng trang (frontend-design / web-design-guidelines / dataviz, thang 10)

Tổng quan 8, Thị trường 8,5, Chứng khoán VN 8, Danh sách 7,5, Phân tích 7,5, Tin tức 8, Lịch 7,5, Chuyên gia 7, Tài khoản 7, Mô phỏng 7,5 (tên chiến lược dài, nhiều run "[DEPRECATED]" gây rối), Cảnh báo 7,5, Báo cáo 8 (sau sửa), Nhật ký 7,5, Hệ thống 7,5. Quét guideline: không `transition: all`, không clickable div, viewport cho phép zoom, có skip-link, `:focus-visible` rõ (outline 2px, kiểm bằng Tab).

## Hiệu năng

Code-splitting theo trang đã có: index ~284 KB (≈90 KB gzip), echarts 650 KB và lightweight-charts 181 KB là chunk riêng chỉ tải khi cần; Tổng quan tải 115 KB JS, DOMContentLoaded ~135 ms trên mạng docker. Không cần tách thêm.

## Hạn chế còn lại

- Màn 2560×1440: Tổng quan còn khoảng trống lớn trong vài panel (bảng giá, lịch, tín hiệu) vì dữ liệu ít, bố cục co giãn lấp đầy.
- Một số nút nhỏ trong chart (legend, công cụ vẽ) và link chữ inline còn < 44px trên cảm ứng; màu chữ legend chỉ báo cố định chưa tối ưu cho nền sáng.
- Dữ liệu thật còn trống/QA (XAUUSD/VN/AAPL chưa có giá, "QA event/QA news/qa-acct", tài khoản equity 0) — không phải lỗi UI, nên dọn dữ liệu kiểm thử.
- Datalist ở form quy tắc cảnh báo vẫn hiện mã thô có tiền tố (vd. `FRED:DFF`) vì là giá trị nhập.
- Giữa chừng có lần 404 chunk cũ do web-ui được build lại bởi agent khác (tab cũ hiện hộp "Tải lại trang").

## Vòng QA hệ thống UX xuyên suốt (Agent E, 2026-10-12)

Phương pháp: Playwright 1.49 + axe-core (WCAG 2.0-2.2 A/AA) chạy trên VPS (container tạm `qa-ui-e-*`, đã dọn; tài khoản master thử `qa-ui-e` đã xoá; cài đặt `ux` thử đã gỡ khỏi prefs). 21 trang × sáng/tối 1366×768; trang mới thêm 360/390/768/3440.
- Trang mới (Cài đặt, Trợ giúp, Giới thiệu, Design): **0 vi phạm axe** ở cả hai giao diện; không tràn ngang ở 360/390/768/1366/3440.
- Đã sửa trên toàn app: tên nút tìm kiếm chứa chữ nhìn thấy; vùng aria-live đồng hồ/độ tuổi (đọc liên tục) tách khỏi nhãn trạng thái; tương phản ô bản đồ nhiệt Tổng quan; thanh trên vừa 360px (ẩn nút giao diện/trợ giúp khi hẹp); vùng cuộn nhận focus bàn phím.
- Còn lại (thuộc trang của agent khác, đã ghi cho họ): Terminal (aria-allowed-attr, aria-required-children, vùng cuộn, `h1` thiếu, chữ 8px), Thị trường/Phân tích (`nested-interactive` trên canvas, nút tên không chứa chữ nhìn thấy), Tin tức/Lịch (`aria-selected` trên role=button, tên nút lệch chữ, chữ 10.5px), Khách hàng (`.hm-cell`, `.cl-badge`).
- Nhất quán (audit DOM): mọi trang có đúng 1 `h1` (trừ Terminal), mọi `.panel` bo 8px, 0 nút không tên, 0 màu hex nội tuyến; cỡ chữ < 11px chỉ còn ở Thị trường, Tin tức, Lịch, Khách hàng, Terminal.
- Kịch bản tương tác đã chạy thật: Ctrl-K (cú pháp cảnh báo → biểu mẫu điền sẵn giá, `>`, `?`), `g k`, `?`, đổi màu nhấn/mật độ/cỡ chữ/màu tăng-giảm (nhớ sau tải lại + lưu server), đổi múi giờ (nhãn UTC-4), chuông + toast, xuất CSV/XLSX (mở được bằng openpyxl, số là số)/PNG, in (nền trắng), banner ngoại tuyến, tour 8 bước, tooltip thuật ngữ, ↑↓ trong bảng.

### Hiệu năng (cùng harness; VPS đang tải ~6-8 do agent khác, số chỉ mang tính tương đối; mạng docker nội bộ, không throttle; tải lạnh; trung vị 3 lần)
| Trang | LCP trước → sau | FCP | CLS | TBT |
|---|---|---|---|---|
| Tổng quan | 555 → 1350 ms (đo lúc VPS bận; 1 lần tải đạt 481-555) | 454 → 350 | 0,03 → 0,055 | 113 → 72 |
| Thị trường | 421 → 495 | 301 → 283 | 0,05 → 0,03 | 11 → 27 |
| Hệ thống | 346 → 525 | 297 → 320 | 0,01 → 0,01 | 4 → 1 |
| Cảnh báo | 347 → 526 | 300 → 317 | 0,004 → 0,004 | 11 → 15 |
Mọi LCP < 2,5 s. JS truyền khi tải (gzip): trước ~119-147 KB/trang → sau ~185-225 KB/trang; phần tăng chủ yếu từ khung Terminal/đăng ký trang (agent A) và hệ thống UX (~+13 KB gzip trong bundle chính); các hộp thoại Ctrl-K/phím tắt/thông báo/tour/xuất tệp/thuật ngữ là chunk riêng nạp lúc rảnh. Bundle chính `index` ≈ 105 KB gzip (mục tiêu < 250 KB: đạt).

