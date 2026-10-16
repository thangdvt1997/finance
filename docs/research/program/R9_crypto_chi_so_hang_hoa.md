# R9 - Crypto, chỉ số, hàng hoá: có edge sau chi phí không?

Ngày: 2026-10-15. Mã: `data/research/program/R9/` (fetch.py, fetch_yahoo.py, run.py, carry_years.py; kết quả thô results.json/results.csv; dữ liệu thô trong raw/, không vào git). READ-ONLY/PAPER, gói 0 đồng.

## 0. Kết luận thẳng
| Ý tưởng | Kết quả sau chi phí (OOS) | Kết luận |
|---|---|---|
| Y1 Funding carry delta-neutral (long spot / short perp) | BTC: ~6,5%/năm trên giá trị spot (tổng 2022-09/2026 +35%); 2026 chỉ ~3%/năm quy năm. Vốn thật (spot + ký quỹ perp) ~2x nên lợi suất trên vốn ~3%/năm, thấp hơn lãi tiền gửi/T-bill. | Edge thật nhưng đã co lại gần 0 sau năm 2021. Không đáng làm với vốn nhỏ + rủi ro sàn. Có thể dùng như tín hiệu tâm lý (funding cao = rủi ro đuôi), không dùng như nguồn lợi nhuận. |
| Y2 TSMOM crypto (BTC/ETH/SOL/BNB) | Walk-forward Sharpe 0,17-0,71; không tốt hơn buy&hold có ý nghĩa (CI95 chênh Sharpe luôn chứa 0); không vượt placebo. Danh mục 4 coin: Sharpe 0,52 vs B&H 0,43, MaxDD -38% vs -75%. | Không có edge xác nhận về lợi suất; có tác dụng giảm drawdown (ngang trend đa tài sản). Không dùng làm nguồn alpha. |
| Y3 Stat-arb cặp crypto (8 cặp, z-score, hedge OLS lăn) | Danh mục 8 cặp Sharpe 0,57, CI95 [-0,58; 1,72], p(Sharpe<=0)=0,18; từng cặp từ -0,28 đến +1,01 (DOGE/XRP là ngoại lệ đơn lẻ, CI chứa 0). 64 cấu hình thử. | Không có edge (sau hiệu chỉnh nhiều lần thử). |
| Y4 SMA-trend chỉ số/vàng/dầu/hàng hoá (ETF, 2010-2026) | Mọi tài sản: Sharpe trend <= buy&hold; ΔSharpe CI95 luôn chứa 0. Danh mục 9 tài sản: 0,62 vs 0,67, nhưng MaxDD -14% vs -30%. Dầu (USO) Sharpe ~0. | Không có alpha; chỉ có giá trị giảm drawdown. Trùng kết luận MULTI_ASSET_BACKTEST. |

Không ý tưởng nào cho thấy edge rõ ràng, có thể khai thác, sau chi phí. Edge duy nhất có thật về cơ chế (carry) đã bị nén gần về lãi suất phi rủi ro.

## 1. Dữ liệu và phương pháp
- Crypto: Binance public data (data.binance.vision, không cần key; API trực tiếp bị HTTP 451 từ VPS). Nến D1 spot + futures USDT-M và funding 8h cho 12 coin: BTC, ETH, BNB, SOL, XRP, ADA, DOGE, LINK, LTC, AVAX, DOT, TRX; 2020-01 -> 2026-09-30.
- Chỉ số/hàng hoá: Yahoo adjusted close D1 của ETF SPY, QQQ, EFA, EEM, GLD, SLV, USO, DBC, TLT (2000/2006 -> 2026); đã dùng thay futures liên tục vì futures Yahoo không điều chỉnh roll. Lưu ý USO/DBC đã gồm chi phí roll, nên phản ánh lợi suất thực nhà đầu tư.
- Chi phí: futures taker 5bp + trượt giá 2bp mỗi chiều; spot taker 10bp + 2bp; ETF 3bp. Funding trả/nhận thật từng kỳ 8h. Tín hiệu chốt cuối ngày t, vị thế áp dụng ngày t+1.
- Walk-forward: tham số chọn theo Sharpe trên cửa sổ mở rộng TRƯỚC mỗi năm, áp dụng cho năm đó. OOS crypto 2022-01 -> 2026-09 (1734 ngày, gồm gấu 2022, bull 2024); OOS chỉ số 2010 -> 2026 (4204 ngày). Số cấu hình thử: Y1 8, Y2 8 (mỗi coin), Y3 64, Y4 6 (mỗi tài sản).
- Kiểm định: bootstrap dừng (stationary, khối TB 20 ngày, 1500 lần) cho CI95 Sharpe và chênh lệch Sharpe với buy&hold cùng ngày; placebo dịch vòng tín hiệu (300 lần) cho Y2.
- Giới hạn trung thực: (1) chọn 12 coin là những coin thanh khoản HIỆN TẠI -> thiên lệch sống sót (lợi cho long-only, hại cho short); (2) không mô hình hoá thanh lý, ADL, trượt giá lớn, rút vốn; (3) D1 close, bỏ qua biến động trong ngày (sai số basis); (4) mẫu OOS crypto chỉ ~4,7 năm, một chu kỳ -> CI rộng; (5) Sharpe không trừ lãi phi rủi ro (không đổi kết luận so sánh tương đối).
- Lưu ý dữ liệu khoá: dùng chuỗi dài hơn tập pattern; không đụng test khoá của kịch bản Sell.

## 2. Funding rate / basis (Y1)
Funding trung bình 2022-2026: BTC 6,6%/năm, ETH 6,0%, LINK 8,0%, LTC 7,3%, DOGE 7,2%; nhưng BNB -5,1%, SOL -5,0%, TRX -5,0% (funding âm: short perp phải trả). 13-49% ngày có funding âm tuỳ coin. Funding BTC theo năm (tổng, %): 2020 17,2; 2021 30,6; 2022 4,2; 2023 7,9; 2024 12,0; 2025 5,1; 2026 (9 tháng) 2,2.

| Cấu hình (OOS 2022-2026) | CAGR trên spot | Vol | Sharpe* | MaxDD |
|---|---|---|---|---|
| BTC luôn giữ (có chi phí vào 1 lần) | 6,8% | 0,6% | 11,1 | -0,3% |
| BTC walk-forward (lọc theo funding trung bình 30 ngày > 0) | 6,6% | 0,6% | 10,1 (CI 7,9-12,3) | -1% |
| BTC+ETH luôn giữ | 6,4% | 0,6% | 10,6 | ~0 |
| 12 coin luôn giữ (cùng trọng số) | 3,2% | 0,7% | 4,3 | -4% |
| 12 coin walk-forward | 4,2% | 0,6% | 6,9 | -1% |
*Sharpe 10+ là hiện vật của việc đánh giá theo ngày với biến động giá gần như bị hedge hết: nó KHÔNG phản ánh rủi ro thực (sàn, thanh lý chân short khi squeeze, tách basis lúc khủng hoảng, ký quỹ, stablecoin depeg). Đừng dùng nó để so sánh.
- Quy đổi vốn: cần spot 1 + ký quỹ perp ~1 (đòn bẩy 1x an toàn) -> lợi suất trên vốn ~ một nửa: BTC ~3,3%/năm cả giai đoạn, 2026 ~1,5%/năm. T-bill/tiền gửi USD đã ở mức xấp xỉ 4% (ước lượng, không đo trong báo cáo này). Sau 2021 carry không còn hấp dẫn hơn tiền mặt.
- Khớp văn liệu: BIS Working Paper 1087 (Schmeling, Schrimpf, Todorov) và He-Manela-Ross-von Wachter, "Fundamentals of Perpetual Futures" cho thấy carry crypto lớn và biến động mạnh, nằm ở khoảng cách arbitrage khi vốn arb hạn chế; khi vốn arb tăng carry co lại - đúng với số liệu. Mức tin cậy: cao (số thật + 2 nguồn học thuật).
- Rủi ro đuôi: ngày 10/10/2025 thanh lý ~19 tỷ USD (CoinShares), perp BTC trên Binance giảm sâu hơn spot ~6%; chân short lãi nhưng chân spot/tài sản ký quỹ khác (USDe depeg) và ADL có thể gây tổn thất; carry cao còn dự báo sụp giá (BIS).

## 3. Time-series momentum crypto (Y2)
OOS 2022-2026, long/short hoặc long/flat, lookback 20/50/100/200 chọn walk-forward, trừ funding và phí.
| Coin | WF CAGR | WF Sharpe (CI95) | B&H CAGR / Sharpe | ΔSharpe CI95 | MaxDD WF / B&H |
|---|---|---|---|---|---|
| BTC | 8,4% | 0,40 [-0,59; 1,40] | 13,3% / 0,50 | [-0,83; 0,57] | -51% / -67% |
| ETH | -1,5% | 0,17 | -6,4% / 0,25 | [-0,87; 0,67] | -53% / -74% |
| SOL | 27,6% | 0,71 | -10,7% / 0,37 | [-0,42; 1,08] | -52% / -95% |
| BNB | 0,5% | 0,22 | 9,0% / 0,43 | [-0,84; 0,38] | -53% / -63% |
| 4 coin EW | 12,7% | 0,52 [-0,40; 1,42] | 7,9% / 0,43 | [-0,53; 0,74] | -38% / -75% |
- Placebo (tín hiệu dịch ngẫu nhiên, cùng cấu hình phổ biến nhất): Sharpe trung bình 0,49 (BTC), 0,59 (ETH), 0,69 (SOL), 0,70 (BNB); tín hiệu thật 0,68 / 0,39 / 0,71 / 0,25 nằm trong khoảng placebo (p95 0,95-1,38). Tức phần lớn "lợi suất" đến từ thiên lệch long của chuỗi tăng giá, không phải từ timing.
- Cấu hình ổn định: long/flat vượt long/short ở mọi lần chọn (mua-giữ có chi phí cơ hội thấp); long/short gần như luôn tệ hơn trong mẫu này.
- Văn liệu: Liu-Tsyvinski (2021) và Zarattini/Han-Kang-Ryu cho TSMOM crypto mạnh, nhưng Han-Kang-Ryu tìm lợi suất mất ý nghĩa sau chi phí/thanh lý, và Swinkels (2018) báo TSMOM ngắn hạn biến mất sau khi có futures BTC. Số của ta khớp bức tranh "có ở mẫu cũ, yếu ở mẫu mới". Mức tin cậy: trung bình (mẫu ngắn).
- Kết luận: dùng vol/trend filter như công cụ GIẢM DRAWDOWN (-75% -> -38% cho danh mục), không phải alpha.

## 4. Mean-reversion cặp / stat-arb (Y3)
Spread log giá a - beta*b (OLS lăn 60/120 ngày), vào |z| > 2/2,5, thoát z về 0 hoặc ±0,5; hai chân perp, trả phí 2 chân + chênh funding. 8 cặp: ETH/BTC, LTC/BTC, BNB/ETH, LINK/ETH, ADA/XRP, SOL/ETH, DOGE/XRP, AVAX/DOT. Sharpe WF: 0,14; 0,15; 0,03; -0,28; -0,07; -0,10; 1,01; 0,34. Danh mục: Sharpe 0,57 [-0,58; 1,72], CAGR 5,6%, vol 10,6%, MaxDD -26%, tương quan với TSMOM -0,22. Chỉ 1/8 cặp dương rõ và với 64 cấu hình thử thì p-value của cái tốt nhất không còn đáng kể (Bonferroni). Cặp crypto thiếu tính cointegration ổn định (beta trôi, đuôi dày, breakout xu hướng gây lỗ lớn); không có mean-reversion đáng tin sau chi phí. Không dùng.

## 5. Chỉ số, vàng, dầu, hàng hoá (Y4)
SMA 50/100/200, long/flat hoặc long/short, chọn WF từ 2010. Sharpe trend vs B&H: SPX 0,84 vs 0,87; NDX 0,84 vs 0,95; EFA 0,33 vs 0,47; EEM 0,25 vs 0,34; Vàng 0,52 vs 0,55; Bạc 0,32 vs 0,40; Dầu -0,03 vs 0,06; DBC 0,19 vs 0,24; TLT 0,16 vs 0,23. Giảm MaxDD đều (SPX -21% vs -34%, vàng -34% vs -46%, danh mục 9 tài sản -14% vs -30%) nhưng lợi suất thấp hơn. Nhóm hàng hoá 4: trend 0,27 vs 0,37. Dầu: không có xu hướng khai thác; USO chịu contango. Không có alpha timing; gần như là "bảo hiểm drawdown rẻ".

## 6. Thanh khoản 24/7, rủi ro vận hành, so sánh forex/vàng
- Biến động năm hoá 2022-2026: BTC 51%, ETH 69%, USO 38%, GLD 19%, SPY 17%. Crypto cao gấp ~3x vàng/cổ phiếu; cùng Sharpe sẽ cần quy mô vị thế nhỏ hơn 3x.
- 24/7: không có gap cuối tuần như FX/vàng/chỉ số (có lợi: stop thật), nhưng thanh khoản mỏng cuối tuần/đêm Á, trượt giá lớn ở alt (ví dụ ATOM 4 -> 0,001 USD trên Binance 10/10/2025).
- Chi phí: crypto futures taker ~5bp/chiều + funding (~6%/năm khi long, cost drag đáng kể cho trend long); FX spread MT5 ~0,1-1 pip; ETF chỉ số 1-3bp. Crypto rẻ phí nhưng funding làm long dài hạn đắt.
- Rủi ro sàn/rút vốn/đòn bẩy: rủi ro đối tác (FTX 2022), thanh lý chuỗi (19 tỷ USD 10/10/2025), ADL, tự động hạ đòn bẩy; carry và pairs đều cần ký quỹ -> chân lỗ có thể bị thanh lý trước khi chân lãi bù. Nguồn: CoinShares "Billions in liquidations: what happened?".
- Pháp lý Việt Nam (mức tin cậy THẤP-TRUNG BÌNH, nguồn báo chí/luật sư, cần đối chiếu văn bản gốc trên vbpl.vn): Nghị quyết 05/2025/NQ-CP (hiệu lực 9/9/2025) thí điểm 5 năm thị trường tài sản mã hoá, Bộ Tài chính cấp phép; theo các bài báo có thông tư thuế (số hiệu 32/2026/TT-BTC, 41/2026/TT-BTC chỉ xuất hiện ở một nguồn; dự thảo 0,1%/giao dịch). Báo cáo ghi nhận chưa rõ doanh nghiệp nào được cấp phép đầy đủ; giao dịch trên sàn nước ngoài (Binance...) và phái sinh perp có thể nằm ngoài khung được bảo hộ; cần tư vấn pháp lý trước (cổng G1-G3 của dự án).
- So với forex/vàng của dự án: FX/vàng qua MT5 cùng kết quả "không edge cổ điển". Crypto đưa thêm 1 nguồn lợi nhuận cấu trúc (carry) nhưng đã hết biên; ưu điểm duy nhất là dữ liệu miễn phí đầy đủ và 24/7 để nghiên cứu/paper.

## 7. Khuyến nghị
1. KHÔNG đưa crypto alpha (TSMOM, pairs) vào paper-trade như chiến lược sinh lời; không có bằng chứng vượt placebo/B&H.
2. Theo dõi funding BTC/ETH và basis như chỉ báo rủi ro (funding > ~30%/năm hoặc basis cực lớn = leverage quá mức, giảm rủi ro) - bộ lọc, giống lịch kinh tế. Có thể kiểm tra giả thuyết này riêng (cần nhiều sự kiện để có ý nghĩa).
3. Trend/vol filter nên là lớp giảm drawdown trong danh mục đa tài sản, trọng số nhỏ.
4. Nếu muốn tiếp: mở rộng kiểm tra carry sang cặp spot-quarterly futures (basis có kỳ hạn, không rủi ro funding) và thêm dữ liệu liquidation/OI từ Binance public để kiểm tra "carry cao -> sụp giá" ra sao; cần kích thước mẫu lớn hơn.

## 8. Nguồn
- Schmeling, Schrimpf, Todorov, "Crypto carry", BIS WP 1087 (https://www.bis.org/publ/work1087.pdf).
- He, Manela, Ross, von Wachter, "Fundamentals of Perpetual Futures" (https://arxiv.org/abs/2212.06888).
- Han, Kang, Ryu, "Time-series and cross-sectional momentum in the cryptocurrency market with transaction costs" (AUT working paper PDF); Rozario et al., "A Decade of Evidence of Trend Following Investing in Cryptocurrencies" (https://arxiv.org/abs/2009.12155); Swinkels 2018 (qua tổng quan tìm kiếm, chưa đọc toàn văn).
- CoinShares, "Billions in liquidations: what happened?" (https://coinshares.com/insights/knowledge/billions-in-liquidations-what-happened/).
- Pháp lý VN: nhadautu.vn, lsvn.vn, thoibaotaichinhvietnam.vn, luatvietan.vn (báo chí/luật sư; chưa đối chiếu văn bản gốc).
- Nội bộ: docs/research/MULTI_ASSET_BACKTEST.md, PATTERN_DATA.md.
