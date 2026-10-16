# QA giao diện cuối — master (web-ui) + client (client-ui)

Ngày: 2026-10-14 (VPS). Tiếp nối [handoff](../handoff/HANDOFF_ui_qa.md) (đợt laptop m61/61).

## Phương pháp
- Bộ công cụ: `services/web-ui/qa/final.sh` + `final.mjs` (Playwright 1.49 trong container tạm, axe-core 4.10 WCAG 2 A/AA).
  Tự tạo và tự xoá tài khoản thử; master bật TOTP; client đổi mật khẩu lần đầu, đặt ngôn ngữ/giao diện qua API prefs.
- Kiểm tra mỗi trang: tràn ngang/ra ngoài khung, chồng panel, chữ bị cắt, cỡ chữ < 10px, mục tiêu chạm < 44px (mobile/tablet),
  NaN/undefined, tên nguồn dữ liệu (danh sách cấm), chữ tiếng Việt sót ở bản en, skeleton kẹt, `role=alert`, axe, lỗi console/HTTP.
- Phạm vi: master 36 route (+4 workspace Terminal) × 375x812 / 768x1024 / 1366x768 × tối/sáng = 240 ngữ cảnh;
  client 17 trang × 3 độ phân giải × tối/sáng × vi/en = 204 ngữ cảnh. Đợt laptop trước đã phủ thêm 1920x1080 và 2560x1440.
- Các lượt chạy: m71 (master, trước khi sửa), 71 (client), m72 (master, sau khi sửa), m73–m76 (chạy lại các ngữ cảnh bị
  gián đoạn khi agent khác deploy web-ui/api-gateway cùng lúc). Kết quả JSON và ảnh lưu kèm ở `docs/final/` (ngoài git).

## Master — trang × độ phân giải × lỗi (trước → sau)
Chỉ liệt kê các trang có lỗi ở ít nhất một lượt. Ở 1366x768 trở lên không đo mục tiêu chạm.

| Trang | 375x812 | 768x1024 | 1366x768 | Đã sửa |
|---|---|---|---|---|
| terminal (+ws Forex/Crypto/Tin & Lịch) | tràn → — | tràn → — | tràn → — | Báo nhầm: băng giá chạy (marquee) → `final.mjs` bỏ qua `.tape` |
| tong-quan | touch → — | touch → — | aria-scroll → — | Liên kết mã/“Chi tiết”/“Tất cả” có `min-width: 44px`; vùng cuộn focus được ngay |
| chung-khoan-vn, danh-sach, movers | touch → — | touch → — | — | Liên kết mã trong bảng có `min-width: 44px` (index.css) |
| lich | contrast → — | contrast → — | contrast → — | Thẻ “N▲” trên tiêu đề hôm nay dùng `text-fg`; sự kiện đã qua dùng `saturate` thay `opacity` |
| mo-phong | contrast → — | contrast, touch → — | aria-scroll → — | Khối chỉ số “chưa tin cậy” dùng viền đứt nét thay `opacity-70`; `.ux-link` ≥ 44px |
| doi-tai-khoan | touch, tràn (472 > 375px) → — | touch → — | — | Thẻ tài khoản `min-w-0` (grid item); nút `all:unset` nội tuyến có `min-height: 44px !important` |
| tai-khoan, vai-tro, nhip-thi-truong | aria-scroll → — | — | aria-scroll → — | App.jsx: MutationObserver gắn `tabindex=0` cho vùng cuộn ngay khi DOM đổi (trước: chỉ chạy mỗi 2,5 giây) |
| su-co | — | touch → — | — | (cùng sửa liên kết 44px) |
| nhat-ky | — | touch → touch | — | Ngoại lệ có chủ ý: ô lịch nhiệt 18px (lưới mật độ cao) |

Các trang sạch ở mọi ngữ cảnh: terminal-ws Chứng khoán VN, thi-truong, tro-giup, cai-dat, phan-tich, kich-ban, suc-manh-tien-te,
phien-giao-dich, ban-do-nhiet, tuong-quan-rui-ro, ban-tin, tin-tuc, chuyen-gia, vi-the-lon, luat, bao-cao-khach,
phien-thiet-bi, kiem-toan, canh-bao, bao-cao, khach-hang, he-thong, gioi-thieu. Không trang nào lộ tên nguồn dữ liệu,
không có NaN/undefined, không có chữ bị cắt hay chữ < 10px.

## Client — 17 trang × 3 độ phân giải × 2 giao diện × vi/en
| Hạng mục | Kết quả |
|---|---|
| Bố cục/tràn/chồng panel, touch < 44px, axe (contrast, ARIA) | 0 lỗi ở cả 204 ngữ cảnh (các sửa của đợt laptop đã có hiệu lực) |
| Tên nguồn dữ liệu, NaN/undefined | 0 |
| `vi-left` ở bản en | Chỉ là nội dung máy chủ (tin, bản tin VN, lịch) và tên ngôn ngữ “Tiếng Việt” trong bộ chọn — đúng thiết kế |
| HTTP 404 `risk/accounts/*`, `journal/*/summary` | Tài khoản thử chưa có dữ liệu; UI hiển thị trạng thái rỗng đúng, chỉ bẩn console |
| 503 rải rác (rui-ro, nhat-ky, thi-truong) | Tạm thời, trùng lúc agent khác deploy api-gateway |

## Điểm (1–5)
| Tiêu chí | Master | Client |
|---|---|---|
| Bố cục đáp ứng (375 → 2560) | 5 | 5 |
| Truy cập (WCAG 2 AA axe, touch 44px) | 4,5 (còn ô lịch Nhật ký 18px có chủ ý; toast đang mờ dần có thể bị axe đo contrast) | 5 |
| Nội dung (không tên nguồn, không giá trị hỏng) | 5 | 5 |
| Trạng thái rỗng/lỗi/đang tải | 4,5 | 4,5 (404 console) |
| Ngôn ngữ en | — | 4,5 (nội dung máy chủ chưa dịch) |
| Ổn định khi deploy | 4 (trang lazy cũ 404 sau deploy → hiện “Tải lại trang”, có hướng dẫn) | 4 |

## Dọn dữ liệu thử
- Tài khoản thử: `master:qa-final-*`, `master:qa-probe`, `mt5:9990xx` do final.sh tạo đều đã xoá. `master:cs-e4d28a`,
  `mt5:98596106/99596106/100596106` (agent secrets) không còn trong `portal_users`/`mt_accounts` khi kiểm tra.
  `view_as_grants` còn 7 bản ghi cũ của actor `master:qa-*` đã hết hạn — giữ làm vết kiểm toán.
- Dữ liệu chuyên gia thử: bảng Postgres `experts`/`expert_signals`/`expert_positions`/`expert_opinions` không còn dòng qa-*/QAUSD.
  Còn trong Redis stream (đã được storage-writer tiêu thụ, pending 0): `expert.signals` 9, `expert.positions` 6, `news.enriched` 2
  (`qa.invalid`) → đã sao lưu nguyên văn vào `data/cleanup_20261014_ui/*.qa.tsv` (0600, ngoài git) rồi `XDEL`.
- Sổ cái track-record `tr_views` còn 3 dòng QAUSD: bất biến theo thiết kế (trigger chặn sửa/xoá, chuỗi băm) — không bao giờ được chấm
  (xem [EXPERT_TRACKRECORD.md](../EXPERT_TRACKRECORD.md)); UI lọc bằng `isQaId`.

## Tồn đọng
1. Console 404 `risk/accounts/*`, `journal/*/summary` cho tài khoản chưa có dữ liệu — cần backend trả 200 rỗng.
2. Ô lịch nhiệt Nhật ký 18px (ngoại lệ có chủ ý), logo TradingView (bắt buộc).
3. Toast/thông báo đang hiệu ứng mờ có thể bị axe đo tương phản thấp (tạm thời, chữ `--muted` đạt AA khi hiện đủ).
4. Nội dung tin/bản tin VN ở client en là dữ liệu máy chủ, chưa dịch.
5. Khi deploy web-ui, tab đang mở với bản cũ gặp 404 chunk lazy → màn “Tải lại trang” (đúng thiết kế, có thể thêm tự tải lại một lần).
6. Toast cảnh báo rủi ro của tài khoản thử từ e2e agent khác (`qa-…`) hiện trên mọi trang khi e2e chạy — e2e nên tự dọn cảnh báo.
7. Trang `design` (nội bộ) cố ý hiển thị trạng thái lỗi/skeleton mẫu — QA tự động báo nhầm.

## Ảnh
- Master: `services/web-ui/docs/final/` (240 ảnh `<vp>-<theme>-vi-<route>.jpg` + `results-master-m7x.json`).
- Client: `services/client-ui/docs/final/` (204 ảnh `<vp>-<theme>-<lang>-<trang>.jpg` + `results-client-71.json`).
- Hai thư mục này bị loại khỏi git (`.git/info/exclude`), chỉ lưu trên VPS.
