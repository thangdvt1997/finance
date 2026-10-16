# R5 - Chuyên gia và nguồn quan điểm: chuyển thành tín hiệu kiểm được, bằng chứng, nguồn bổ sung

Ngày: 2026-10-15. Agent R5 (chương trình nghiên cứu). Tài liệu NỘI BỘ (có ghi nguồn học thuật; UI không hiển thị tên nguồn - xem docs/UI_NO_SOURCES.md). Không phải khuyến nghị đầu tư. READ-ONLY/PAPER, gói 0 đồng.

Quy ước độ tin cậy: **Cao** = tôi tự đo được trong phiên này hoặc đã xác minh nội dung nguồn; **Trung bình** = kiến thức văn liệu quen thuộc, có kiểm tra một phần; **Thấp/Chưa xác minh** = chỉ nhớ lại hoặc chỉ thấy trong danh mục tham khảo. Mục nào "Chưa xác minh" cần đọc lại bản gốc trước khi trích dẫn ra ngoài.

## 1. Kết luận ngắn (2 phút)

1. **Ý kiến công khai (chuyên gia, sell-side, khảo sát) không phải nguồn alpha đã chứng minh.** Văn liệu tỷ giá: bước ngoặt Meese-Rogoff (1983) vẫn là chuẩn; nghiên cứu các nhà dự báo trong khảo sát WSJ (Mitchell và Pearce) cho thấy đa số dự báo tỷ giá kém hơn mô hình bước ngẫu nhiên và có thiên lệch (độ tin cậy: Trung bình, đã đọc tóm tắt qua tìm kiếm). Hệ thống đã coi ý kiến là NGỮ CẢNH, đúng hướng.
2. **COT (vị thế đầu cơ CFTC)**: ghi chú phân tích của RBNZ (Mulligan và Steenkamp, 2018) kết luận dữ liệu COT "giúp diễn giải các biến động tỷ giá quá khứ, nhưng khả năng dự báo hạn chế" (Cao - đã đọc tóm tắt). Khớp với kiểm định nội bộ trước (INFO_SIGNALS_STUDY: 52 kiểm định, không cái nào sống sót hiệu chỉnh đa kiểm định) và kết quả mới ở mục 4: **không có edge dùng được sau chi phí và walk-forward**.
3. **Giá trị thật của "chuyên gia" nằm ở 3 chỗ kiểm được**: (a) lịch sự kiện và dự báo đồng thuận làm bộ lọc rủi ro (đã có); (b) số liệu khảo sát chính thức (kỳ vọng lạm phát/GDP của ECB, Fed Philadelphia, BoE) làm biến vĩ mô có dấu thời gian chuẩn - nên dùng làm đặc trưng chế độ (regime), không dùng để vào lệnh; (c) đo track-record khách quan để LOẠI nguồn kém (đã có service track-record).
4. **Đề xuất nguồn mới hợp pháp, miễn phí**: CFTC Public Reporting (API Socrata), khảo sát SPF của ECB và Philadelphia Fed, Decision Maker Panel / Survey of Market Participants (NHTW), bản tin Beige Book/FOMC minutes (RSS đã phần lớn có), Fed SEP. Chi tiết và điều kiện ở mục 6.
5. **Không nên bổ sung**: sentiment bán lẻ từ nhà môi giới (SSI, client sentiment, Myfxbook "community outlook") vì ToS cấm trích xuất/phân phối lại hoặc đã bị chặn bot (docs/sources/research_macro.md ghi DailyFX 403, Oanda không dùng được); không vượt chặn.

## 2. Hệ thống đã có (chỉ đọc để biết, không lặp lại)

- `services/expert-collector`: thu RSS/Atom, Bluesky, Form 4, nhiều feed NHTW (63 feed dùng được theo docs/sources/central_banks.md); gán stance bằng quy tắc từ khoá; PoliteClient (robots, giới hạn tốc độ, không vượt chặn). COT `deafut.txt` đã khảo sát nhưng `enabled=false` (docs/sources/insiders_commodities.md, dòng CFTC COT).
- `services/track-record`: gộp quan điểm theo entity/mã/ngày, chống look-ahead (COT: published_at = thứ Sáu = as_of + 3 ngày 20:30 UTC), chấm điểm hướng, nói thẳng "chưa đủ mẫu".
- `research/info/cot_study.py`: kiểm định contrarian cực đoan 3 năm, 7 tài sản x 2 nhóm x 2 ngưỡng x 2 kỳ hạn; kết luận ở INFO_SIGNALS_STUDY.

## 3. Danh mục nguồn quan điểm uy tín và cách định lượng hoá

Nguyên tắc chuyển đổi: mọi quan điểm phải thành (thời điểm biết được, tài sản, hướng/độ lớn, horizon, mức vô hiệu) -> chấm theo kết quả giá SAU thời điểm biết, so với baseline ngẫu nhiên/ngày-trong-tuần, hiệu chỉnh đa kiểm định (Holm/BH), cần >= vài trăm quan điểm độc lập mới kết luận.

| Nhóm | Ví dụ công khai | Biến định lượng | Kiểm được không | Độ tin cậy bằng chứng |
|---|---|---|---|---|
| Vị thế đầu cơ (COT/TFF) | CFTC weekly | net long/OI theo nhóm trader, z-score 3 năm, thay đổi 4 tuần | Có (mục 4) | Cao (đo trực tiếp) |
| Khảo sát chuyên gia chính thức | ECB SPF (lạm phát/GDP/thất nghiệp, quý), Philadelphia Fed SPF (quý, có dự báo cá nhân ẩn danh), BoE Decision Maker Panel | kỳ vọng trung bình/độ phân tán, surprise so với dữ liệu thực | Có, tần số thấp (quý) nên ít mẫu | Trung bình |
| Truyền thông NHTW | Fed (statement, minutes, SEP, Beige Book), ECB, BoE, BoJ | điểm hawkish/dovish theo từ khoá; thay đổi so với kỳ trước; độ bất ngờ so với giá OIS | Có thể, nhưng độ bất ngờ cần giá lãi suất không có miễn phí tin cậy | Trung bình |
| Sell-side miễn phí / quỹ | ING Think, RBC (feed dùng được); nghiên cứu mở của AQR, Alpha Architect, Robeco, Man Institute | hướng + horizon do bài tự nêu (hiếm khi có số) | Khó: bài viết ít khi có dự báo có thể chấm điểm | Thấp |
| Podcast/sách | phỏng vấn nhà giao dịch, sách kinh điển | Không có chuỗi quan điểm có dấu thời gian | Không kiểm được đạo hàm hệ thống; chỉ dùng làm nguồn giả thuyết (R1-R3) | Thấp |
| Sentiment bán lẻ | tỷ lệ long/short của nhà môi giới, AAII, put/call | tỷ lệ cực đoan -> contrarian | Có nếu có nguồn hợp pháp; nguồn môi giới bị chặn/ToS cấm | Thấp-Trung bình |
| Mạng xã hội | Bluesky (đã có), tài khoản chuyên gia | stance + volume | Nhiễu cao, thiên lệch sống sót | Thấp |

Điểm lưu ý khi dự báo của người nổi tiếng: thiên lệch sống sót (ta chỉ nghe người thắng), dự báo mơ hồ không chấm được, không có chi phí giao dịch trong lời kể; do đó track-record phải do HỆ THỐNG ghi nhận từ lúc công bố (đúng thiết kế service hiện tại), không dùng thành tích tự công bố.

## 4. Thử nghiệm sơ bộ R5: tín hiệu COT trên FX và vàng (số thật)

Mã: `data/research/program/R5/cot_wf.py`; kết quả: `cot_wf_results.csv`, `cot_per_asset_sharpe_gross.csv`. Dữ liệu CFTC (TFF 2006-2026 cho 6 FX, Disaggregated cho vàng COMEX) tải miễn phí từ `cftc.gov/files/dea/history/` (lưu ở `data/research/program/R5/cot/`, ngoài git). Giá ngày: 7 chuỗi giá FX/vàng tải từ nguồn miễn phí (chỉ dùng nội bộ).

Thiết kế (không look-ahead): as_of thứ Ba, công bố thứ Sáu 15:30 ET; vào lệnh tại close thứ Hai kế tiếp, giữ 1 tuần. Danh mục 7 tài sản (EUR, GBP, JPY, AUD, CAD, CHF, vàng), tỷ trọng nghịch với biến động 26 tuần (tổng |w| <= 1), chi phí 2 bps trên mỗi đơn vị turnover. Hai luật cố định, không chỉnh tham số:
- contrarian: z-score 156 tuần của net long (LevMoney; vàng dùng ManagedMoney) với |z| > 1 -> đi ngược.
- trend: dấu của thay đổi net 4 tuần -> đi theo.
Bootstrap khối ngừng (block trung bình 8 tuần, 4000 lần) cho p hai phía. Mẫu: 1060 tuần dữ liệu, giao dịch từ 2008.

| Luật | Giai đoạn | Số tuần | Sharpe ròng | Sharpe gộp | Lợi suất/năm | p bootstrap |
|---|---|---|---|---|---|---|
| contrarian | 2008-2026 | 978 | -0,18 | -0,14 | -0,6% | 0,38 |
| contrarian | 2008-2016 | 469 | -0,30 | -0,27 | -1,3% | 0,29 |
| contrarian | 2017-2026 | 509 | +0,02 | +0,07 | +0,05% | 0,94 |
| trend (đổi 4 tuần) | 2008-2026 | 978 | **-0,51** | -0,40 | -2,3% | 0,011 |
| trend | 2008-2016 | 469 | -0,51 | -0,42 | -2,8% | 0,09 |
| trend | 2017-2026 | 509 | -0,54 | -0,40 | -1,9% | 0,042 |
| Walk-forward chọn luật/dấu theo Sharpe 5 năm trước, chỉ giao dịch nếu > 0,3 (chi phí tính cả khi đảo dấu) | 2013-2026 | 208 tuần có vị thế | **+0,24** | - | +0,32% | **0,62** |

Đọc kết quả:
1. **Contrarian cực đoan không có edge** (Sharpe quanh 0, p = 0,38), khớp kiểm định trước của hệ thống (độc lập về mã, vì tôi viết lại từ đầu với thiết kế danh mục và chi phí).
2. **Trend theo thay đổi vị thế 4 tuần có Sharpe ÂM đều ở cả hai nửa mẫu** (-0,51 và -0,54). Nghĩa là đảo dấu (đi NGƯỢC dòng chảy vị thế của quỹ đòn bẩy 4 tuần) có Sharpe gộp +0,40 và ròng +0,30 (2008-16: +0,33; 2017-26: +0,26) - nhưng đây là **lựa chọn sau khi nhìn kết quả** nên không được tính là phát hiện. Hiệu chỉnh thô: ~8 phép thử đã xem trong phiên này -> p 0,011 x 8 ~ 0,09, không vượt ngưỡng 0,05; cộng với 52 phép thử trước đó thì hoàn toàn không đáng kể.
3. **Walk-forward trung thực** (chọn luật chỉ bằng 5 năm trước): thuật toán chọn `trend_inv` ở 11/14 năm, nhưng Sharpe huấn luyện giảm dần (0,51 năm 2014 xuống 0,03-0,3 sau 2017) và chỉ 208/~730 tuần đủ ngưỡng 0,3 để giao dịch; Sharpe ngoài mẫu ròng chỉ **+0,24, p = 0,62** (không phân biệt được với 0). Lợi thế hậu nghiệm +0,30 đã mỏng đi theo thời gian.
4. Theo từng tài sản (Sharpe gộp, không hiệu chỉnh), không có mẫu hình nhất quán: contrarian từ -0,52 (EUR) tới +0,28 (CAD); trend từ -0,50 (CHF) tới +0,38 (AUD).

Kết luận R5-COT: **KHÔNG DÙNG làm tín hiệu vào lệnh**. Giữ làm bối cảnh (đo "đông đúc" của vị thế) và làm đặc trưng cho mô hình rủi ro. Giả thuyết còn mở (ghi vào backlog, chưa kiểm): (a) hiệu ứng "fade dòng chảy 4 tuần" có thể là dạng phản ứng quá mức/đảo chiều ngắn hạn của giá, vốn đã biết ở FX; cần kiểm trên dữ liệu có chi phí thực của broker và với đối chứng "đảo chiều giá 4 tuần" thuần giá (nếu cùng Sharpe thì COT không thêm thông tin). (b) Tần số cao hơn (RBNZ gợi ý) không khả thi miễn phí vì COT chỉ có tuần.
Hạn chế trung thực: giá miễn phí là giá đóng cửa tham chiếu không phải giá broker; không có spread động; vàng dùng hợp đồng tương lai liên tục (có roll); 7 tài sản tương quan nên mẫu độc lập thấp hơn số tuần.

## 5. Bằng chứng học thuật (nội bộ)

| Chủ đề | Nguồn | Kết luận | Tin cậy |
|---|---|---|---|
| COT và tỷ giá | Mulligan và Steenkamp, RBNZ Analytical Note AN2018/03 | Giải thích quá khứ tốt, dự báo hạn chế; gợi ý dữ liệu tần số cao hơn | Cao (đã đọc abstract) |
| COT/vị thế đầu cơ và tỷ giá | Klitgaard và Weir (2004, NY Fed); Wang (2004, J. Banking & Finance); Tornell và Yuan (2012, J. Futures Markets) | có trong danh mục tham khảo của ghi chú RBNZ; nội dung kết luận chi tiết CHƯA xác minh | Thấp |
| Dự báo tỷ giá | Meese và Rogoff (1983); tổng quan Rossi; Mitchell và Pearce (khảo sát WSJ) | Bước ngẫu nhiên khó thắng; phần lớn nhà dự báo kém hơn bước ngẫu nhiên, có thiên lệch | Trung bình |
| Ngoại lệ | Pincheira và Neumann (peso Chile), Jackson và Magkonis (meta-phân tích 8.413 sai số) | Dự báo khảo sát có thể thắng bước ngẫu nhiên với một số điều kiện/tần số; hiệu ứng nhỏ, không tổng quát | Thấp-Trung bình |
| Sentiment và lợi suất | Baker và Wurgler (2006); Tetlock (2007, tin tức/tâm lý) | Sentiment dự báo lợi suất chủ yếu ở cổ phiếu khó định giá/khó arbitrage, không phải FX thanh khoản cao | Trung bình (kiến thức văn liệu, chưa kiểm lại trong phiên) |
| Kết luận nội bộ | INFO_SIGNALS_STUDY (52 kiểm định COT), mục 4 ở trên | Không edge sau hiệu chỉnh | Cao |

Hàm ý: mọi nguồn "quan điểm" nên bị đối xử như giả thuyết null (không có thông tin) cho tới khi vượt kiểm định out-of-sample có chi phí. Ưu tiên đầu tư công sức vào lọc rủi ro và quy mô vị thế (vol-targeting) hơn vào đoán hướng.

## 6. Nguồn hợp pháp, miễn phí, có API/RSS để bổ sung cho track-record và expert-collector

Quy tắc áp dụng như SOURCES.md hiện có: User-Agent có liên hệ, tôn trọng robots.txt, >= 2 giây/host, ETag/If-Modified-Since, chỉ lưu tiêu đề + link + tóm tắt <= 300 ký tự (với dữ liệu số: lưu giá trị và tham chiếu), không vượt chặn. Cột "ToS" là điều đã xác minh hay chưa; **chưa xác minh = phải đọc trang điều khoản trước khi bật**.

| Ưu tiên | Nguồn | Truy cập | Giá trị | ToS/giấy phép | Trạng thái xác minh |
|---|---|---|---|---|---|
| 1 | CFTC COT, bộ lịch sử và báo cáo tuần (`cftc.gov/files/dea/history/*.zip`, `deafut.txt`, `FinFutWk`) | tải tệp CSV/zip; tuần | bật lại COT trong expert-collector làm dữ liệu số (không phải quan điểm); nguồn cho bối cảnh vị thế | dữ liệu cơ quan liên bang Mỹ; tôi tải được tệp zip bằng HTTP 200 (Cao); điều khoản sử dụng trang chính CFTC chưa lấy được (URL privacy trả 404) -> Chưa xác minh | tải thực: có |
| 1 | CFTC Public Reporting Environment (Socrata, `publicreporting.cftc.gov`) | REST/JSON, lọc theo cột | tiện hơn zip, có lọc theo mã | điều khoản/giới hạn tốc độ chưa tìm thấy; dùng token ẩn danh nếu cần, đọc trang dev.socrata.com của dataset | Chưa xác minh |
| 2 | ECB Survey of Professional Forecasters (microdata + tổng hợp, quý) | tệp tải xuống (định dạng chưa rõ trên trang) | kỳ vọng lạm phát/GDP có phân phối xác suất | trang có "Disclaimer & Copyright"; nội dung điều khoản chưa đọc | Dữ liệu có thật (Cao); ToS Chưa xác minh |
| 2 | Philadelphia Fed SPF (quý; Excel; dự báo cá nhân ẩn danh) | tệp xlsx tải xuống | benchmark dự báo Mỹ, có dự báo từng người (ID) -> chấm điểm được | trang ghi "Copyright, all rights reserved", điều khoản dữ liệu không nêu -> đọc Documentation PDF/liên hệ | Dữ liệu có thật (Cao); ToS Chưa xác minh |
| 2 | BoE Decision Maker Panel, Survey of Market Participants; Fed SEP/minutes/Beige Book | RSS/tệp trên trang NHTW | kỳ vọng doanh nghiệp, dự báo lãi suất | nhiều NHTW cho phép tái sử dụng có ghi nguồn; từng NHTW khác nhau | Chưa xác minh từng cái |
| 3 | FRED/ALFRED API (Fed St. Louis; dữ liệu theo vintage) | REST + khoá miễn phí tự đăng ký (cần người dùng đăng ký khoá nếu muốn, KHÔNG tự đăng ký) | dữ liệu vĩ mô theo thời điểm công bố (chống look-ahead khi tạo "surprise") | điều khoản FRED có hạn chế với dữ liệu bên thứ ba; kiểm tra theo từng chuỗi | Chưa xác minh |

Không đề xuất: SSI/client-sentiment của nhà môi giới, Myfxbook, ForexFactory scraping (ToS/anti-bot), mạng xã hội cần API trả phí.

Việc cần làm để tích hợp (đề xuất, chưa làm vì không sửa service ngoài phạm vi R5): (1) thêm job nạp COT số vào bảng `expert_positions` (đã có entity COT trong track-record); (2) thêm kiểm định định kỳ "COT có thêm thông tin so với đảo chiều giá thuần" trong lab; (3) thêm bảng `survey_expectations` (SPF/DMP) làm đặc trưng chế độ, không phát tín hiệu mua/bán.

## 7. Đề xuất thiết kế "tín hiệu từ chuyên gia" cho kiểm định công bằng

1. Chỉ ghi nhận quan điểm có dấu thời gian do hệ thống thu (observed_at), không dùng bài tự công bố hồi tố.
2. Tối thiểu 200 quan điểm độc lập/entity trước khi chấm điểm; dưới đó hiển thị "chưa đủ mẫu" (đã có).
3. So với 3 baseline: ngẫu nhiên có cùng tỉ lệ hướng, "luôn mua", và đảo chiều giá thuần cùng horizon.
4. Hiệu chỉnh đa kiểm định theo họ (số entity x tài sản x horizon); bootstrap khối; báo cáo khoảng tin cậy.
5. Dùng điểm uy tín tổ chức như độ nhiễu của nguồn, không như xác suất đúng.

## 8. Tái lập

```
cd /root/trading-system/data/research/program/R5
# dữ liệu: tải zip TFF/Disaggregated từ cftc.gov/files/dea/history/ vào cot/ (tff_*.zip, dis_*.zip) và giá ngày vào cot/px_<mã>.json
timeout 900 python3 -I cot_wf.py
```
Đầu ra: `cot_wf_results.csv`, `cot_per_asset_sharpe_gross.csv`.
