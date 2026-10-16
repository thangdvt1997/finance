# Backtest trung thực cổ phiếu Việt Nam (phương án C): momentum, bộ lọc xu hướng, benchmark

Ngày: 2026-10-12. Mã: `research/vn/` (chạy trên VPS <VPS_IP>, container `python:3.12-slim` tên `research-*`, `nice 19`, `--cpus 6 --memory 16g`; laptop chỉ sửa file). Kết quả thô: `research/results/vn/`. Hình: `research/figures/vn_fig*.png`. Mô phỏng thuần, không tiền thật.

## 0. Kết luận thẳng

| Câu hỏi | Trả lời |
|---|---|
| Momentum 12-1, top-15 trong top-100 thanh khoản, rebalance tháng, có lãi sau chi phí? | **Có, nhưng không hơn thị trường**: Sharpe 0,21 (CI95 −0,40…+0,88), CAGR 6,9%, MaxDD **−58,8%** (2014-03 → 2026-10, 12,6 năm). VN-Index (giá) 0,31 / 9,0%; E1VFVN30 0,38 / 10,4%; top-100 đều 0,25 / 7,7%. |
| Có "alpha" chọn cổ phiếu? | **Không phát hiện**: so với top-100 đều (cùng universe, cùng chi phí) ΔSharpe −0,04 (CI −0,35…+0,28), lợi suất hoạt động +0,2%/năm, IR 0,02. Hồi quy tháng theo VN-Index: alpha −0,4%/năm (t = −0,1), beta 0,91. |
| Qua kiểm định? | **KHÔNG.** Deflated Sharpe 0,24 (744 cấu hình; ngưỡng 0,95). Walk-forward: cấu hình tốt nhất 2014-19 (Sharpe 0,77) chỉ 0,10 ngoài mẫu 2020-26 (xếp hạng 12%), tương quan hạng IS/OOS −0,30. Walk-forward 36 tháng mở rộng: Sharpe 0,07. |
| Tín hiệu momentum có tồn tại không? | **Có, yếu và đang suy giảm.** IC xếp hạng +0,04…+0,06 (t ≈ 2–3), nhưng top-15 chỉ hơn universe +0,4%/tháng (t = 1,2) *trước chi phí*; phần lớn hiệu ứng nằm ở **phía thua** (Q1−Q5 ≈ 1,0–1,6%/tháng) mà long-only không khai thác được. IC 2014-17 = 0,09; 2022 và 2023-26 ≈ 0. Chi phí (≈ 5,3%/năm do vòng quay 6,3 lần/năm) nuốt hết phần dư. |
| Bộ lọc VN-Index > MA200 (tháng)? | **Giảm rủi ro, không tăng lợi suất có ý nghĩa**: MaxDD −58,8% → −35,0%, năm 2022 −46,5% → −9,3%; Sharpe 0,27 vs 0,21 (ΔSharpe +0,06, CI −0,32…+0,47, p = 0,40). Mất 2023-26 (+14% vs +58%) và thua ở 2018-19, 2023 do whipsaw. Lọc theo ngày tệ hơn (Sharpe 0,10). |
| Value/chất lượng (P/E, P/B, ROE)? | **Không dùng trong backtest** (không có lịch sử point-in-time, xem §5). |
| Đáng đưa vào paper? | **Không có chiến lược nào đủ điều kiện làm "phương án có edge"**; không triển khai plugin/tài khoản `vn_momentum_v1` (lý do §8). |
| Kỳ vọng thực tế nếu vẫn làm | Sharpe 0–0,3 sau chi phí, CAGR 4–8%/năm, MaxDD −35…−60% (long-only, beta ≈ 0,9 với thị trường). Rẻ và đơn giản hơn: **E1VFVN30 mua-giữ** (cùng hoặc tốt hơn mọi biến thể chọn cổ phiếu) hoặc E1VFVN30 + MA200 tháng (Sharpe 0,47, MaxDD −27,5% nhưng chưa phân biệt được với mua-giữ). |

Cảnh báo lớn nhất: nếu dùng **danh sách VN100 hiện tại áp ngược quá khứ** (cách làm phổ biến) Sharpe của cùng chiến lược nhảy từ 0,21 lên **0,58** (CAGR 15,9%) — hoàn toàn do thiên lệch sống sót (§4.6).

## 1. Dữ liệu

| Nguồn | Nội dung | Ghi chú |
|---|---|---|
| VNDirect finfo `stock_prices` (không chính thức, tự giới hạn ≥0,9 s/request, UA khai báo) | OHLC thô + **giá điều chỉnh** (adClose/adAverage, gồm cổ tức tiền + thưởng/chia tách: kiểm tra thấy các bước nhảy ~1–3% ở ngày GDKHQ cổ tức tiền và ~20% ở cổ phiếu thưởng), khối lượng/giá trị khớp, tham chiếu/trần/sàn | **Khác `vn_daily`** (chỉ ~150 mã rổ hiện tại, từ 2018): nạp lại **toàn bộ 876 mã** = mọi mã HOSE đang niêm yết (427) + **mọi mã đã hủy niêm yết** (449, gồm FLC, ROS, HQC…) từ **2013-01-02** → 12,7 năm, 852 mã, 3.434 phiên |
| `vnmarket_prices` | VN-Index, VN30, VN100… | chỉ từ **2017-08-24** |
| Chuỗi "VNI chain" (tự dựng) | VN-Index thật (từ 2017-08) nối ngược bằng E1VFVN30 (2014-10 → 2017-08) và proxy top-100 theo thanh khoản (trước đó) | Proxy khớp VN-Index thật: tương quan ngày 0,92, đồng pha chế độ MA200 84% (ETF: 92%). Yahoo `^VNINDEX.VN` bị 429 từ VPS nên không dùng. Chỉ ảnh hưởng bộ lọc MA200 ở 2014–2017 |

Chất lượng: không có |lợi suất điều chỉnh| > 25% nào trong top-100 (không lỗi điều chỉnh rõ); 683 phiên không khớp bị coi là không giao dịch được. Số mã/phiên tăng 409 (2013) → 649 (2020) → 448 (2026).

## 2. Phương pháp

**Universe theo thời điểm (giảm survivorship):** tại mỗi ngày quyết định, các cổ phiếu HOSE có ≥ 40/60 phiên có khớp và ≥ 200 quan sát, xếp theo GTGD khớp trung bình 60 phiên; top-100 ≈ "VN100", top-30 ≈ "VN30" (xấp xỉ: trùng 87/100 và 22/30 với rổ hiện tại). **Bao gồm cả cổ phiếu sau này hủy niêm yết**: 10,5/100 thành viên top-100 năm 2014, 7/100 năm 2018 về sau biến mất; 25/283 mã từng vào top-100 đã hủy niêm yết.

**Tín hiệu (CHỐT TRƯỚC khi chạy):** CHÍNH = momentum 12−1 (lợi suất [t−252, t−21] phiên, giá điều chỉnh), top-15 trong top-100, tỷ trọng đều, rebalance cuối tháng. PHÒNG THỦ = CHÍNH + giữ cổ phiếu chỉ khi VNI chain > SMA200 (đánh giá cuối tháng), ngược lại tiền mặt 4,5%/năm (giả định, không kiểm chứng; nhạy rf ở §4.4).

**Khớp lệnh (engine `research/vn/vn_engine.py`, từng ngày):**
- Quyết định ở close ngày t; **bán ở phiên t+1** (VWAP phiên ± trượt giá), tiền về sau **T+2** nên **mua ở t+3**; cổ phiếu mới mua chỉ bán lại từ d+2.
- Lô 100 cp; **không mua nếu cả phiên khóa trần (low ≥ trần), không bán nếu khóa sàn (high ≤ sàn)**; giá khớp kẹp trong trần/sàn; phiên không khớp thì không giao dịch; lệnh dở dang chuyển sang 5 phiên sau.
- Khối lượng/ngày ≤ **10% KL trung bình 20 phiên** (và ≤ 20% KL phiên đó).
- Phí 0,15%/chiều, **thuế bán 0,1%**, trượt giá = nửa bước giá HOSE + 5 bps + 10 bps × √(tỷ lệ GTGD TB20 / 1%). Tổng ≈ 0,76% khứ hồi cho cổ phiếu 25.000đ.
- Tiền mặt sinh lãi 4,5%/năm; đầu tư 98% NAV; vốn cơ sở 1 tỷ đồng. Mã hết dữ liệu = hủy niêm yết → tất toán ở giá cuối (tùy chọn giảm 50%).
- Chưa mô hình: thuế cổ tức 5%, trễ cổ tức, margin, tạm ngừng giao dịch/cảnh báo/hạn chế giao dịch của sở, thanh toán riêng lẻ lô lẻ.

**Kiểm chứng:** bootstrap khối (21 ngày, 2.000 lần) cho Sharpe và hiệu Sharpe cặp đôi; Deflated Sharpe (Bailey–López de Prado) với **744 cấu hình đã chạy** (672 lưới + 72 độ nhạy/benchmark); placebo ngẫu nhiên (200) và dịch vòng tròn bộ lọc (200); tách mẫu và walk-forward; theo giai đoạn; chi phí ×0…×3; sức chứa; sống sót. Lưới: lookback {3,6,9,12} × skip {0,1} × universe {30,100} × N {10,15,20,30} × rebalance {M,Q} × tỷ trọng {đều, nghịch biến động} × lọc {không, tháng, ngày}.

## 3. Kết quả chính (2014-03 → 2026-10, sau chi phí)

| Chiến lược | Sharpe | CI95 | CAGR | Vol | MaxDD | Năm âm |
|---|---|---|---|---|---|---|
| **Momentum 12-1 (CHÍNH)** | 0,21 | −0,40…0,88 | 6,9% | 23,4% | −58,8% | 36% |
| **Momentum + MA200 tháng (PHÒNG THỦ)** | 0,27 | −0,35…0,91 | 8,1% | 19,3% | −35,0% | 45% |
| Momentum + MA200 ngày | 0,10 | −0,55…0,76 | 4,8% | 17,8% | −43,6% | 45% |
| VN-Index (giá, không cổ tức, không phí) | 0,31 | −0,26…0,91 | 9,0% | 19,4% | −45,3% | 18% |
| E1VFVN30 (từ 2014-11) | 0,38 | −0,20…0,98 | 10,4% | 19,2% | −44,6% | 18% |
| Top-100 đều, hàng tháng | 0,25 | −0,36…0,91 | 7,7% | 18,9% | −53,5% | 18% |
| Top-30 đều, hàng quý (VN30 xấp xỉ) | 0,10 | −0,51…0,71 | 4,2% | 22,0% | −59,5% | 45% |
| E1VFVN30 + MA200 tháng | 0,47 | −0,08…1,04 | 11,0% | 15,4% | −27,5% | 45% |
| E1VFVN30 + MA200 ngày | 0,33 | −0,29…0,95 | 8,4% | 13,9% | −35,7% | 36% |
| VN-Index + MA200 tháng (không phí) | 0,37 | −0,19…0,94 | 9,5% | 15,9% | −30,0% | 45% |
| Tiền mặt 4,5% | — | — | 4,6% | 0 | 0 | 0 |

Sharpe tính trên lợi suất vượt rf 4,5%. Giao dịch của CHÍNH: vòng quay 6,3 lần/năm (một chiều), chi phí 5,3%/năm, giữ ~14,5 mã, đầu tư 93%; PHÒNG THỦ: 5,8 lần, 4,7%/năm, ở ngoài thị trường 31% thời gian. Hình: `vn_fig1_equity.png`, `vn_fig2_yearly.png`.
Mọi CI đều chứa 0: với biến động 19–23% và 12,6 năm, **không thể phân biệt Sharpe 0,2–0,4 với 0**, cũng không phân biệt các dòng trên với nhau.

### 3.1 Theo giai đoạn (lợi suất kỳ / Sharpe)
| Giai đoạn | CHÍNH | PHÒNG THỦ | VN-Index | Top-100 đều |
|---|---|---|---|---|
| 2014-17 | +102% / 0,83 | +52% / 0,46 | +68% / 0,58 | +41% / 0,38 |
| 2018-19 | −16% / −0,58 | −20% / −0,85 | −2% / −0,24 | −12% / −0,72 |
| 2020 (COVID) | −4% / −0,24 | +25% / 2,06 | +15% / 0,53 | +31% / 1,16 |
| 2021 (bong bóng) | +69% / 1,96 | +69% / 1,97 | +36% / 1,35 | +73% / 2,50 |
| 2022 (sập) | **−47%** / −1,58 | −9% / −0,59 | −33% / −1,67 | −42% / −1,79 |
| 2023-26 | +58% / 0,46 | +14% / 0,06 | +72% / 0,65 | +56% / 0,48 |

Hai nửa mẫu (cắt 2020-06): Sharpe CHÍNH 0,16 → 0,27; PHÒNG THỦ 0,03 → 0,46 (lọc chỉ có ích từ 2020). Tháng tệ nhất của CHÍNH: 2020-03 (−21,6%), 2022-01 (−19,7%), 2022-09/10 (−16%, −16%) — kiểu "momentum crash" khi thị trường đảo chiều. Lợi suất từng năm: `research/results/vn/vn_yearly.csv`; năm 2025 CHÍNH +27% vs ETF +51% (thua thị trường tăng mạnh), 2026 đến 10-09: −10,8% vs ETF −5,8%.

## 4. Kiểm định

### 4.1 Ý nghĩa thống kê / Deflated Sharpe
PSR(0): CHÍNH 0,77, PHÒNG THỦ 0,83. **Deflated Sharpe** (744 lần thử, ngưỡng kỳ vọng của max là Sharpe 0,41): **CHÍNH 0,24, PHÒNG THỦ 0,31** (cần ≥ 0,95). Cấu hình tốt nhất trong lưới 672 chỉ 0,48 (`Q|iv|M`, N=15) — gần ngưỡng 0,41 nên cũng không vượt. Trung vị lưới 0,16; 90% cấu hình có Sharpe > 0, nhưng chỉ **26%** hơn top-100 đều (0,25).

### 4.2 So với benchmark (bootstrap cặp đôi)
| So sánh | ΔSharpe (CI95) | p(≤0) | Lợi suất hoạt động/năm |
|---|---|---|---|
| CHÍNH − top-100 đều (cùng universe) | −0,04 (−0,35…+0,28) | 0,59 | +0,2% (IR 0,02) |
| CHÍNH − VN-Index | −0,10 (−0,51…+0,32) | 0,67 | −1,1% |
| CHÍNH − E1VFVN30 | −0,23 (−0,71…+0,29) | 0,81 | −3,6% |
| PHÒNG THỦ − CHÍNH | +0,06 (−0,32…+0,47) | 0,40 | +0,2% |
| E1VFVN30+MA200 − E1VFVN30 | +0,06 (−0,30…+0,48) | 0,40 | −0,6% |
Không có so sánh nào có ý nghĩa; mọi ước lượng điểm đều ≤ 0 so với benchmark thụ động. Đáng chú ý: top-100 đều **không hơn** VN-Index (−0,06) và top-30 đều thua rõ (0,10) — "universe thanh khoản cao" theo thời điểm không tự cho lợi thế.

### 4.3 Placebo và tín hiệu thuần
- **Chọn 15 mã ngẫu nhiên** (cùng universe/tần suất/chi phí, 200 lần): Sharpe TB −0,31 (SD 0,10) → momentum hơn rõ (z = 5,2, p < 0,5%). Nhưng placebo này chịu cùng vòng quay cao nên *bị phạt chi phí mạnh hơn*; so sánh công bằng hơn ở chi phí 0: CHÍNH 0,35 vs top-100 đều 0,29 vs ngẫu nhiên 0,08 ± 0,10 (p = 0,5%); **CHÍNH − top-100 đều (chi phí 0): +0,06 (CI −0,24…+0,38), +2,8%/năm, p(≤0) = 0,33** — chọn momentum tốt hơn ngẫu nhiên nhưng *chưa chứng minh hơn mua rổ đều*, và +2,8%/năm trước chi phí < chi phí thực ~5%/năm.
- **Bộ lọc MA200 vs dịch thời điểm ngẫu nhiên** (≥ 1 năm, giữ tỷ lệ bật/tắt): Sharpe placebo 0,11 ± 0,18; PHÒNG THỦ 0,27 → p = 16,5% (z = 0,9) — **không có bằng chứng timing**; lợi ích chủ yếu là giảm rủi ro cơ học. Với ETF: E1VFVN30 + MA200 (Sharpe 0,50 trong chạy kiểm định, từ 2015) p = 5,2% vs placebo, DSR (20 cấu hình) 0,81, hơn mua-giữ +0,09 (CI −0,32…+0,54): gần ngưỡng nhưng **không qua**.
- **Kiểm tra tín hiệu thuần** (`vn_signal_test.json`, trễ 3 phiên, không chi phí): IC trung bình 12−1/U100 = +0,040 (t = 2,0); top-15 − universe = +0,39%/tháng (t = 1,2); Q1−Q5 = +0,78%/tháng (t = 1,4); lookback 3 và 6 tháng mạnh hơn (Q1−Q5 1,5–1,6%/tháng, t ≈ 2,5–2,9). Theo giai đoạn IC: 2014-17 0,090; 2018-19 0,065; 2020 −0,035; 2021 0,056; 2022 −0,005; 2023-26 0,002 → hiệu ứng **biến mất sau 2019**. Mọi lát cắt thua ở phía đảo chiều: đảo dấu (mua top thua) Sharpe −0,41.

### 4.4 Độ nhạy chi phí, rf, thực thi
| Biến thể (CHÍNH / PHÒNG THỦ) | Sharpe | CAGR |
|---|---|---|
| Chi phí ×0 | 0,35 / 0,41 | 10,4% / 10,9% |
| ×0,5 | 0,29 / 0,34 | 8,7% / 9,6% |
| **×1 (cơ sở)** | **0,21 / 0,27** | 6,9% / 8,1% |
| **×2** | **0,09 / 0,14** | 3,9% / 5,3% |
| ×3 | −0,04 / 0,00 | 0,9% / 2,7% |
| Chỉ trượt giá ×2 | 0,18 / 0,23 | 6,0% / 7,2% |
| Khớp ở close / open thay VWAP | 0,23 / 0,23 | 7,3% |
| Mua không đợi T+2 (t+1) | 0,22 / 0,33 | 7,2% |
| rf = 0% / 3% / 7% | 0,41 / 0,28 / 0,11 | (CHÍNH) |
Chiến lược **rất nhạy chi phí**: gấp đôi chi phí còn Sharpe ~0,1 (CAGR 3,9% < tiền gửi). Chênh lệch giữa các cách khớp (±0,06) nằm trong nhiễu.

### 4.5 Sức chứa / thanh khoản (`vn_fig5_capacity_cost_survivorship.png`)
Vốn 1 → 200 tỷ đồng: Sharpe 0,21 → 0,21 (giới hạn 10% KL TB20 hầu như không cắn nhờ top-100 lọc theo thanh khoản); 1.000 tỷ: 0,09 (đầu tư chỉ 80%, vòng quay giảm). Hạn mức 2/5/10/20% KL: 0,20/0,21/0,21/0,21. Không phải ràng buộc thực tế với tài khoản cá nhân.

### 4.6 Survivorship bias
| Universe | CHÍNH Sharpe / CAGR | PHÒNG THỦ |
|---|---|---|
| Đầy đủ, theo thời điểm, có mã hủy niêm yết (CƠ SỞ) | 0,21 / 6,9% | 0,27 / 8,1% |
| Chỉ mã còn niêm yết cuối 2026 | 0,25 / 7,7% | 0,31 / 8,9% |
| **Rổ VN100 hiện tại áp ngược** | **0,58 / 15,9%** | 0,57 / 13,9% |
| Hủy niêm yết −50% thêm | 0,20 / 6,5% | 0,25 / 7,6% |
Thiên lệch sống sót khi dùng rổ hiện tại: **+0,37 Sharpe, +9%/năm** (chủ yếu vì rổ hiện tại gồm những mã *đã thắng*, tính cả mã còn nhỏ năm 2014 sau này lớn). Hạn chế còn lại: chưa nạp mã đang niêm yết trên HNX/UPCoM từng ở HOSE rồi chuyển sàn (hiếm); mã hủy niêm yết bị đóng băng giá cuối (halt) — thực tế mất tiền khi thanh lý có thể xấu hơn.

### 4.7 Độ nhạy tham số (`vn_fig3_sensitivity.png`)
Sharpe lưới 672 cấu hình: −0,23…+0,48, trung vị 0,16. Trung vị theo chiều: lookback 12−0 0,25 / 12−1 0,21 / 3−1 0,06 (vùng xấu: lookback ngắn có bỏ tháng gần nhất); universe 100 0,23 vs 30 0,10; N 10/15/20/30 = 0,13/0,15/0,16/0,24 (càng đa dạng càng tốt); rebalance Q 0,21 vs M 0,12 (chi phí); tỷ trọng nghịch biến động 0,20 vs đều 0,14; lọc tháng 0,20 ≈ không lọc 0,20 > lọc ngày 0,11. Tức *kiểm soát chi phí và đa dạng hoá* quan trọng hơn tín hiệu — nghĩa là hướng "cải tiến" tự nhiên là tiến dần về danh mục thụ động rộng.

### 4.8 Tách mẫu / walk-forward
| Phép thử | Kết quả |
|---|---|
| Chọn tốt nhất trên 2014-19 → thử 2020-26 | chọn `6-0/U100/N15/M/iv/không lọc`: IS 0,77 → OOS **0,10** (hạng 12%; trung vị OOS 0,30; top-100 đều OOS 0,39) |
| Chọn trên 2020-26 → thử 2014-19 | IS 0,71 → OOS 0,01 (top-100 đều 0,02) |
| Tương quan hạng Sharpe IS vs OOS (672 cấu hình) | **−0,30** (cấu hình tốt trong mẫu thường tệ ngoài mẫu) |
| Walk-forward mở rộng (chọn theo Sharpe 36 tháng, 2018-26) | 0,07 (9 lần chọn đều khác nhau) vs CHÍNH 0,01, PHÒNG THỦ 0,20, top-100 đều 0,22 |
| CHÍNH tham số cố định, 2014-19 / 2020-26 | 0,34 / 0,14 (PHÒNG THỦ 0,03 / 0,45) |

### 4.9 Beta/alpha
Hồi quy tháng trên VN-Index (HAC 3): CHÍNH alpha −0,4%/năm (t −0,1), beta 0,91, tương quan 0,74; PHÒNG THỦ alpha +2,1% (t 0,5), beta 0,49; top-100 đều alpha −0,5%, beta 0,91; top-30 đều alpha −4,1% (t −1,5), beta 1,09. CHÍNH − top-100: alpha +0,1%/năm (t 0,03). **Toàn bộ lợi suất là beta thị trường.**

## 5. Yếu tố cơ bản (value/chất lượng): KHÔNG dùng
Đã kiểm tra thật nguồn VNDirect:
- `ratios` (PE, PB…) có chuỗi hằng ngày từ 2017-12 nhưng **không point-in-time**: EPS ngầm định (close/PE) thay đổi đúng vào **ngày cuối quý** hoặc ngày đầu quý sau (độ trễ 1–2 hoặc 90–92 ngày so với cuối quý trước) ở 8 cổ phiếu được thử đến ~2022-09 (≈ 20–45 ngày trước khi báo cáo thực sự công bố) → look-ahead. Từ ~2022-10 các bước nhảy lệch 25–35 ngày sau cuối quý (giống thời điểm công bố thật), tức chỉ ≈ 4 năm gần đây đáng tin.
- `financial_statements` có `createdDate` nhưng nhiều bản ghi bị nạp bù hàng loạt (2019-12-01) và không có từ điển mã khoản mục công khai.
- ROE/EPS trong `vn-market` là suy ra từ P/E, P/B hiện tại (snapshot), không có lịch sử.
Theo quy tắc đã đặt, **không đưa yếu tố cơ bản vào backtest**. Muốn làm cần nguồn BCTC có ngày công bố (FiinQuant/WiChart/CTCK) hoặc tự dựng từ BCTC + độ trễ bảo thủ (+45/+100 ngày).

## 6. Giới hạn
1. **Chỉ 12,7 năm** (2014-2026; ~8 năm nếu chỉ dùng vn_daily); bao gồm đúng **một** chu kỳ bong bóng 2021 và sập 2022; Sharpe ±0,3 là sai số bình thường (CI rộng ±0,6).
2. Proxy VN-Index trước 2017-08 và rổ "VN100/VN30" xấp xỉ theo thanh khoản (không phải theo vốn hóa tự do chuyển nhượng; top-30 của ta chứa nhiều cổ phiếu đầu cơ → benchmark yếu hơn VN30 thật).
3. Chi phí/trượt giá là mô hình (không có dữ liệu sổ lệnh); tiền gửi 4,5% là giả định; thuế cổ tức, margin, hạn chế giao dịch, T+1 (chưa thấy) không mô hình.
4. Nguồn dữ liệu là API không chính thức, có thể đổi; giá điều chỉnh tính theo hiện tại.
5. Đã thử 744 cấu hình (tính hết vào Deflated Sharpe); cấu hình "Q/nghịch biến động/lọc" tốt hơn trong lưới (0,48) chỉ được báo cáo, không dùng làm cơ sở chọn.

## 7. Tín hiệu hiện tại (2026-10-09, chỉ để tham khảo, không phải khuyến nghị)
VN-Index 1.735 < SMA200 1.797 → bộ lọc **TẮT** (PHÒNG THỦ giữ tiền mặt). Top-15 momentum 12−1 trong top-100 thanh khoản: VIC, HHP, PET, BSR, VHM, NAF, PVD, GAS, DCL, MCH, STB, PVP, PVT, VJC, DHC (`vn_last.json`).

## 8. Quyết định về paper trading
Không triển khai `vn_momentum_v1`: (a) không qua cổng nào làm cơ sở cho kỳ vọng vượt thị trường (DSR 0,24; ΔSharpe so với thụ động ≤ 0; walk-forward thất bại; tín hiệu biến mất sau 2019); (b) vận hành thật cần dữ liệu giá điều chỉnh + thanh khoản cho ~100 mã trong `md.bars` (hiện chỉ có VN:FPT/VCB/VNM) và luật T+2/bước giá/biên độ trong paper-trader (chưa có) — công sức lớn cho một chiến lược không có edge; (c) 12 tuần paper không thể phân biệt Sharpe 0,2 với 0. Nếu người dùng vẫn muốn: ứng viên rẻ nhất là **E1VFVN30 + MA200 tháng** (như lớp giảm rủi ro, không phải nguồn lợi nhuận) — cần nạp E1VFVN30 + VN-Index vào bars và gắn thêm bước giá ETF 10đ; hoặc chạy dữ liệu `vn-market` làm "đối chứng thụ động" EW top-100. Khuyến nghị hành động thực tế: giữ **phương án A** (cảnh báo/dữ liệu, tự quyết) và mua-giữ ETF rộng nếu có nhu cầu đầu tư VN.

## 9. Tái lập (trên VPS)
```
python research/vn/fetch_vn.py      # ~25 phút, 876 mã -> /root/research/vn/data/raw
python run_vn.py bench grid sens placebo last extra   # ~2 phút (6 CPU)
python signal_test.py; python analyze_vn.py            # hình + vn_analysis.json
```
Script upload + chạy container `research-vn-*`: `research/vn/vps_run_vn.sh <script> [stage]`.
