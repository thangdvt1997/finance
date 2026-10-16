# Báo cáo phương án: các phương pháp giao dịch ổn định, kỳ vọng lợi nhuận thực tế

Ngày: 2026-10-11 · Phạm vi: nghiên cứu văn liệu, KHÔNG sửa code, hệ thống vẫn READ-ONLY · Mọi nội dung chỉ là thông tin, không phải tư vấn đầu tư.

**Quy ước mức chắc chắn:** [CAO] = nhiều nguồn độc lập/peer-review, tôi đã thấy nguồn trong phiên nghiên cứu này; [TB] = có nguồn nhưng một phần dựa trên kiến thức nền của tôi hoặc nguồn thứ cấp, cần kiểm lại; [THẤP] = ước lượng/suy luận, chưa kiểm chứng. Các con số Sharpe/drawdown "điển hình" ở mục 1 là KHOẢNG ĐỊNH HƯỚNG tổng hợp từ văn liệu, không phải số đo trực tiếp cho hệ thống này.

---

## 0. Sự thật nền tảng (đọc trước)

1. **Phần lớn trader bán lẻ thua lỗ.** Đây là kết luận mạnh nhất và chắc nhất của toàn bộ báo cáo.
2. **Không phương pháp nào đảm bảo lợi nhuận.** Các "premia" có bằng chứng (trend, carry, value, momentum) có Sharpe thấp-vừa, đi kèm các giai đoạn lỗ nhiều năm.
3. **Kỳ vọng thực tế khiêm tốn** cho vốn nhỏ sau chi phí: Sharpe danh mục đa dạng ~0,3-0,7 là đã tốt; drawdown 15-30% là bình thường. Đừng thiết kế hệ thống dựa trên Sharpe > 1.
4. Giá trị lớn nhất của hệ thống ở giai đoạn này là **kiểm chứng + kỷ luật rủi ro + cảnh báo**, không phải "tìm ra máy in tiền".

### 0.1 Thống kê tỷ lệ thua của retail CFD/forex và day trading

| Nguồn | Con số | Ghi chú | Mức chắc |
|---|---|---|---|
| ESMA (quyết định can thiệp sản phẩm 2018, tổng hợp từ cơ quan quốc gia EU) | 74-89% tài khoản CFD bán lẻ lỗ; lỗ TB/khách ~1.600-29.000 EUR | Số cũ (2018) nhưng là mốc quy định; EU buộc nhà môi giới công bố % lỗ 12 tháng trên mọi quảng cáo | CAO |
| ASIC REP 579 (2017), dẫn trong thông cáo 19-220MR | 72% khách CFD lỗ; 63% với CFD cặp tiền; 80% quyền chọn nhị phân | https://www.asic.gov.au/about-asic/news-centre/find-a-media-release/2019-releases/19-220mr-asic-proposes-ban-on-the-sale-of-binary-options-to-retail-clients-and-restrictions-on-the-sale-of-cfds | CAO |
| ASIC thông cáo 26-004MR (2026), dẫn lại qua Finance Magnates | FY2024: 68% nhà đầu tư CFD bán lẻ lỗ, >458 triệu AUD (gồm 73 triệu phí); CFD quyền chọn 85% | https://www.asic.gov.au/about-asic/news-centre/find-a-media-release/2026-releases/26-004mr-asic-secures-nearly-40-million-in-refunds-to-investors-and-drives-change-after-cfd-sector-falls-short/ ; chi tiết 68%/85% qua nguồn thứ cấp | TB |
| FCA (đề xuất 12/2016) | 82% khách CFD trong mẫu tài khoản đại diện lỗ; đề xuất giảm đòn bẩy xuống 50:1 | https://fca.org.uk/news/press-releases/fca-proposes-stricter-rules-contract-difference-products ; có tranh cãi phương pháp từ ngành | CAO (mẫu) |
| Chague, De-Losso, Giovannetti, "Day Trading for a Living?" (FGV 2020) | Trong nhóm day trade hợp đồng tương lai chỉ số Brazil >=300 ngày: 97% lỗ, 0,4% kiếm hơn lương nhân viên ngân hàng; không có bằng chứng "học được" | https://repositorio.fgv.br/items/e87d04fc-4b4c-4a56-ab5a-1c84c1afde1b/full | CAO |

Hàm ý thiết kế: (a) tránh scalping/day-trading đòn bẩy cao; (b) tránh sản phẩm có chi phí cố định lớn (spread rộng, phí qua đêm); (c) hệ thống phải có cơ chế **tự dừng** khi bằng chứng không ủng hộ.

### 0.2 Rủi ro phương pháp luận (tại sao backtest đẹp thường vô nghĩa)

| Rủi ro | Bằng chứng | Mức chắc |
|---|---|---|
| Overfitting / chọn mô hình tốt nhất sau nhiều lần thử | Bailey et al., Probability of Backtest Overfitting (CSCV): https://papers.ssrn.com/abstract=2326253 ; Deflated Sharpe Ratio: https://papers.ssrn.com/abstract=2460551 | CAO |
| Data-snooping / "factor zoo": cần ngưỡng t-stat cao hơn (~3) | Harvey, Liu, Zhu, RFS 2016 (con số t~3 là từ kiến thức nền, nguồn tìm được chỉ xác nhận trích dẫn) | TB |
| Alpha decay sau công bố | McLean & Pontiff, J. Finance 2016: lợi nhuận dự báo giảm ~26% ngoài mẫu và ~58% sau công bố (97 biến) https://ivey.uwo.ca/media/3775549/pontiff.pdf | CAO |
| Survivorship bias | Cổ phiếu bị hủy niêm yết/ETF đóng bị loại khỏi dữ liệu miễn phí (Yahoo...). Đặc biệt nặng trên thị trường VN nếu dữ liệu không có mã đã hủy | CAO (nguyên lý), THẤP (mức độ ở VN) |
| Chi phí bị đánh giá thấp | Man AHL: chi phí ảnh hưởng chiến lược nhanh nhiều hơn vì turnover cao https://www.man.com/insights/need-for-speed-trend-following | TB |
| Biến thiên ngẫu nhiên: Sharpe thật ~0,5 cần nhiều năm mới phân biệt được với 0 | Thống kê cơ bản (SE của Sharpe ~ 1/sqrt(số năm)): cần ~10-16 năm dữ liệu để t~2 với Sharpe 0,5 | CAO (toán học) |

---

## 1. Bằng chứng theo họ chiến lược

Cột "Sharpe sau chi phí" là khoảng ĐỊNH HƯỚNG cho phiên bản đa dạng hóa, có thể áp dụng thực tế; số trong bài báo gốc thường cao hơn do gộp 60-70 thị trường, giả định chi phí thấp, hoặc mẫu dài.

| Họ chiến lược | Sharpe sau chi phí (định hướng) | Drawdown điển hình | Ổn định theo thời kỳ | Còn hiệu lực sau công bố? | Nhạy chi phí | Vốn nhỏ |
|---|---|---|---|---|---|---|
| Trend following / time-series momentum (đa tài sản) | 0,3-0,7 (danh mục CTA); mẫu dài 1880-2016 tốt hơn | 15-30%; có chu kỳ 2-4 năm yếu | 2008 rất tốt; 2020 hỗn hợp; 2022 rất tốt (SG Trend +~36% 9 tháng đầu); 2023 -3%; 2025 -8% đến -11% nửa đầu | Còn, nhưng yếu đi sau 2009-2013 theo một số replication (Kim-Tse-Wald); giải thích chu kỳ chứ chưa phải chết hẳn | Trung bình (tín hiệu chậm ít nhạy) | Khả thi nếu dùng ETF/CFD ít thị trường; đa dạng hóa kém |
| Cross-sectional momentum (cổ phiếu) | 0,3-0,6 sau phí (long-only yếu hơn long-short) | 30-50%+ trong momentum crash (2009) | Crash sau thị trường hồi phục (2009); 2022 tốt trên hàng hóa | Giảm một phần; Daniel-Moskowitz: quản trị bằng điều chỉnh theo biến động ~gấp đôi Sharpe | Cao (turnover) | Khả thi với cổ phiếu thanh khoản; VN không short được |
| Carry (FX carry) | 0,2-0,5 | 20-40%, đuôi trái nặng (2008, 2015, 2020) | Crash khi biến động toàn cầu tăng; lợi nhuận âm khi risk-off | Còn nhưng thấp, đuôi rủi ro lớn | Thấp-TB nhưng swap/phí qua đêm của broker có thể xóa hết | Khả thi nhưng KHÔNG ổn định |
| Value (đa tài sản, cổ phiếu) | 0,2-0,4 | 20-40%, có thập kỷ yếu (2010s) | 2020-2022 hồi phục một phần | Yếu đi, ở VN bằng chứng trái chiều | Thấp (turnover thấp) | Tốt, phù hợp dài hạn |
| Mean reversion / pairs / stat-arb | Gross 0,5-1,5; net thường thấp hơn nhiều | Thường nhỏ rồi "nổ" đuôi (2007 quant quake) | Nhạy chế độ thị trường | Alpha decay mạnh (cạnh tranh HFT) | Rất cao | Kém; VN không short được |
| Volatility targeting / risk parity (lớp quản trị, không phải alpha) | Tăng Sharpe nhẹ cho tài sản rủi ro; giảm drawdown | Giảm nhưng không loại bỏ; 2022 risk parity lỗ nặng (trái phiếu+cổ phiếu cùng giảm) | 2022 xấu cho risk parity | Là công cụ, vẫn dùng được | Thấp | Rất tốt |
| Breakout (Donchian/Turtle) | Cùng họ trend: 0,2-0,5 trên danh mục đa dạng | 25-40% | Tương tự trend; whipsaw nhiều ở thị trường đi ngang | Giảm so với thời Turtle (1980s) | Trung bình | Khả thi, tập trung thị trường -> rủi ro |
| Seasonality / hiệu ứng lịch | <0,3, thường không sống sót sau chi phí và kiểm định đa giả thuyết | Trung bình | Thất thường (ở VN: day-of-week chỉ có giai đoạn Covid theo một nghiên cứu) | Thường mất sau công bố | Thấp | Chỉ dùng làm bộ lọc phụ, không đứng một mình |
| Event-driven (tin, lịch kinh tế), COT, sentiment | Bằng chứng yếu, không ổn định cho retail | Cao (gap, trượt giá khi tin) | Rất nhạy chế độ | Cạnh tranh tốc độ cực mạnh | Rất cao (spread nở khi tin) | Kém; phù hợp làm CẢNH BÁO/bộ lọc "đứng ngoài" |
| Market making | Cao cho tổ chức có hạ tầng | Rủi ro tồn kho | - | Cần độ trễ thấp, rebate | Quyết định | KHÔNG phù hợp retail |

**Nguồn chính và mức chắc**
- Trend/TSMOM: Moskowitz-Ooi-Pedersen JFE 2012 https://papers.ssrn.com/abstract=2089463 ; Hurst-Ooi-Pedersen "A Century of Evidence on Trend-Following" (67 thị trường, 1880-2016, mục tiêu biến động 10%) https://www.aqr.com/Insights/Research/Journal-Article/A-Century-of-Evidence-on-Trend-Following-Investing [CAO]. Phản biện: Kim-Tse-Wald cho rằng phần lớn lợi nhuận đến từ volatility scaling (alpha 0,41% chưa scale vs 1,27% có scale) và vắng sau khủng hoảng 2009-2013 [TB, nguồn thứ cấp].
- Dữ liệu CTA gần đây: SG CTA best-ever 2022; SG Trend -3,3% 2023; nửa đầu 2025 SG Trend/CTA -8% đến -11%, phân tán lớn giữa quỹ (Aspect -14%, Campbell dương): https://www.hedgeweek.com/man-groups-trend-tracker-facing-one-of-its-toughest-years-on-record/ ; https://www.alternativeswatch.com/2025/06/02/trend-following-hedge-funds-endure-more-pain-societe-generale-indices/ ; Man cho rằng đảo chiều không tăng tần suất theo thời gian (nguồn có lợi ích thương mại) [TB]. Số liệu 2024 và 2026 chưa lấy được [THẤP].
- Chi phí/tần suất: Baltas-Kosowski, 71 hợp đồng tương lai, Sharpe >1,2 và không thấy ràng buộc capacity (tranh luận về giả định impact) https://papers.ssrn.com/abstract=2140091 ; giảm turnover >1/3 mà không mất hiệu suất đáng kể [TB].
- Value + Momentum: Asness-Moskowitz-Pedersen J. Finance 2013 (8 thị trường/lớp tài sản; hai yếu tố tương quan âm nhau, kết hợp tốt) https://pages.stern.nyu.edu/~lpederse/papers/ValMomEverywhere.pdf [CAO].
- Momentum crash và quản trị: Daniel-Moskowitz JFE 2016 https://www.nber.org/papers/w20439 [CAO].
- Carry crash: Brunnermeier-Nagel-Pedersen "Carry Trades and Currency Crashes" https://www.nber.org/papers/w14473 ; Lustig-Roussanov-Verdelhan 2011 (yếu tố rủi ro chung) ; Menkhoff et al. J. Finance 2012 (carry tương quan âm với biến động FX toàn cầu) [CAO về hướng, TB về độ lớn].
- Con số Sharpe/drawdown trong bảng tổng hợp là phạm vi định hướng của tôi, [TB-THẤP]; phải tự đo lại trong hệ thống với dữ liệu thực và chi phí thực của broker.

**Khả năng áp dụng theo loại tài sản**
- Forex: carry & trend có bằng chứng, nhưng pháp lý VN (gate G1) và chi phí swap/spread của broker offshore là vấn đề lớn; đòn bẩy là kẻ thù.
- Vàng/hàng hóa: trend đã có bằng chứng tốt nhất ở hàng hóa; vàng qua ETF hoặc CFD đều khả thi về kỹ thuật.
- Chỉ số: trend/vol targeting phù hợp; dùng chỉ số làm bộ lọc chế độ.
- Cổ phiếu: momentum/value, long-only ở VN.

---

## 2. Thị trường Việt Nam

### 2.1 Đặc thù cấu trúc (cần kiểm chứng văn bản gốc trước khi dựa vào)

| Hạng mục | Nội dung | Mức chắc |
|---|---|---|
| Chu kỳ thanh toán | Vẫn T+2 theo các nguồn tìm được đến 2/2026 (VSDC); KHÔNG tìm thấy quyết định chuyển sang T+1. Từ 8/2022 có thể bán lại cổ phiếu vào phiên chiều T+2 (nguồn Việt). Hệ thống KRX (HoSE-Korea Exchange) dự kiến vận hành từ 5/2025, từng gặp sự cố thanh toán 2/2026; các tính năng như T+0, bán khống, CCP chưa xác nhận đã có hiệu lực | CAO (T+2), TB (KRX) |
| Biên độ giá | HOSE ±7%, HNX ±10%, UPCoM ±15% (kiến thức nền, chưa kiểm lại trong phiên này; cần xác nhận với HOSE) | TB |
| Bán khống | Cá nhân không bán khống cổ phiếu cơ sở (theo kiến thức nền; PLAN ghi như vậy) | TB |
| Phái sinh | Hợp đồng tương lai VN30 từ 8/2017, mở cho nhà đầu tư cá nhân qua công ty chứng khoán có tài khoản phái sinh; có bán (short) và đòn bẩy ký quỹ; chứng quyền có bảo đảm; ETF | CAO (ra đời 2017), TB (điều kiện mở tài khoản, phí) |
| Thanh khoản/cấu trúc | Nhà đầu tư cá nhân chiếm tỷ trọng giao dịch rất lớn, hành vi bầy đàn/đuổi giá được các nghiên cứu ghi nhận (2026) https://businessperspectives.org/images/pdf/applications/publishing/templates/article/assets/23714/IMFI_2026_01_Vu.pdf | TB |
| FTSE nâng hạng | Nguồn thứ cấp nêu hiệu lực 21/9/2026, chưa xác minh với FTSE Russell | THẤP |

### 2.2 Bằng chứng chiến lược trên thị trường VN

| Chiến lược | Bằng chứng | Mức chắc |
|---|---|---|
| Momentum | Idiosyncratic momentum dự báo lợi suất dương, vững sau khi kiểm soát beta, size, B/M (nghiên cứu 2022); hành vi đuổi giá của cá nhân hỗ trợ | TB |
| Value | Trái chiều: nghiên cứu 2013-2023 cho value thắng growth; luận án 2009-2019 cho growth thắng ("growth effect") | TB |
| Hiệu ứng lịch | Day-of-week chỉ có trong giai đoạn Covid theo một nghiên cứu HOSE; sau khi có phái sinh VN30 hiệu ứng ngày trong tuần biến mất | TB |
| VN30 futures trend | Chưa tìm thấy nghiên cứu độc lập đáng tin về trend VN30 futures; dữ liệu khối lượng nhà đầu tư cá nhân cũng chưa có | THẤP (khoảng trống) |
| Cổ tức/ổn định | Chưa tìm được nghiên cứu mạnh; cần tự backtest | THẤP |

Hầu hết nghiên cứu VN là bài tạp chí địa phương, mẫu ngắn, ít kiểm soát chi phí và survivorship. Coi là "gợi ý để tự kiểm chứng", không phải bằng chứng.

### 2.3 Rủi ro pháp lý (theo PLAN.md; chưa tự xác minh văn bản luật trong phiên này)

- **G1 Forex:** NHNN chưa cấp phép sàn forex nào; Nghị định 340/2025 (hiệu lực 9/2/2026) phạt đến 250 triệu cho phái sinh ngoại hối không phép; chế tài với cá nhân chưa rõ -> cần luật sư và đọc nguyên văn nghị định.
- **G2 Chứng khoán:** UBCKNN 2023 yêu cầu dừng đặt lệnh bằng robot; SSI/DNSE vẫn bán API -> hỏi bằng văn bản công ty chứng khoán.
- **G3 Broker MT5:** điều khoản về API/EA/VPS.
- Hệ quả: chỉ làm phase 1-3 (dữ liệu, backtest, paper) cho tới khi G1-G3 xong. Rủi ro đối tác (sàn lừa đảo, rút tiền) cũng là rủi ro lớn.

---

## 3. Quản trị vốn và rủi ro

| Công cụ | Nội dung | Khuyến nghị cho hệ thống | Mức chắc |
|---|---|---|---|
| Fixed-fractional | Rủi ro mỗi lệnh 0,25-1% vốn, tính qua khoảng cách stop | Mặc định: <=0,5%/lệnh | CAO |
| Kích thước theo ATR | Vị thế = (rủi ro % x vốn) / (k x ATR) -> tự thu nhỏ khi biến động tăng | Dùng chung cho mọi chiến lược | CAO |
| Volatility targeting | Mục tiêu biến động danh mục (vd 8-10%/năm), thang theo biến động thực hiện; Daniel-Moskowitz cho thấy giảm momentum crash | Dùng, có trần đòn bẩy | CAO |
| Kelly phân đoạn | Full Kelly rất rủi ro ngắn hạn; thực hành dùng 1/4-1/2 Kelly. MacLean-Thorp-Ziemba, Quantitative Finance 2010 (good/bad properties) https://www.stat.berkeley.edu/~aldous/157/Papers/Good_Bad_Kelly.pdf | Chỉ làm trần tham chiếu; Kelly cần ước lượng edge mà ta không biết chính xác -> dùng <=1/4 Kelly, thực tế thường thấp hơn nhiều fixed-fractional | CAO (nguyên lý) |
| Giới hạn drawdown / kill-switch | Ngưỡng ngày/tuần/tháng/đỉnh-đáy; vượt -> ngừng mở lệnh mới, rồi flatten, rồi khóa tới khi người xem xét | Ví dụ khởi điểm: lỗ ngày 1-2%, tháng 5%, đỉnh-đáy 10-15% -> HALT (con số để người dùng chọn) | CAO (cấu trúc) |
| Tương quan danh mục | Nhiều lệnh forex cùng USD thực chất là một lệnh; giới hạn rủi ro theo cụm tương quan | Giới hạn tổng rủi ro mở (heat) và theo cụm | CAO |
| Ngân sách rủi ro | Chia ngân sách biến động cho từng chiến lược (ví dụ ngang nhau theo vol) | Chia đều rủi ro, không chia đều vốn | TB |
| Đa dạng hóa chiến lược | Value + momentum tương quan âm (Asness et al. 2013); trend phòng thủ khi cổ phiếu giảm | Kết hợp 2-3 họ ít tương quan; không thêm chiến lược chưa qua kiểm chứng | CAO |

Nguyên tắc: kill-switch và giới hạn nằm ở lớp bất biến phía thực thi; lớp phân tích/LLM không có quyền vượt giới hạn.

---

## 4. Quy trình kiểm chứng đáng tin

| Bước | Nội dung | Tiêu chí |
|---|---|---|
| 1. Giả thuyết trước | Ghi lý do kinh tế TRƯỚC khi chạy backtest; ghi số lần thử (N trials) | Nhật ký thử nghiệm bắt buộc |
| 2. Dữ liệu sạch | Bao gồm mã hủy niêm yết, điều chỉnh cổ tức/split, dữ liệu bid/ask thật hoặc spread mô hình bảo thủ | Không lookahead, không survivorship |
| 3. Chi phí thực | Spread, phí, swap, slippage (x1,5-2 so với ước tính), phí giao dịch VN + thuế bán 0,1% (kiến thức nền, cần xác nhận) | Edge phải sống ở chi phí x2 |
| 4. Walk-forward | Huấn luyện/tối ưu trong cửa sổ, kiểm tra ngoài mẫu liên tiếp | Hiệu suất OOS >= ~50% in-sample (heuristic) |
| 5. CPCV / PBO | Combinatorial purged CV (López de Prado) và Probability of Backtest Overfitting (CSCV) https://papers.ssrn.com/abstract=2326253 | PBO thấp (ví dụ <0,3, ngưỡng do người dùng chọn) |
| 6. Deflated Sharpe | Hiệu chỉnh theo số lần thử và phân phối không chuẩn https://papers.ssrn.com/abstract=2460551 | DSR có ý nghĩa (xác suất > 0,95 là thông lệ, TB) |
| 7. Độ nhạy tham số | Lưới tham số: hiệu suất phải là "cao nguyên", không phải đỉnh nhọn; thử đổi ±20-30% | Không có đỉnh cô lập |
| 8. Kiểm tra theo chế độ | Chia theo 2008, 2020, 2022, giai đoạn thanh khoản thấp | Không chỉ sống nhờ một giai đoạn |
| 9. Paper trading | >= 4 tuần (PLAN) cho kiểm tra kỹ thuật; để kiểm tra thống kê cần nhiều tháng và chỉ nên coi là kiểm tra kỹ thuật + thực thi, không chứng minh edge | So sánh fill thật với mô phỏng |
| 10. Tiêu chí dừng | Định trước: drawdown > 1,5x drawdown backtest tối đa, hoặc live Sharpe dưới bậc dưới của khoảng tin cậy sau N tháng, hoặc lệch chi phí > 50% | Tự động đưa sang trạng thái ngừng/cảnh báo |

Quy tắc thực tế: ưu tiên ít tham số (<=3 mỗi chiến lược), chiến lược có lý do kinh tế rõ, tín hiệu chậm (ngày/tuần), đa thị trường.

---

## 5. KẾT LUẬN: xếp hạng 6 phương án ứng viên

Mọi phương án đặt sau cổng pháp lý G1-G3; trước đó chỉ chạy dữ liệu/backtest/paper. Hệ thống hiện READ-ONLY nên PA1 và PA2 không cần quyền ghi.

| Hạng | Phương án | Mô tả | Kỳ vọng thực tế (khiêm tốn) | Rủi ro chính | Điều kiện vận hành | Độ phức tạp tích hợp | Dữ liệu cần |
|---|---|---|---|---|---|---|---|
| 1 | **A. Theo dõi + cảnh báo, người dùng tự quyết** (read-only) | Máy quét tín hiệu trend/regime, cảnh báo Telegram, nhật ký quyết định, thống kê hiệu suất giả định, kill-switch tư vấn (cảnh báo khi vượt ngưỡng rủi ro) | Không sinh lợi nhuận tự động; giảm sai lầm hành vi, kỷ luật; chi phí thấp | Người dùng bỏ qua cảnh báo; tin tín hiệu quá mức | Không cần broker API ghi; không bị G1/G2 chặn hơn (vẫn cần hiểu pháp lý khi tự giao dịch) | Thấp: phù hợp kiến trúc READ-ONLY | Giá EOD/H1 (Dukascopy, HistData, vnstock/nguồn VN), lịch kinh tế |
| 2 | **B. Trend following chậm đa tài sản (ETF/CFD ít thị trường), vol-targeted** | 3 khung (1/3/12 tháng) hoặc Donchian dài hạn, trên vàng, chỉ số, vài cặp tiền, trái phiếu/hàng hóa qua ETF; kích thước theo vol, rủi ro 0,25-0,5%/lệnh | Sharpe ~0,3-0,6 sau phí nếu may mắn; drawdown 15-30%; có thể 2-4 năm yếu | Chu kỳ lỗ dài (2023-2025), whipsaw, ít thị trường -> kém đa dạng | Phải qua kiểm chứng mục 4; broker hợp pháp (G1/G3) | Trung bình: module tín hiệu + portfolio + risk | Dữ liệu ngày nhiều thị trường, nhiều năm, có roll/điều chỉnh |
| 3 | **C. Bán tự động có duyệt tay** | Hệ thống đề xuất lệnh (kích thước, stop, lý do), người dùng bấm duyệt (OTP/xác nhận) trước khi gửi; giới hạn cứng, kill-switch | Như PA2, giảm lỗi kích thước/kỷ luật | Lỗi lệch trạng thái, trễ, pháp lý robot (G2: không đặt lệnh tự động?) | G1-G3 xong; idempotency, đối soát; vốn nhỏ | Cao: lớp thực thi, trạng thái, OTP | Như PA2 + dữ liệu vị thế/lệnh |
| 4 | **D. Momentum + value cổ phiếu VN long-only (rổ VN30/VNMidcap), xoay vòng tháng/quý** | Xếp hạng momentum 6-12 tháng (bỏ 1 tháng) và chất lượng/value, giữ top N, bộ lọc chế độ (VN-Index trên MA200) | Chưa rõ; bằng chứng VN trái chiều; kỳ vọng thấp, drawdown 30-50% (chu kỳ VN) | Dữ liệu survivorship, thanh khoản, biên độ, T+2, không short, hành vi nhà đầu tư cá nhân | G2 nếu đặt lệnh tự động; có thể chỉ làm tín hiệu + người dùng tự đặt | Trung bình | Giá điều chỉnh, báo cáo tài chính, danh sách hủy niêm yết, thanh khoản |
| 5 | **E. Phòng thủ: bộ lọc chế độ + vol targeting cho danh mục sẵn có** | Không tạo tín hiệu mới; chỉ cắt/giảm vị thế khi biến động cao hay hết xu hướng, cảnh báo drawdown | Giảm drawdown, không tăng lợi nhuận kỳ vọng | Bỏ lỡ hồi phục (momentum crash ngược) | Chỉ cần dữ liệu giá | Thấp | Giá chỉ số/tài sản người dùng đang giữ |
| 6 | **F. VN30 futures trend (chỉ paper)** | Trend dài hạn/ breakout trên hợp đồng tương lai VN30, có short | Chưa có bằng chứng độc lập; phái sinh có đòn bẩy | Đòn bẩy, thanh khoản phiên, hợp đồng hết hạn, G2 robot | Mở tài khoản phái sinh; chỉ paper tới khi có >=2-3 năm dữ liệu kiểm chứng | Trung bình | Dữ liệu VN30F liên tục, khối lượng, phí |
| 7 | **G. Carry FX / mean reversion/ sự kiện** | KHÔNG khuyến nghị đưa vào giai đoạn đầu | Đuôi trái nặng (carry), chi phí cao, cạnh tranh tốc độ | Crash (2008/2015/2020), spread khi tin | - | - | - |

**Loại bỏ rõ ràng:** scalping/day-trading đòn bẩy cao, market making, "tín hiệu tin tức" tốc độ cao, martingale/grid, copy-trading không kiểm soát, bất kỳ chiến lược chỉ có backtest đẹp mà chưa qua DSR/PBO.

### Lộ trình đề xuất (chưa quyết, để người dùng chọn)

1. Triển khai **PA1 (cảnh báo)** + khung kiểm chứng (mục 4) + nhật ký thử nghiệm. Thời gian ngắn, rủi ro thấp.
2. Dùng khung đó để backtest **PA2 và PA4** với dữ liệu sạch; công bố báo cáo DSR/PBO/độ nhạy.
3. Paper >= 3 tháng. Chỉ khi (i) G1-G3 được xác nhận bằng văn bản, (ii) tiêu chí dừng đã định, (iii) kill-switch được thử thật -> cân nhắc **PA3** với vốn nhỏ, tăng dần.
4. Mọi LLM chỉ làm phân tích/giải thích, KHÔNG có quyền đặt lệnh.

### Khoảng trống và việc cần kiểm lại
- Dữ liệu CTA 2024-2026 và hiệu suất trend sau 2025; con số Sharpe sau chi phí do tôi định hướng.
- Nội dung gốc Nghị định 340/2025, văn bản UBCKNN 2023 về robot, quy định cập nhật về T+1/KRX/bán khống, biên độ giá hiện hành.
- Bằng chứng độc lập cho VN30 futures trend; dữ liệu khối lượng nhà đầu tư cá nhân.
- Điều kiện mở tài khoản phái sinh cho cá nhân và phí thực tế tại DNSE/SSI.
- Chưa tải toàn văn nhiều bài báo; một số kết luận dựa trên tóm tắt/nguồn thứ cấp (đã đánh dấu TB).

### Tuyên bố miễn trừ
Báo cáo này là nghiên cứu thông tin nội bộ, không phải tư vấn tài chính hay pháp lý. Giao dịch có đòn bẩy có thể gây mất toàn bộ vốn.
