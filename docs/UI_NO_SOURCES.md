# UI_NO_SOURCES — không hiển thị tên nguồn dữ liệu

**Quy tắc sản phẩm**: mọi nội dung người dùng nhìn thấy (web, báo cáo PDF/HTML, thông báo ntfy/Apprise/Telegram, bản tin, nhật ký)
chỉ hiển thị **NỘI DUNG** (tin, tín hiệu, chỉ báo, giá, lịch). KHÔNG hiển thị tên nguồn (dukascopy, yahoo, cafef, reuters, forexfactory, ...).
Công cụ vận hành nội bộ (log, Prometheus, Gatus, Grafana, `docs/*`) GIỮ NGUYÊN tên nguồn để chẩn đoán.

## Bộ lọc trung tâm — `libs/common/src/tscommon/sources.py`
- Danh sách tên: `sources.yaml` (đóng gói cùng thư viện; ghi đè bằng `SOURCES_CONFIG=/đường/dẫn.yaml`). Mục: `strict` (luôn loại), `contextual`
  (tên dễ nhầm với nội dung thật — ecb, fred, bls, cftc, sec, ssi, gate: chỉ loại ở ngữ cảnh nguồn: "nguồn: X", "theo X", "X API/lỗi/feed", tên miền),
  `id_prefixes` (id feed `fed_press_all`, `bls_cpi`, `vietstock_cophieu`...), `domains` (URL có host này bị gỡ khỏi văn bản), `rewrites`, `strong_keys`,
  `source_keys`, `id_keys`. Thêm nguồn mới: sửa `sources.yaml` rồi build lại service (hoặc `sources.reload()`).
- API: `scrub_sources(text)` (khớp hoa/thường, `_`/khoảng trắng, tên miền, URL, hậu tố id; idempotent; không đổi chuỗi không chứa tên),
  `scrub_tags(tags)` (bỏ tag là tên nguồn, giữ `ch:*`/`rule:*`), `scrub_obj(obj)` (đệ quy dict/list), `has_source_name`, `is_source_value`.
- `rewrites`: viết lại câu kỹ thuật thành câu trung tính, ví dụ `dukascopy lỗi lấy dữ liệu GBPUSD M1` → `dữ liệu giá GBPUSD M1: lỗi cập nhật`
  (khớp cả có dấu / không dấu). Phần còn lại: bỏ "Nguồn: X", "theo X", "- X" cuối dòng; tên sót thay bằng `nguồn dữ liệu`.
- `scrub_obj`: khoá `strong_keys` (provider, publisher, feed, feed_id, needs_env...) luôn bị bỏ; khoá "giống nguồn" (`source`, `*_source`, `src`, `via`, `origin`)
  chỉ bị bỏ khi GIÁ TRỊ là tên nguồn (`mt5:demo-mt5-01`, `sim:*`, `price_source=quote` được giữ); khoá định danh `id_keys` (url, event_id, expert_id,
  dedupe_key, id...) giữ nguyên giá trị (UI dùng làm khoá/liên kết, không hiển thị); mọi chuỗi khác được `scrub_sources`.

## Nơi áp dụng
| Nơi | Cách |
|---|---|
| `alert-service` (điểm phát cuối) | `engine.scrub_payload` ở đầu `AlertEngine.handle` (title/body/tags → dùng cho dedupe-report, `alerts:recent`, digest, sự kiện `alerts.delivery` → `alerts.delivered`); thêm lớp cuối `Dispatcher.send`, `AppriseChannel.send` (ntfy/Apprise), `TelegramClient.send` (kể cả trả lời lệnh). `LogChannel` ghi log đã scrub. `dedupe_key` giữ nguyên (định danh). |
| Mọi emitter `alerts.out` (market/news/expert-collector, nlp, risk-monitor, journal, paper-trader, analytics, reporter, alert-rules) | Không sửa từng service: đi qua alert-service nên được scrub tập trung. Log/Prometheus của chính service giữ nguyên. |
| `reporter` (PDF/HTML ngày/tuần) | `build()` bỏ cột/trường nguồn (nguồn tin, bảng nhà cung cấp, "Nguồn: …") và chạy `scrub_obj` lên toàn bộ ngữ cảnh; mục "Sức khoẻ hệ thống & dữ liệu" chỉ nêu trạng thái tổng hợp ("luồng dữ liệu giá đang hoạt động n/m, ổn định/chậm cập nhật"); `render_html` chạy `scrub_sources` lần cuối trên HTML (PDF dựng từ HTML đã sạch). |
| `api-gateway` (`HIDE_SOURCES`, mặc định `true`) | Middleware `hide_sources_mw` xử lý mọi phản hồi JSON `/v1/*` (và HTML của `/v1/reports`) bằng `scrub_obj`; payload WebSocket `/v1/stream` cũng được scrub; `/v1/bars` khử trùng nến theo ưu tiên nguồn khi nhiều nguồn cùng `(symbol, tf, ts_open)` (UI không còn phân biệt nguồn); `/v1/data-sources` trả trạng thái tổng hợp ẩn danh (`provider` = "Luồng giá 1..n", bỏ `needs_env`); `/v1/system` giữ nguyên (tên service/bảng vận hành, không phải tên nguồn). `HIDE_SOURCES=false` để debug (đặt trong env service `api-gateway`). Khoá `source` vẫn có thể có mặt khi giá trị trung tính (vd `sim:*` của nhật ký — reporter dùng để loại tài khoản mô phỏng). |
| `web-ui` | Do agent giao diện xử lý (không render `source`). |
| `briefing` (bản tin AI) | Do agent bản tin xử lý; dùng `tscommon.sources.scrub_sources` cho đầu ra. |

## Kiểm thử
- `libs/common/tests/test_sources.py` — hàm scrub (nhiều biến thể hoa/thường/tên miền/id/URL; nội dung thường giữ nguyên; idempotent; ghi đè cấu hình YAML).
- `services/alert-service/tests/test_alert.py` — không kênh nào (Telegram/Apprise/digest/delivery) nhận tên nguồn.
- `services/reporter/tests/test_no_sources.py` — quét HTML + văn bản PDF của báo cáo ngày/tuần.
- `services/api-gateway/tests/test_hide_sources.py` — gateway ẩn trường nguồn khi `HIDE_SOURCES`, trả nguyên khi tắt.

## Track-record chuyên gia (`/v1/experts/*`)
- Thực thể chuyên gia (`entity_id`) chỉ có `label` TRUNG LẬP: người/tổ chức có tên thật → tên đó; luồng tin / loại vị thế → nhãn chung ("Luồng tin #n", "Ngân hàng trung ương #n", "Vị thế đầu cơ — EUR"). TUYỆT ĐỐI không đặt tên website/nhà cung cấp/URL làm nhãn, và không trả `source`/`url`/`ref` dạng thô ra UI (`ref` chỉ là khoá băm).
- Gateway vẫn chạy bộ lọc `hide_sources` trên các phản hồi này (scrub_obj): nhãn trung lập và số liệu không bị đổi; mọi chuỗi chứa tên nguồn (kể cả trong ghi chú) bị gỡ. Test: `services/api-gateway/tests/test_track_routes.py::test_hide_sources_scrubs_but_keeps_expert_label`.
- Thông báo đồng thuận của expert-collector chỉ nêu số lượng chuyên gia + tổng trọng số + "chỉ tham khảo", không nêu nguồn.

## Còn lộ (biết trước)
- Trường định danh `url` của tin/chuyên gia (liên kết bài gốc, có tên miền) và `dedupe_key`, `expert_id`, `event_id` giữ nguyên trong JSON (UI không hiển thị; chỉ dùng làm khoá/liên kết). Nếu cần ẩn cả tên miền: thêm bước chuyển hướng/rút gọn liên kết ở UI.
- Báo cáo đã sinh TRƯỚC khi áp dụng và bảng `alerts`/`news_items` trong DB vẫn chứa tên nguồn (chỉ phần phát ra UI/thông báo được scrub); báo cáo cũ có thể sinh lại bằng `python -m reporter.cli daily|weekly --force`.
- Tên nguồn chưa có trong `sources.yaml` sẽ lọt qua — bổ sung khi thêm collector/feed mới.
