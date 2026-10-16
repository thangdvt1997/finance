# Nghiên cứu backtest: chiến lược kinh điển trên forex và vàng

Ngày: 2026-10-11 · Phạm vi: nghiên cứu nội bộ, hệ thống READ-ONLY, không có lệnh thật · Mã tái lập: `research/` (xem `research/README.md`)

## 0. Tóm tắt (đọc phần này nếu chỉ có 1 phút)

1. **Không chiến lược nào có bằng chứng bền** trên dữ liệu và mô hình chi phí này. Không cấu hình nào vượt Deflated Sharpe 0,95 (cao nhất 0,49, tức khoảng một nửa khả năng là may mắn sau khi tính 38 cấu hình đã thử).
2. **Trend-following (TSMOM, MA, Donchian) trên 7 cặp FX: Sharpe quanh 0 sau chi phí** (TSMOM +0,05; MA 50/200 −0,13; Donchian −0,08 trong 2002-2026). Giai đoạn 2002-2011 tốt (Sharpe 0,14-0,41) rồi mất hẳn từ 2012 (−0,17 đến −0,49). Đây là kết quả đúng xu hướng trong văn liệu về "suy giảm hậu công bố", nhưng một mẫu 14 năm không đủ để khẳng định.
3. **Thêm vàng và bạc làm trend "đẹp lên"** (TSMOM 0,33 trên panel B) nhưng phần lớn là do vàng tăng mạnh 2002-2026. Mua-và-giữ vàng (Sharpe 0,74, chưa trừ lãi vay) còn hơn mọi chiến lược trend trên vàng. Đó là thiên kiến chọn mẫu theo kết quả, không phải năng lực của chiến lược.
4. **FX carry là chiến lược có Sharpe sau chi phí cao nhất ở panel FX (0,21), nhưng** CI 95% là [−0,20; +0,63], MaxDD −56%, thua 20% năm 2008, 16% năm 2015, 12% năm 2020, và Sharpe sau 2012 là −0,07. Đây là phần thưởng cho rủi ro đuôi, không phải lợi thế vô hại.
5. **Mean reversion (RSI2, Bollinger) là đối chứng:** RSI2 trông đẹp trên 7 cặp FX (0,19) nhưng biến mất khi thêm kim loại (0,02), nhạy với chi phí (Sharpe 0,03 khi chi phí gấp đôi) và dữ liệu ECB là giá tham chiếu nên có thể chứa nhiễu đảo chiều giả. **Không tin.** Bollinger thua ở mọi kịch bản.
6. **Danh mục kết hợp không cứu được:** COMBO4 (trend3 + carry) Sharpe −0,01 (FX) và 0,23 (FX+kim loại). Diversification giảm rủi ro nhưng không biến edge ≈ 0 thành edge dương.
7. **Kỳ vọng thực tế cho tài khoản bán lẻ:** edge sau chi phí trong khoảng 0 đến +0,3 Sharpe, với khoảng bất định rộng hơn (±0,4) và drawdown 30-60% ở mức 10% vol. Đây không phải nền tảng để kỳ vọng thu nhập ổn định.

## 1. Dữ liệu và giới hạn

| Nguồn | Nội dung | Phạm vi | Chất lượng |
|---|---|---|---|
| Frankfurter/ECB | 7 cặp FX (EUR, GBP, JPY, AUD, CAD, CHF, NZD so với USD), đóng cửa hằng ngày | 1999-01-04 → 2026-10-09, 7.111 dòng | Sạch, không bad print >14%. **Là giá tham chiếu ECB 14:15 CET, không phải giá giao dịch**; không có bid/ask |
| Yahoo (yfinance) | GC=F (vàng), SI=F (bạc), SPY | 2000-08 → 2026-10 | Hợp lý. GC/SI là hợp đồng tương lai liên tục chưa điều chỉnh roll (có bước nhảy roll nhỏ); đóng cửa COMEX ~19:30 CET lệch ~5 giờ so với fix ECB |
| FRED/OECD | Lãi suất liên ngân hàng 3 tháng, 8 đồng tiền (tháng) | EUR từ 1994, JPY từ 2002-04, CHF từ 1999-07 | Chuỗi tháng, tôi trễ 1 tháng. JPY trước 2002-04 điền 0,1%; CHF trước 1999-07 điền backfill (xấp xỉ). Chuỗi EUR kết thúc 2026-01 nên **cửa sổ đánh giá cắt ở 2026-02-27** |

**Dữ liệu đã loại và lý do** (`research/results/data_quality.csv`):
- **Yahoo FX bị loại.** Tương quan lợi suất ngày với ECB chỉ 0,43-0,54 (kỳ vọng ~0,9), có bad print tới 17%, mốc ngày lệch (ví dụ ngày SNB 2015-01-15 hiện giá trước cú sốc). Dùng ECB cho toàn bộ FX.
- **WTI loại:** giá âm tháng 4/2020 (−37,63) làm lợi suất phần trăm vô nghĩa. **SPY** chỉ dùng làm benchmark.
- Dukascopy (code `market-collector`) **chưa dùng để kiểm tra chéo** (rate limit chậm). Đây là khoảng trống: chưa có nguồn thứ hai độc lập xác nhận giá FX.
- Parquet qua `fastparquet`: `pyarrow` bị Application Control chặn `_parquet.dll` trên máy dev.

**Hệ quả của việc dùng giá fix ECB:** (a) không giao dịch được đúng giá fix; tín hiệu tính từ giá này và vào lệnh "tại chính giá đó" là lạc quan; (b) giá fix có nhiễu thời điểm nên chiến lược đảo chiều ngắn hạn có thể ăn nhiễu giả; (c) ngày lễ TARGET không có dòng.

## 2. Phương pháp

**Engine** tự viết, vector hóa (`research/engine.py`); không dùng vectorbt vì license Commons Clause và cần kiểm soát từng khoản chi phí. Có 4 kiểm chứng trong `tests_sanity.py` đều qua: tín hiệu nhân quả (cắt dữ liệu tương lai không đổi tín hiệu quá khứ), khớp giải tích, chi phí tác động đúng chiều, 60 chuỗi tín hiệu ngẫu nhiên không phí cho Sharpe trung bình −0,001 (độ lệch chuẩn 0,21).

**Quy ước:** tín hiệu từ close ngày t, vị thế giữ từ t đến t+1. Mỗi instrument chuẩn hóa rủi ro theo 1/vol (EWMA 60 ngày), chia đều cho N; toàn chiến lược scale ex-ante về **vol mục tiêu 10%** (trễ 1 ngày, đòn bẩy tối đa 6x). Nhờ vậy CAGR so sánh được giữa các chiến lược. Lợi suất là excess return (ký quỹ không sinh lãi), 252 ngày/năm.

**Chiến lược (tham số cố định theo văn liệu):**
1. TSMOM 12 tháng (Moskowitz-Ooi-Pedersen 2012): dấu lợi suất 252 ngày, tái cân bằng cuối tháng.
2. MA cross 50/200; Donchian 55/20 (turtle hệ 2, dùng close vì không có high/low).
3. FX carry cắt ngang: cuối tháng xếp hạng 8 đồng tiền (gồm USD) theo lãi 3M trễ 1 tháng, long 3 cao nhất, short 3 thấp nhất, quy về vị thế so với USD.
4. Đối chứng đảo chiều: RSI(2) kiểu Connors (10/90, lọc SMA200, thoát SMA5) và Bollinger 20/2.
5. Kết hợp cân bằng rủi ro (tỷ lệ nghịch vol 252 ngày): COMBO4 = TSMOM + MA + Donchian + Carry; COMBO5 thêm RSI2; TREND3 = 3 trend.
6. Benchmark mua-và-giữ cùng vol (long ngoại tệ/kim loại so với USD), kiểm soát dịch-thời-gian, mua-và-giữ SPY/vàng không đòn bẩy.

**Mô hình chi phí (bảo thủ, không có spread thật):** nửa spread mỗi chiều: EURUSD 0,6 pip, GBPUSD 0,9, USDJPY 0,7, AUDUSD 0,9, USDCAD/USDCHF 1,1, NZDUSD 1,2; vàng 2,5 bps, bạc 6 bps; nhân 1,5 trước 2010. Swap = chênh lệch lãi 3M (chuỗi tháng) **trừ markup 0,5%/năm trên mỗi đơn vị notional**. Báo cáo 3 kịch bản: không phí; cơ sở (1x, 0,5%); xấu (2x spread, markup 1%). Không mô hình hóa trượt giá khi gap/dừng lỗ.

**Cửa sổ chung:** 2002-06-01 → 2026-02-27 (23,7 năm). Panel A = 7 cặp FX; panel B = A + vàng + bạc.

## 3. Kết quả chính (cơ sở: 1x chi phí, markup 0,5%, vol mục tiêu 10%)

CI = khoảng tin cậy 95% của Sharpe qua block bootstrap (khối 21 ngày, 2.000 mẫu, seed cố định). DSR = Deflated Sharpe Ratio với N = 38 cấu hình đã thử (xác suất Sharpe thật > 0 sau hiệu chỉnh chọn lọc; ngưỡng thông thường ≥ 0,95).

### Panel A: 7 cặp FX (ECB)

| Chiến lược | CAGR | Vol | Sharpe [CI 95%] | Sortino | MaxDD | Calmar | % năm lỗ | DSR |
|---|---|---|---|---|---|---|---|---|
| TSMOM 12m | −0,1% | 10,3% | 0,05 [−0,35; 0,45] | 0,06 | −49,7% | −0,00 | 52% | 0,08 |
| MA 50/200 | −1,8% | 10,3% | −0,13 [−0,49; 0,27] | −0,17 | −59,8% | −0,03 | 61% | 0,01 |
| Donchian 55/20 | −1,4% | 10,4% | −0,08 [−0,45; 0,30] | −0,11 | −44,8% | −0,03 | 61% | 0,02 |
| Carry k=3 | +1,7% | 10,4% | 0,21 [−0,20; 0,63] | 0,29 | −56,1% | 0,03 | 44% | 0,27 |
| RSI2 10/90 | +1,5% | 10,7% | 0,19 [−0,17; 0,57] | 0,28 | −33,2% | 0,05 | 52% | 0,25 |
| Bollinger 20/2 | −1,7% | 10,4% | −0,11 [−0,48; 0,28] | −0,15 | −46,2% | −0,04 | 61% | 0,02 |
| Mua-và-giữ cùng vol | −0,3% | 10,3% | 0,02 [−0,39; 0,42] | 0,03 | −62,2% | −0,01 | 57% | 0,06 |
| **COMBO4 (trend3+carry)** | −0,6% | 10,4% | −0,01 [−0,37; 0,37] | −0,01 | −58,5% | −0,01 | 65% | 0,05 |
| COMBO5 (+RSI2) | −0,1% | 10,5% | 0,04 [−0,31; 0,41] | 0,06 | −53,4% | −0,00 | 57% | 0,07 |
| TREND3 | −1,4% | 10,4% | −0,08 [−0,45; 0,31] | −0,12 | −56,5% | −0,03 | 65% | 0,02 |

### Panel B: 7 cặp FX + vàng + bạc

| Chiến lược | CAGR | Vol | Sharpe [CI 95%] | Sortino | MaxDD | Calmar | % năm lỗ | DSR |
|---|---|---|---|---|---|---|---|---|
| TSMOM 12m | +3,0% | 10,4% | 0,33 [−0,08; 0,75] | 0,47 | −26,6% | 0,11 | 52% | 0,49 |
| MA 50/200 | −0,3% | 10,4% | 0,02 [−0,36; 0,41] | 0,03 | −59,2% | −0,01 | 57% | 0,06 |
| Donchian 55/20 | −0,5% | 10,4% | 0,01 [−0,39; 0,39] | 0,01 | −39,1% | −0,01 | 48% | 0,05 |
| Carry k=3 (chỉ FX) | +1,7% | 10,4% | 0,21 [−0,19; 0,63] | 0,29 | −56,6% | 0,03 | 48% | 0,27 |
| RSI2 10/90 | −0,3% | 10,3% | 0,02 [−0,34; 0,38] | 0,03 | −40,8% | −0,01 | 52% | 0,06 |
| Bollinger 20/2 | −2,4% | 10,4% | −0,17 [−0,56; 0,21] | −0,24 | −49,5% | −0,05 | 61% | 0,01 |
| Mua-và-giữ cùng vol | +1,8% | 10,3% | 0,22 [−0,20; 0,62] | 0,31 | −56,0% | 0,03 | 48% | 0,28 |
| **COMBO4 (trend3+carry)** | +2,0% | 10,4% | 0,23 [−0,15; 0,64] | 0,33 | −45,5% | 0,04 | 44% | 0,31 |
| COMBO5 (+RSI2) | +1,5% | 10,5% | 0,19 [−0,21; 0,60] | 0,26 | −51,4% | 0,03 | 48% | 0,23 |
| TREND3 | +1,2% | 10,4% | 0,16 [−0,25; 0,58] | 0,23 | −46,6% | 0,03 | 44% | 0,20 |

**Mọi CI 95% đều chứa 0.** Không chiến lược nào, kể cả tốt nhất, phân biệt được với Sharpe bằng 0 ở mức tin cậy thông thường.

Benchmark thuần (không đòn bẩy, cửa sổ tương tự): SPY tổng lợi suất CAGR 10,3%, Sharpe 0,61, MaxDD −55%; vàng (GC=F, chưa trừ lãi vay) CAGR 12,4%, Sharpe 0,74, MaxDD −44%. **Mua-và-giữ cổ phiếu hoặc vàng thắng mọi chiến lược trong nghiên cứu này** ở vol thực của chúng, nhưng đó cũng là mẫu một chiều (thị trường tăng dài) và không cùng mục tiêu rủi ro.

Hình: `research/figures/fig1_equity_dd_*.png` (vốn và drawdown), `fig4_sharpe_ci_*.png`, `fig9_yearly_*.png` (lợi suất theo năm).

### 3.1 Chi phí và carry ăn bao nhiêu (panel A, Sharpe)

| Chiến lược | Không phí | Cơ sở | Xấu (2x spread, markup 1%) |
|---|---|---|---|
| TSMOM | 0,17 | 0,05 | −0,08 |
| MA 50/200 | 0,00 | −0,13 | −0,25 |
| Donchian | 0,03 | −0,08 | −0,19 |
| Carry | 0,37 | 0,21 | 0,05 |
| RSI2 | 0,36 | 0,19 | 0,03 |
| COMBO4 | 0,22 | −0,01 | −0,23 |

Trên panel B: TSMOM 0,46 → 0,33 → 0,20; COMBO4 0,45 → 0,23 → 0,01. **Chi phí và swap tiêu hao khoảng 0,12-0,24 Sharpe**, tương đương toàn bộ hoặc phần lớn edge. Gánh nặng chủ yếu là markup swap trên notional có đòn bẩy 1,5-3x (chứ không phải spread; spread chỉ 0,2-1,7%/năm; RSI2 chịu spread nặng nhất do vòng quay 127 lần/năm). Hình `fig7_costs_*.png`.

## 4. Kiểm chứng độ bền

### 4.1 Trước/sau công bố (2002-2011 so với 2012-nay), Sharpe

| Chiến lược | A: 2002-11 | A: 2012+ | B: 2002-11 | B: 2012+ |
|---|---|---|---|---|
| TSMOM | 0,37 | −0,17 | 0,61 | 0,15 |
| MA 50/200 | 0,41 | −0,49 | 0,70 | −0,44 |
| Donchian | 0,14 | −0,22 | 0,21 | −0,12 |
| Carry | 0,63 | −0,07 | 0,64 | −0,07 |
| RSI2 | 0,29 | 0,13 | 0,31 | −0,16 |
| COMBO4 | 0,51 | −0,35 | 0,78 | −0,13 |

Hầu hết chiến lược (trừ Bollinger) dương trước 2012 và suy giảm sau. Lưu ý: tham số lấy từ văn liệu có mẫu chồng lên giai đoạn này (MOP dùng 1985-2009), nên **2002-2011 không phải out-of-sample thực sự**; giai đoạn 2012+ thì gần như là. Đáng chú ý nhất: kết quả ngoài mẫu gần với "không có edge". `fig8_rolling_sharpe_*.png` cho thấy Sharpe trượt 3 năm dao động mạnh, không ổn định.

### 4.2 Khủng hoảng (lợi suất trong năm, panel B; panel A tương tự)

| Chiến lược | 2008 | 2015 | 2020 | 2022 | Ngày CHF 15/01/2015 |
|---|---|---|---|---|---|
| TSMOM | +2,9% | +6,6% | +14,5% | +17,2% | −4,5% |
| MA 50/200 | +2,4% | +2,6% | +8,3% | +14,5% | −4,3% |
| Donchian | +8,4% | −6,0% | +9,7% | +9,7% | −3,9% |
| Carry | **−20,3%** | **−16,7%** | **−11,7%** | +2,9% | −4,9% |
| RSI2 | −7,1% | +1,3% | −2,7% | +11,2% | −1,2% |
| Bollinger | −7,2% | +3,9% | −11,5% | −6,9% | +4,7% |
| COMBO4 | −5,8% | −7,1% | +12,8% | +17,7% | −6,2% |

Trend-following làm đúng vai "bảo hiểm khủng hoảng" ở 2008/2020/2022 (nhất quán với văn liệu) nhưng bị lỗ trong cú sốc đột ngột như CHF. Carry thua nặng đúng lúc rủi ro tăng, ba lần trong 18 năm. **Số ngày CHF là cận dưới:** dữ liệu close chỉ ghi giá cuối ngày; thực tế gap vượt stop có thể gây lỗ lớn hơn (tài khoản bán lẻ có đòn bẩy cao có thể mất toàn bộ).

### 4.3 Độ nhạy tham số (lưới nhỏ, ghi cả vùng xấu; `fig5_sensitivity_*.png`)

Panel A, Sharpe sau chi phí: TSMOM lookback 3/6/12/18 tháng = 0,16 / 0,00 / 0,04 / −0,02; MA (20/50, 20/100, 50/200, 100/250) = −0,06 / 0,06 / −0,13 / −0,11; Donchian (20/10, 55/20, 100/50) = −0,24 / −0,08 / 0,11; RSI2 (5/95, 10/90, 20/80) = 0,10 / 0,19 / 0,03; Bollinger −0,11 đến −0,15; Carry k=2 / k=3 = 0,31 / 0,21. Không có vùng ổn định nào: chênh lệch giữa các cấu hình lớn hơn chênh lệch giữa chiến lược, đúng đặc trưng của nhiễu. Trong 38 cấu hình, kết quả tốt nhất (carry k=2: 0,31) không đáng tin vì là cực đại của 38 lần thử.

### 4.4 Walk-forward (chọn cấu hình trend tốt nhất theo 5 năm gần nhất, áp dụng năm sau; OOS 2007-2026)

| | Panel A Sharpe | Panel B Sharpe |
|---|---|---|
| Walk-forward (11 cấu hình trend) | −0,02 | −0,07 |
| TSMOM 12m cố định | −0,11 | 0,19 |
| MA 50/200 cố định | −0,31 | −0,17 |
| Donchian 55/20 cố định | −0,17 | −0,04 |
| Trung bình đều 11 cấu hình | −0,20 | −0,04 |

Việc "tối ưu thích nghi" không cải thiện: cấu hình được chọn đổi liên tục (lb 63, 126, 378, MA 20/100...). TSMOM 12m cố định trên panel B tốt hơn walk-forward nhưng chỉ là một cấu hình trong 11; sự vượt trội đến từ kim loại (mục 4.7), không chứng minh việc chọn tham số cố định tốt hơn thích nghi.

### 4.5 Kiểm soát dịch-thời-gian (panel A, 300 mẫu; `fig6_random_baseline_A.png`)

Tín hiệu mỗi instrument bị dịch vòng ngẫu nhiên ≥ 1 năm (giữ nguyên tỷ lệ long/short, số lần đảo chiều, thời gian ngoài thị trường), chạy qua cùng engine và chi phí. Hạng của chiến lược thật trong phân phối này: TSMOM 92%, Donchian 75%, MA 68%, Bollinger 62%, Carry 71%, **RSI2 98%**. Mọi giá trị ngoài RSI2 không đạt 95%. Phân phối ngẫu nhiên lệch âm (trung bình −0,25 với trend) vì chi phí; so sánh với 0 là không công bằng, so sánh với phân phối này mới đúng. Carry ngẫu nhiên +0,14: một phần lớn "carry" thu được từ vị thế cấu trúc (luôn long AUD/NZD, short JPY/CHF) chứ không phải thời điểm.

### 4.6 Tương quan (`fig3_corr_*.png`)

TSMOM-MA 0,57-0,64, TSMOM-Donchian 0,29-0,33, Donchian-Bollinger **−0,73**; carry gần như độc lập với trend (0,01-0,07). Tức: đa dạng hóa trend + carry có cơ sở lý thuyết, nhưng hai thành phần đều có edge ≈ 0 sau chi phí nên tổng không dương.

### 4.7 Từng instrument riêng lẻ (Sharpe, panel B)

| | TSMOM | MA | Donchian | Mua-và-giữ vol 10% |
|---|---|---|---|---|
| EURUSD | −0,02 | 0,16 | 0,02 | 0,00 |
| USDJPY | 0,30 | −0,06 | 0,21 | −0,46 |
| AUDUSD | 0,29 | 0,03 | −0,10 | 0,16 |
| USDCAD | −0,13 | −0,20 | −0,22 | −0,12 |
| USDCHF | −0,12 | −0,07 | −0,14 | 0,10 |
| **Vàng** | 0,49 | 0,38 | 0,20 | **0,64** |
| Bạc | 0,36 | 0,19 | −0,02 | 0,42 |

Edge trend nằm ở kim loại; nhưng với kim loại, "luôn long" còn tốt hơn "theo xu hướng". Trên FX, kết quả rải rác quanh 0, đúng dạng nhiễu.

## 5. Kết luận thực tế

| Chiến lược | Bằng chứng | Phán đoán |
|---|---|---|
| TSMOM / MA / Donchian trên FX | Gộp Sharpe −0,13…+0,05; mất edge sau 2012 | **Không có bằng chứng bền** |
| Trend trên vàng/bạc | Sharpe 0,2-0,5 nhưng thua mua-và-giữ; phụ thuộc xu hướng tăng 20 năm | **Không tách được khỏi "vàng tăng"**; không nên coi là edge của chiến lược |
| FX carry | Sharpe 0,21 (CI −0,20…0,63), 3 lần thua 12-20%/năm; sau 2012 −0,07 | **Premium có thật trong văn liệu nhưng ở mẫu này mỏng, nhiều rủi ro đuôi**; không phải "tiền miễn phí" |
| RSI2 | 98% hạng so với kiểm soát trên FX; nhưng biến mất ở panel B, mong manh với chi phí, nghi ngờ nhiễu fix | **Không tin**; chỉ đáng kiểm tra lại bằng dữ liệu giao dịch thật |
| Bollinger | Âm ở mọi kịch bản | Bỏ |
| Kết hợp đa chiến lược | −0,01 (FX) / 0,23 (FX+kim loại) | Giảm biến động, không tạo edge |

**Kỳ vọng hợp lý:** với dữ liệu close và chi phí retail bảo thủ, kỳ vọng Sharpe ròng 0 đến 0,3 trên danh mục đa dạng, CAGR 0-3% ở vol 10%, drawdown 30-60% và khoảng 45-60% số năm thua. Thời gian dưới nước dài 11-24 năm (nhiều chiến lược hầu như không bao giờ vượt đỉnh trong mẫu). Nếu hệ thống nhắm vào giao dịch FX bán lẻ, **các chiến lược kinh điển này không đủ để biện minh cho rủi ro vốn thật**; nên coi chúng là baseline để so sánh với ý tưởng mới và ưu tiên thử nghiệm giả lập/paper (đã theo PLAN.md), không phải nguồn lợi nhuận đã được chứng minh.

## 6. Cảnh báo giới hạn và tính trung thực của nghiên cứu

- **Bậc tự do của người nghiên cứu (tôi đã chạm vào):** (1) lần chạy đầu dùng markup swap 1%/năm; thấy kết quả quá nặng nên **đổi cơ sở sang 0,5%** và giữ 1% làm kịch bản xấu. Cả hai mức đều được báo cáo, nhưng đây là một lựa chọn sau khi thấy dữ liệu. (2) Lần đầu kiểm soát dùng tín hiệu ngẫu nhiên luôn có vị thế, so sánh không công bằng với RSI2 (thường đứng ngoài), nên **thay bằng kiểm soát dịch-thời-gian**. (3) Việc loại Yahoo FX và WTI là theo kiểm tra chất lượng dữ liệu, không theo kết quả. (4) DSR dùng N = 38 (lưới × 2 panel); các quyết định thiết kế như trên không được tính, nên DSR **lạc quan** (thực tế khắt khe hơn).
- **In-sample:** tham số cố định theo văn liệu, không tối ưu trên dữ liệu này, nhưng văn liệu (turtle, MOP, carry) chồng lên 2002-2011.
- **Dữ liệu:** giá fix ECB (không giao dịch được, không bid/ask, nhiễu thời điểm); vàng/bạc là futures liên tục chưa điều chỉnh roll và lệch giờ so với FX; lãi suất là chuỗi tháng xấp xỉ forward points (bỏ qua cross-currency basis); JPY 1999-2002 điền tay; **chưa kiểm tra chéo Dukascopy**.
- **Chi phí:** spread/markup là giả định điển hình; không có trượt giá, gap qua đêm/dừng lỗ, hay chi phí rollover thực tế của broker cụ thể. Đòn bẩy trung bình 1,5-2,9x và tối đa 6x.
- **Phạm vi:** chỉ 7 cặp + 2 kim loại (văn liệu dùng 24-58 tài sản); thiếu nhóm cổ phiếu/trái phiếu/hàng hóa nên bất lợi cho trend. Carry không trừ phí giao dịch của forward thật.
- **Thống kê:** 23,7 năm là ngắn so với Sharpe ~0,2 (cần hàng chục năm để phân biệt). Block bootstrap giả định độc lập giữa các khối.
- **Chưa làm:** Dukascopy/tick, tác động phiên (Á/Âu/Mỹ), mô hình hóa regime, phân tích theo loại phí broker cụ thể, sau thuế (theo yêu cầu).

## 7. Tái lập

```
cd D:\Work\trading-system
.venv\Scripts\python.exe research\fetch_data.py      # tải dữ liệu -> research/data/*.parquet (gitignore)
.venv\Scripts\python.exe research\tests_sanity.py    # kiểm chứng engine
.venv\Scripts\python.exe research\run_study.py       # ~80 giây; sinh results/*.csv, summary.md, figures/*.png
```
Seed 20261011 cố định. Bảng đầy đủ: `research/results/summary.md` (+ CSV từng bảng, `grid_all_trials.csv` liệt kê 38 cấu hình). Lưu ý: dữ liệu Yahoo/FRED được tải lại mỗi lần fetch nên kết quả sẽ thay đổi nhẹ khi dữ liệu cập nhật; cửa sổ đánh giá bị cắt ở tháng có dữ liệu lãi suất đầy đủ.
