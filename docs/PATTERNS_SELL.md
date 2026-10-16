# PATTERNS_SELL — Kịch bản Sell KB-1..KB-4 (pattern-engine)

> CHỈ thông tin / paper. Không gửi lệnh thật; SL/TP là GỢI Ý. Nguồn kịch bản: `plan1/` (hội thoại + `Lệnh Sell.docx` 3 ảnh XAUUSD M15). Buy: chưa có tài liệu (giai đoạn E).

## 1. Kiến trúc
`bars` (ts_ro) → `services/pattern-engine` (Python, tscommon) → stream `pattern.signals` + bảng `pattern_signals` (migration 018, role `ts_pattern` chỉ SELECT/INSERT) → gateway `GET /v1/patterns`, `/v1/patterns/spec` (cache 10s/300s; master xem mọi trạng thái, client chỉ `armed|triggered`, không thấy tham số). Cấu hình: `spec/common.yaml` + `spec/kb1..4.yaml` (tham số, bước checklist, điều kiện huỷ) + `pattern-engine.example.yaml` (runtime: khung, symbol, ghi đè tham số).

## 2. Nền tảng chung (mọi ngưỡng chuẩn hoá theo ATR14 hoặc độ dài sóng)
- **Chỉ nến đã đóng**; ATR Wilder 14. Nến i chỉ dùng dữ liệu ≤ i. Cấu trúc chốt ở nến i−1, nến i là nến kích hoạt/huỷ → **không look-ahead**. Pivot đã xác nhận append-only, sự kiện đã phát bất biến → **không repaint** (đổi ý chỉ bằng sự kiện `invalid` mới). Test tự động: `tests/test_no_lookahead.py` (kết quả trên nến i giống hệt khi cắt/thêm/thay nến tương lai bằng dữ liệu rác).
- **Swing**: ZigZag thích nghi ATR, đảo chiều khi giá đi ngược ≥ k×ATR, đa thang `zigzag_atr: [2.0, 3.0]` (thang lớn xác định cấu trúc, thang mịn cho chi tiết bên trong tích luỹ). Pivot xác nhận trễ; cực trị đang chạy ("tạm thời") chỉ dùng như điểm tạm.
- **Sóng dẫn hướng giảm**: đỉnh h0 → đáy l1 (h0 cao nhất, l1 thấp nhất của nhịp), dài ≥ `lead_min_atr`, ≥ `lead_min_long_red` nến đỏ thân ≥ `lead_long_body_atr`×ATR, tỷ trọng thân nến xanh ≤ `lead_max_green`.
- **Nhấn chìm giảm**: thân đỏ ≥ `trigger_body_atr`×ATR, bao thân nến trước (dung sai `engulf_eps_atr`) và đóng dưới đáy nến trước. **Cụm nén**: `cluster_bars`=3 nến liên tiếp thân ≤ `small_body_atr`×ATR, biên cụm ≤ `cluster_range_atr`×ATR.
- **Trạng thái**: `forming` → `armed` (đủ cấu trúc, chờ nến kích hoạt) → `triggered` | `invalid` (cuối). Mỗi (setup_id, symbol, tf, state) phát đúng 1 lần; nhiều thang swing cùng neo gộp thành 1 chuỗi sự kiện. Chỉ setup đã `armed` mới phát `invalid`.
- **Mức gợi ý**: entry = giá đóng nến kích hoạt; SL = đỉnh cấu trúc + `sl_buffer_atr`×ATR (KB-1: max(đỉnh 4, đỉnh 5); KB-2: đỉnh thấp dần cuối; KB-3: đỉnh đầu; KB-4: đỉnh đầu tiên của vùng đi ngang mới); TP = entry − m×R, m ∈ `tp_r` = 1, 2, 3 (R = SL − entry). Thêm mức tham chiếu: đáy trước, đường cổ/cạnh dưới, measured move (KB-3).
- **Điểm (score 0..100)**: tỉ lệ bước đã thoả × chất lượng từng bước (độ gần lý tưởng); CHỈ để xếp hạng, chưa phải xác suất thắng.

## 3. Bốn kịch bản
| KB | Cấu trúc (checklist `steps`) | Nến kích hoạt (đóng nến) | Huỷ |
|---|---|---|---|
| KB-1 (ảnh 2) | (1) sóng dẫn → (2) hồi 15–60% → (3) giảm nhẹ ≈ sóng (2) ±25% → (4) hồi vượt đỉnh (2) ≤ 25% sóng (3) → (5) đi ngang, 2 đỉnh giảm dần (đáy giữa sâu ≥ 1 ATR) | nhấn chìm giảm thân ≥ 1.5 ATR trong ≤ 8 nến sau đỉnh (5), đỉnh (5) < đỉnh (4) | đóng cửa > đỉnh (4)+0.25 ATR; quá hạn; thủng đáy giữa > 0.75 ATR không có nhấn chìm |
| KB-2 (ảnh 1) | (1) sóng dẫn → (2) hồi 25–75% (≈50% ±25 điểm %) → (3) nêm: ≥ 3 đỉnh thấp dần, ≥ 2 đáy cao dần, co hẹp ≤ 85% (cạnh = nối điểm đầu–cuối, điểm giữa được xuyên ≤ 2 ATR) | nhấn chìm giảm thân ≥ 1.5 ATR, ĐÓNG DƯỚI cạnh dưới | đóng cửa > đỉnh hồi (2)+0.25 ATR; quá 220 nến; đóng dưới cạnh dưới > 0.75 ATR không có nhấn chìm |
| KB-3 (ảnh 3) | (1) sóng dẫn ≥ 8 ATR → (2) đi ngang ≥ 40 nến, biên ≥ 7 ATR và ≤ 1.2× sóng dẫn, nến thân vừa → (3) vai-đầu-vai (đầu cao hơn vai ≥ 12% chiều cao đầu-cổ, vai/cổ cân ±40%/±35%) → (4) giá về sát đường cổ | cụm 3 nến thân ≤ 0.5 ATR ngay sát đường cổ | nến chạm quá đỉnh đầu / đóng > vai phải+0.25 ATR; thủng đường cổ > 1 ATR trước cụm nén; quá 90 nến sau vai phải |
| KB-4 (6 mục chat) | (1) đi ngang (hộp ≤ 8 ATR) → (2) nến thân ≥ 2 ATR đóng dưới hộp → (3) ≥ 3 nến đỏ liên tiếp + sóng dẫn → (4) đi ngang mới → (5) 3 đỉnh giảm dần → | cụm 3 nến nén dưới đỉnh thứ 3 | đóng cửa > đỉnh đầu của vùng mới; thủng đáy sóng dẫn > 0.75 ATR; quá 30 nến sau đỉnh 3 |

## 4. Giả định mặc định và phần ĐÃ HIỆU CHỈNH theo golden (phải đọc)
Giả định gốc (plan1): thân dài > 1.5×ATR14; sóng dẫn ≥ 3 nến đỏ thân dài, xanh ≤ 25%; nhấn chìm giảm = thân đỏ bao thân trước + đóng dưới đáy trước; "bằng sóng" ±25%; "vượt đỉnh một chút" ≤ 25% sóng.
Kết quả đo trên 3 sóng dẫn của ảnh mẫu KB-2/KB-1/KB-3 (xem `services/pattern-engine/tools/leg.py`): số nến đỏ thân ≥ 1.5 ATR = **1 / 1 / 3** (cần ≥ 3) và tỷ lệ nến xanh theo SỐ nến = **40% / 23% / 39%** (cần ≤ 25%) → giả định gốc **không sóng mẫu nào thoả cả hai điều kiện (0/3)**. Hiệu chỉnh (đã ghi trong `spec/common.yaml`, đánh dấu `[HIỆU CHỈNH]`):
1. `lead_long_body_atr` 1.5 → **0.8** (chỉ áp dụng cho sóng dẫn; nến KÍCH HOẠT vẫn 1.5 ATR);
2. `lead_max_green` 25% theo số nến → **40% theo tỷ trọng thân** (3 sóng mẫu: 23% / 12% / 37%);
3. KB-3: `lead_min_atr` 8, `range_min_atr` 7 (loại 1 hình vai-đầu-vai nhỏ bắt nhầm lúc 22/09 03:15; sóng mẫu = 10.6 ATR / 7.9 ATR);
4. KB-2: điểm giữa được xuyên cạnh nêm ≤ 2 ATR (`envelope_tol_atr`, mẫu xuyên 1.5 ATR); KB-2/KB-1 hồi dùng khoảng 25–75% / 15–60% (ảnh mẫu 69% / 35%);
5. swing đa thang [2, 3] và (KB-1) bước 5 tính theo nến thay vì pivot (nhịp hồi giữa 2 đỉnh chỉ ~1.6 ATR, không đủ là pivot).
**Cảnh báo overfit**: 5 điều chỉnh trên được chọn để khớp đúng 3 ví dụ (+ loại 1 FP quan sát được); mẫu quá nhỏ nên chưa chứng minh tổng quát. Chỉ dùng làm điểm khởi đầu; phải kiểm trên dữ liệu rộng (giai đoạn B/C: walk-forward, nhiều mã/khung, ngoài mẫu) trước khi tin. **Đã kiểm (2026-10-14, `docs/research/PATTERN_SELL_BACKTEST.md`)**: không có edge sau chi phí (walk-forward −0,10 R/lệnh, test khoá −0,26 R/lệnh, không hơn vào lệnh ngẫu nhiên); bộ tham số gốc không tệ hơn bộ đã hiệu chỉnh.

## 5. Golden test (3/3)
`tests/test_golden.py` + `tests/fixtures/` (nguồn nến và ánh xạ giờ ảnh→UTC trong `tests/fixtures/README.md`). Nến kích hoạt đúng với kỳ vọng đọc từ ảnh: **KB-3** 2026-09-27 23:45 UTC (cụm nén ở đường cổ sau cuối tuần), **KB-2** 2026-10-02 00:00 UTC (nhấn chìm phá cạnh dưới nêm), **KB-1** 2026-10-05 11:30 UTC (nhấn chìm tại đỉnh (5)); sai lệch 0 nến (dung sai ±2). Trên ~1290 nến mẫu: 3 triggered, 0 triggered ngoài kỳ vọng, 2 setup KB-2 `armed` rồi `invalid` (phá đáy không có nhấn chìm). KB-4 chưa có ảnh mẫu → kiểm bằng chuỗi nến tổng hợp (`tests/test_kb4_synthetic.py`).
**Hạn chế dữ liệu**: nến fixture lấy từ nguồn công khai khả dụng là vàng kỳ hạn (GC=F) vì nguồn tick giao ngay bị chặn từ VPS lúc xuất; giá lệch ~+30 so với ảnh nhưng detector chuẩn hoá theo ATR. Cần thay bằng nến giao ngay (xem README fixture) và chạy lại.

## 6. Hợp đồng sự kiện / API
Stream `pattern.signals`, event `pattern.signal`: `{pattern, tf, symbol, state, side:"sell", score, levels{entry,sl,tp_1r,tp_2r,tp_3r,r,atr,...}, steps[{id,label,ok,detail}], ts, bar_ts, setup_id, reason, points[{label,t,p}], info_only:true}` — `points` = toạ độ đỉnh/đáy để vẽ (KB-1: h0,(1)..(5); KB-2: h0,(1),(2); KB-3: LS,cổ,H,cổ,RS; KB-4: h0,(1),H1..H3), chỉ hiển thị, không ảnh hưởng logic (xem `docs/CONTRACTS.md`). `GET /v1/patterns?symbol=&tf=&pattern=&state=&since=&limit=`; `GET /v1/patterns/spec`.

## Render

Module độc lập `services/pattern-render` (matplotlib + numpy + pillow, headless, không phụ thuộc engine/DB). Engine gọi:

```python
from pattern_render import render_signal
png = render_signal(candles, annotations, out_path="sig.png", size=(1920, 900), max_kb=150)
```
CLI: `python -m pattern_render render --candles c.json --ann a.json --out x.png [--max-kb 150]`.
API nội bộ: `python -m pattern_render serve --port 8791` → `POST /render {"candles":[..],"annotations":{..},"max_kb":150}` trả `image/png`; `GET /healthz`.
Phong cách: nền đen, nến xanh/đỏ kiểu MT4 (trục X theo chỉ số nến, không khoảng trống cuối tuần), nhãn trắng, trục giá bên phải. Ảnh KHÔNG chứa tên nguồn dữ liệu.

**candles**: `[{"t": ISO8601|epoch_giây(UTC), "o","h","l","c"}]` hoặc `[[t,o,h,l,c]]`; tăng dần, không trùng; OHLC nhất quán.

**annotations** (mọi khoá tuỳ chọn). Một *điểm* là `{"t": thời_gian | "i": chỉ_số_nến (có thể lẻ), "p": giá}`:

| Khoá | Dạng | Ý nghĩa |
|---|---|---|
| `title` | `{symbol, tf, scenario, time}` | dòng tiêu đề góc trên trái: `XAUUSD, M15:  <kịch bản>  <thời điểm>` |
| `legs[]` | `{from, to, arrow?, label?, label_at?}` | sóng/swing nối 2 điểm; `label` ví dụ `"(1)"` đặt cạnh đoạn (hoặc tại `label_at`); `arrow` thêm đầu mũi tên |
| `lines[]` | `{kind: trend\|boundary\|wedge\|neckline\|horizontal, from, to, arrow?, label?, label_at?}` | đường xu hướng / biên / nêm / neckline |
| `zones[]` | `{from, to, label?, fill?}` | hộp chữ nhật (2 góc) |
| `arrows[]` | `{from (đuôi), to (mũi nhọn), label?}` | mũi tên nến kích hoạt, nhãn đặt ở đuôi |
| `labels[]` | `{at, text}` | nhãn tự do |
| `levels[]` | `{kind: entry\|sl\|tp, price, label?}` | đường nét đứt ngang: Entry vàng, SL đỏ, TP xanh lơ, kèm giá |
| `tz_offset_h` | số | cộng vào giờ UTC khi in trục thời gian (mặc định 0) |
| `watermark` | chuỗi | mặc định `"Pattern Lab - mo phong"`; `""` = tắt |
| `style` | `{label_size, line_width, digits, last_price_line, right_pad_bars, left_pad_bars, body_width, title_size, xtick_bars}` | tinh chỉnh hiển thị |

Ví dụ tối thiểu:
```json
{"title":{"symbol":"XAUUSD","tf":"M15","scenario":"KB2 SELL","time":"2026-10-01 10:00"},
 "legs":[{"from":{"t":"2026-10-01T03:00:00Z","p":4219.3},"to":{"i":95,"p":4139.0},"arrow":true,"label":"(1)"}],
 "lines":[{"kind":"boundary","from":{"i":110,"p":4192},"to":{"i":190,"p":4181}}],
 "arrows":[{"from":{"i":196,"p":4190},"to":{"i":191,"p":4181}}],
 "levels":[{"kind":"entry","price":4178.5},{"kind":"sl","price":4186.0},{"kind":"tp","price":4140.0}]}
```
Ảnh demo dựng lại 3 ảnh mẫu: `services/pattern-render/docs/demo/` (tạo bằng `tools/build_demos.py`). Test: `pytest` trong `services/pattern-render` (chạy trên VPS).

## 7. Live: quét + paper + thông báo ảnh + trang "Kịch bản" (service `pattern-scan`, 2026-10-14)
CHỈ thông tin/mô phỏng: không có đường tới lệnh thật (test AST `tests/test_no_real_execution.py`). Chi tiết vận hành: `services/pattern-scan/README.md`.
- **Quét**: pattern-engine quét nến ĐÃ ĐÓNG của watchlist (`pattern-engine.example.yaml`: XAUUSD, XAGUSD, EURUSD, GBPUSD, USDJPY, AUDUSD, USDCAD, USDCHF, NZDUSD, BTC, ETH × M15/H1/H4; cần ≥ 80 nến/chuỗi — H4 vàng/FX intraday mới có ~47 nến nên sẽ tự vào khi đủ). Chỉ số (US500/NAS100) chưa có nến intraday trong `bars`.
- **Luồng**: `pattern.signals` (consumer group `pattern-scan`, + bù từ bảng `pattern_signals` mỗi 10 phút) → `pattern_scan_events` → ảnh PNG (cùng `pattern_render`, nến tới đúng nến đổi trạng thái — không look-ahead; điểm vẽ từ `points` của sự kiện nếu có, không thì suy từ `setup_id` + `levels`) → `pattern_scan_media` → thông báo ntfy kèm ảnh (topic `tradingsys-patterns`; trạng thái `armed`, `triggered` và khi lệnh paper đóng; ≤ 20 tin/phút; nội dung qua `scrub_sources`) → `triggered` mở lệnh PAPER.
- **Live vs replay**: sự kiện nhận ≤ 3 nến sau khi nến đóng = live; cũ hơn (bù/khởi động lại) = replay: không thông báo, lệnh paper gắn cờ `replay` và KHÔNG vào thống kê mặc định.
- **Quy tắc paper** (bảo thủ, `pattern_scan/paper.py`): vào = giá đóng nến kích hoạt; SL = `levels.sl`; 3 phần bằng nhau chốt ở TP 1R/2R/3R; không dời SL; chỉ nến đã đóng cùng khung sau nến kích hoạt; nến chạm cả SL và TP ⇒ SL trước; mở cửa nhảy qua SL/TP ⇒ khớp giá mở; hết hạn 192 nến ⇒ đóng ở giá đóng; chi phí khứ hồi theo bps (mặc định 2, XAUUSD 3, XAGUSD 6, crypto 10) trừ vào R.
- **Track record**: `pattern_paper_trades` (trigger DB chặn sửa lệnh đã đóng/thông số vào lệnh) + sổ cái `pattern_paper_ledger` chỉ-thêm, `hash = sha256(prev|kind|ref|json chuẩn hoá)`; kiểm tại `/v1/patterns/stats` (`ledger.ok`). Role DB hẹp `ts_pscan` (`infra/db/create_pscan_role.sh`, migration 019).
- **API** (gateway, GET): `/v1/patterns/live?view=active|history|all`, `/v1/patterns/setup`, `/v1/patterns/media/{id}.png`, `/v1/patterns/trades`, `/v1/patterns/stats`, `/v1/patterns/examples[/{id}.png]`. Client bị ép `audience=client`: chỉ setup đã armed/triggered (setup bị huỷ, forming, lý do huỷ và ảnh forming/invalid bị ẩn); dữ liệu là tín hiệu chung, không gắn tài khoản ai.
- **UI**: web-ui `#/kich-ban` (trang "Kịch bản" master, nhóm Thị trường: mọi trạng thái + tham số) và client-ui `#/kich-ban` (vi/en): tín hiệu hiện tại theo trạng thái, chi tiết với ảnh + biểu đồ nến tương tác (Entry/SL/TP + điểm đánh dấu), lịch sử + kết quả paper (R, winrate, PF, maxDD R, đường R luỹ kế, cảnh báo mẫu nhỏ n<30), thư viện ví dụ (3 mẫu chuẩn sinh bằng `services/pattern-scan/tools/build_examples.py` + tín hiệu đã kích hoạt), mô tả KB-1..KB-4, băng cảnh báo "chỉ thông tin, không phải khuyến nghị".
- **Hạn chế**: chưa có tín hiệu triggered live tại thời điểm triển khai (paper mới kiểm bằng test); Telegram chờ bot của người dùng; Web Push cho client chưa nối (alert-rules chỉ có mẫu push chung theo người dùng) — bước sau.
