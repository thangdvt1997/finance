# Backtest trend chậm đa tài sản (1990–2026): có qua kiểm định không?

Ngày: 2026-10-11. Mã: `research/multiasset/`. Kết quả thô: `research/results/ma_*.csv`, `ma_analysis.json`. Hình: `research/figures/ma_fig*.png`. Cấu hình đề xuất cho paper-trader: `research/strategies/slow_trend_multiasset.yaml`.
Toàn bộ tính toán chạy trên VPS <VPS_IP> (thư mục `/root/research`, container `python:3.12-slim`, `nice -n 19`, `--cpus 6 --memory 16g`); laptop chỉ sửa file.

## 0. Kết luận thẳng

| Câu hỏi | Trả lời |
|---|---|
| Trend chậm đa tài sản có sinh lời dương sau chi phí không? | **Có, nhưng khiêm tốn**: Sharpe 0,55 (CI95 0,21–0,87), CAGR tổng 8,0%/năm ở vol 9,5%, MaxDD −23,5% (1990–2026). |
| Có tốt hơn 60/40 không? | **Không.** 60/40: Sharpe 0,60, CAGR 9,0%, MaxDD −31,5%. Chênh lệch Sharpe (trend − 60/40) có CI95 [−0,55; +0,42], p(≤0) = 0,61: không phân biệt được với 0. Trend chỉ thắng 38% số năm. |
| Có qua kiểm định không? | **Qua một phần.** *Qua*: Sharpe > 0 (p<0,001), thắng placebo dịch tín hiệu (p = 0,7%), tương quan ≈ 0 với 60/40, "crisis alpha" thật ở 2000–02, 2008, 2020, 2022. *Không qua*: Deflated Sharpe 0,87 (< 0,95 đã đặt từ trước; 0,74 nếu tính 200 lần thử), **không thắng 60/40 độc lập**, suy giảm theo thời gian (Sharpe 0,67 → 0,74 → **0,16** (2010–19) → 0,59; toàn bộ danh mục đủ 35 tài sản từ 2012: **0,29**), tham số nhạy (lookback 3–6 tháng chỉ 0,11–0,28), walk-forward có chọn cấu hình *kém hơn* tham số cố định. |
| Nên dùng thế nào? | Như **lớp đa dạng hoá / bảo hiểm đuôi** (20–30% rủi ro) cạnh danh mục cổ phiếu/trái phiếu, **không** như nguồn lợi nhuận độc lập. Pha trộn 70% 60/40 (vol-matched) + 30% trend: Sharpe 0,61 → 0,79, MaxDD −30% → −18% (trong mẫu), CAGR gần như không đổi. |
| Kỳ vọng thực tế đi tới | Sharpe sau chi phí **0,3–0,5**; ở vol 10%: lợi suất excess **3–5%/năm**, MaxDD **−20% … −30%**, ~30% số năm âm, có thể nằm dưới đỉnh 4–5 năm. Thấp hơn trung bình lịch sử. |

Biến thể "long-flat" (chỉ mua khi xu hướng lên) có Sharpe 0,80 nhưng **không** nên nhầm là phát hiện: placebo cho thấy một tín hiệu dịch ngẫu nhiên đã đạt Sharpe trung bình 0,57 (do thiên lệch mua dài hạn của cổ phiếu/trái phiếu); phần timing thực chỉ thêm ~0,23, và biến thể này **không** có crisis alpha (tháng 60/40 tệ nhất: −0,8%).

## 1. Dữ liệu

### 1.1 Nguồn thật sự dùng được từ VPS (đã kiểm tra thật)
| Nguồn | Kết quả | Dùng cho |
|---|---|---|
| Yahoo chart API (cần User-Agent, ~1 req/s; đòi `period1/period2`, `range=max` trả về dữ liệu tháng) | OK | 14 chỉ số cổ phiếu, ETF hàng hóa/nông sản, vàng/bạc/đồng futures liên tục, BTC/ETH |
| FRED `fredgraph.csv` (không cần key) | OK | lợi suất UST 2/5/10/20/30y, T-bill 3M (DTB3), WTI/Brent spot, lãi suất liên ngân hàng 3M (OECD, tháng) |
| Frankfurter (ECB) | OK (chuyển hướng sang `api.frankfurter.dev/v1`) | 7 cặp FX major từ 1999 |
| Stooq | **Chặn** (thử thách JavaScript) | — |
| Dukascopy `.bi5` | **HTTP 429** từ VPS | — (không dùng; market-collector chạy trên cùng IP) |
| Binance API | HTTP 451; `data.binance.vision` 200 nhưng không cần vì Yahoo có BTC/ETH | — |
| VN-Index | Yahoo không có `^VNINDEX`; VNDirect bị Cloudflare chặn; `vnstock` không cài được trên Python 3.12 slim | **Chỉ có ETF VNM (USD, từ 2009-08)** — thiếu VN-Index thật |
| Tiingo / Alpha Vantage / Twelve Data / Nasdaq Data Link | Không có key → bỏ qua | — |
| CFTC | Truy cập được (200), không dùng (trend chậm không cần COT) | — |

### 1.2 Cách dựng chuỗi lợi suất (mọi tài sản quy về "excess" so với tiền mặt USD, tương đương hợp đồng tương lai)
- **Cổ phiếu (14)**: chỉ số giá Yahoo + cổ tức giả định **hằng số** theo chỉ số (S&P 2,0%; Nasdaq 0,9%; FTSE 3,8%…; DAX là performance index nên q = 0) − lãi T-bill. Đây là giả định thô (cổ tức thực thay đổi theo thời gian); đối chiếu SPY: tương quan ngày 0,985, lợi suất excess 9,4% vs 9,2%/năm.
- **Trái phiếu (4)**: **proxy** từ lợi suất CMT của FRED, định giá lại trái phiếu par (coupon = yield t−1, đáo hạn M − dt) rồi trừ lãi T-bill. Đối chiếu ETF: IEF tương quan 0,958; TLT 0,944; SHY 0,896 (lợi suất excess lệch ≤ 0,4%/năm). Không có trái phiếu ngoài Mỹ (Bund/JGB/Gilt): **không có chuỗi ngày miễn phí**.
- **FX (7)**: ECB spot + carry = chênh lãi suất liên ngân hàng 3M (OECD, trễ 1 tháng). Lãi EUR/GBP chỉ có đến 2026-01 → giữ nguyên sau đó (carry giai đoạn cuối xấp xỉ).
- **Kim loại**: vàng = futures liên tục GC=F (2000–2004-11) rồi GLD; bạc SI=F → SLV; đồng HG=F; trừ lãi tiền mặt. Futures liên tục Yahoo **không điều chỉnh roll** nên là proxy của giá giao ngay (≈ chuỗi spot, hơi lệch). Đồng HG=F so CPER chỉ tương quan 0,62 → **chất lượng kém hơn các lớp khác**.
- **Năng lượng**: WTI = spot FRED (trước 2006-04) rồi ETF USO; Brent = spot FRED (trước 2010-06) rồi BNO; khí tự nhiên = UNG (từ 2007-04). **Giá âm 2020 được xử lý bằng cách dùng ETF liên tục (USO/BNO, giá luôn dương)**; spot FRED chỉ dùng trước 2006/2010 nên mức âm 2020-04-20 không đi vào backtest. Spot không có roll yield nên proxy trước ETF kém hơn (tương quan ngày spot–USO 0,88).
- **Nông sản (4)**: chỉ ETF CORN/WEAT/SOYB/CANE (từ 2010-06/2011-09) — chưa đủ ≥ 20 năm; futures Yahoo không dùng vì roll không điều chỉnh gây nhảy giá giả.
- **Crypto (tuỳ chọn)**: BTC từ 2014-09, ETH từ 2017-11; **không nằm trong lõi**, chỉ chạy kiểm tra mở rộng.
- Tất cả trên lịch ngày thường (Mon–Fri) chung; ngày lễ giữ giá (lợi suất 0), tối đa 7 ngày; ngoài đó coi như chưa có dữ liệu. Loại spike khi |r| > 25% rồi đảo chiều gần hết ngày sau (chỉ xảy ra với chuỗi FRED WTI/Brent 2020-04 không dùng trong backtest). Các cú sốc thật (HSI 1987-10-26 −33%, BVSP 1999-01 +33%) được giữ.
- **Không dùng Parquet nào trong git**: `/root/research/data/` (raw_yahoo, fred, ecb, rates3m, excess_returns, rf…).

### 1.3 Bảng chất lượng dữ liệu (`research/results/data_quality_multiasset.csv`)
| Lớp | Tài sản | Bắt đầu | Số năm | % phiên thiếu* | Ghi chú |
|---|---|---|---|---|---|
| Cổ phiếu | SPX, NDX | 1976 | 50,4 | 3,4 | |
| | RUT / DAX / CAC / FTSE | 1987–1990, 1984 | 39 / 39 / 37 / 43 | 2,6–3,5 | |
| | N225 | 1976 | 50,4 | 5,7 | 3 khoảng trống > 7 ngày |
| | HSI | 1987 | 39,8 | 5,4 | |
| | ASX | 1992 | 33,9 | 11,6 | nhiều ngày thiếu hơn |
| | KOSPI / SENSEX / BVSP | 1996 / 1997 / 1993 | 30 / 29 / 33 | 5–6 | |
| | SX5E | 2007 | 19,5 | 3,9 | |
| | VNM (ETF) | 2009 | 17,1 | 3,6 | proxy VN, USD |
| Trái phiếu | UST2/5/10 (proxy) | 1976 | 50,4 | 4,2 | |
| | UST30 (proxy) | 1977 | 49,6 | 4,2 | |
| FX | 7 cặp | 1999 | 27,8 | 1,8 | ECB, 1 lần/ngày |
| Kim loại | vàng, bạc, đồng | 2000-08 | 26,1 | 3,7 | |
| Năng lượng | WTI | 1986 | 40,8 | 9,6 | spot→USO |
| | Brent | 1987 | 39,4 | 11,0 | spot→BNO; 22 khoảng trống > 7 ngày (spot) |
| | NATGAS | 2007 | 19,5 | 3,6 | |
| Nông sản | CORN | 2010 | 16,3 | 3,6 | |
| | WHEAT/SOY/SUGAR | 2011 | 15,1 | 3,6 | |
| Crypto (ngoài lõi) | BTC / ETH | 2014 / 2017 | 12 / 9 | 0 | |

\* = % phiên Mon–Fri không có quan sát gốc trong khoảng sống của tài sản (chủ yếu ngày lễ) — không phải lỗi dữ liệu. Số tài sản sống tại thời điểm: 14 (1990), 28 (2000/2005), 32 (2010), **35 (2012+)**. Chỉ **2012 trở đi** có đủ 35 tài sản; trước đó danh mục là cổ phiếu + trái phiếu (+ FX/kim loại từ 2000), nên kết quả 1990–2011 dựa nhiều vào hai lớp này.

Kiểm tra chéo (`data_checks.txt`): UST10 vs IEF 0,958; UST30 vs TLT 0,944; SPX vs SPY 0,985; vàng vs GLD 1,000 (cùng nguồn); đồng vs CPER 0,617; WTI spot vs USO 0,878.

## 2. Phương pháp (tham số cố định theo văn liệu, không tối ưu)

- **Tín hiệu** (từng tài sản, trên chỉ số tích luỹ `I = cumprod(1 + r_excess)`):
  1. TSMOM 12−1 (Moskowitz–Ooi–Pedersen 2012: dấu lợi suất 12 tháng bỏ tháng gần nhất);
  2. TSMOM 3 khung 1/3/12 tháng (Hurst–Ooi–Pedersen), trung bình dấu;
  3. Giá trên/dưới SMA 200 ngày;
  4. Donchian dài 200/100 ngày (vào/ra như hệ Turtle, chỉ dùng close).
  **Ensemble = trung bình 4 tín hiệu** (được khai báo là cấu hình CHÍNH trước khi chạy; các tín hiệu đơn là đối chứng). Long/short (±1) là chính; long-flat là đối chứng.
- **Sizing**: vol mục tiêu 10%/năm; vol từng tài sản EWMA span 60; ngân sách rủi ro **cân bằng theo lớp** (6 lớp ngang nhau, trong lớp chia đều) — đây là danh mục "cân bằng rủi ro"; đối chứng: chia đều theo tài sản. Quy mô danh mục `L = min(3, 10% / σ_ex-ante)` với ma trận hiệp phương sai EWMA (halflife 60 ngày, co 20% về đường chéo); tối đa 3x/tài sản, 8x tổng notional (thực tế TB 2,3x, tối đa ~4x). Cân bằng lại **hàng tháng** (đối chứng: hàng tuần).
- **Thực thi bảo thủ**: tín hiệu ở close t → vào lệnh ở close t+1 (lệch múi giờ giữa các sàn) → hưởng lợi suất phiên t+2.
- **Chi phí**: nửa spread + hoa hồng + trượt giá một chiều theo từng tài sản (1–3 bps trái phiếu, 1–2 FX, 2,5–12 cổ phiếu, 3–8 kim loại, 6–15 năng lượng, 10–12 nông sản), **×1,5 trước 2010**; cộng phí duy trì 0,30%/năm trên tổng notional (markup funding/CFD). Chi phí đã hấp thụ −0,11 Sharpe (0,67 → 0,55). Lợi suất "excess" đã bao gồm lãi tài trợ cổ phiếu/FX (carry) theo kiểu hợp đồng tương lai.
- **Chỉ số**: Sharpe tính trên lợi suất excess sau chi phí; CAGR/MaxDD tính trên lợi suất tổng (excess + lãi T-bill). Benchmark: SPX excess; 60/40 (60% SPX, 40% UST10, cân bằng lại hàng ngày, chưa ép vol; bản vol-matched 10% đối chiếu); risk-parity long-only (cân bằng lớp, vol 10%, không FX).
- **Tái sử dụng OSS/mã sẵn có**: pandas/numpy/scipy/statsmodels/matplotlib; `research/engine.py` (metrics, block bootstrap, Deflated Sharpe) và `strategies.py` (Donchian, dịch tín hiệu) của dự án; đối chiếu Sharpe với **quantstats** (khớp đến 4 chữ số: 0,5530). Không dùng vectorbt (giấy phép Commons Clause, đã nêu ở nghiên cứu trước).
- **Kiểm tra engine** (`ma_analysis.json → sanity`): tín hiệu "nhìn trước 21 ngày" cho Sharpe 6,6 (engine phát hiện được rò rỉ); nhìn trước 1 ngày nhưng trễ 2 phiên → −0,32 (không rò); 20 tín hiệu ngẫu nhiên → Sharpe TB −0,27 (không dương giả; âm do chi phí).

## 3. Kết quả chính (1990-02 → 2026-10, sau chi phí)

| Cấu hình | Sharpe | CI95 (bootstrap khối 21 ngày) | Vol | CAGR tổng | MaxDD | Skew | Năm âm |
|---|---|---|---|---|---|---|---|
| **Ensemble L/S, hàng tháng (CHÍNH)** | **0,55** | 0,21 – 0,87 | 9,5% | 8,0% | −23,5% | −0,26 | 29% |
| Ensemble L/S, hàng tuần | 0,55 | — | 9,3% | 7,8% | −17,8% | −0,23 | 26% |
| Ensemble long-flat (đối chứng) | 0,80 | 0,47 – 1,13 | 7,6% | 9,1% | −16,7% | −0,39 | 23% |
| TSMOM 12−1 (tháng) | 0,68 | — | 10,4% | 10,0% | −23,0% | −0,33 | |
| TSMOM 1/3/12 | 0,46 | — | 9,3% | 6,9% | −21,6% | −0,13 | |
| MA200 | 0,35 | — | 10,5% | 6,1% | −30,7% | −0,11 | |
| MA100/200 | 0,12 | — | 10,3% | 3,5% | −30,7% | −0,41 | |
| Donchian 200/100 | 0,46 | — | 9,9% | 7,2% | −29,2% | −0,27 | |
| **60/40 (SPX/UST10)** | **0,60** | 0,34 – 0,90 | 10,5% | 9,0% | −31,5% | −0,04 | 20% |
| Risk parity long-only | 0,58 | — | 11,1% | 9,1% | −40,9% | −0,44 | 31% |
| S&P 500 | 0,51 | — | 17,6% | 11,0% | −55,5% | −0,14 | 20% |

Hình: `ma_fig1_equity_dd.png` (đường vốn + drawdown), `ma_fig2_yearly.png` (lợi suất theo năm), `ma_fig8_rolling_sharpe.png`.

Lưu ý khi đọc: TSMOM 12−1 đơn có Sharpe 0,68 cao hơn ensemble, nhưng chọn nó sau khi xem kết quả là *data snooping* — ensemble được chốt trước và cũng là cấu hình ổn định hơn theo tham số (xem §4.3). Trung bình 21 cấu hình đơn trong lưới độ nhạy: Sharpe trung vị 0,35.

### 3.1 Theo giai đoạn (Sharpe / CAGR tổng / MaxDD)
| Giai đoạn | Trend L/S | Trend long-flat | 60/40 | Risk parity LO | S&P |
|---|---|---|---|---|---|
| 1990–1999 | 0,67 / 12,2% / −15% | 1,09 | 0,89 / 13,9% / −13% | 0,87 | 0,86 |
| 2000–2009 | 0,74 / 10,5% / −12% | 0,90 | 0,08 / 2,9% / −32% | 0,94 | −0,04 |
| 2010–2019 | **0,16** / 1,6% / −24% | 0,28 | 1,15 / 10,1% / −11% | 0,11 | 0,88 |
| 2020–2026 | 0,59 / 8,1% / −15% | 0,81 | 0,57 / 9,6% / −21% | 0,31 | 0,69 |
| 2012–2026 (đủ 35 TS) | **0,29** / 3,9% / −17% | 0,50 | 0,81 / 9,8% / −21% | 0,08 | 0,83 |
Hai nửa mẫu: Sharpe 0,73 (1990 → 2008-06) và **0,36** (2008-06 → 2026), trong khi 60/40 tăng 0,56 → 0,65.

### 3.2 Các năm sự kiện (lợi suất năm, `ma_events.csv`)
| Năm | Trend L/S | Long-flat | 60/40 | S&P (excess) |
|---|---|---|---|---|
| 2008 | **+20,2%** | +4,2% | −17,4% | −38,1% |
| 2013 | +7,4% | +1,0% | +14,3% | +32,1% |
| 2015 | +10,3% | −0,6% | +1,6% | +1,2% |
| 2018 | −5,5% | −4,3% | −3,9% | −6,2% |
| 2020 | +18,8% | +11,1% | +17,0% | +18,2% |
| 2022 | **+14,1%** | +4,0% | −18,3% | −19,4% | 
| 2023 | **−10,3%** | −3,5% | +11,6% | +20,5% |
| 2025 | +5,1% | +10,8% | +10,2% | +14,0% |
Mẫu hình: trend thắng khi thị trường giảm kéo dài (2008, 2022), thua khi đảo chiều V (2018Q4, 2023, 2025Q1) và bị kẹt trong thị trường tăng kiểu 2013.

## 4. Kiểm định

### 4.1 Ý nghĩa thống kê và đa lần thử
- Bootstrap khối (21 ngày, 2000 lần): Sharpe 0,55, CI95 [0,21; 0,87], P(Sharpe ≤ 0) = 0,05%.
- **Deflated Sharpe** (Bailey–López de Prado) với **52 cấu hình đã chạy** (14 cấu hình chính × 2 tần suất, 8 biến thể thực thi, 30 điểm lưới độ nhạy; phương sai Sharpe giữa các lần thử thật): ngưỡng kỳ vọng của max-trong-52 là Sharpe 0,37 → **DSR = 0,87** (< 0,95 → **không qua** ở mức tin cậy thông thường); nếu coi như đã thử 200 cấu hình: 0,74. PSR(0) = 0,9997 (tức Sharpe > 0 chắc chắn, nhưng không vượt rõ ràng ngưỡng của việc thử nhiều lần). Long-flat: DSR 0,995 (nhưng xem §4.2).
- **So với 60/40** (bootstrap khối cặp đôi): Δ Sharpe CI95 [−0,55; +0,42] (L/S) và [−0,23; +0,58] (long-flat): **không thể khẳng định trend hơn 60/40**.

### 4.2 Placebo / kiểm soát thời gian (`ma_fig4_placebo.png`)
Dịch vòng tròn tín hiệu từng tài sản một độ lệch ≥ 1 năm (giữ nguyên tỉ lệ long/short, số lần đổi chiều; chỉ phá quan hệ với giá thật), 300 lần:
- L/S: Sharpe placebo TB 0,11 (SD 0,18, p95 = 0,39); thật 0,55 → **p = 0,7%**: tín hiệu *có thông tin thời điểm*.
- Long-flat: placebo TB **0,57** (SD 0,09); thật 0,80 → p = 0,3%, nhưng **phần lớn Sharpe là thiên lệch mua dài hạn**; timing thật chỉ cộng ≈ 0,23.

### 4.3 Độ nhạy tham số (`ma_sensitivity.csv`, `ma_fig3_sensitivity.png`; lưới 21 cấu hình đơn)
- Sharpe trung vị 0,35, thấp nhất 0,11, cao nhất 0,69; **100% > 0** nhưng chỉ **2/21 > 0,6**; 15/21 > 0,3.
- TSMOM: 3 tháng 0,14–0,24; 6 tháng 0,11–0,28; 9 tháng 0,41–0,47; **12 tháng 0,68–0,69**; 18 tháng 0,34–0,38 → đỉnh duy nhất ở 12 tháng (đúng văn liệu, nhưng đỉnh nhọn nên một phần có thể là may mắn mẫu).
- MA: 50–100 ngày 0,17–0,28 (vùng xấu); 200 ngày 0,35; 250–300 ngày 0,47–0,54 (chậm hơn lại tốt hơn). Donchian: 0,34–0,57.
- Vol mục tiêu 6–15%: Sharpe không đổi (0,553), CAGR/MaxDD tỉ lệ (6%: 6,0% / −14,7%; 15%: 10,3% / −33,5%). Cap đòn bẩy: lmax 1,5 → vol 5,1%, Sharpe 0,56, MaxDD −12,6%; lmax 6 → 0,61.
- Chi phí ×0 / ×1 / ×2 / ×3: Sharpe **0,67 / 0,55 / 0,44 / 0,33** → chiến lược nhạy với chi phí; nếu chi phí thực > 2x giả định thì Sharpe < 0,45. Bỏ trễ 1 phiên: 0,61.
- Cân bằng lớp vs chia đều theo tài sản: 0,55 vs 0,69 (chia đều nghiêng về cổ phiếu 14/35 tài sản — nghiêng về beta cổ phiếu/trái phiếu trong mẫu). Cân bằng lớp được giữ vì chốt trước và đa dạng hơn.

### 4.4 Walk-forward có chọn cấu hình
Mỗi tháng 12 từ 1996, chọn trong 14 cấu hình chính cái có Sharpe 5 năm trước cao nhất rồi dùng năm sau: Sharpe **0,46** < tham số cố định 0,51 (cùng giai đoạn) < 60/40 0,58; trộn đều 14 cấu hình 0,54. Chọn thay đổi 16 lần/30 năm, 12 cấu hình khác nhau → không có ổn định để khai thác; **giữ tham số cố định**.

### 4.5 Phụ thuộc vào lớp/tài sản (`ma_fig5_contrib.png`, `ma_fig6_loco.png`)
Đóng góp P&L (trước chi phí, ~6,3%/năm): **trái phiếu 40%**, cổ phiếu 27%, kim loại 14%, FX 11%, năng lượng 6%, nông sản 2%. Riêng 1990–2000, trái phiếu đóng góp 6,1%/năm trên tổng ~7,5% (thị trường bull lãi suất); 2020–26 lại do nông sản/năng lượng/kim loại/trái phiếu (cổ phiếu chỉ 0,3%).
| Loại bỏ | Sharpe | MaxDD |
|---|---|---|
| Tất cả (35) | 0,55 | −23,5% |
| bỏ cổ phiếu | 0,43 | −30,2% |
| bỏ trái phiếu | 0,41 | −25,4% |
| bỏ FX | 0,55 | −22,9% |
| bỏ kim loại | 0,53 | −21,9% |
| bỏ năng lượng | 0,64 | −21,9% |
| bỏ nông sản | 0,55 | −24,0% |
| **bỏ vàng** | 0,53 | −25,4% |
| bỏ trái phiếu + vàng | 0,37 | −27,6% |
| chỉ cổ phiếu + trái phiếu | 0,63 | −19,0% |
| chỉ hàng hóa + FX | 0,39 | −31,3% |
Bỏ từng tài sản một (35 lần): Sharpe 0,51–0,58 → **không phụ thuộc một tài sản đơn lẻ (kể cả vàng)** nhưng **phụ thuộc lớp cổ phiếu + trái phiếu**; hàng hóa/FX riêng lẻ chỉ ~0,39. Bỏ năng lượng cải thiện (0,64) nhưng đây là quan sát *sau khi xem kết quả* nên **không** dùng để cắt lớp tài sản. Thiên lệch ròng trung bình: trái phiếu +0,45x notional (lệch mua dài hạn của lãi suất giảm), cổ phiếu +0,17x.

### 4.6 Tương quan với 60/40, đuôi, "crisis alpha" (`ma_fig7_tail_corr.png`, `ma_crisis_episodes.csv`)
- Tương quan tháng với 60/40: **−0,08**; với S&P: **−0,15** (long-flat: +0,29).
- Hồi quy tháng trên 60/40 (HAC): alpha **6,0%/năm (t = 3,6)**, beta −0,09 (t = −0,9). Hồi quy bậc hai trên S&P (kiểu Fung–Hsieh): γ = +1,48 (t = 2,2) → có dạng lồi/"smile" nhẹ.
- 45 tháng tệ nhất của 60/40 (−4,5% TB): trend L/S **+1,0% TB, dương 58% số tháng** (long-flat −0,8%).
- Các đợt 60/40 giảm ≥ 10%: 2000-09→2002-07 (60/40 −28,7%): trend **+15,6%**; 2007-10→2009-03 (−32,7%): **+35,1%**; 2020-02→03 (−18,8%): **+19,3%**; 2021-12→2022-10 (−22,1%): **+24,2%**; nhưng 1994 (−10,3%): **−9,6%**; 2018Q4: −4,2%; 2024-12→2025-04: −5,6% — thất bại khi đảo chiều nhanh hoặc "lạm phát/lãi suất gây thua cả hai".
- Vì tương quan âm nhẹ, pha trộn có lợi: 80% 60/40(vol-matched) + 20% trend: Sharpe 0,73, MaxDD −21,9%; 70/30: 0,79, −17,9%; 50/50: 0,85, −10,0% (CAGR ~8,7–8,9% không đổi; **trong mẫu**, đòn bẩy vol-match là giả định).
- Chiều ngược lại: trend thua nặng khi cổ phiếu bull êm (2013 +7% so với 60/40 +14%; 2023 −10% vs +12%) — đó là "chi phí bảo hiểm".

### 4.7 Mở rộng crypto (tuỳ chọn)
Thêm BTC/ETH (lớp riêng): Sharpe 0,63 (toàn mẫu), từ 2018: 0,43 vs 0,39 không crypto — cải thiện nhỏ và ngắn, rủi ro vận hành cao → **không đưa vào lõi**.

## 5. Điều kiện áp dụng và giới hạn trung thực
1. Là **bảo hiểm/đa dạng hoá**, không phải máy tạo lợi nhuận: nửa sau của mẫu Sharpe 0,36; cả thập kỷ 2010–19 hầu như không sinh lời (1,6%/năm). Cần chấp nhận nhiều năm không có lãi, MaxDD ~−20–30% và ~30% số năm âm.
2. **Chi phí** phải ≤ ~1,5x giả định; trên CFD/spread bán lẻ có thể mất phần lớn lợi thế (×2 → Sharpe 0,44, ×3 → 0,33). Ưu tiên futures/ETF thanh khoản; tránh năng lượng/nông sản ETF nếu không quản được contango.
3. **Dữ liệu là proxy**: không có futures roll thật (kim loại/đồng), trái phiếu tổng hợp từ lợi suất, cổ tức cổ phiếu giả định hằng số, VN-Index không có (chỉ ETF VNM), không có trái phiếu ngoài Mỹ. Kết quả 1990–2011 chủ yếu từ cổ phiếu + trái phiếu; hàng hóa nông sản chỉ từ 2010–11; 35 tài sản chỉ đủ từ 2012. Sai khác nhỏ trên từng proxy không đổi kết luận định tính nhưng sai số của mức Sharpe ±0,1 là chuyện thường.
4. Mẫu 36 năm chỉ chứa **một** chế độ lãi suất giảm dài hạn (đến 2020) có lợi cho phía long trái phiếu; đã tách phần này (§4.5) nhưng không thể loại hẳn.
5. Chi phí biến động thực, thuế, margin call, giới hạn short của ETF, rủi ro đứt cầu giao dịch (gap) **chưa mô hình hoá**. Lợi suất excess giả định đòn bẩy futures (TB 2,3x notional, tối đa ~4x); bản không đòn bẩy (`lmax 1`, vol 3,4%) giữ Sharpe 0,56 nhưng CAGR thấp (4,8%).
6. Đã thử 52 cấu hình (nêu trong §4.1); mọi cấu hình đều đã được tính vào Deflated Sharpe. Những phát hiện *sau khi xem* (long-flat, bỏ năng lượng, chia đều theo tài sản) được liệt kê nhưng **không** dùng làm cơ sở chọn tham số.

## 6. Đề xuất cho paper-trader (xem `research/strategies/slow_trend_multiasset.yaml`)
- **Vị thế**: lớp đa dạng hoá, ghi nhận song song với 60/40 và risk-parity; **chưa** đủ cơ sở để dùng tiền thật độc lập. Mục tiêu của paper là kiểm chứng *kỹ thuật* (tín hiệu/trọng số khớp backtest, chi phí thực tế, tương quan với 60/40) — 12 tháng paper không đủ để chứng minh lợi nhuận vì thập kỷ có thể toàn năm hoà vốn.
- **Cấu hình CHÍNH**: ensemble 4 tín hiệu (TSMOM 12−1, TSMOM 1/3/12, giá > SMA200, Donchian 200/100), long/short, hàng tháng (lịch cuối tháng), vol mục tiêu 10%, ngân sách rủi ro cân bằng theo 6 lớp, `lmax` 3, cap 3x/tài sản, 8x tổng, vào lệnh ở phiên sau ngày tín hiệu. Bản bán lẻ không đòn bẩy: `lmax 1`, `gross_cap 2` (vol ~3,4%).
- **Chạy kèm** bản long-flat để đối chiếu; ghi log P&L theo lớp, đòn bẩy, chi phí thực.
- **Danh mục tài sản**: 35 tài sản trong YAML; nếu hạn chế dữ liệu, ưu tiên cổ phiếu + trái phiếu + vàng + FX (≥ 80% đóng góp) trước, nhưng **không** cắt lớp nào chỉ vì Sharpe lịch sử cao hơn.
- **Tiêu chí dừng/đi tiếp** (xem YAML `validation_gates`): tracking khớp backtest, chi phí thực ≤ 1,5x giả định, tương quan với 60/40 vẫn < 0,3.

## 7. Tái lập
```
# trên VPS (container python:3.12-slim, pip --target /root/research/pylib)
python multiasset/fetch_multiasset.py      # Yahoo + FRED + ECB -> /root/research/data/*.parquet
python multiasset/build_dataset.py         # excess_returns.parquet + data_quality_multiasset.csv + data_checks.txt
python multiasset/run_multiasset.py        # ~8s: 52 cấu hình, benchmark, lưới độ nhạy
python multiasset/analyze_multiasset.py    # vài phút: bootstrap, DSR, placebo, LOCO, khủng hoảng, hình
```
Script `research/multiasset/vps_run.sh` tải mã lên VPS và chạy trong container `research-run`.
