# Track record chuyên gia / nguồn ý kiến (service `track-record`)

Mục tiêu: đo độ **uy tín khách quan** của mỗi chuyên gia/nguồn ý kiến bằng **thành tích kiểm chứng được**, không bằng danh tiếng hay lời quảng cáo.
Nguyên tắc dẫn đường (từ `docs/research/INFO_SIGNALS_STUDY.md`): ý kiến công khai thường **không vượt được ngẫu nhiên**, nên hệ thống phải nói thẳng
**"chưa đủ mẫu"** thay vì xếp hạng giả. Hệ thống **chỉ đọc**: không đặt lệnh, không sinh văn bản tự do. Hợp đồng API: `services/track-record/CONTRACT.md`.

## 1. Phương pháp

### 1.1 Trích quan điểm có hướng (bằng quy tắc, `extract.py`)
| Nguồn | Quy tắc | Entity |
|---|---|---|
| Tin (`news_items`) | có `sentiment` NLP, **|s| ≥ 0,35**, có `symbols`; tối đa **3 mã/bài**, chỉ mã **có giá D1** (bảng `bars` D1 / `vn_daily` / `vn_index_daily`); s>0 = bullish, s<0 = bearish | mỗi nguồn tin = 1 entity; nhãn trung lập "Luồng tin #n" / "Ngân hàng trung ương #n" / "Báo kinh tế #n" (phân loại theo id nguồn, **id/tên website không bao giờ lộ** ra nhãn hay API) |
| Tín hiệu (`expert_signals`) | `buy`→bullish, `sell`→bearish, bỏ `flat`; `sl` → mức vô hiệu (`invalidation`) | entity = `expert_id`, nhãn = tên hiển thị của chuyên gia |
| COT (`expert_positions`, CFTC) | stance = dấu(noncomm_long − noncomm_short) × `pair_direction` | entity = từng hợp đồng, nhãn "Vị thế đầu cơ — EUR" |

* `entity_id` = `ent:<hash8>` (băm có muối từ khoá nguồn) — ổn định, không đảo ngược được ra tên nguồn.
* **Gộp**: 1 quan điểm / entity / mã / ngày UTC. Nếu trong ngày mâu thuẫn (cả bullish lẫn bearish) → **bỏ cả ngày**. Chỉ ghi sổ các ngày **đã đóng** (ngày quan sát < hôm nay); khoá `ref` = băm(entity, mã, ngày) nên chạy lại không tạo bản sao.
* **Thời điểm**: `published_at` = lúc công bố gốc (tin: bài; COT: **thứ Sáu = as_of + 3 ngày 20:30 UTC**, tuyệt đối không dùng ngày chốt vị thế làm lúc công bố). `observed_at = max(published_at, ingested_at, enriched_at)` — tức **lúc ta thực sự biết quan điểm** (tin chưa có NLP thì chưa là quan điểm). `published_at` thiếu/ở tương lai → dùng `ingested_at`.

### 1.2 Chống look-ahead (`pricing.py`)
* Vào lệnh giả định = **giá MỞ của nến D1 đầu tiên có `ts_open` > `observed_at`** (không bao giờ dùng nến đang chứa thời điểm quan sát).
* Thoát = **giá ĐÓNG** của nến thứ **1 / 5 / 21** tính từ nến vào (kỳ hạn 1D / 1W / 1M). Chưa đủ nến → *pending* (không chấm). Khoảng trống dữ liệu giá >6 ngày → bỏ.
* Lợi suất = ln(đóng/mở); `hit` = hướng đúng (lợi suất × hướng > 0). Mỗi mã dùng **một nguồn giá D1 duy nhất** (nguồn có nhiều nến nhất) để không trộn bảng giá.
* **Chế độ thị trường** (`trend|range|high_vol|low_vol`) tính chỉ từ các nến D1 **đã đóng trước** thời điểm quan sát: vol 20 ngày so với phân phối vol 20 ngày của 1 năm trước (≥ phân vị 75 = high_vol, ≤ 25 = low_vol; còn lại: |t-stat 20 ngày| ≥ 1 = trend, ngược lại range).
* Mã không có giá D1 trực tiếp dùng đại diện (SPX→SPY, NDX→QQQ, XAGUSD→SLV, USOIL→USO, BTCUSD/ETHUSD→cặp USDT). **DXY chưa có giá D1 nên chưa chấm được.**

### 1.3 Chấm điểm (`scoring.py`)
* **Mẫu độc lập**: với mỗi (entity, mã), một quan điểm chỉ được tính nếu nến vào không sớm hơn nến thoát của quan điểm đã tính trước — loại chồng lấn (đặc biệt 1W/1M, và COT hằng tuần). `n` = số quan điểm độc lập đã chấm, `n_total` = tổng quan điểm.
* **Hit-rate** + **khoảng tin cậy Wilson 95%**.
* **Lợi suất TB theo hướng** + KTC **stationary block bootstrap** (Politis–Romano, 1000 lần, khối TB ≈ n^⅓).
* **Kiểm định hoán vị nhãn hướng** (2000 lần, seed cố định ⇒ tái lập): H0 = nhãn hướng không mang thông tin; thống kê = lợi suất TB theo hướng; hoán vị giữ nguyên tỉ lệ mua/bán (nên một chuyên gia luôn "mua" trong thị trường tăng **không** bị tính là có kỹ năng). p một phía.
* **Hiệu chỉnh đa kiểm định Benjamini–Hochberg** trên **toàn họ** (mọi entity × phạm vi × kỳ hạn có n ≥ 30), FDR q = 0,10 → `q_value`.
* **`beats_baseline`** = `rated` **và** q < 0,10 **và** cận dưới Wilson > 0,5 **và** cận dưới bootstrap lợi suất > 0. Cả ba điều kiện cùng lúc.
* **`rated`** chỉ khi n ≥ **30**; dưới đó là `insufficient`: **không có xếp hạng (rank = null)**, không p/q, `weight = 1`, hiển thị "n=…/30".
* **Co Beta (shrinkage)**: `score = 100 × (hits + k·m0)/(n + k)`; m0 = 0,5 + tilt theo loại; k theo loại (analyst 20, central_bank 20, media 30, positioning 30, signal_provider 25, other 30). Tilt tiên nghiệm **tối đa ±0,02** và hiện chỉ **âm nhẹ −0,01** cho tin tức thô (nhiễu cao) và nhà cung cấp tín hiệu (thiên lệch sống sót), các loại khác = 0 — căn cứ `INFO_SIGNALS_STUDY.md` (không có bằng chứng cho tilt dương). Ít bằng chứng ⇒ điểm co về ~50.
* **Trọng số**: `weight = clamp(1 + 6·(post_mean − 0,5), 0,25, 2,0)` khi rated; `1` khi chưa đủ mẫu.
* **Phân rã**: theo `all`, asset class (`forex|metal|index|commodity|crypto|stock_us|stock_vn|etf|bond`), `sym:<MÃ>`, và chế độ thị trường. **Đường equity** "nếu theo ý kiến" (tổng lợi suất log %, không phí) kèm **dải ngẫu nhiên p05/p50/p95** (hoán vị hướng, 400 lần) — đường của chuyên gia nằm trong dải = không phân biệt được với ngẫu nhiên.

### 1.3b Khoá `tr:weights` (tích hợp expert-collector)
Mỗi entity được ghi dưới 3 khoá: `entity_id` (`ent:…`), `expert_id` (vd `CFTC:099741`) và `source:expert_id` (vd `cftc:CFTC:099741`), khớp `expert_collector.trackweights.lookup`. Ánh xạ entity↔expert_id suy ra mỗi vòng chấm từ dữ liệu (nội bộ, không lộ qua API). Nếu nhiều entity cùng một khoá, chọn **trọng số nhỏ nhất** (bảo thủ). Luồng tin không có expert_id nên chỉ có khoá `ent:`. Test hồi quy: `tests/test_keys_contract.py` (nạp trực tiếp `trackweights.py` của expert-collector).

### 1.4 Đồng thuận có trọng số (`consensus.py`)
Mỗi entity chỉ tính quan điểm **mới nhất** trên mỗi mã trong cửa sổ (`window_days`). `net_weighted = (Σw_bull − Σw_bear)/Σw`; `level`: `consensus` khi ≥3 entity và |net_weighted| ≥ 0,6; `weak` khi ≥ 0,3; còn lại `none`. Entity chưa đủ mẫu có w = 1 (như hợp đồng) — nên đồng thuận hiện chủ yếu là **đếm phiếu**, chưa phải đồng thuận của những người đã chứng minh.

### 1.5 Sổ cái bất biến hash-chain (`ledger.py`, `store.py`)
`tr_views` append-only: `hash_i = sha256(prev_hash_i | canonical_json(row_i))`; `seq` tuần tự gán dưới **advisory lock** Postgres; idempotent theo `ref` UNIQUE. Ba lớp bảo vệ: (1) role `ts_trackrec` chỉ INSERT/SELECT trên `tr_views`; (2) trigger BEFORE UPDATE/DELETE/TRUNCATE chặn; (3) `GET /track/chain/verify` duyệt cả chuỗi — **superuser vô hiệu hoá trigger rồi sửa 1 dòng vẫn bị phát hiện** (kiểm chứng tự động, xem §5). Lưu ý: chuỗi chứng minh *không sửa lịch sử sau khi ghi*, **không** chứng minh thời điểm ghi đúng cho phần backfill (xem §3).

## 2. Cách đọc kết quả
* Bảng xếp hạng (`/v1/experts/leaderboard`): đọc **`status` trước**. `insufficient` = chưa đủ bằng chứng — đừng suy diễn từ hit-rate hay điểm.
* `score` ≈ 50 là mặc định "không biết"; chỉ ý nghĩa khi `rated`. `beats_baseline = true` mới là bằng chứng (sau hiệu chỉnh đa kiểm định) rằng ý kiến vượt hướng ngẫu nhiên.
* Số `summary.expected_false_positives` = q × số entity vượt baseline (số dương tính giả kỳ vọng khi FDR đúng); `uncorrected_expected_false_positives` = 0,05 × số kiểm định (số "vượt" sẽ thấy nếu KHÔNG hiệu chỉnh) — cho thấy vì sao top bảng không hiệu chỉnh là vô nghĩa.
* Hit-rate cao nhưng p lớn là bình thường: hit đếm đúng/sai, p đo **lợi suất TB** (vài lệnh thua lớn có thể xoá hết).
* Trang chi tiết: `by_regime` cho biết hiệu quả chỉ nằm ở một chế độ nào đó (cẩn thận: chia nhỏ thì mẫu mỏng), `rolling` cho thấy hit-rate tích luỹ hội tụ về đâu, `equity` so với dải ngẫu nhiên.

## 3. Hạn chế trung thực
* **Dữ liệu mỏng**: tin có sentiment chủ yếu từ 2026-10; COT hằng tuần từ 2023-09 (~158 tuần/hợp đồng) là nguồn duy nhất đủ n. Hầu hết luồng tin sẽ ở `insufficient` nhiều tuần.
* **Sentiment của bài tin ≠ quan điểm về mã**: bài tích cực gắn nhiều mã không có nghĩa tác giả bullish từng mã; NLP có sai số. Entity tin là *luồng tin*, không phải một người.
* **Backfill không chứng minh thời gian thực**: COT quá khứ được ghi sổ muộn (có `recorded_at`); độ tin cậy về *thời điểm công bố* dựa vào quy tắc lịch (thứ Sáu 20:30 UTC), không phải bằng chứng ghi nhận lúc đó. Chỉ quan điểm ghi sau ngày triển khai mới có dấu thời gian ghi nhận đáng tin.
* **1W/1M chồng lấn** giữa các mã khác nhau (chỉ độc lập trong từng mã) → p-value có thể lạc quan khi gộp nhiều mã; BH giả định phụ thuộc dương nhẹ, họ kiểm định ở đây chồng lấn (all ⊃ class ⊃ sym) nên mang tính tham khảo.
* **Không có phí/spread/trượt giá**; vào theo giá mở D1 kế tiếp (có thể xa giá lúc công bố, nhất là với tin tức); giá FX D1 của một số nguồn là giá tham chiếu cuối ngày.
* **Thiên lệch sống sót**: chỉ theo dõi nguồn đang được thu thập; nguồn đã biến mất không có trong bảng.
* **Chế độ thị trường** chỉ là nhãn quy tắc từ D1, không phải mô hình trạng thái thật sự; chia theo chế độ làm mẫu rất mỏng.
* Kiểm định hoán vị với COT (vị thế bền, tự tương quan) bẻ gãy tự tương quan nên có thể hơi lạc quan.
* Dữ liệu QA cũ (`qa-expert-*`, mã `QAUSD` không có giá) vẫn nằm trong sổ cái vì sổ cái không xoá được; chúng không bao giờ được chấm.

## 4. Vận hành
* Service: `track-record` (compose `docker-compose.tools.yml`, mạng backend+ops, không publish cổng, read_only, cap_drop ALL, mem 512m). Chỉ api-gateway gọi nội bộ (`/v1/experts/*`), chỉ GET.
* Khởi tạo một lần: `infra/db/create_trackrec_role.sh` (migration `016_track_record.sql` + role `ts_trackrec` + `POSTGRES_TRACKREC_PASSWORD`), `DEFAULT_OFF=1 infra/ops/redis_acl_render.sh` rồi `redis-cli --user ts_admin ACL LOAD` (thêm user `ts_trackrec` chỉ key `tr:*`), `deploy.sh "up -d --build track-record"`.
* Lịch: chấm lại mỗi `TRACKREC_INTERVAL_S` (900 s = 15 phút): trích quan điểm → ghi sổ ngày đã đóng → lấy giá → kết quả (`tr_outcomes`) → thẻ điểm (`tr_scorecards`) → `tr_runs`; ghi Redis `tr:weights` (hash `entity_id → {"w","score","n","status","hit","beats"}`, kèm `tr:weights:ts`) cho expert-collector đọc; một lần chạy ~30 s.
* Metrics Prometheus (job `track-record`): `trackrec_views_total{basis}`, `trackrec_entities{status}`, `trackrec_rated_beating_baseline`, `trackrec_last_scoring_timestamp`, `trackrec_chain_verified`, `trackrec_scoring_seconds`. Nên cảnh báo khi `trackrec_chain_verified == 0` hoặc `time() - trackrec_last_scoring_timestamp > 3600`.
* Khi chuỗi hash hỏng: **không** sửa tay; điều tra (backup DB), `verify` trả `first_bad_seq` + `reason`.
* Test: `sh infra/ops/run_tests.sh track-record` (26 test, tổng hợp, không cần mạng). Test ledger trên Postgres thật (superuser sửa trực tiếp) cần `TRACKREC_TEST_DSN` (schema tạm `trtest`, tự xoá).

## 5. Kiểm chứng
Test thống kê (`services/track-record/tests`): chuyên gia ngẫu nhiên (3 họ × 25 entity × n=80) có tỉ lệ vượt baseline ≤ q sau BH (thực tế 0); chuyên gia 62% đúng, n=200 → `rated`, `beats_baseline`, xếp hạng 1; thay đổi giá sau nến thoát không đổi lợi suất, nến chứa `observed_at` không bao giờ là nến vào, chế độ thị trường không dùng nến chưa đóng; n<30 → `insufficient`, rank null, weight 1; sửa trực tiếp 1 dòng sổ cái (kể cả bằng superuser trên Postgres thật) làm `verify` báo hỏng; nhãn/API không chứa tên nguồn.

## 6. Số liệu ban đầu thực (backfill 2026-10-12, VPS <VPS_IP>)
Xem mục "Kết quả backfill" ngay dưới (cập nhật theo lần chạy đầu).

### Kết quả backfill
* Sổ cái: **1998 quan điểm** (COT 1900, tin 95, tín hiệu QA 3), **42 entity** (12 hợp đồng COT, 27 luồng tin, 3 mục QA), hash-chain hợp lệ; 5151 kết quả đã chấm (360 ô còn *pending*, 483 ô chưa có giá).
* **11 entity `rated`** (đều là hợp đồng COT; n ≈ 154–158 ở 1D/1W, 36 ở 1M); **31 `insufficient`** (toàn bộ luồng tin + tín hiệu + DXY).
* **Không entity nào vượt baseline** (`beats_baseline = 0/99` kiểm định; không hiệu chỉnh sẽ kỳ vọng ~5 dương tính giả/99). Hit-rate COT 1W: 40–58% (XAU 58%, SPX 40%), p nhỏ nhất ≈ 0,11, q = 1,0. Phù hợp kết luận của `INFO_SIGNALS_STUDY.md` (COT không cho tín hiệu hướng dùng được).
* Đồng thuận 90 ngày: 42 mã, một số `consensus` chỉ do đếm phiếu (entity chưa đủ mẫu w = 1) — **không** phải bằng chứng.
