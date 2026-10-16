# R10 - Đăng ký giả thuyết trước (preregistration)

Thời điểm soạn: 2026-10-15T04:38:36Z (UTC). Tài liệu này được băm SHA-256 ngay sau khi lưu; hash ghi ở `docs/research/program/R10_preregistration.sha256` và trong báo cáo R10. Mọi thay đổi sau đó phải ghi vào mục "Sửa đổi" cuối file, không sửa phần trên.

## 0. Công khai trung thực về thứ tự thực hiện
- Dựng panel dữ liệu và thư viện engine trước khi viết tài liệu này. Một lần chạy "smoke" 6 ứng viên (A-F, tham số chính) trên cửa sổ 2008-2020 chỉ để kiểm tra mã chạy được và kiểm tra nhân quả (cắt dữ liệu không đổi trọng số). Không có tham số nào bị đổi sau lần chạy đó; tham số chính dưới đây đã chốt trước khi chạy. Tập TEST (2021-01-01 trở đi) chưa được nạp vào bất cứ tiến trình nào (Ctx bị cắt tại 2020-12-31).
- Vì vậy mọi kết luận "thất bại" ở DEV/VAL không do chỉnh tham số theo kết quả; số lần thử được đếm đầy đủ (mục 5).

## 1. Dữ liệu và chia đoạn
- Nguồn: nến D1 MT5 native của broker demo, 39 mã: 28 cặp FX G8 (USD, EUR, GBP, JPY, AUD, CAD, CHF, NZD), 9 chỉ số (US500, US30, DE40, SWI20, NETH25, IT40, US2000, MIDDE50, CHINA50), 2 kim loại (XAUUSD, XAGUSD). Mã chỉ vào danh mục khi đã có >= 260 nến.
- Snapshot: `data/research/program/R10/panel_d1.parquet`, SHA-256 = 9681d1c06409931cf4b5ec623ff0551fcb0faf5665838e7f127aee56cb3550ce (cắt tại 2026-03-10 để KHÔNG chạm tập TEST khoá kịch bản Sell, bắt đầu 2026-03-11).
- Khởi động (warm-up): 2000-01-03. DEV = 2008-01-01..2017-12-31. VAL = 2018-01-01..2020-12-31. TEST KHOÁ MỚI = 2021-01-01..2026-03-10 (5,2 năm), chỉ mở MỘT lần sau khi chốt mã + tham số; ghi nhật ký tại `data/research/program/R10/test_access.log`.
- "Walk-forward": ứng viên có tham số cố định (A-F) không có bước khớp; hiệu năng DEV/VAL là ngoài-mẫu so với tham số văn liệu. Ứng viên G (meta-labeling) huấn luyện lại hằng năm (mở rộng, từ 2008, tối thiểu 300 sự kiện, purge theo ngày đóng lệnh, embargo 10 ngày); với TEST dùng mô hình ĐÓNG BĂNG huấn luyện đến 2020-12-15.
- Mức độ "mới" của TEST: không ứng viên nào từng được tinh chỉnh trên đoạn này và tham số chốt trước; dữ liệu MT5 native chưa từng dùng trong MULTI_ASSET/BACKTEST_STUDY (nguồn Yahoo/FRED/ECB). Nhưng các nghiên cứu trước đã quan sát thị trường cùng giai đoạn (kiến thức chung), nên đây không phải đoạn "trinh nguyên" tuyệt đối. KB Sell dùng 2023-10 trở đi cho 8 mã (chiến lược khác).

## 2. Mô hình chi phí và thực thi (chung)
- Quyết định ở close t, khớp tại close t (độ trễ 1 nến), hưởng lợi suất t+1. Độ nhạy: trễ 2 nến.
- Chi phí một chiều (bps giá trị) = 0,5 x max(spread nến trung vị 60 ngày, spread_bp MT5 hiện tại từ R7_spread_theo_ma.csv, sàn FX 0,3 / chỉ số 1,0 / kim loại 0,5) + trượt giá (FX 0,3 / chỉ số 1,0 / kim loại 1,0). Độ nhạy: x2.
- Tài trợ qua đêm: FX = chênh lãi suất 3M công khai (trễ công bố 45 ngày) x vị thế - markup 0,35%/năm (trung vị |mid swap| của G8 trong dữ liệu MT5 thật, R7_swap_carry.csv) ; chỉ số = (cổ tức giả định 2% - lãi USD) - markup 0,5%; kim loại = -lãi USD x vị thế - markup 0,5%. Swap lịch sử MT5 không có (chỉ ảnh chụp hiện tại), nên swap MT5 dùng để hiệu chuẩn markup và đối chiếu dấu carry; lịch sử dùng lãi suất công khai làm proxy.
- Định cỡ: vol mục tiêu 10%/năm theo cov EWMA (half-life 60, co 20% về đường chéo), trần 3x/mã, 6x tổng; ngân sách rủi ro cân bằng theo lớp (FX/CHỈ SỐ/KIM LOẠI) trừ khi ghi khác.

## 3. Ứng viên (tham số CHÍNH chốt; lưới 3x3 chỉ để đo độ bền, PBO, đếm thử nghiệm)
| ID | Ứng viên | Tham số chính | Lưới (cột x hàng) |
|---|---|---|---|
| A | Trend đa tài sản + vol-target | ensemble 4 tín hiệu: TSMOM 12-1, TSMOM 1/3/12 tháng, giá vs SMA200, Donchian 200/100; rebal tháng | hệ số khung k {0,5; 1; 2} x rebal {tuần, tháng, quý} |
| B | Cross-sectional momentum | 12-1 tháng; FX xếp hạng sức mạnh tiền tệ (top/bottom 3 trên 8), chỉ số xếp hạng (top/bottom 37,5%); rebal tháng | lookback {63; 126; 252} x tỉ lệ {25%; 37,5%; 50%} |
| C | TSMOM nhiều khung | trung bình dấu khung 5/21/63/126/252 ngày; 1/N nghịch vol (không ngân sách lớp); rebal tuần | tập khung {5-21-63; 5-21-63-126-252; 63-126-252} x rebal {ngày, tuần, tháng} |
| D | Mean-reversion có điều kiện regime | z lợi suất 3 ngày (theo vol 60 ngày) > 1,5 ngược chiều, chỉ khi ADX14 < 20; thoát khi z đổi dấu hoặc sau 5 ngày | ngưỡng z {1,0; 1,5; 2,0} x trần ADX {15; 20; 25} |
| E | Breakout Donchian | vào 55 ngày, thoát 22 ngày (0,4x), long/short, rebal tuần | vào {20; 55; 100} x tỉ lệ thoát {0,2; 0,4; 0,6} |
| F | Carry proxy | tín hiệu = clip(chênh lãi suất 3M / 2%, -1, 1) trên FX; 1/N nghịch vol; rebal tháng | trần {1%; 2%; 4%} x rebal {tuần, tháng, quý} |
| G | Meta-labeling lên tín hiệu E | LightGBM (7 lá, sâu 3, lr 0,05, 200 cây) dự đoán lệnh Donchian-E có lãi sau chi phí hay không; bỏ lệnh nếu p < 0,50; đặc trưng: vol, ret21/63/252 chuẩn hoá, ADX, khoảng cách SMA200, độ rộng kênh, spread, lớp, chiều, chênh carry; purged K-fold (5, embargo 10 ngày) báo AUC | ngưỡng p {0,45; 0,5; 0,55} x số cây {100; 200; 400} |
| H | Ensemble | cân bằng rủi ro 7 dòng lợi suất A-G, mỗi dòng nhân 10%/vol trượt 252 ngày (trễ 1 ngày), trọng số bằng nhau | không có lưới |

## 4. Đối chứng (baseline)
(1) Mua-giữ 1/N chỉ số + kim loại, vol 10%. (2) Tín hiệu NGẪU NHIÊN: dấu ngẫu nhiên mỗi tháng/mã, 200 lần, cùng engine/chi phí. (3) Placebo dịch vòng tín hiệu cho A, B, C, E, F (200 lần, dịch ngẫu nhiên 250+ ngày mỗi mã). (4) Chênh lệch Sharpe so mua-giữ qua bootstrap.

## 5. Số thử nghiệm (cho DSR)
7 ứng viên x 9 ô lưới (đã chứa ô chính) + H = **N = 64**. Phương sai Sharpe giữa các thử nghiệm lấy từ 63 ô lưới trên DEV+VAL.

## 6. Tiêu chí chấp nhận (cố định trước)
Cửa DEV-VAL (2008-2020, 13 năm, sau chi phí) - phải đạt CẢ 5:
1. CI95 dưới của Sharpe (block bootstrap 21 ngày, 2000 mẫu) > 0.
2. DSR (N = 64) > 0,95.
3. PBO (CSCV, S = 16) trên lưới 9 ô của chính ứng viên < 0,5.
4. Sharpe > 0 ở cả DEV và VAL.
5. Sharpe cao hơn phân vị 95 của tín hiệu ngẫu nhiên (đối chứng 2).
Cửa TEST (một lần): Sharpe sau chi phí > 0 VÀ P(Sharpe <= 0) < 0,10 (bootstrap khối) VÀ Sharpe TEST >= 0,5 x Sharpe DEV-VAL VÀ MaxDD TEST <= 1,5 x |MaxDD DEV-VAL|.
Kết luận: **ĐẠT** = qua cả hai cửa. **ĐA DẠNG HOÁ CÓ ĐIỀU KIỆN** = không qua đủ nhưng Sharpe DEV-VAL > 0,3 và Sharpe TEST > 0 (chỉ làm lớp đa dạng hoá/ paper theo dõi, không phải nguồn lợi nhuận độc lập). **KHÔNG ĐẠT** = còn lại. Báo cáo thêm (không phải cửa): chi phí x2, trễ 2 nến, Sharpe theo năm, so mua-giữ.

## 7. Sửa đổi
(chưa có)
