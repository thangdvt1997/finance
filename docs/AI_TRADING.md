# AI_TRADING — Tab "AI Trading": nền để thử, đo và ghi lại mọi phương pháp giao dịch (2026-10-15)

> CHỈ nghiên cứu / paper / thông báo. KHÔNG có đường đặt lệnh thật. Trung thực là yêu cầu số 1: tab hiển thị kết quả thật, kể cả âm. Giao việc: `docs/handoff/TASK_ai_trading_tab.md`; tiến độ: `docs/handoff/PROGRESS.md`.
> Ghi chú về trạng thái tài liệu: service `ai-trading` (A1) và trang UI (A2) do agent khác xây song song; các mục "kiến trúc/API/YAML" dưới đây là THIẾT KẾ đã chốt trong nhiệm vụ. Khi A1/A2 xong, đối chiếu lại tên đường dẫn/ trường với `services/ai-trading/README.md` và sửa tại đây nếu lệch.

## 1. Mục tiêu và ràng buộc

**Mục tiêu.** Một chỗ duy nhất để (a) xem mọi chiến lược/mô hình đã thử cùng kết quả backtest và forward-paper, (b) thêm phương pháp mới mà không viết code (YAML + ảnh mẫu), (c) chạy backtest trung thực một bấm, (d) lưu backlog ý tưởng AI trading và trạng thái từng ý tưởng. Tab không hứa lợi nhuận: nó là máy đo.

**Ràng buộc cứng (STANDING).**
| Ràng buộc | Nghĩa cụ thể |
|---|---|
| READ-ONLY + PAPER | Không `order_send`/`OrderSend`/lệnh thật. Có test quét tĩnh (AST) trong pytest của service; tab chỉ sinh tín hiệu, thông báo, lệnh giả vào sổ paper. Không thêm công cụ gọi broker cho LLM. |
| Cổng pháp lý G1-G3 | Chuyển sang giao dịch thật chỉ sau G1-G3 + duyệt người dùng + control plane (`CONTROL_PLANE_DESIGN.md`: risk engine tất định, kill-switch 4 tầng, 4-eyes, paper-shadow bắt buộc). Tab AI không bao giờ tự nâng bậc. |
| Gói 0 đồng | Chỉ OSS và nguồn miễn phí (`FREE_STACK.md`); mô hình chạy cục bộ (CPU; llama.cpp/Qwen đã có). Không SaaS trả phí, không API LLM trả phí. |
| Trung thực số 1 | Mọi kết quả kèm n, CI95, so với baseline ngẫu nhiên, chi phí thật, snapshot sha; kết quả âm hiển thị nổi bật; không chọn lọc ví dụ đẹp; thống kê đa so sánh phải khai báo số lần thử. |
| UI không hiện tên nguồn dữ liệu | Theo `UI_NO_SOURCES.md`. Tên thư viện/bài báo ở tài liệu docs này là tham khảo kỹ thuật, KHÔNG đưa lên UI. |
| Ranh giới VPS | Chỉ tài nguyên `tradingsys` và `/root/mtlab`; dữ liệu lịch sử lớn ở `data/research/patterns/` (không vào git). |

**Điểm xuất phát thật (không làm đẹp).** Kịch bản Sell KB-1..KB-4 (`PATTERNS_SELL.md`, `research/PATTERN_SELL_BACKTEST.md`): walk-forward 8.290 lệnh −0,100 R/lệnh (CI95 [−0,124; −0,073]), trước phí +0,012 R; Deflated Sharpe 0, PBO 0,86; TEST khoá chạy đúng 1 lần: 433 lệnh −0,263 R/lệnh (CI [−0,375; −0,152]), kém cả ngẫu nhiên (p = 0,97). Trend/carry/mean-reversion cổ điển trên FX: không qua kiểm định (`STRATEGY_OPTIONS.md`); ý kiến chuyên gia: 0/99 vượt baseline (`EXPERT_TRACKRECORD.md`). Thẻ KB-1..4 trên tab mang trạng thái `no_edge` (không phải "chưa chạy").

## 2. Kiến trúc

### 2.1 Thành phần
```
web-ui  #/ai-trading (master)        client-ui  #/ai-trading (bản rút gọn, read-only)
        \                                  /
         api-gateway  /v1/ai-trading/*  (phân quyền: master xem tất cả; client chỉ phần được phép, ép audience=client)
                         |
                 services/ai-trading  (FastAPI nội bộ; đọc registry YAML; hàng đợi job nền; role DB hẹp)
        +----------------+------------------+------------------+
 pattern-engine/scan   pattern-research   paper-trader/        llama.cpp (Qwen)
 (tín hiệu, ảnh)       (backtest, snapshot, track-record       (AI analyst, sau)
                        walk-forward)      (sổ hash-chain)
```
Tái dùng, không viết lại: `pattern-engine` (detector + `spec/*.yaml`), `pattern-render` (ảnh), `pattern-scan` (quét live, paper, sổ cái hash-chain `pattern_paper_ledger`), `pattern-research` (khớp lệnh bi quan, walk-forward, baseline, PBO/DSR, test khoá), `track-record` (chấm uy tín chuyên gia), `briefing` (hậu kiểm tất định).

### 2.2 API `/v1/ai-trading/*` (qua api-gateway, GET trừ job)
| Đường dẫn (thiết kế) | Nội dung | Quyền |
|---|---|---|
| `GET /v1/ai-trading/strategies` | thẻ chiến lược/mô hình: id, tên, loại (`pattern`/`ml`/`llm`/`rl`/`consensus`), trạng thái (`research`/`paper`/`paused`/`no_edge`), tóm tắt số liệu, cảnh báo | master đủ; client bản rút gọn |
| `GET /v1/ai-trading/strategies/{id}` | chi tiết: tham số, kết quả walk-forward/test/forward-paper, ảnh (đường vốn, DD, heatmap), tải sổ lệnh CSV | master; client chỉ thẻ được đánh dấu công khai |
| `GET /v1/ai-trading/arena` | bảng xếp hạng paper cùng điều kiện (giai đoạn D) | master |
| `GET /v1/ai-trading/lab` | thí nghiệm đã chạy: tham số, snapshot sha, kết quả, lệnh tái lập | master |
| `GET /v1/ai-trading/backlog` | ý tưởng + trạng thái (mục 5) | master |
| `POST /v1/ai-trading/jobs` / `GET .../jobs/{id}` | job nền (giai đoạn B): detector thử, golden test, backtest trung thực; có timeout | chỉ master, CSRF |
Gateway cache ngắn (10–300 s) cho GET; mọi tham số validate; không có đường nào nhận lệnh giao dịch. Test e2e: IDOR/phân quyền, không lộ tên nguồn, quét tĩnh `order_send`/`OrderSend`.

### 2.3 Registry YAML (thêm chiến lược KHÔNG cần code)
Mỗi chiến lược là một tệp YAML trong thư mục registry của service (thiết kế: `services/ai-trading/registry/<id>.yaml`); service nạp lúc khởi động/gọi lại (reload). Dạng tối thiểu:
```yaml
id: KB-2
kind: pattern                 # pattern | ml | llm | rl | consensus
name: "KB-2: giảm - hồi ~50% - nêm - nhấn chìm"
status: no_edge               # research | paper | paused | no_edge
side: sell
spec_ref: services/pattern-engine/spec/kb2.yaml     # kind=pattern: dùng lại đặc tả detector
examples: [fixtures/kb2_anh1.png]                   # ảnh mẫu (vào repo, nhỏ)
results:
  walk_forward: {n: 1687, e_r: -0.179, ci95: [-0.240, -0.109], baseline_e_r: -0.128, p: 0.96}
  test_locked: {opened: true}        # đã mở -> KHOÁ VĨNH VIỄN cho kịch bản này
  report: docs/research/PATTERN_SELL_BACKTEST.md
warnings: ["Không có edge sau chi phí; chỉ dùng như mô tả cấu trúc."]
public_client: true
```
Kết quả trong YAML chỉ là bản chép số kèm `report:` trỏ tới tài liệu/artefact gốc; trường được job sinh ra thì ghi từ `wf_report.json`, không gõ tay khi có thể. Giá trị số trong thẻ phải khớp tài liệu gốc (test đối chiếu).

### 2.4 Định dạng một kịch bản nến mới (kind: pattern)
Một kịch bản = (1) **đặc tả detector** YAML cùng định dạng `services/pattern-engine/spec/kbN.yaml`: `id`, `name`, `side`, `summary`, `steps` (checklist đánh số), `invalidation`, `params` (mọi ngưỡng chuẩn hoá theo ATR14 hoặc độ dài sóng), `levels` (SL/TP gợi ý); phần dùng chung ở `spec/common.yaml` (swing ZigZag ATR đa thang, sóng dẫn, nhấn chìm, cụm nén); (2) **ảnh mẫu** (PNG, nên 2–3 ảnh) kèm ánh xạ giờ ảnh→UTC trong README fixture; (3) **golden test**: nến fixture + nến kích hoạt kỳ vọng đọc từ ảnh (`tests/fixtures/`, `tests/test_golden.py`). Quy trình thêm:
1. Viết YAML detector + đặt ảnh mẫu; nếu cần khối hình mới (vd. nêm, vai-đầu-vai) mới phải thêm code vào engine — còn lại chỉ đổi tham số.
2. Chạy detector thử trên dữ liệu (job B): xem số tín hiệu, ảnh render, so với golden.
3. Chỉ nến ĐÃ ĐÓNG, không look-ahead, không repaint (kiểm bằng `test_no_lookahead.py`); mỗi (setup_id, symbol, tf, state) phát 1 lần.
4. Backtest trung thực (mục 6). **Kịch bản mới có tập TEST khoá RIÊNG** (cắt thời gian sau ngày đóng băng của kịch bản, hoặc tập mã/khung mới); KHÔNG tái dùng test khoá của kịch bản đã mở.
5. Ghi YAML registry (`status: research`), chạy forward-paper rồi mới xem xét `paper`.
Cảnh báo bắt buộc: hiệu chỉnh theo vài ảnh mẫu là overfit nhỏ-mẫu (xem `PATTERNS_SELL.md` mục 4; backtest cho thấy bộ tham số GỐC không tệ hơn bộ đã hiệu chỉnh). Mọi điều chỉnh sau golden phải được liệt kê.

### 2.5 Cách thêm một mô hình (kind: ml/llm/rl/consensus)
- **ml** (meta-labeling, regime, dự báo): YAML khai `features` (danh sách tên đặc trưng từ thư viện đặc trưng; mục 4.8), `label` (triple-barrier hay nhãn thắng/thua của tín hiệu ứng viên), `model` (`logistic`|`gbm`|`onnx:<tệp>`), `cv` (purged k-fold + embargo), `split` (tham chiếu snapshot + splits.json), `candidates` (id chiến lược nguồn tín hiệu). Mô hình huấn luyện ngoài tab (job nền) xuất ONNX vào thư mục artefact trên VPS; tab chỉ nạp ONNX để suy luận (CPU), không nạp pickle không rõ nguồn.
- **llm**: YAML khai prompt mẫu, nguồn ngữ cảnh (tin/lịch/COT/kỹ thuật), schema đầu ra có trích dẫn, bước hậu kiểm tất định (số liệu phải khớp dữ liệu; câu không có trích dẫn bị loại). Không công cụ, không URL, không ra lệnh.
- **rl**: môi trường mô phỏng paper có chi phí thật; chỉ prototype nghiên cứu; không bao giờ nối vào paper chính thức nếu chưa qua cùng bộ kiểm định.
- **consensus**: dùng `track-record` làm bộ lọc/đặc trưng; chỉ khi `beats_baseline` (hiện 0/99) mới có trọng số > 1.
Mọi mô hình bắt buộc có baseline đối chứng (ngẫu nhiên cùng điều kiện, và "luôn vào" không lọc) trước khi được gắn nhãn `paper`.

### 2.6 Dạy kịch bản mới (giai đoạn B): nạp YAML + ảnh -> detector thử -> backtest nền -> test khoá riêng
Khung này cho phép thử một ý tưởng nến/sóng KHÔNG cần viết mã. Kịch bản là YAML **khai báo luật** (AND) trên nến đã đóng; worker chạy bằng detector vector hoá (`services/ai-trading-worker/src/ai_trading_worker/dsl.py`, không look-ahead, có test cắt cụt). Mẫu chạy được: `services/ai-trading/examples/SC-DEMO-1.yaml` (không có edge, chỉ để chứng minh luồng).

**Cách thêm (UI):** tab "Kịch bản nến & sóng" -> khung "Dạy kịch bản mới": dán/nạp YAML, chọn tối đa 5 ảnh mẫu (png/jpg/webp, mỗi ảnh <= 700 KB; UI tự gắn `images:`), bấm "Kiểm tra & lưu". Sau đó thẻ kịch bản (nhãn "Nghiên cứu", nguồn: người dùng nạp) có khung "Quy trình trung thực" với 3 bước: (1) Detector thử + golden, (2) Backtest nền, (3) Mở test khoá. Bước 1-2 chạy được nhiều lần cho id khác nhau; bước 3 chỉ sau khi bước 2 xong và phải gõ lại id để xác nhận.

**Cách thêm (API, chỉ master + Origin + CSRF):** `POST /v1/ai-trading/scenarios {yaml, images:{ten.png: base64}}` (body <= 6 MB) -> 201; `POST /v1/ai-trading/scenarios/{id}/jobs {type: detector_test|backtest|final_test, confirm: <id>}` -> 202 (409 nếu đã có job của kịch bản / test đã mở, 429 nếu hàng đợi > 3); `GET /v1/ai-trading/jobs/{jid}`, `GET .../scenarios/{id}/jobs`, `GET .../scenarios/{id}/images/{ten}`, `GET /v1/ai-trading/ledger.csv?strategy=<id>&source=backtest_dev|backtest_test`.

**Schema YAML** (`ai_trading/scenario_schema.py`, mọi số có biên, khoá lạ bị từ chối, cấm anchor/alias, <= 16 KB):
```yaml
id: SC-MY-1              # 3-32 ký tự; KHÔNG trùng id có sẵn; sửa luật = id mới (family giữ để DSR trừ đúng số lần thử)
name: "..."; summary: "..."; side: sell     # hiện chỉ sell (mô phỏng paper)
family: SC-MY            # tuỳ chọn; mặc định = id
symbols: [EURUSD]        # <= 4 mã;  tfs: [H1]  (M15|H1|H4|D1)
detector:
  cooldown_bars: 8
  rules:                 # 1..8 luật, AND
    - {rule: move_atr, dir: up|down, bars: 6, min: 2.0, ago: 0}   # biến động >= min ATR trong `bars` nến, kết thúc `ago` nến trước
    - {rule: bear_body, min_atr: 0.3}      # nến giảm thân dài
    - {rule: bear_engulf}                  # giảm nhấn chìm thân nến trước
    - {rule: upper_wick, min_ratio: 0.4}   # bóng trên / biên độ
    - {rule: break_low, bars: 10}          # đóng cửa thủng đáy N nến trước
    - {rule: ma, side: above|below, kind: ema|sma, period: 50}
    - {rule: rsi, period: 14, op: ">="|"<=", value: 60}
    - {rule: hours, from: 7, to: 16}       # giờ mở nến UTC
levels:
  sl: {type: swing_high, bars: 6, buffer_atr: [0.25, 0.5]}   # hoặc {type: atr, mult: [1.0, 1.5]}
  tp_r: [1.0, 2.0]       # lưới (tp_r x tham số SL) <= 12 cấu hình
  max_hold: 60
golden:                  # tuỳ chọn, <= 5: nến PHẢI (expect: true) / KHÔNG (false) kích hoạt, sai lệch +-1 nến; bar_ts = giờ mở nến UTC, TRƯỚC vùng test khoá
  - {symbol: EURUSD, tf: H1, bar_ts: "2024-08-23T18:00", expect: true, image: mau1.png}
images: [mau1.png]
```
Vào lệnh Sell ở giá mở nến kế tiếp tín hiệu; mỗi (mã, khung) chỉ giữ 1 vị thế tại một thời điểm. Nếu cần khối hình học mới ngoài các luật trên (nêm, vai-đầu-vai...) thì thêm luật vào `dsl.py` + `scenario_schema.py` (kèm test) — không nhận mã từ người dùng. **Ảnh mẫu chỉ để đối chiếu mắt người** (hệ thống không nhận dạng ảnh); đối chiếu máy dùng `golden` theo thời điểm nến.

**Backtest trung thực (job `backtest`, `ai-trading-worker`):** snapshot sha của dữ liệu dev (băm nội dung OHLC của phần < ngày test) -> phát hiện -> mô phỏng lưới tham số với chi phí thật (spread theo nến + trượt + phí, SL theo ASK, cùng nến chạm SL và TP tính SL) -> walk-forward theo năm 2008-2024 + 2025H1 + VAL (tham số mỗi fold chỉ chọn bằng lệnh ĐÃ ĐÓNG trước đầu fold; < 30 lệnh IS dùng cấu hình đầu lưới) -> baseline vào lệnh ngẫu nhiên cùng điều kiện (p), bootstrap CI95, DSR (n_trials = lưới x số kịch bản cùng family), PBO (CSCV theo quý), kỳ vọng trước chi phí. Dùng lại `pattern_research/backtest.py` (cùng mô phỏng với KB-1..4). Kết quả ghi `result.json` của kịch bản -> thẻ tự cập nhật (verdict: `edge` chỉ khi test khoá CI95 > 0 và p < 0,05 và DSR >= 0,95 và PBO < 0,5; `no_edge` nếu kỳ vọng <= 0; còn lại `unproven`).

**Test khoá RIÊNG cho mỗi id (job `final_test`):** chỉ nhận khi dev xong + body `confirm` == id; worker tạo `test_opened.json` bằng `O_EXCL` (một lần duy nhất, kể cả khi job sau đó lỗi), ghi `test_access.log`, kiểm snapshot sha dev trùng lúc chạy dev (khác -> không đánh giá, vẫn tính là đã mở), đánh giá đúng 1 cấu hình đã chốt trên dữ liệu từ ngày test (`splits.json`: 2026-03-11). Sau khi mở: không chạy lại backtest dev, không mở lại test. KB-1..4 giữ nguyên test khoá của chúng (worker chỉ đọc dữ liệu :ro và không ghi `data/research/patterns/test_access.log`). Lưu ý trung thực: giai đoạn test dùng chung mốc thời gian với KB-1..4 vì dữ liệu chung; ý nghĩa "riêng" là khoá riêng theo kịch bản, mỗi kịch bản đã chốt luật trước khi xem test, nhưng người dùng đã thấy kết quả test của kịch bản khác — nên DSR/PBO và số lần thử trong family được hiển thị.

**Vận hành/giới hạn:** worker là container riêng `tradingsys-ai-trading-worker` (`network_mode: none`, dữ liệu :ro, chỉ ghi `data/ai-trading/`, 3 GB RAM, 1,5 CPU, `nice 15`), chạy 1 job/lần theo hàng đợi file `data/ai-trading/jobs/*.json` (queued -> running -> done|failed; timeout cứng 25 phút -> failed `error: timeout`, kill cả nhóm tiến trình; worker khởi động lại giữa chừng -> job đang chạy thành failed `worker_restart`). Luật quá lỏng (> 40000 tín hiệu dev) bị từ chối. Trạng thái lưu ở `data/ai-trading/{scenarios,jobs}` (không vào git, ACL uid 10001). Kịch bản người dùng nạp KHÔNG hiện cho client (lọc ở service + gateway).

**An toàn nạp tệp:** YAML `safe_load` + cấm anchor/alias + giới hạn 16 KB; ảnh: base64 nghiêm ngặt, magic bytes phải khớp đuôi, <= 700 KB, tối đa 5, tên `^[A-Za-z0-9][A-Za-z0-9_-]{0,58}\.(png|jpg|jpeg|webp)$` (không `/`, không `..`; SVG bị từ chối); phục vụ lại với `nosniff` + CSP `sandbox`; không có tham số đường dẫn nào lấy từ người dùng.

## 3. Trạng thái

### 3.1 Giai đoạn
| GĐ | Nội dung | Trạng thái (2026-10-15) |
|---|---|---|
| A | Khung tab + API + thẻ + tích hợp pattern hiện có + hiển thị kết quả backtest thật | ĐANG LÀM (A1 service+registry+gateway; A2 UI master/client; A3 tài liệu này) |
| B | Khung "Dạy kịch bản mới": nạp YAML+ảnh, detector thử, golden test, backtest nền một bấm | XONG (mục 2.6; `ai-trading-worker`; kịch bản mẫu SC-DEMO-1) |
| C | Meta-labeling ML + LLM analyst + regime | Chưa bắt đầu |
| D | Arena paper + prototype RL | D1 (arena + guardrail + hash-chain) XONG, mục 3.3; RL prototype chưa làm |

### 3.2 Module 1–9 (theo nhiệm vụ)
| # | Module | Nền đã có | Trạng thái |
|---|---|---|---|
| 1 | Tổng quan/thẻ chiến lược, arena | số liệu KB-1..4, paper-trader | A: thẻ; D1: arena (mục 3.3) |
| 2 | Kịch bản nến & sóng (+ "Dạy kịch bản mới") | pattern-engine/scan/render, trang `#/kich-ban`, thư viện ví dụ | Tích hợp ở A; "Dạy" ở B. KB-1..4: ĐÃ backtest, `no_edge` |
| 3 | Mô hình AI tín hiệu (meta-labeling, regime, dự báo) | dữ liệu MT5 152 mã × 21 khung, khung pattern-research | C — chưa làm |
| 4 | LLM phân tích cục bộ | llama.cpp/Qwen, `briefing` có hậu kiểm | C — chưa làm |
| 5 | Đồng thuận & chuyên gia | `track-record` (0/99 vượt baseline) | A hiển thị; dùng làm đặc trưng ở C |
| 6 | RL/tối ưu (nghiên cứu) | — | D — chỉ khảo sát (mục 4) |
| 7 | Quản trị rủi ro & guardrail | paper-trader, sổ hash-chain, risk-monitor, cửa sổ tin | D1 XONG (mục 3.3): cỡ vị thế ATR/risk%, lỗ ngày, cửa sổ tin, kill-switch master, hash-chain có neo |
| 8 | Lab (thí nghiệm + backlog) | artefact backtest, snapshot sha | A: liệt kê KB; mở rộng B |
| 9 | Ghi chú pháp lý | `CONTROL_PLANE_DESIGN.md` | A (văn bản cố định trên tab) |
Dừng theo chỉ đạo 2026-10-14: không chạy thêm backtest/huấn luyện KB-1..4; TEST khoá của KB-1..4 đã mở một lần và giữ nguyên.

### 3.3 D1: arena paper + guardrail rủi ro + hash-chain sổ paper (2026-10-15)
**Arena** (`GET /v1/ai-trading/arena`, tab Tổng quan; client cũng xem được): nguồn `pattern-scan /scan/trades/r` (lệnh LIVE đã đóng, bỏ replay) + `paper-trader /paper/overview` (tài khoản danh mục đối chứng, KHÔNG xếp hạng). Mỗi kịch bản KB-* một dòng (kể cả khi 0 lệnh): tổng R, số lệnh, kỳ vọng + CI95 (phân phối t), sụt vốn tối đa (R), p một phía đổi dấu (H0: kỳ vọng 0; chính xác khi n<=16, Monte Carlo seed cố định khi lớn hơn). Chỉ xếp hạng khi n >= 30 (`min_n`); dưới ngưỡng gắn nhãn "chưa đủ mẫu", `rank=null`. Khi chưa có lệnh nào: `note` giải thích, UI hiện trạng thái rỗng + bảng 0 lệnh. Mã: `services/ai-trading/src/ai_trading/arena.py`.

**Guardrail** (`pattern_scan/guardrail.py`, áp cho tín hiệu paper LIVE mới ngay trước khi mở lệnh; repair/backfill cũng qua cùng cổng, không lách được). Thứ tự: kill-switch -> lỗ ngày -> cửa sổ tin -> cỡ vị thế.
- Cỡ vị thế: `units = equity x risk% / (|entry-sl| hoặc ATR x atr_mult)`, làm tròn XUỐNG theo bước lot, trần cứng `max_risk_pct`; bảng thử 16 ô (ATR x risk%) trả về trong `/guardrail` và hiển thị ở tab. Quyết định ghi vào bản ghi `open` của sổ cái (`content.guard`, nằm trong hash).
- Lỗ ngày: tổng R đã đóng trong ngày UTC (bỏ replay) <= -`max_daily_loss_r` (mặc định 3R) -> chặn tới hết ngày.
- Cửa sổ tin: `tscommon.risk_windows` + `calendar_events` (impact=high), cùng logic với `/v1/risk-windows`.
- Kill-switch: cờ Redis `aitrading:killswitch` (JSON {on,by,at,reason}); CHỈ master ghi qua `POST /v1/ai-trading/guardrail/killswitch` (master + Origin + CSRF; nginx whitelist riêng); pattern-scan chỉ đọc. Mặc định: không có cờ = tắt, guardrail BẬT cho sổ paper (cấu hình `guardrail.enabled`). Cờ hỏng -> coi như BẬT (an toàn). Redis/lịch tin lỗi -> cho qua + hiện "nguồn phụ suy giảm" (đây là paper).
- Cấu hình: khoá `guardrail:` trong `pattern-scan.example.yaml` (`equity, risk_pct, max_risk_pct, atr_mult, lot_step, max_daily_loss_r, news_window, enabled`).
- Bộ đếm/danh sách tín hiệu bị chặn nằm trong RAM của pattern-scan (mất khi restart; Prometheus `pattern_scan_paper_trades_total{action="blocked_*"}`). Giới hạn: chưa có chu trình tự dừng theo drawdown cho sổ pattern (paper-trader có kill-switch riêng theo tài khoản).

**Hash-chain sổ paper**: bảng `pattern_paper_ledger` (mỗi bản ghi chứa `prev_hash` + `hash = sha256(prev|kind|ref|nội dung chuẩn hoá)`; ghi trong cùng giao dịch với lệnh). `GET /v1/ai-trading/ledger/verify` (master) tính lại toàn chuỗi; phát hiện SỬA nội dung, XOÁ/CHÈN giữa chuỗi (đứt prev_hash/seq). Cắt đuôi hoặc viết lại toàn chuỗi cần NEO NGOÀI DB: ai-trading lưu `{n, hash}` ở Redis `aitrading:ledger_anchor` (chỉ tiến lên khi chuỗi hợp lệ) và truyền vào verify. Tab "Rủi ro & guardrail" hiện "chuỗi toàn vẹn ✓/✗" + số bản ghi + đầu chuỗi + có neo hay chưa. Giới hạn: kẻ có quyền ghi cả Postgres lẫn Redis vẫn viết lại được; neo off-site chưa có (xem hạng mục backup off-site).

**Test**: `pattern-scan/tests/test_guardrail.py` (cỡ vị thế, lỗ ngày, tin, kill-switch, repair không lách, sửa/xoá/chèn/cắt đuôi/viết lại có neo, endpoint), `ai-trading/tests/test_d1.py` (arena rỗng/ngưỡng/p, kill-switch, neo), `api-gateway/tests/test_ai_trading_proxy.py::test_d1_*` (master-only, CSRF, Origin, client/analyst 403), quét tĩnh không `order_send` ở cả hai service. QA ảnh UI: `sh services/web-ui/qa/run_ai_trading.sh master real`.

## 4. Khảo sát ý tưởng AI trading miễn phí/OSS

Phương pháp: tổng hợp từ văn liệu quen thuộc (không tra cứu trực tuyến ở đợt này; cần kiểm lại phiên bản/giấy phép trước khi cài). Tham khảo kỹ thuật, KHÔNG đưa tên lên UI. Kết luận chung đồng thuận với `STRATEGY_OPTIONS.md`: edge hiếm, retail CFD phần lớn lỗ, alpha công bố giảm mạnh.

### 4.1 Meta-labeling và khung AFML (López de Prado)
Ý tưởng: tín hiệu gốc (ở đây KB-1..4) quyết định HƯỚNG; mô hình nhị phân thứ hai quyết định CÓ VÀO hay không (và cỡ lệnh) dựa trên đặc trưng. Công cụ chống tự lừa: nhãn triple-barrier (SL/TP/hết giờ, khớp đúng cơ chế khớp lệnh của ta), **purged k-fold + embargo** (loại mẫu chồng thời gian giữa train/test), trọng số mẫu theo độ độc nhất (nhiều tín hiệu chồng nhau), **Deflated Sharpe** (đã có), **PBO/CSCV** (đã có). Đây là hướng hợp lý đầu tiên: không cần phát hiện tín hiệu mới, chỉ hỏi "lọc có cứu được −0,10 R không". Rủi ro: lọc trên 8.290 lệnh với −0,10 R trung bình; nếu không có thông tin trong đặc trưng thì lọc chỉ khớp nhiễu — phải báo âm nếu vậy. Chi phí: CPU, giờ. Thư viện OSS: scikit-learn, LightGBM/XGBoost, `mlfinlab` (bản đóng gói có giới hạn giấy phép — ưu tiên tự cài purged CV vài chục dòng thay vì dùng gói thương mại), `skfolio`/`timeseriescv`.

### 4.2 GBM và ONNX
LightGBM/XGBoost/sklearn HistGradientBoosting là chuẩn thực dụng cho đặc trưng dạng bảng; huấn luyện CPU vài phút. Xuất ONNX (`onnxmltools`, `skl2onnx`) và suy luận bằng `onnxruntime` CPU để tách huấn luyện khỏi service chạy, không phụ thuộc pickle. Lưu ý giấy phép (đa số MIT/Apache) và độ lệch số khi chuyển ONNX (kiểm khớp đầu ra trên tập mẫu). Rủi ro chính: rò rỉ thời gian trong đặc trưng/nhãn; quá khớp siêu tham số — dùng lưới nhỏ, đếm số lần thử cho DSR.

### 4.3 Regime (HMM, clustering)
HMM Gauss 2–3 trạng thái trên lợi suất/biến động (`hmmlearn`), hoặc clustering (k-means/GMM) trên đặc trưng vol/xu hướng; dùng như đặc trưng hoặc công tắc (tắt chiến lược trong regime xấu). Tài liệu đã có bộ lọc regime D1 trong track-record (`trend|range|high_vol|low_vol`, tính chỉ từ nến đã đóng). Rủi ro: nhãn regime thường chỉ rõ SAU sự kiện (smoothing look-ahead) — chỉ dùng xác suất lọc (filtered), không dùng Viterbi toàn chuỗi; số trạng thái chọn theo BIC là một bậc tự do.

### 4.4 LSTM/TCN nhỏ
Chuỗi lợi suất/ATR chuẩn hoá vào LSTM/TCN nhỏ (PyTorch CPU, vài chục nghìn tham số) dự báo dấu lợi suất h bước hoặc biến động. Văn liệu và kinh nghiệm: tỷ số tín hiệu/nhiễu rất thấp, mạng sâu thường không hơn GBM trên đặc trưng thủ công khi dữ liệu ít; dễ nhớ nhiễu. Chỉ thử sau meta-labeling, với baseline "dự báo = 0"/ngẫu nhiên, và đo trên biến động (dễ dự báo hơn hướng). Chi phí huấn luyện CPU chấp nhận được với M15–H1 vài triệu nến; GPU không có.

### 4.5 LLM analyst cục bộ
Qwen qua llama.cpp (đã có): tóm tắt tin/lịch/COT/kỹ thuật, giải thích vì sao một kịch bản đang hình thành. Giá trị: giảm tải đọc và nhắc rủi ro; KHÔNG phải nguồn alpha. Điều kiện: đầu vào cố định theo schema, đầu ra có trích dẫn, hậu kiểm tất định (số liệu lệch dữ liệu thì loại), không công cụ/URL/ra lệnh, không sinh khuyến nghị mua/bán. Rủi ro: bịa số, thiên lệch ngôn từ, độ trễ CPU. Sentiment tin dùng làm đặc trưng chỉ khi đo được giá trị tăng thêm (track-record cho thấy ý kiến công khai thường không vượt ngẫu nhiên).

### 4.6 Học tăng cường (FinRL, stable-baselines3)
FinRL (khung nghiên cứu, chủ yếu cổ phiếu/crypto theo ngày), stable-baselines3 (PPO/A2C/SAC, PyTorch), gymnasium cho môi trường. CẢNH BÁO OVERFITTING: RL tối ưu trên một quỹ đạo lịch sử duy nhất, phần thưởng nhiễu, nhạy với seed/siêu tham số; kết quả công bố thường không tái lập trên dữ liệu mới và bỏ qua chi phí/trượt; agent dễ "khai thác" lỗi mô phỏng (vd. khớp ở giá đóng). Điều kiện tối thiểu nếu thử: môi trường có spread/trượt/phí thật của `COSTS`, khớp ở giá mở nến kế tiếp, nhiều seed báo phân phối (không báo seed tốt nhất), walk-forward đa năm + test khoá riêng, so baseline mua-giữ/ngẫu nhiên. Ưu tiên thấp; chỉ prototype nhỏ ở giai đoạn D.

### 4.7 Khác đáng cân nhắc
Vol targeting/vị thế theo ATR (giảm DD, không tăng kỳ vọng — `STRATEGY_OPTIONS.md` E); trend chậm đa tài sản (có Sharpe 0,55 nhưng không thắng 60/40 phân biệt được); bộ lọc tin (lịch kinh tế là giá trị rõ nhất ở mức rủi ro); tìm bất thường/ chất lượng dữ liệu bằng isolation forest; conformal prediction để có khoảng bất định đúng độ phủ cho mô hình xác suất; Bayesian shrinkage cho xếp hạng (đã dùng ở track-record).

### 4.8 Đặc trưng đề xuất (chỉ dùng dữ liệu đã đóng tại thời điểm tín hiệu)
ATR14 và ATR/giá; tỷ lệ ATR ngắn/dài (nén/giãn biến động); khoảng cách tới S/R/đỉnh-đáy N nến chuẩn hoá theo ATR; độ nén cụm (biên/ATR); độ dài và độ dốc sóng dẫn; tỷ lệ hồi; số nến kể từ đỉnh cấu trúc; phiên giao dịch (Á/Âu/Mỹ, giờ UTC) và giờ trong tuần; khoảng cách tới tin kinh tế gần nhất và cấp độ ảnh hưởng (cửa sổ rủi ro); regime xác suất lọc; xu hướng khung lớn (độ dốc EMA H4/D1); volume tick và spread tương đối; chuỗi lợi suất trễ (vài bước); chỉ số tương quan chéo (DXY/USD basket) khi có; sentiment tin (nếu đo được giá trị tăng thêm). Cấm đặc trưng dùng nến ≥ thời điểm vào lệnh; kiểm bằng test nhân quả như `test_no_lookahead.py`.

### 4.9 Chi phí thực (gói 0 đồng)
| Hạng mục | Thực tế |
|---|---|
| Tính toán | CPU VPS chia sẻ với hệ thống khác; job nền có timeout, nice thấp, không chiếm CPU feed (feed đã ghim 32 CPU/shares 4096). GBM/logistic: giờ; LSTM nhỏ: giờ-chục giờ; RL: nhiều seed × nhiều giờ (đắt nhất). |
| Dữ liệu | Lịch sử MT5 152 mã × 21 khung đã có; nến M1 backfill 152/155 mã; không cần mua thêm. |
| LLM | Qwen cục bộ, tốc độ thấp trên CPU; chỉ chạy theo lịch/ khi cần. |
| Chi phí giao dịch mô phỏng | Dùng bảng `COSTS` bi quan của backtest (spread sàn, trượt, phí crypto 10 bp/chiều); chưa mô hình swap qua đêm. |
| Chi phí nhân lực/thời gian | Thường lớn hơn chi phí máy: mỗi ý tưởng cần pipeline không look-ahead, test khoá riêng, báo cáo. |

## 5. Backlog ý tưởng (27 mục)
Ưu tiên: P1 làm trước / P2 sau / P3 thăm dò. Rủi ro: chủ yếu rủi ro tự lừa (overfit/look-ahead) hoặc kỹ thuật. Khả thi: Cao/TB/Thấp với CPU + dữ liệu hiện có. Trạng thái ban đầu: `idea` (chưa làm), trừ mục đã nêu.
| # | Ý tưởng | Mô-đun | Ưu tiên | Rủi ro | Khả thi |
|---|---|---|---|---|---|
| 1 | Meta-labeling KB-1..4 bằng logistic regression (đối chứng đơn giản nhất) | 3 | P1 | Thấp lọc được gì thì cũng nhỏ; overfit nếu nhiều đặc trưng | Cao |
| 2 | Meta-labeling bằng GBM (LightGBM) + purged CV + embargo | 3 | P1 | Rò rỉ; chọn siêu tham số | Cao |
| 3 | Thư viện đặc trưng tập trung (mục 4.8) + test nhân quả | 3 | P1 | Look-ahead tinh vi | Cao |
| 4 | Nhãn triple-barrier khớp cơ chế khớp lệnh bi quan hiện có | 3 | P1 | Lệch giữa nhãn và khớp thật | Cao |
| 5 | Trọng số mẫu theo độ độc nhất (lệnh chồng lấn) | 3 | P2 | Phức tạp, ít lợi nếu mẫu lớn | TB |
| 6 | Bộ lọc cửa sổ tin kinh tế như đặc trưng/ lớp lọc cho mọi kịch bản | 3,7 | P1 | Số sự kiện tin ít (mẫu nhỏ) | Cao |
| 7 | Bộ lọc regime HMM (xác suất lọc) bật/tắt kịch bản | 3 | P2 | Look-ahead nếu dùng smoothing | TB |
| 8 | Clustering regime (GMM) trên vol/xu hướng làm đặc trưng | 3 | P2 | Số cụm tuỳ ý | Cao |
| 9 | Khoảng bất định bằng conformal prediction cho xác suất meta-label | 3 | P3 | Giả định hoán đổi được bị vi phạm theo thời gian | TB |
| 10 | Triển khai ONNX + onnxruntime cho suy luận trên service | 3 | P2 | Lệch số khi chuyển đổi | Cao |
| 11 | Dự báo biến động ngắn hạn (GARCH/HAR + GBM) để chỉnh cỡ/ SL | 3,7 | P2 | Lợi ích ở rủi ro, không ở kỳ vọng | Cao |
| 12 | LSTM/TCN nhỏ dự báo dấu lợi suất, đối chiếu "dự báo = 0" | 3 | P3 | Nhiễu, overfit, khó tái lập | TB |
| 13 | Xác suất breakout (GBM) quanh vùng đi ngang/nén | 3 | P2 | Nhãn breakout phụ thuộc định nghĩa | TB |
| 14 | LLM analyst tóm tắt bối cảnh kèm trích dẫn + hậu kiểm tất định | 4 | P2 | Bịa số; chậm trên CPU | TB |
| 15 | LLM giải thích "vì sao KB đang hình thành" từ `steps` (khuôn mẫu, không tự do) | 4 | P2 | Giá trị thông tin, không phải edge | Cao |
| 16 | Sentiment tin (NLP đã có) làm đặc trưng, đo giá trị tăng thêm | 3,5 | P3 | Track-record cho thấy ít tín hiệu | Cao |
| 17 | Consensus chuyên gia có trọng số theo track-record + khoảng "chưa đủ mẫu" | 5 | P3 | Hiện 0/99 vượt baseline | Cao |
| 18 | Vị thế theo ATR/ risk % + giới hạn lỗ ngày trong paper (so sánh DD) | 7 | P1 | Không tăng kỳ vọng; có thể gây ảo tưởng giảm rủi ro | Cao |
| 19 | Kill-switch và guardrail mô phỏng trong paper (chuẩn bị cho control plane) | 7 | P2 | Chỉ ý nghĩa nếu có chiến lược đáng chạy | Cao |
| 20 | Arena paper: cùng vốn ảo/ chi phí/ cửa sổ, xếp hạng theo kỳ vọng R + CI | 1 | P2 | Nhiều so sánh → hiệu chỉnh FDR | TB |
| 21 | Forward-paper bắt buộc 8–12 tuần, so với backtest trước khi đổi trạng thái | 1,8 | P1 | Mẫu ngắn; cần ghi thật thà "chưa đủ mẫu" | Cao |
| 22 | Tự động sinh báo cáo trung thực (CI, baseline, DSR, PBO) cho mọi job | 2,8 | P1 | Công cụ sai thì lừa có hệ thống — cần test | Cao |
| 23 | Trend chậm đa tài sản + vol targeting làm đối chứng (đã có Sharpe 0,55) | 1 | P2 | Không thắng 60/40 phân biệt được | Cao |
| 24 | Khung H1 của KB-1..4 (+0,054 R, CI chứa 0): đặt giả thuyết, test khoá RIÊNG, forward-paper | 2 | P3 | Đa so sánh, kết quả chọn sau khi xem dữ liệu | TB |
| 25 | RL (PPO, stable-baselines3) trong môi trường có chi phí thật, nhiều seed | 6 | P3 | Overfit rất cao, khó tái lập | Thấp |
| 26 | Phát hiện bất thường dữ liệu (isolation forest) để loại nến lỗi trước backtest | 3,8 | P3 | Phụ trợ chất lượng dữ liệu | Cao |
| 27 | Đa tài sản hoá backtest (chỉ số, vàng, trái phiếu proxy) để tăng mẫu độc lập | 3,8 | P2 | Tương quan chéo; chi phí khác nhau | TB |
Thứ tự đề xuất: 3 → 4 → 1 → 2 → 6 → 22 → 21 (khung A-C); 14/15 song song; RL và LSTM cuối cùng.

## 6. Cách tái lập backtest

1. **Đóng băng dữ liệu**: `sh bt.sh snapshot` sao dữ liệu vào `data/research/patterns/backtest/snapshot/` kèm sha256 trong `manifest.json` (snapshot hiện tại: chụp 2026-10-14 14:14 UTC, manifest `9cbc2531…d0d00a`). Mọi bước dev/walk-forward/test cùng dùng snapshot này; kết quả ghi `snapshot sha` + sha mã (git commit) + tham số + seed. Dữ liệu mới → snapshot mới, KHÔNG ghi đè snapshot cũ.
2. **Chia thời gian** `splits.json`: train | embargo 5 ngày | VAL | embargo | TEST khoá. Mã và dữ liệu cho đến ngày bắt đầu TEST là tất cả những gì dev được thấy; detector chế độ dev cắt nến ≥ ngày test trước khi chạy.
3. **Dev**: `sh bt.sh detect --mode dev` → `sh bt.sh wf` (walk-forward theo năm, lưới nhỏ, chọn tham số chỉ trên lệnh ĐÃ ĐÓNG trước điểm quyết định) + baseline ngẫu nhiên 300 seed + PBO/CSCV + DSR (đếm số cấu hình đã thử). Khớp lệnh bi quan: vào giá mở nến sau, SL ưu tiên khi cùng nến, bảng `COSTS`.
4. **Với mô hình ML**: purged k-fold + embargo trong dev; siêu tham số chọn bằng walk-forward lồng; không dùng thông tin VAL/TEST để chọn đặc trưng.
5. **TEST khoá**: mở ĐÚNG 1 LẦN cho mỗi (kịch bản/mô hình, phiên bản đặc tả). `bt.sh detect --mode final` ghi `test_access.log`; `bt.sh test` từ chối chạy lại nếu `test_report.json` đã có. Sau khi mở, sổ lệnh chmod 444 và checksum ghi vào báo cáo.
6. **Quy tắc cứng**: KHÔNG mở TEST khoá mới của KB-1..4 (đã mở 2026-10-14); KHÔNG chỉnh tham số KB-1..4 rồi coi test cũ còn "sạch". Kịch bản/mô hình MỚI cần tập TEST khoá riêng, khai báo TRƯỚC khi nhìn dữ liệu (cắt thời gian sau ngày đóng băng, hoặc giữ nguyên khoảng thời gian đã khoá nhưng chỉ khi chưa từng dùng cho kịch bản đó và mọi chọn lọc ý tưởng không nhìn khoảng đó). Lý tưởng: forward-paper làm tập khoá thật.
7. **Ghi vào Lab**: mỗi thí nghiệm một dòng — id, giả thuyết khai báo trước, tham số, số lần thử, snapshot sha, commit, kết quả (E[R], CI95, p vs baseline, DSR, PBO), artefact, trạng thái. Kết quả không đạt vẫn ghi.
Chi tiết và lệnh đầy đủ: `research/PATTERN_SELL_BACKTEST.md` mục 7 và 9; mã: `services/pattern-research/pattern_research/` (`backtest.py`, `bt_run.py`, `bt_artifacts.py`).

## 7. Liên kết
`handoff/TASK_ai_trading_tab.md` · `PATTERNS_SELL.md` · `research/PATTERN_SELL_BACKTEST.md` · `STRATEGY_OPTIONS.md` · `EXPERT_TRACKRECORD.md` · `CONTROL_PLANE_DESIGN.md` · `FREE_STACK.md` · `UI_NO_SOURCES.md`.
