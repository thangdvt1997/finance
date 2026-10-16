# R1 — Học thuật & quỹ: premia nào còn sống sau chi phí với vốn nhỏ bán lẻ qua MT5

Ngày: 2026-10-15. Agent R1. Phương pháp: WebSearch (tóm tắt kết quả tìm kiếm + abstract), đối chiếu số liệu nội bộ (BACKTEST_STUDY, MULTI_ASSET_BACKTEST). Giới hạn trung thực: phần lớn số liệu dưới đây lấy từ abstract/bản tóm tắt thứ cấp (Quantpedia, CXO, Alpha Architect, Man), CHƯA đọc toàn văn từng bài; mức tin cậy phản ánh điều đó. Nhiều tác giả thuộc AQR/Man (bên bán sản phẩm) nên có thiên lệch lợi ích.

## 1. Tóm tắt (kết luận thẳng)

1. Bằng chứng học thuật dài hạn mạnh nhất là **trend/time-series momentum đa tài sản** (hàng trăm năm, hàng chục thị trường), nhưng edge **đã yếu đi rõ rệt sau 2009-2010**: SG Trend Index Sharpe 0,05 (2010-2018) so với 0,28 (từ 2000); drawdown -20,4% (5/2024-5/2025). Phù hợp số nội bộ của ta (Sharpe 0,55 cả kỳ; 0,16 trong 2010-19; DSR 0,87 < 0,95).
2. Mọi premia công bố đều **suy giảm**: McLean-Pontiff: -26% ngoài mẫu, -58% sau công bố (cổ phiếu, 97 biến). Kỳ vọng thực tế = **một nửa hoặc ít hơn** số trong bài báo.
3. Với vốn nhỏ bán lẻ trên MT5 (CFD), **chi phí nuôi vị thế (swap/markup trên notional có đòn bẩy) mới là kẻ giết edge**, không phải spread (nội bộ: chi phí+swap ăn 0,12-0,24 Sharpe). Chiến lược quay vòng thấp, khung D1/W, đòn bẩy thấp mới sống nổi.
4. **Không có premia nào đủ bằng chứng để coi là nguồn lợi nhuận độc lập chắc chắn cho tài khoản bán lẻ MT5.** Ứng viên đáng thử ở mức "diversifier + kiểm soát rủi ro": trend chậm đa tài sản (đòn bẩy thấp), cross-sectional momentum/carry FX (đã có bằng chứng sau chi phí bid-ask nhưng bị ăn bởi swap), vol-targeting (chủ yếu giảm đuôi, không tăng Sharpe trừ tài sản rủi ro).

## 2. Bảng phát hiện

| # | Premia / chủ đề | Bằng chứng chính (số) | Nguồn | Tin cậy | Decay / chi phí | Kết luận cho ta |
|---|---|---|---|---|---|---|
| 1 | Time-series momentum (TSMOM) | 58 hợp đồng tương lai (chỉ số, FX, hàng hoá, trái phiếu); dai dẳng 1-12 tháng rồi đảo chiều một phần; danh mục đa dạng cho alpha bất thường, tốt nhất ở thị trường cực đoan. JFE 2012. | https://papers.ssrn.com/abstract=2089463 | Cao (hiện tượng), Vừa (độ lớn hiện tại) | Mẫu gốc 1985-2009; sau đó yếu | THỬ (R10: trend đa tài sản + vol-target) |
| 2 | Trend 137 năm | 67 tài sản, 1880-2016, lookback 1/3/12 tháng; Sharpe ~0,4 sau phí 2%/20% (CXO tóm tắt); AQR nói chi phí giao dịch thực chỉ ~1/6 ước tính của bài (thứ cấp, tác giả bán sản phẩm) | https://www.aqr.com/Insights/Research/Journal-Article/A-Century-of-Evidence-on-Trend-Following-Investing ; https://www.cxoadvisory.com/momentum-investing/trend-following-with-intrinsic-momentum-over-the-very-long-run | Cao (dài hạn), Vừa (kỳ vọng tương lai) | Dữ liệu cũ có chi phí rất khác | THỬ như diversifier |
| 3 | Hai thế kỷ trend (độc lập, Bouchaud/CFM) | Sharpe ~0,7 (danh mục đa dạng, 1800+), t~5 từ 1960, ~10 từ 1800; chỉ số đơn lẻ Sharpe ~0,3 | https://ar5iv.arxiv.org/html/1404.3274 ; https://arxiv.org/pdf/1708.07637 | Cao (nghiên cứu độc lập khỏi AQR) | Sharpe 0,7 là tổng hợp thế giới, không phải bán lẻ | Xác nhận hiện tượng; đừng kỳ vọng 0,7 |
| 4 | Trend mở rộng | "Trends Everywhere": 82 chứng khoán mới + 16 yếu tố cổ phiếu long-short vẫn có TSMOM (out-of-sample) | https://joim.com/trends-everywhere | Vừa (chưa xác nhận tác giả; abstract) | — | Hỗ trợ độ bền |
| 5 | Trend sau 2009 | SG Trend: Sharpe 0,05 (2010-18) vs 0,28 (từ 2000), AQR quy cho biên độ giá nhỏ, không phải đông đúc. SG Trend drawdown -20,4% 5/2024-5/2025 (Cambridge Assoc.: mang tính chu kỳ, "chưa hỏng cấu trúc"). Preprint arXiv 2607.01550 lập luận gãy cấu trúc trong trend ngắn hạn (chưa bình duyệt) | https://theideafarm.com/alternative-investment/you-cant-always-trend-when-you-want-2/ ; https://www.cambridgeassociates.com/insight/does-trend-followings-recent-struggle-signal-that-the-strategy-is-structurally-broken/ ; https://arxiv.org/pdf/2607.01550 | Vừa (số), Thấp (preprint) | Trend ngắn hạn tệ hơn trend chậm | Chỉ trend CHẬM (>=3 tháng); tránh trend ngắn hạn |
| 6 | Trend như bảo hiểm cổ phiếu | AQR "Hold the Dip": SG Trend alpha 4,7% so với cổ phiếu; 4 đợt giảm >20% từ 2000 trung bình +28,6% (BTD -18,4%); MA 10 tháng giảm MaxDD ~60% -> ~20%, Sharpe 0,47 -> 0,75 (chỉ số cổ phiếu) | https://alphaarchitect.com/is-trend-following-better-than-buy-the-dip/ ; https://aqr.com/Insights/Research/Alternative-Thinking/Should-Your-Portfolio-Protection-Work-Fast-or-Slow | Vừa (AQR tự công bố, chưa tính chi phí) | Chưa phí | Dùng làm lớp bảo vệ/đa dạng hoá, khớp kết quả nội bộ |
| 7 | Decay sau công bố | McLean-Pontiff (JF 2016): 97 biến; -26% ngoài mẫu, -58% sau công bố; giảm nhiều hơn với cổ phiếu dễ giao dịch | https://ivey.uwo.ca/media/3775549/pontiff.pdf | Cao | Quy tắc: chia 2 số học thuật | Áp dụng haircut >=50% cho mọi kỳ vọng |
| 8 | Decay premia thế kỷ (value/momentum/carry/defensive) | Premia ước lượng giảm ~30% ngoài mẫu, nhiều khả năng do overfit hơn do giao dịch thông tin (Gray, qua Alpha Architect). Momentum cổ phiếu ~10%/năm thập niên 1990 -> ~2% nay (Lee 2025, preprint; fit mô hình decay hyperbol; value/quality không fit) | https://alphaarchitect.com/factor-investing-research-on-steroids/ ; https://arxiv.org/html/2512.11913v1 | Vừa / Thấp (preprint) | — | Ưu tiên premia "cơ chế rủi ro/hành vi bền" hơn "pattern cơ học" |
| 9 | Chi phí giao dịch | Novy-Marx & Velikov: chi phí giảm lợi nhuận và ý nghĩa thống kê ở MỌI anomaly; chỉ chiến lược quay vòng thấp (<50%/tháng một chiều) mới còn ý nghĩa; Patton-Weller: quỹ thực nhận rất ít momentum/value | https://nber.org/papers/w20721 ; https://public.econ.duke.edu/~ap172/Patton_Weller_MF_28nov18.pdf | Cao (cổ phiếu Mỹ) | Phù hợp BACKTEST_STUDY nội bộ | Chỉ chạy quay vòng thấp |
| 10 | FX carry | Payoff lớn, ít tương quan với yếu tố truyền thống, giải thích bằng "peso problem"/đuôi (Burnside et al., RFS 2011). Carry thô ăn bid-ask (một bảng: gộp 0,53% -> ròng 0,21%) | https://www.nber.org/papers/w14054 ; https://mycourses.aalto.fi/mod/resource/view.php?id=444217 | Vừa | Rủi ro crash (đuôi trái); swap broker bán lẻ ăn markup | THỬ thận trọng (carry proxy bằng swap MT5, R10); không kỳ vọng lớn |
| 11 | FX momentum (cross-sectional) | Có báo cáo 5,7-5,8%/năm sau chi phí bid-ask (formation 1 và 3 tháng) trong một nghiên cứu độc lập; một WP khác tới 10%/năm gộp; ít tương quan carry | https://www.bis.org/publ/work366.pdf (liên quan) ; kết quả tìm kiếm trên | Thấp-Vừa (không xác minh bài gốc; mẫu cũ, G10) | Chưa tính swap và decay | THỬ (R10: CS momentum FX) |
| 12 | Vol-targeting / vol-managed | Moreira-Muir (JF 2017): alpha lớn với yếu tố cổ phiếu và carry FX, tăng Sharpe ~25% thị trường. NHƯNG Cederburg et al. (JFE 2020, 103 chiến lược): ngoài mẫu thực thi được thường KHÔNG hơn bản không quản lý; Barroso-Detzel: không sống sau chi phí. Harvey et al. (Man AHL, JPM 2018, 60+ tài sản): Sharpe chỉ tăng ở tài sản rủi ro (cổ phiếu/tín dụng, nhờ hiệu ứng đòn bẩy); với trái phiếu/FX/hàng hoá ~0; luôn giảm xác suất đuôi | https://www.nber.org/papers/22208 ; https://www.lehigh.edu/~xuy219/research/COWY.pdf ; https://www.man.com/insights/the-impact-of-volatility-targeting | Cao (kết luận trái chiều có lý do) | Chi phí tái cân bằng | DÙNG làm công cụ kiểm soát rủi ro/đuôi, KHÔNG coi là nguồn alpha |
| 13 | Risk parity / leverage aversion | AFP (FAJ 2012): tài sản an toàn có Sharpe cao hơn; risk parity cổ phiếu+trái phiếu 1926-: excess 2,2% (chưa đòn bẩy) vs thị trường 3,84%; đòn bẩy lên vol 15% -> 7,99%. Bị phê phán: phụ thuộc kỳ mẫu, có look-ahead (Anderson-Bianchi-Goldberg) | https://www.aqr.com/Insights/Research/Journal-Article/Leverage-Aversion-and-Risk-Parity ; https://cdar.berkeley.edu/sites/default/files/Anderson2012-01revised.pdf | Vừa-Thấp (cần đòn bẩy; trái phiếu 2022 đau; AQR bán sản phẩm) | Cần đòn bẩy -> chi phí tài trợ CFD cao | KHÔNG DÙNG làm chiến lược lõi qua MT5 (không có trái phiếu sạch, tài trợ đắt) |
| 14 | Value / defensive (low-vol, quality) | Cổ phiếu: value/quality suy giảm chậm hơn mô hình cơ học; AQR Style Premia long-short +21,2% 2024 (Morningstar, nguồn có lợi ích) nhưng các premia này chủ yếu ở rổ cổ phiếu/đòn bẩy cao | https://www.morningstar.com/financial-advisors/factor-investing-is-very-much-alive | Thấp | Cần danh mục cổ phiếu rộng, short | KHÔNG DÙNG qua MT5 CFD (rổ nhỏ, short đắt); xem R8 cho cổ phiếu VN long-only |
| 15 | Commodity TF out-of-sample | Một bản cài QuantConnect (hàng hoá 2010-2020) Sharpe -0,13 (một lần cài, không phải bác bỏ) | https://www.quantconnect.com/research/15257/commodities-futures-trend-following/ | Thấp | — | Cẩn trọng với hàng hoá CFD (chỉ có ETF/futures liên tục, không điều chỉnh roll) |

## 3. Đối chiếu quỹ / nguồn công khai

- **AQR** (Pedersen, Hurst, Ooi, Asness): nguồn của #1, 2, 6, 13; ủng hộ mạnh trend/premia nhưng là bên bán quỹ -> thận trọng, nhưng cũng thừa nhận giai đoạn 2010-2018 kém và quy cho biên độ giá.
- **Man AHL / Oxford-Man** (Harvey et al.): vol-targeting; công khai chỉ ra Sharpe không tăng ngoài tài sản rủi ro. Hữu ích vì nói ngược lợi ích marketing.
- **CFM / Bouchaud** (độc lập, Pháp): xác nhận trend qua 2 thế kỷ nhưng chỉ ra chỉ số đơn lẻ Sharpe chỉ ~0,3.
- **Cambridge Associates**: trend yếu 2024-25 là chu kỳ, không phải hỏng.
- **Alpha Architect / Robeco / Winton**: Alpha Architect chỉ dùng như người tóm tắt học thuật (đã trích). Tìm Robeco/Winton trực tiếp không trả được tài liệu nguyên bản trong phiên này -> **chưa đối chiếu**; ghi là việc còn lại (ưu tiên Robeco "Conservative Formula/ Factor Investing" và Winton "Trend Following Primer" nếu cần).
- Không tải được bài gốc "Value and Momentum Everywhere" và "Common Risk Factors in Currency Markets" qua công cụ này; số liệu về hai bài này **không** đưa vào bảng.

## 4. Premia nào còn sống sau chi phí với vốn nhỏ bán lẻ qua MT5?

| Premia | Khả thi qua MT5 CFD | Ước tính thực tế (sau haircut + chi phí) | Phán quyết |
|---|---|---|---|
| Trend chậm đa tài sản (chỉ số, vàng, FX major, vài hàng hoá) | Có (D1/W, quay vòng thấp, đòn bẩy <=1,5x) | Sharpe 0,3-0,5; excess 3-5%/năm ở vol 10%; ~30% số năm âm; có thể dưới đỉnh 4-5 năm (nội bộ). Giá trị chính: đa dạng hoá/crisis alpha | THỬ (paper), vai trò diversifier |
| TSMOM từng tài sản đơn lẻ | Có | Sharpe đơn lẻ ~0,3 (CFM); nhiễu cao | Chỉ làm một phần của rổ |
| Trend ngắn hạn (H1-H4, <1 tháng) | Có | Có bằng chứng gãy/suy yếu mạnh sau 2009; chi phí cao | KHÔNG DÙNG |
| Cross-sectional momentum FX | Có (G7 + vài cặp) | Còn dương sau bid-ask trong nghiên cứu cũ; swap + decay -> có thể ~0 | THỬ nhưng kỳ vọng thấp |
| Carry FX | Có nhưng swap broker có markup; đuôi trái | Gộp nhỏ; ròng có thể âm sau markup 0,5-1% | THỬ như bộ lọc/đối chứng; không phải lõi |
| Vol-targeting | Có | Không tăng Sharpe trừ cổ phiếu; giảm đuôi | DÙNG như quản trị rủi ro |
| Value/defensive/quality cổ phiếu | Không thực tế (CFD cổ phiếu, rổ nhỏ) | — | KHÔNG DÙNG (xem R8) |
| Risk parity | Không thực tế (đòn bẩy + trái phiếu) | — | KHÔNG DÙNG |

Nguyên tắc: chỉ tin phần học thuật cho phép chi phí + decay; nhân đôi spread/swap trong kịch bản xấu; mọi ứng viên đều cần qua DSR/PBO trên TEST chưa dùng.

## 5. Đề xuất ứng viên cho R10 (đăng ký giả thuyết TRƯỚC khi mở test)

1. **C1 Trend chậm đa tài sản + vol-target (lớp diversifier).** Lookback 3/6/12 tháng ghép, vol-target 10%, đòn bẩy <=1,5x, D1 tái cân bằng tuần. H0: Sharpe sau phí <= 0 trên đoạn chưa chạm; kỳ vọng 0,3-0,5. Đối chứng: placebo dịch tín hiệu, 60/40.
2. **C2 Rổ trend 3 lookback so với 1 lookback** (kiểm tra độ nhạy; nội bộ lookback 3-6 tháng yếu): chỉ báo độ bền, không chọn tham số tốt nhất.
3. **C3 Cross-sectional momentum FX G7** (formation 1-3 tháng, giữ 1 tháng, dài top-2/ngắn bottom-2); tính bid-ask từ spread MT5 thật + swap thật của MT5 (không dùng markup giả định). H0: Sharpe ròng <= 0.
4. **C4 Carry proxy bằng swap MT5** (rank theo swap long/short thực của MT5), kèm bộ lọc vol; so sánh có/không bộ lọc crash. Kỳ vọng thấp; chủ yếu để đo markup broker.
5. **C5 Overlay quản trị rủi ro:** vol-target + cắt vị thế khi drawdown/vol cao áp lên C1; đo tác động lên MaxDD và đuôi, không lên Sharpe (theo Harvey et al.).
6. **C6 MA 10 tháng trên chỉ số/vàng** (quy tắc đơn giản kiểu AQR): kiểm tra Sharpe và MaxDD so với buy-and-hold; chú ý thiên lệch mua dài hạn (placebo nội bộ: tín hiệu ngẫu nhiên đã đạt 0,57).

Không đề xuất: risk parity, value/low-vol cổ phiếu CFD, trend ngắn hạn.

## 6. Cảnh báo phương pháp
- Hầu hết số liệu là từ tóm tắt; cần đọc toàn văn nếu dùng để đặt tham số.
- Thiên lệch lợi ích (AQR, Man, Morningstar). Hai preprint (arXiv 2607.01550, 2512.11913) chưa bình duyệt.
- Nghiên cứu học thuật dùng futures (không swap/markup đòn bẩy); CFD bán lẻ có cấu trúc chi phí khác -> kết quả gốc chỉ là cận trên.
- Bậc tự do người nghiên cứu: bảng chọn nguồn theo kết quả tìm kiếm, có thể bỏ sót bài phản biện (ví dụ "Time series momentum: is it there?" chưa kiểm được).

## 7. Việc còn lại / cho người dùng
- Đọc toàn văn: TSMOM, Century of Evidence (bảng phí), Cederburg 2020, Novy-Marx-Velikov.
- Bổ sung nguồn Robeco/Winton/Man AHL công khai; Lustig-Roussanov-Verdelhan, Menkhoff 2012 (FX momentum, chi phí) trước khi dùng cho C3/C4.
