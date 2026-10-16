# Backtest Kịch bản Sell KB-1..KB-4 (pattern-engine) — báo cáo trung thực

Ngày: 2026-10-14 · Phạm vi: nghiên cứu nội bộ, READ-ONLY/paper, **không có lệnh thật** · Mã: `services/pattern-research/pattern_research/{backtest,bt_run}.py` · Kết quả thô (không vào git): `data/research/patterns/backtest/` (VPS).

## 0. Tóm tắt (1 phút)

1. **Không có edge sau chi phí.** Walk-forward ngoài mẫu 2008 → 03/2026, 8.290 lệnh trên 9 mã × 5 khung: kỳ vọng **−0,100 R/lệnh** (CI95 [−0,124; −0,073]), winrate 36,9%, profit factor 0,83. Trước chi phí: **+0,012 R/lệnh** (≈ 0). Chi phí (spread + trượt + phí) ăn ≈ 0,11 R/lệnh, nặng nhất ở M5/M15 và crypto.
2. **Tốt hơn vào lệnh ngẫu nhiên một chút, nhưng vẫn lỗ.** Baseline ngẫu nhiên cùng điều kiện (cùng mã/khung/giai đoạn, cùng số lệnh, cùng phân bố SL theo ATR, cùng TP/thời gian giữ/chi phí, 300 seed): −0,126 R → p = 0,02. Phần "tốt hơn" đến gần như toàn bộ từ **KB-3** (p = 0,003); KB-1, KB-2, KB-4 **không tốt hơn ngẫu nhiên** (p 0,63 / 0,96 / 0,98).
3. **Chọn tham số không bền:** Deflated Sharpe = 0; PBO của lưới TP×điểm = 0,86 (cấu hình tốt nhất trong mẫu thường dưới trung vị ngoài mẫu — lưới gần như phẳng, TP 1R..3R chênh < 0,01 R).
4. **Điểm sáng duy nhất là khung H1** (+0,054 R, CI [−0,047; +0,153], n=589) — CI chứa 0 và là kết quả tìm được SAU khi xem dữ liệu (đa so sánh), nên chỉ là giả thuyết.
5. **Hiệu chỉnh theo 3 ảnh golden không giúp tổng quát hoá:** bộ tham số GỐC (chưa hiệu chỉnh) cho ít tín hiệu hơn 6 lần nhưng kỳ vọng không tệ hơn (−0,027 R so với −0,065 R, CI chồng nhau).
6. **Tập TEST khoá (2026-03-11 → 10-14), chạy đúng 1 lần: tệ hơn dev.** 433 lệnh, **−0,263 R/lệnh** (CI95 [−0,375; −0,152]), PF 0,60, winrate 33,7%; trước chi phí −0,095 R; **kém cả baseline ngẫu nhiên** (−0,157 R, p = 0,97). Cả 3 giả thuyết phụ đăng ký trước (H1 > 0, KB-3 > ngẫu nhiên, KB-3|H1 > 0) **không được xác nhận**.

Kết luận thẳng: ở dạng hiện tại, KB-1..KB-4 **không phải chiến lược có lợi nhuận**; dùng làm **công cụ mô tả/cảnh báo cấu trúc** (thông tin + paper) là phù hợp, không dùng để vào lệnh thật.

## 1. Dữ liệu

| Nhóm | Mã | Khung | Giai đoạn dùng | Ghi chú |
|---|---|---|---|---|
| MT5 (CFD broker demo, có spread theo nến) | EURUSD, GBPUSD, USDJPY | M5, M15, H1, H4, D1 | 2001 → | trước 2001 nến tổng hợp (QC MT5_status) |
| | XAUUSD | M5–M30 từ 2009, H1+ từ 2007 | | 2004–2008 nến thưa |
| | US500, US30 | 2012-08 → | | |
| | USTEC | 2022-07 → | | lịch sử ngắn |
| Crypto spot | BTCUSD, ETHUSD | M5–D1 | 2021 → | phí taker 0,1%/chiều |
| D1 tham chiếu | US500 (ETF), vàng kỳ hạn | D1 | | gần như không có tín hiệu |

- Giờ UTC; server MT5 = EET (DST châu Âu) đã được nhập lại đúng (`docs/handoff/MT5_status.md`). Bỏ nến có `n_m1 < 50%` số phút kỳ vọng.
- **Dữ liệu đóng băng**: `backtest/snapshot/` (copy + sha256 trong `manifest.json`) chụp 14:14 UTC 2026-10-14, dùng cho MỌI bước (dev, walk-forward, test) để kết quả tái lập.
- Chia thời gian (chung mọi mã, `splits.json`): train < 2025-07-27 | embargo 5 ngày | VAL 2025-08-01 → 2026-03-06 | embargo | **TEST 2026-03-11 → 2026-10-14 (KHOÁ)**.

## 2. Phương pháp

**Tín hiệu.** `pattern_engine.Detector` (đúng mã production) chạy tuần tự từng nến ĐÃ ĐÓNG; chỉ dùng sự kiện `triggered`. Ở chế độ dev, detector KHÔNG nhìn thấy nến ≥ ngày bắt đầu test (cắt dữ liệu trước khi chạy). Kiểm tra nhân quả: tín hiệu dev phải trùng tiền tố tín hiệu chạy trên toàn bộ dữ liệu (`causality_check`). pattern-engine có test no-look-ahead riêng.

**Khớp lệnh (bi quan).**
- Sell market ở **giá mở nến kế tiếp** nến kích hoạt (tín hiệu chỉ biết khi nến đóng) − trượt giá.
- Nến là giá BID; lệnh Sell đóng ở ASK = bid + spread → SL/TP kích hoạt theo ASK. Spread = max(spread MT5 của nến, sàn theo mã).
- SL = mức SL của engine (đỉnh cấu trúc + 0,25 ATR). Gap qua SL → khớp ở giá mở (xấu hơn). Cùng 1 nến chạm cả SL và TP → tính SL.
- TP = entry − m×R (m chọn bằng walk-forward); hết `max_hold` = 100 nến → đóng ở giá đóng + spread. Kết quả tính bằng R (đã trừ chi phí).
- Chi phí (bảng `COSTS` trong `backtest.py`, giả định tài khoản retail standard, cố ý bi quan hơn spread demo):

| Mã | Sàn spread | Trượt / lần khớp | Phí |
|---|---|---|---|
| EURUSD | 1,0 pip | 0,2 pip | 0 |
| GBPUSD | 1,4 pip | 0,2 pip | 0 |
| USDJPY | 1,2 pip | 0,2 pip | 0 |
| XAUUSD | 0,20 USD | 0,05 | 0 |
| US500 / US30 / USTEC | 0,6 / 2,0 / 1,5 điểm | 0,25 / 1,0 / 0,75 | 0 |
| BTC/ETH | 1 bp | 1 bp | 10 bp/chiều |

**Walk-forward.** Lưới nhỏ, cố ý ít bậc tự do: TP ∈ {1; 1,5; 2; 3}R × điểm tối thiểu ∈ {0; 80} (8 cấu hình; `max_hold` cố định). Mỗi năm 2008..2024, nửa đầu 2025, rồi VAL: chọn cấu hình có R trung bình cao nhất trên các lệnh **đã đóng trước** đầu giai đoạn (mở rộng dần, embargo theo thời điểm đóng lệnh), cần ≥ 30 lệnh; áp cho giai đoạn đó. Ghép các giai đoạn = chuỗi ngoài mẫu (OOS). Tham số cuối cho test chọn bằng toàn bộ dev.

**Baseline ngẫu nhiên.** Với mỗi mã×khung (và mỗi TP đã dùng): cùng số lệnh, thời điểm vào ngẫu nhiên đều trong khoảng [lệnh đầu, lệnh cuối], SL = giá mở + d×ATR với d hoán vị từ phân bố SL/ATR thật, cùng TP/hold/chi phí; 300 seed. p = P(trung bình ngẫu nhiên ≥ trung bình thật), một phía.

**Chống tự lừa.** Bootstrap CI95 trung bình R; Deflated Sharpe (Bailey & López de Prado) với số thử = 8; PBO bằng CSCV (16 nhóm theo quý, 12.870 tổ hợp); độ nhạy tham số detector (gốc / hiệu chỉnh / giữa); thống kê theo KB, khung, mã, mã×khung, phiên, năm; chuỗi thua dài nhất; max drawdown (R).

**Hạn chế phương pháp.** Lệnh có thể chồng nhau (nhiều mã/khung cùng lúc) — thống kê theo lệnh, chưa mô phỏng vốn/đòn bẩy. Spread demo MT5 là spread NHỎ NHẤT trong nến nên dùng sàn. Chưa mô hình swap qua đêm (bất lợi thêm cho lệnh giữ lâu trên H4/D1). Một số mã có lịch sử ngắn (USTEC, crypto).

## 3. Kết quả walk-forward (dev, ngoài mẫu)

### 3.1 Gộp
| | n | win | E[R] net | CI95 | PF | E[R] trước phí | Baseline | p | MaxDD (R) | Chuỗi thua |
|---|---|---|---|---|---|---|---|---|---|---|
| Tất cả | 8.290 | 36,9% | **−0,100** | [−0,124; −0,073] | 0,83 | +0,012 | −0,126 | 0,02 | 834 | 21 |

Thoát: SL 4.108 · hết thời gian 2.594 · TP 1.587. Deflated Sharpe 0,00 (Sharpe/lệnh −0,083). PBO 0,86.
Tham số được chọn: TP 2R ở mọi năm (từ 2025: TP 2R + điểm ≥ 80 — điểm gần như luôn ≥ 80 nên bộ lọc điểm vô tác dụng).

### 3.2 Theo kịch bản
| KB | n | win | E[R] | CI95 | PF | Baseline | p |
|---|---|---|---|---|---|---|---|
| KB-1 | 590 | 33,9% | −0,162 | [−0,263; −0,051] | 0,76 | −0,144 | 0,63 |
| KB-2 | 1.687 | 31,5% | −0,179 | [−0,240; −0,109] | 0,75 | −0,128 | 0,96 |
| KB-3 | 5.804 | 39,0% | −0,064 | [−0,093; −0,035] | 0,88 | −0,125 | **0,003** |
| KB-4 | 209 | 29,7% | −0,283 | [−0,434; −0,127] | 0,57 | −0,110 | 0,98 |

### 3.3 Theo khung
| Khung | n | win | E[R] net | CI95 | E[R] "trước phí"* |
|---|---|---|---|---|---|
| M5 | 5.439 | 35,9% | −0,125 | [−0,157; −0,093] | −0,035 |
| M15 | 2.037 | 38,1% | −0,076 | [−0,127; −0,026] | −0,028 |
| H1 | 589 | 41,8% | **+0,054** | [−0,047; +0,153] | +0,074 |
| H4 | 202 | 38,1% | −0,092 | [−0,245; +0,067] | −0,084 |
| D1 | 23 | 34,8% | −0,136 | [−0,606; +0,362] | −0,133 |

\* cùng đường đi của lệnh net, chỉ bỏ chi phí khỏi giá — cho thấy phần chi phí theo khung (≈ 0,09 R ở M5, ≈ 0,02 R ở H1).

### 3.4 Theo mã (gộp khung)
| Mã | n | E[R] | CI95 | Mã | n | E[R] | CI95 |
|---|---|---|---|---|---|---|---|
| XAUUSD | 1.258 | −0,025 | [−0,092; +0,043] | US500 | 415 | −0,018 | [−0,131; +0,104] |
| EURUSD | 1.483 | −0,124 | [−0,183; −0,064] | US30 | 457 | −0,095 | [−0,203; +0,011] |
| GBPUSD | 1.580 | −0,078 | [−0,139; −0,019] | USTEC | 185 | −0,009 | [−0,176; +0,165] |
| USDJPY | 1.664 | −0,069 | [−0,124; −0,011] | BTCUSD | 654 | −0,309 | [−0,401; −0,215] |
| | | | | ETHUSD | 591 | −0,204 | [−0,305; −0,100] |

Crypto: trước phí +0,02..+0,04 R nhưng phí 0,2% khứ hồi trên SL hẹp ở M5/M15 làm lỗ nặng.

### 3.5 Mã × khung (chọn lọc; đủ bảng trong `wf_report.json` → `oos.by_series`)
| Chuỗi | n | E[R] | CI95 | p vs ngẫu nhiên |
|---|---|---|---|---|
| GBPUSD H4 | 41 | +0,588 | [+0,187; +1,015] | 0,003 |
| US500 H1 | 30 | +0,313 | [−0,185; +0,833] | 0,037 |
| XAUUSD H1 | 92 | +0,154 | [−0,092; +0,400] | 0,030 |
| EURUSD H1 | 107 | +0,106 | [−0,103; +0,327] | 0,12 |
| GBPUSD H1 | 121 | +0,110 | [−0,108; +0,339] | 0,11 |
| USDJPY M5 | 1.125 | −0,060 | [−0,129; +0,009] | 0,04 |
| EURUSD H4 | 36 | −0,440 | [−0,706; −0,122] | 0,997 |
| BTCUSD M5 | 434 | −0,378 | [−0,496; −0,265] | 0,45 |

**Cảnh báo đa so sánh:** có 43 chuỗi mã×khung có lệnh; với ngưỡng 0,05 kỳ vọng ~2 chuỗi "có ý nghĩa" do may rủi. Sau hiệu chỉnh Bonferroni (0,05/43 ≈ 0,001) **không chuỗi nào đạt**. GBPUSD H4 tốt nhưng EURUSD H4 xấu tương đương — không nhất quán giữa các cặp tương tự.

### 3.6 Theo phiên (giờ vào lệnh UTC) và theo năm
Á 00–07: −0,081 · Âu 07–13: −0,034 · Mỹ 13–21: −0,143 · 21–24: −0,153.
Năm: chỉ 2012 (+0,13), 2013 (+0,04), 2026 (+0,01) dương; 2023–2025 xấu nhất (−0,18 … −0,24). Không có xu hướng cải thiện.

## 4. Overfit do hiệu chỉnh theo 3 ảnh golden

Tham số sóng dẫn đã được nới để khớp 3 ảnh mẫu (`docs/PATTERNS_SELL.md` §4: thân nến đỏ dài 1,5 → 0,8 ATR, tỷ trọng xanh 25% → 40%). Kiểm tra độ nhạy trên dev (M15–D1, TP 2R, trong mẫu, không walk-forward):

| Bộ tham số | Tín hiệu | E[R] | CI95 | KB-3 | KB-2 |
|---|---|---|---|---|---|
| GỐC theo plan1 (1,5 ATR / 25%) | 560 | −0,027 | [−0,130; +0,072] | +0,018 | −0,340 |
| Giữa (1,0 / 33%) | 2.199 | −0,052 | [−0,100; −0,003] | −0,015 | −0,176 |
| **Hiệu chỉnh golden (0,8 / 40%) — đang chạy production** | 3.352 | −0,065 | [−0,106; −0,024] | −0,033 | −0,159 |

- Nới tham số tăng số tín hiệu ~6 lần nhưng **không** cải thiện chất lượng (xu hướng còn hơi xấu đi; CI chồng nhau nên chưa kết luận chắc). Đây đúng là dấu hiệu khớp quá mức theo 3 ví dụ: golden test 3/3 KHÔNG phải bằng chứng hiệu quả.
- Golden đo trên vàng M15 tháng 9–10/2026 — cũng nằm trong giai đoạn TEST; nghĩa là test KHÔNG hoàn toàn "mù" với tham số detector (các tham số được chọn để bắt 3 ví dụ trong test). Kết quả test của XAUUSD M15 vì vậy thiên lạc quan.
- Khuyến nghị: nếu tiếp tục, dùng lại ngưỡng gốc hoặc chọn ngưỡng bằng walk-forward trên dữ liệu rộng, không theo ảnh mẫu.

## 5. Tập TEST khoá (2026-03-11 → 2026-10-14) — chạy 1 lần

Nhật ký mở test (`data/research/patterns/test_access.log`): `14:44:17 detect final (MO TAP TEST)` → `15:07:47 test (danh gia 1 lan) params={tp_r: 2.0, min_score: 80}`. Một lần mở trước đó (14:42) lỗi ngay khi ghi nhật ký, trước khi đọc dữ liệu. Giả thuyết + tiêu chí được ghi vào `docs/handoff/PE_status.md` (commit 88a56df) TRƯỚC khi mở. Kiểm tra nhân quả: 47/47 chuỗi, tín hiệu dev trùng tiền tố tín hiệu chạy trên toàn bộ dữ liệu (0 lệch). Không chỉnh gì sau khi xem test.

| | n | win | E[R] net | CI95 | PF | Trước phí | Baseline | p | MaxDD | Chuỗi thua |
|---|---|---|---|---|---|---|---|---|---|---|
| **Gộp (giả thuyết chính)** | 433 | 33,7% | **−0,263** | [−0,375; −0,152] | 0,60 | −0,095 | −0,157 | 0,97 | 120,5 R | 17 |

Thoát: SL 220 · hết giờ 140 · TP 69 · hết dữ liệu 4. Deflated Sharpe 0.

| Theo KB | n | E[R] | CI95 | p | Theo khung | n | E[R] | CI95 |
|---|---|---|---|---|---|---|---|---|
| KB-1 | 25 | −0,475 | [−1,121; +0,173] | 0,84 | M5 | 302 | −0,307 | [−0,437; −0,174] |
| KB-2 | 77 | −0,174 | [−0,485; +0,168] | 0,39 | M15 | 98 | −0,206 | [−0,427; +0,023] |
| KB-3 | 320 | −0,270 | [−0,381; −0,146] | 0,99 | H1 | 24 | −0,003 | [−0,498; +0,542] |
| KB-4 | 11 | −0,195 | [−0,908; +0,572] | 0,43 | H4 | 9 | −0,078 | [−0,766; +0,754] |

Giả thuyết đăng ký trước: chính (gộp > 0) — **bác** (E[R] < 0, CI < 0). (a) H1 > 0 — −0,003, n=24: **không xác nhận**. (b) KB-3 > ngẫu nhiên — p = 0,99: **không xác nhận** (đảo chiều so với dev). (c) KB-3|H1 > 0 — +0,013, n=21, CI [−0,50; +0,57]: **không xác nhận**.

Theo mã: chỉ XAUUSD dương (+0,174, n=56, CI [−0,137; +0,502]; M15 +0,40 n=17) — **không tin**: tham số detector được hiệu chỉnh trên 3 ảnh vàng M15 tháng 9–10/2026, NẰM TRONG giai đoạn test (§4). Crypto lỗ nặng nhất (BTC −0,557, ETH −0,382) vì phí; GBPUSD (−0,371) đảo ngược kết quả H4 tốt ở dev (chỉ 1 lệnh H4 trong test).

Đọc kết quả: test ngắn (7 tháng) nên CI rộng, nhưng hướng nhất quán với dev: kỳ vọng âm sau chi phí, không tốt hơn vào lệnh ngẫu nhiên. **Không có bằng chứng edge.**

## 6. Kết luận và khuyến nghị

- KB-1..KB-4 (tham số production hiện tại) **không có edge** sau chi phí trên 9 mã × 5 khung, cả walk-forward 2008–2026 lẫn test khoá. Trước chi phí kỳ vọng ≈ 0 (dev +0,01 R, test −0,09 R) → mẫu hình chủ yếu mô tả cấu trúc giá, không dự báo hướng đi tiếp.
- Hệ thống giữ đúng vai trò: **thông tin + paper-trade** (pattern-scan đã ghi sổ cái hash-chain để đo forward-test trung thực). Không đưa vào giao dịch thật; không quảng bá winrate/kỳ vọng.
- Nếu muốn nghiên cứu tiếp (mỗi hướng là một thử nghiệm MỚI, phải walk-forward + test mới, cộng dồn số lần thử vào Deflated Sharpe): (1) quay về ngưỡng gốc chặt hơn (ít tín hiệu, dev không tệ hơn); (2) chỉ H1+ và mã chi phí thấp; (3) bộ lọc xu hướng khung lớn; (4) thoát lệnh khác (trailing). Cần dữ liệu test mới (sau 2026-10-14) — tập test hiện tại đã "dùng".
- Hạn chế: chưa có swap; spread demo có thể thấp hơn thực tế giờ tin; lệnh chồng nhau chưa mô phỏng vốn; crypto/USTEC lịch sử ngắn; golden nằm trong giai đoạn test.

## 7. Tái lập

```
sh bt.sh snapshot                 # 1 lần: đóng băng dữ liệu + sha256
sh bt.sh detect --mode dev        # chỉ nến < test_start
sh bt.sh wf                       # walk-forward + baseline + PBO -> wf_report.json, wf_oos_trades.parquet
sh bt.sh detect --mode dev --tag orig --tfs M15,H1,H4,D1 --overrides '{"common":{"lead_long_body_atr":1.5,"lead_max_green":0.25}}'
sh bt.sh sens                     # độ nhạy -> sens_report.json
sh bt.sh detect --mode final      # MỞ test (ghi test_access.log)
sh bt.sh test                     # 1 lần; từ chối chạy lại nếu test_report.json đã có
sh bt.sh examples                 # thư viện ví dụ PNG+JSON
```
`bt.sh` = `docker run pe-research python -m pattern_research.bt_run` với `PATTERN_DATA` gắn vào `data/research/patterns`. Test đơn vị: `services/pattern-research/tests` (mô phỏng khớp lệnh, chi phí, ATR khớp engine, baseline/p-value, PBO, khoá test, lọc QC, walk-forward không dùng lệnh chưa đóng, kiểm nhân quả).

## 8. Thư viện ví dụ
16 ví dụ backtest (mỗi KB: 1 thắng, 1 thua, 1 "điển hình" = gần trung vị R — thường là thua −1R vì đa số lệnh thua, 1 lệnh trong tập test): `services/pattern-scan/examples/bt-*.png|json` (kind `backtest`, có `result`, `levels`, `steps`, `points`) — trang "Kịch bản" hiển thị cùng 3 mẫu chuẩn (API `/v1/patterns/examples`). Chọn ngẫu nhiên có seed cố định trong từng nhóm (không chọn ảnh đẹp nhất). Ảnh vẽ sóng theo `points` của engine; không ghi tên nguồn dữ liệu.

## 9. Sổ lệnh và hình ảnh đầy đủ (ART, 2026-10-14)
Sổ lệnh: 8.723 lệnh = dev 7.886 + val 404 + **test 433** (`data/research/patterns/backtest/final/ledger/`, README tái lập cùng thư mục; bản nhỏ ở `docs/research/pattern_sell/`). Checksum sha256:
- ledger_test.csv.gz `cc84c83f653b7f60bad3667f8e936bb94fa664e27111208bc478255fd2b58601` (chmod 444, không sửa sau khi mở); ledger_dev `3c3b3969...9352`; ledger_val `7b504e1c...dce`; `test_trades.parquet` gốc `7a5b6b8e...ae3d`; snapshot manifest `9cbc2531...d0d00a`.
- Minh bạch: `test_trades.parquet` (lưu 15:09) thiếu cột spread/slip/MAE/MFE/signal_time; các cột này được tái dựng từ chính file đó + bar snapshot đóng băng, KHÔNG chạy lại phát hiện/đánh giá; R tái dựng khớp 1e-9 cả 8.723 lệnh, tổng khớp (n=433, −0,263R; dev+val n=8.290, −0,100R, p baseline 0,0199 / 0,9701 khớp báo cáo). Ghi trong `test_access.log`.

![equity](pattern_sell/charts/a1_equity_total.png)
![KB](pattern_sell/charts/a2_equity_by_kb.png)
![drawdown](pattern_sell/charts/b_drawdown.png)
![dist](pattern_sell/charts/c_dist_r_mae_mfe.png)
![heat](pattern_sell/charts/d1_heat_kb_tf.png)
![heat2](pattern_sell/charts/d2_heat_symbol_tf.png)
![year](pattern_sell/charts/e_by_year_session.png)
![baseline](pattern_sell/charts/f_baseline_random.png)
![pbo](pattern_sell/charts/g_pbo_dsr.png)
![golden1](pattern_sell/charts/i_golden_kb-1.png)
![golden2](pattern_sell/charts/i_golden_kb-2.png)
![golden3](pattern_sell/charts/i_golden_kb-3.png)

44 ví dụ tiêu biểu (mỗi KB: 4 thắng, 4 thua, 3 tệ nhất): `pattern_sell/examples/`; đủ 200 ảnh ở VPS. Kết quả xấu và được ghi nguyên trạng: không có edge.
