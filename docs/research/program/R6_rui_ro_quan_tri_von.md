# R6 — Rủi ro & quản trị vốn (vốn nhỏ 1k–10k USD)

Ngày: 2026-10-15. Phạm vi: READ-ONLY/PAPER, không lệnh thật. Mã: `data/research/program/R6/r6_sim.py`; kết quả thô: `data/research/program/R6/out/*.csv|json` (seed cố định 20261015, 10.000 đường/mô phỏng). Không mở tập TEST khoá của pattern-sell (chỉ dùng dev+val).

## 0. Tóm tắt khuyến nghị (đọc phần này là đủ)

| Hạng mục | Ngưỡng đề xuất | Cơ sở |
|---|---|---|
| Rủi ro mỗi lệnh (giai đoạn paper/ chưa có edge được chứng minh) | **0,25%** vốn (tối đa 0,5%) | Ledger Sell thật có E[R] = −0,10R: ở 1%/lệnh, P(DD≥30%) = 58% trong 250 lệnh; ở 0,25% chỉ 0% và lỗ ~6%/năm. Rủi ro nhỏ = mất chậm, kịp phát hiện. |
| Rủi ro mỗi lệnh (khi có edge đã qua walk-forward + test khoá, E[R] ≥ +0,15R) | **0,5%–1%**, trần cứng 1% | Với E[R]≈+0,2R: 1% cho P(DD≥20%)≈9%, P(DD≥30%)≈0,6%; 2% đã P(DD≥30%)≈24%. |
| Kelly | Dùng **≤ 1/4 Kelly** ước lượng, và không bao giờ vượt 1% | Kelly đầy đủ ước lượng 7,5%–21% (mẫu +0,10R..+0,25R) nhưng sai số ước lượng E[R] rất lớn; sai lệch edge ±0,1R đủ đổi dấu. |
| Tổng nóng (open risk = Σ khoảng cách SL × size) | **≤ 3%** vốn (paper: ≤ 2%); mỗi nhóm tương quan (cùng đồng tiền/ cùng chiều USD) ≤ 1,5% | FX7 có chỉ số cược độc lập hiệu dụng chỉ ≈ 2,6/7 cặp; 3+ cặp cùng ±2σ cùng ngày: 3,8% số ngày. |
| Đòn bẩy danh nghĩa gộp | ≤ 3x vốn (retail), ≤ 10x trần risk-monitor MT | Xem §3. |
| Giảm đòn theo DD | DD 8% → 12% → 16%: rủi ro/lệnh ×1 → ×0,5 → ×0,25 | Overlay tuyến tính cắt P(DD≥30%) từ 13,8% xuống 0% (trend vol 15%) với chi phí CAGR ≈ 2 điểm. |
| Kill switch | **DD 20% từ đỉnh vốn: dừng mở lệnh mới, đóng hết, review thủ công ≥ 1 tuần**; ngày: −2% (paper) / −3% (MT demo); tuần: −4%/−6%; 5 lệnh thua liên tiếp: ngừng phiên ngày đó | Khớp với `budget` của risk-monitor (dd_pct 10 paper/15 MT -> nên là mức *cảnh báo*, kill ở 20%). |
| Dừng khi edge hỏng | 250 lệnh gần nhất E[R] < 0 (CI trên của trung bình < +0,05R) → quay về 0,25% hoặc dừng | Với std_R ≈ 1,2, sai số chuẩn của E[R] trên 250 lệnh ≈ 0,075R; cần ≥ 250–500 lệnh mới phân biệt edge +0,1R với 0. |

Kết luận cứng: **sizing không tạo ra edge**. Ledger Sell (8.290 lệnh dev+val) có E[R] âm; mọi mức rủi ro đều chỉ làm tài khoản chết nhanh hơn. Quản trị vốn chỉ quyết định *thoát hiểm* và *tốc độ tăng trưởng khi đã có edge*.

## 1. Phương pháp
- Bootstrap theo khối (không xáo trộn từng lệnh để giữ tự tương quan): chuỗi ngày khối 21 ngày; chuỗi lệnh khối 10 lệnh. Compounding theo vốn hiện tại; chạy lặp trên từng bước để áp luật phụ thuộc đường (giảm đòn, kill).
- Nguồn dữ liệu thật:
  - A: lợi nhuận ngày Trend đa tài sản (Ensemble|M, `ma_returns.parquet`, 9.552 ngày 1990–2026, vol thực 9,5%, Sharpe 0,56 sau phí; xem MULTI_ASSET_BACKTEST.md). Không có sổ lệnh riêng của trend, nên dùng chuỗi lợi nhuận ngày; mức vol mục tiêu = hệ số nhân. Khung 3 năm.
  - B: chuỗi R_net thật của ledger pattern-sell (dev+val, 8.290 lệnh, thắng 36,9%, std R 1,19; cắt R ∈ [−3,10]); khung 250 lệnh (≈1 năm hoặc ít hơn; coi các lệnh tuần tự, bỏ qua chồng lấn nên rủi ro đồng thời bị *đánh giá thấp*). Vì E[R] thật âm nên thêm hai kịch bản GIẢ ĐỊNH (dịch E[R] lên +0,10R, +0,25R) và một chuỗi tổng hợp (thắng 40%, RR 1:2, E=+0,20R) để cho thấy tác động của sizing khi *có* edge — đây không phải bằng chứng edge.
- Vốn 1k–10k: kết quả theo tỉ lệ vốn nên giống nhau; điểm khác nằm ở lot tối thiểu (§6).

## 2. Kết quả A — Trend đa tài sản, 3 năm (vol mục tiêu thay đổi)
(`out/A_trend_mc.csv`; P_DDx = xác suất chạm DD ≥ x% từ đỉnh trong 3 năm; "Lỗ cuối" = vốn cuối < vốn đầu)

| Vol mục tiêu/năm | CAGR trung vị | MDD trung vị | MDD P95 | P(DD≥20%) | P(DD≥30%) | P(DD≥50%) | P(lỗ sau 3 năm) |
|---|---|---|---|---|---|---|---|
| 3,4% (retail không đòn) | 1,9% | 4,9% | 9,4% | 0% | 0% | 0% | 17,8% |
| 5% | 2,7% | 7,1% | 13,6% | 0,2% | 0% | 0% | 18,2% |
| 7,5% | 4,0% | 10,6% | 19,9% | 4,9% | 0,2% | 0% | 18,9% |
| **10%** | 5,3% | 13,9% | 25,7% | 16,5% | 1,8% | 0% | 19,4% |
| 15% | 7,6% | 20,3% | 36,4% | 51,8% | 13,8% | 0,2% | 20,6% |
| 20% | 9,7% | 26,4% | 45,8% | 80,2% | 35,6% | 2,5% | 21,9% |
| 30% | 13,2% | 37,6% | 61,3% | 98,4% | 77,1% | 18,2% | 24,5% |

Nhận xét: tăng vol gấp 3 (10%→30%) chỉ tăng CAGR ×2,5 nhưng MDD trung vị ×2,7 và P(DD≥50%) từ 0 lên 18%. Xác suất lỗ sau 3 năm *không giảm* theo vol (≈ 18–25%) → leverage không mua được an toàn. Ngưỡng hợp lý cho vốn nhỏ: **vol 7,5–10%/năm** (MDD P95 20–26%).

Overlay kiểm soát DD (CPPI / giảm đòn / kill) ở vol 15% và 20%:

| Cấu hình | CAGR TV | MDD P95 | P(DD≥20%) | P(DD≥30%) | P(lỗ 3 năm) | P kill |
|---|---|---|---|---|---|---|
| 15% trần | 7,6% | 36,4% | 51,8% | 13,8% | 20,6% | – |
| 15% + giảm đòn theo DD (8%→20%: ×1→×0,25) | 5,5% | 23,2% | 28,0% | 0% | 27,4% | 0% |
| 15% + giảm đòn + kill 25% | 5,5% | 23,2% | 28,0% | 0% | 27,4% | 1,5% |
| 15% + CPPI m=4, sàn 70% đỉnh | 6,2% | 26,1% | 39,4% | 0% | 25,1% | 0% |
| 15% + kill 25% (không giảm dần) | 6,9% | 26,0% | 51,8% | 0% | 27,5% | 28% |
| 20% + giảm đòn theo DD | 5,7% | 26,3% | 60,3% | 0,6% | 29,9% | 0% |
| 20% + kill 25% | 5,1% | 26,8% | 80,2% | 0% | 37% | 56% |

Điểm then chốt: (1) kill cứng chặn cực trị nhưng "khóa lỗ" — với trend đảo chiều V thì dừng xong bỏ lỡ hồi phục (xác suất lỗ cuối kỳ tăng, 20%+kill: 37%); (2) giảm đòn dần cho đánh đổi tốt hơn kill cứng; (3) overlay làm CAGR ở 15–20% về ≈ vol 10% không overlay (5,3%) nhưng với MDD tương đương — **tức overlay không "ăn trưa miễn phí"; cùng lợi suất, chọn vol thấp hơn từ đầu đơn giản hơn**. Overlay tác dụng chính là *giới hạn đuôi* (P(DD≥30%) = 0) khi sai mô hình.

## 3. Kết quả B — Chuỗi lệnh R, 250 lệnh (`out/B_trade_mc.csv`, `B_kelly.csv`)

Kelly (tối đa hoá E[log(1+f·R)] trên chuỗi): ledger thật: **0** (không có f dương); dịch +0,10R: 7,5%; +0,25R: 21,1%; tổng hợp E=+0,20R: 10,0%.

A) Ledger Sell THẬT (E[R] = −0,099):

| Rủi ro/lệnh | Vốn cuối TV (1.000 USD) | MDD TV | P(DD≥20%) | P(DD≥30%) | P(DD≥50%) |
|---|---|---|---|---|---|
| 0,25% | 937 | 9% | 0,4% | 0% | 0% |
| 0,5% | 877 | 17% | 36% | 3,5% | 0% |
| 1% | 762 | 32% | 88% | 58% | 4,8% |
| 2% | 560 | 55% | 100% | 96% | 63% |
| 3% | 398 | 71% | 100% | 99,7% | 89% |

B) Có edge (GIẢ ĐỊNH) — chuỗi tổng hợp thắng 40%, RR 1:2, E=+0,20R:

| Rủi ro/lệnh | CAGR/250 lệnh TV | MDD TV | MDD P95 | P(DD≥20%) | P(DD≥30%) | P(DD≥50%) |
|---|---|---|---|---|---|---|
| 0,25% | +13% | 3,2% | 5,9% | 0% | 0% | 0% |
| 0,5% | +28% | 6,4% | 11,5% | 0% | 0% | 0% |
| **1%** | +60% | 12,5% | 22,0% | 8,9% | 0,6% | 0% |
| 1,5% | +99% | 18,4% | 31,6% | 40% | 6,8% | 0% |
| 2% | +144% | 24,0% | 40,2% | 77% | 24% | 0,9% |
| 3% | +252% | 34,6% | 54,7% | 98,5% | 70% | 9,5% |

(Tăng trưởng ở đây là *tuần tự lý thuyết*; thực tế chồng lấn, phí, trượt giá, edge suy giảm → nhân hệ số ≤ 0,3–0,5.)
Ledger dịch E[R] = +0,10R, ở 1%: CAGR +25%, P(DD≥30%) 2,5%; 2%: P(DD≥30%) 41%.

Kết hợp overlay (E=+0,20R, r=2%): giảm đòn theo DD đưa P(DD≥30%) từ 24% xuống 0,2% (chi phí: tăng trưởng +144% → +100%); kill 20% **làm hại** (P(lỗ) 2,1% → 25%, tăng trưởng +144% → +43%) vì dừng ngay sau chuỗi thua bình thường — **không dùng kill cứng đơn lẻ ở DD nhỏ khi rủi ro/lệnh ≥ 2%; luật kill nên đi cùng "chờ review", không tự khởi động lại**. Kết luận: phải để r thấp để chuỗi thua bình thường *không chạm kill*.

Chuỗi thua liên tiếp (xác suất 1% xuất hiện trong 1.000 lệnh): thắng 40% → 23 lệnh thua liên tiếp; 50% → 17; 35% → 27; 45% → 20. Ở 1% rủi ro, 23 lệnh thua liên tiếp = −20,7%; ở 2%: −37%. Đây là *lý do toán học* của trần 1%.

## 4. Rủi ro phá sản (chuỗi tổng hợp 1.000 lệnh, "phá sản" = mất ≥ 50%; `out/C_ruin.csv`)

| Thắng/RR (E[R]) | 0,25% | 0,5% | 1% | 2% | 5% |
|---|---|---|---|---|---|
| 40% / 1:2 (+0,20R) | 0% | 0% | 0% | 4,8% | 97,6% |
| 45% / 1:1,5 (+0,125R) | 0% | 0% | 0% | 7,9% | 97,8% |
| 35% / 1:2 (+0,05R) | 0% | 0% | 6,8% | 66% | 100% |
| 50% / 1:1 (0R) | 0% | 0% | 7,1% | 62% | 99,9% |

Quy tắc: P(mất 50% | edge ≥ +0,1R) ≈ 0 khi r ≤ 1%; khi edge ≈ 0 thì ngay 1% đã có 7%. Vì edge thật luôn không chắc chắn, chọn **r ≤ 0,5% cho đến khi có ≥ 250 lệnh paper thật có E[R] > 0**.

## 5. Tương quan & đuôi (`out/D_corr.json`, từ 2015)
- Tương quan trung bình FX7: −0,04 (bình thường); trong 5% ngày SPX xấu nhất: −0,003 (quy đổi USD trong chuỗi "excess"). Toàn rổ (FX7+vàng/bạc/WTI/SPX/BTC): 0,03 → 0,10 (tăng ~3 lần khi stress).
- Số cược độc lập hiệu dụng của FX7 = 2,6 (theo trị riêng) → 7 vị thế FX không phải 7 lần đa dạng hoá; đặt trần theo nhóm (đồng tiền cơ sở/ USD).
- P(≥3 trong 7 cặp FX cùng lệch > 2σ trong một ngày) = 3,8% số ngày.
- Tương quan bình thường thấp nhưng *đuôi* dày hơn nhiều; sizing dựa tương quan lịch sử bình thường sẽ đánh giá thấp rủi ro stress → dùng ES/ tổng nóng thay vì phương sai.

## 6. Stress kịch bản và gap (`out/D_stress_*.csv`, `D_gap_atr.csv`)

| Sự kiện | Chuyển động thực trong dữ liệu | Ý nghĩa cho SL |
|---|---|---|
| SNB 2015-01-15 | USDCHF −13,9% trong ngày (cao điểm trong phiên lớn hơn); WTI −4,5% | SL 20–30 pip trượt hàng trăm pip: lỗ gấp ≥ 10–50× khoảng SL ⇒ lệnh 1% có thể lỗ 10–50% vốn; tài khoản đòn bẩy cao âm vốn (nhiều broker FX bị phá sản). |
| Brexit 2016-06-24 | GBPUSD −7,8%, EURUSD −2,8%, USDJPY −3,2% | Gap qua đêm 5–10× ATR ngày. |
| Flash GBP 2016-10-07 | GBPUSD −2,6% (ngày; phiên châu Á −6% trong vài phút) | SL thị trường mỏng; lệnh stop kích hoạt giá xấu. |
| Flash crash 2010-05-06 | SPX −3,2%, WTI −3,5% (trong phiên: −9% rồi hồi) | Stop bị kích hoạt đáy; dùng stop-limit/ giảm cỡ trước tin. |
| COVID 2020-03 | 9/3: WTI −25%, SPX −7,6%; 12/3: BTC −37%, SPX −9,5%; 16/3: SPX −12% | Tương quan → 1 ở đuôi, đòn gộp không còn đa dạng hoá. |
| Black Monday 1987 | SPX −20,5% ngày | Mô hình Gauss vô nghĩa. |

Phân phối cú sốc 1 ngày tính theo ATR (20 ngày) từ 2010, `D_gap_atr.csv`: EURUSD max 8,9 ATR (5 ngày > 6 ATR trong 4.376 phiên), GBPUSD 8,5, USDJPY 10,9, USDCHF **29,7**, vàng 7,6, bạc 8,0, BTC 14,5 (13 ngày > 6 ATR/ 3.147). Bội số gap trung bình 4 ATR xảy ra ~0,5–1% số ngày FX (21–37 ngày/4.376) và ≥ 6 ATR chỉ 3–7 ngày trong ~17 năm cho mỗi cặp FX/kim loại (13 ngày cho BTC trong ~12,5 năm).
→ **Tổn thất thực của 1 lệnh có thể là 4–10R chứ không phải 1R**. Quy tắc: tính rủi ro/lệnh theo SL, nhưng đặt *tổng nóng* sao cho kịch bản "mọi vị thế gap 6 ATR ngược" ≤ 20% vốn: với SL = 1,5 ATR, gap 6 ATR ≈ 4R/vị thế; tổng nóng 3% ×4 = **12%** (OK); tổng nóng 5% ×4 = 20% (trần). Gap cuối tuần: không giữ lệnh qua cuối tuần/ sự kiện SNB-ECB-NFP nếu rủi ro/lệnh > 0,5%, hoặc giảm 1/2 cỡ.

Danh mục trend (Ensemble) tại các sự kiện: SNB −1,1% (vol 9,5%) đến −2,3% (vol 20%), COVID tăng (+4,3% ngày 9/3, +4,4% 16/3): trend đa dạng có phòng thủ tốt ở các cú gap *đã được định vị theo xu hướng*, nhưng thua lỗ ở đảo chiều V (2018Q4 −7,2%, 2023 −10,3% ở vol 9,5%; ở vol 20%: −14,7% và −20,9%). Ghi chú: sự kiện nhật ký là ex-post; không dùng như bảo đảm.

## 7. Nguyên tắc survival & sizing theo ATR
1. Sống sót trước tăng trưởng: mục tiêu bài toán là *không phải ngừng*. DD 50% cần +100% để hoà vốn; DD 20% cần +25%.
2. Sizing theo ATR: `size = (vốn × r) / (k_ATR × ATR × giá trị điểm)`, k_ATR = SL theo ATR (1,5–3 ATR). Giữ r cố định theo *R*, để biến động tự điều chỉnh lot (nghịch với vol). Chặn trên: lot ≤ vốn×3/giá trị danh nghĩa 1 lot; sàn: lot 0,01.
3. Vol-targeting (trend): vol đích 7,5–10%; ước lượng EWMA 60 ngày + shrink; trần đòn 3x (lmax trong YAML).
4. Vốn 1k–10k: lot tối thiểu 0,01 (≈ 0,1 USD/pip FX): 1k với r=0,25% = 2,5 USD ≈ SL 25 pip; r=0,5% = 5 USD ⇒ SL 50 pip. Nếu SL ngắn hơn, lot 0,01 đã vượt r → **bỏ lệnh**, không làm tròn lên. Dưới 1k USD dùng cent/micro hoặc paper.
5. Tương quan: trần theo nhóm tiền tệ (cùng USD hoặc cùng đồng tiền cơ sở ≤ 1,5%), tổng nóng ≤ 3%.
6. Không tăng cỡ sau thắng (martingale/ pyramiding) cho đến khi DD < 5% và edge được xác nhận; tăng bậc: sau mỗi 250 lệnh E[R] dương (CI > 0) mới +0,25 điểm %.
7. Không tăng cỡ để "gỡ" sau thua; giảm đòn theo DD là đường duy nhất cho phép thay đổi cỡ trong chuỗi thua.
8. Đòn bẩy nội tại chỉ là hệ quả, không phải đầu vào: dùng margin ≤ 20% vốn, margin level ≥ 300% (risk-monitor cảnh báo 200%).

## 8. Ngưỡng cụ thể đề xuất (khớp `services/risk-monitor/risk.example.yaml`)

| Khoá | Hiện tại (paper / mt) | Đề xuất |
|---|---|---|
| risk_per_trade | (chưa có) | paper: 0,25%; sau khi có edge: ≤1% |
| open_risk_total (tổng nóng) | (chưa có) | 2% paper / 3% mt; nhóm tương quan ≤ 1,5% |
| day_loss_pct | 2 / 3 | giữ (≈ 4 lần r=0,5% thua liên tiếp); dừng giao dịch trong ngày |
| week_loss_pct | 4 / 6 | giữ; dừng đến thứ Hai |
| dd_pct | 10 / 15 | **cảnh báo + giảm đòn tại 8–12%**; **kill (đóng, review) tại 20%** |
| leverage_gross | 2 / 10 | paper 2x giữ; mt 3x (10x là trần broker, không phải mục tiêu) |
| positions | 40 / 20 | 6–10 đồng thời (do tổng nóng 3% và r 0,25–0,5%) |
| es_1d_pct | 3 / 4 | giữ; thêm kiểm tra gap-6ATR ≤ 20% |
| thua liên tiếp | – | 5 lệnh → nghỉ phiên; 8 → review chiến lược |
| edge-decay | – | E[R] 250 lệnh gần nhất < 0 → về 0,25% hoặc dừng |

## 9. Hạn chế
- Trend: chuỗi lợi nhuận ngày dùng đòn gộp 2,3x TB, tài sản "excess" (hợp đồng tương lai/ETF) — không phải FX CFD giao ngay có swap; kết quả cho vốn nhỏ cần phí thực + lot tối thiểu.
- Bootstrap khối 21 ngày/ 10 lệnh giữ tự tương quan ngắn hạn nhưng không giữ chế độ dài hạn (2010–2019 trend yếu, Sharpe 0,16) → P(DD) thực có thể cao hơn ở chế độ xấu; kết quả là ước lượng điều kiện trên mẫu 1990–2026.
- Ledger Sell: mô phỏng tuần tự bỏ qua lệnh chồng lấn; R cắt [−3, 10]; kịch bản E[R] dương là GIẢ ĐỊNH để minh hoạ sizing, không phải kết quả huấn luyện.
- Gap/ stress: dữ liệu ngày (OHLC không có) nên cú sốc trong phiên (SNB, GBP flash) bị đánh giá thấp; thực tế nhiều hơn.
- Chưa mô phỏng chi phí thanh khoản/ trượt giá/ swap khi đòn lớn và tương quan giữa chuỗi thua và chế độ biến động.

## 10. Tái lập
`cd data/research/program/R6 && python3 r6_sim.py` (RDATA mặc định `/root/research/data`; ledger tại `data/research/patterns/backtest/final/ledger/ledger_all.parquet`). Đầu ra ở `out/`: `A_trend_mc.csv`, `B_trade_mc.csv`, `B_kelly.csv`, `C_ruin.csv`, `D_stress_assets.csv`, `D_stress_portfolio.csv`, `D_stress_windows.csv`, `D_gap_atr.csv`, `D_corr.json`.
