# R10 - Thực nghiệm trung thực trên dữ liệu của ta

Ngày: 2026-10-15. Đăng ký trước: `docs/research/program/R10_preregistration.md` (SHA-256 `07161ccd...a5b6b8e26e` xem `R10_preregistration.sha256`). Mã/sổ lệnh/hình đầy đủ: `data/research/program/R10/` (mã trong `code/`, nhật ký mở test `test_access.log`, đóng băng `freeze.json`). Bản nhỏ nén: `docs/research/program/R10_artifacts/`. JSON ứng viên cho registry: `docs/research/program/R10_candidates.json`.

## 0. Kết luận thẳng
**Không có ứng viên nào qua tiêu chí đã đăng ký trước. Không có edge sau chi phí trên dữ liệu này.**
- 8/8 ứng viên: KHÔNG ĐẠT. DSR (N = 64 thử nghiệm) tối đa 0,19 (A); không ứng viên nào có CI95 dưới của Sharpe > 0 trong 2008-2020.
- Ứng viên gần nhất là **A (trend đa tài sản + vol-target)**: Sharpe sau chi phí 0,27 (2008-2020) và 0,53 (TEST 2021-26), nhưng CI rộng (TEST: -0,27..1,35), PBO 0,62, VAL âm (-0,29), và tốt hơn đường mua-giữ không có ý nghĩa thống kê. Phân rã thăm dò (không phải cửa) cho thấy lợi suất A đến chủ yếu từ **kim loại** (vàng/bạc: +3,2%/năm DEV-VAL, +5,3%/năm TEST), FX gần 0 hoặc âm ở DEV-VAL. Phù hợp kết luận cũ: trend chậm chỉ là lớp đa dạng hoá, không phải nguồn lợi nhuận độc lập.
- Mean-reversion có điều kiện regime (D), TSMOM nhiều khung (C), Donchian (E): thua cả sau lẫn trước chi phí; chi phí do vòng quay cao (44-98 lần/năm) làm tệ thêm.
- Carry (F): carry thật dương (+3,1%/năm) nhưng bị giá đảo chiều (-4,7%/năm) ở DEV-VAL; TEST Sharpe 0,28 (không có ý nghĩa). Meta-labeling (G): AUC purged-CV 0,50 (không có kỹ năng dự đoán), chỉ cho qua ~10% lệnh.
- Mua-giữ 1/N chỉ số + kim loại (vol 10%) đạt Sharpe 0.49 (DEV-VAL) và 0.72 (TEST), cao hơn mọi ứng viên; phần lớn là premium thị trường cổ phiếu/vàng, không phải kỹ năng giao dịch.

## 1. Dữ liệu và chia đoạn
- 39 mã D1 MT5 native (28 cặp FX G8 từ 2000, 9 chỉ số từ 2007-2014 tuỳ mã, vàng từ 2004, bạc từ 2008). Snapshot `panel_d1.parquet`, SHA-256 `9681d1c06409931c...` (đủ hash ở `panel_meta.json`), cắt tại **2026-03-10** để không chạm tập TEST khoá của kịch bản Sell.
- Khởi động 2000; DEV 2008-2017; VAL 2018-2020; **TEST khoá mới 2021-01-01..2026-03-10 (5,2 năm)**, mở MỘT lần sau khi đóng băng mã + tham số (`freeze.json`, `test_access.log`). Kiểm tra nhân quả: cắt dữ liệu tại 2020-12 rồi chạy lại cho trọng số/lợi suất DEV-VAL trùng hoàn toàn (chênh lệch tối đa 0,0).
- Giới hạn về "mới": TEST mới đối với các ứng viên này và với nguồn dữ liệu MT5, nhưng các nghiên cứu trước (nguồn khác) đã quan sát cùng giai đoạn thị trường nên không trinh nguyên tuyệt đối. Dữ liệu MT5 demo chưa được đối chiếu độc lập với nguồn thứ hai; chuỗi FX cũ (trước 2007) của broker demo có thể là dữ liệu tổng hợp.
- Thành thật về quy trình: một lần chạy smoke 6 ứng viên A-F (tham số chính) trên 2008-2020 diễn ra trước khi chốt tài liệu đăng ký (chỉ để kiểm mã), không đổi tham số sau đó (ghi ở mục 0 của đăng ký trước). TEST chưa được nạp trước thời điểm mở.

## 2. Phương pháp rút gọn
Engine vector hoá (`code/lib.py`): quyết định ở close t, khớp close t, hưởng lợi suất t+1 (trễ 2 nến = độ nhạy). Chi phí một chiều = 0,5 x max(spread nến 60 ngày, spread MT5 từ R7) + trượt giá; tài trợ qua đêm FX theo chênh lãi suất 3M công khai trừ markup 0,35%/năm (hiệu chuẩn từ swap MT5 thật của R7: không có swap lịch sử nên dùng proxy lãi suất); chỉ số = cổ tức giả định 2% - lãi USD - markup; kim loại = -lãi USD - markup. Vol mục tiêu 10%, cov EWMA, trần đòn bẩy. Bootstrap khối 21 ngày x 2000. DSR (Bailey-Lopez de Prado) với N = 64; PBO bằng CSCV (S = 16) trên lưới 3x3 của chính ứng viên.

## 3. Kết quả DEV+VAL (2008-2020, sau chi phí)
| Ứng viên | CAGR | Sharpe [CI95] | MaxDD | Số lệnh | DSR | PBO | Kết luận |
|---|---|---|---|---|---|---|---|
| A Trend đa tài sản + vol-target | 2.5% | 0.27 [-0.26; 0.78] | -28% | 984 | 0.19 | 0.62 | **KHÔNG ĐẠT** |
| B Cross-sectional momentum (FX/chỉ số) | -4.5% | -0.36 [-0.88; 0.17] | -52% | 879 | 0.00 | 0.92 | **KHÔNG ĐẠT** |
| C TSMOM nhiều khung | -4.3% | -0.31 [-0.80; 0.21] | -59% | 5019 | 0.00 | 0.45 | **KHÔNG ĐẠT** |
| D Mean-reversion có điều kiện regime | -3.1% | -0.59 [-1.11; -0.06] | -37% | 2695 | 0.00 | 0.64 | **KHÔNG ĐẠT** |
| E Breakout kênh Donchian | -3.8% | -0.27 [-0.76; 0.21] | -55% | 2139 | 0.00 | 0.81 | **KHÔNG ĐẠT** |
| F Carry proxy (lãi suất 3M công khai) | -2.3% | -0.14 [-0.62; 0.37] | -37% | 106 | 0.01 | 0.20 | **KHÔNG ĐẠT** |
| G Meta-labeling LightGBM trên Donchian | -4.3% | -0.43 [-0.96; 0.13] | -49% | 199 | 0.00 | 0.11 | **KHÔNG ĐẠT** |
| H Ensemble cân bằng rủi ro A-G | -2.7% | -0.44 [-0.93; 0.09] | -37% | - | 0.00 | - | **KHÔNG ĐẠT** |

Ngưỡng ngẫu nhiên: Sharpe trung bình của 200 chuỗi dấu ngẫu nhiên = -0.20 (do chi phí), phân vị 95 = 0.26. Mua-giữ 1/N: Sharpe 0.49 [-0.08; 1.10], CAGR 5.3%, MaxDD -30%. Đối chiếu placebo dịch vòng: A p = 0.21 (21% chuỗi placebo dịch vòng bằng hoặc hơn A: không phân biệt được với may rủi).

## 4. TEST khoá (một lần, 2021-01-01..2026-03-10)
| Ứng viên | CAGR | Sharpe [CI95] | P(Sharpe<=0) | MaxDD | Số lệnh | Sharpe chi phí x2 / trễ 2 nến | Chênh Sharpe vs mua-giữ (CI95) |
|---|---|---|---|---|---|---|---|
| A | 5.8% | 0.53 [-0.27; 1.35] | 0.09 | -30% | 411 | 0.51 / 0.42 | -1.28..0.82 |
| B | 1.9% | 0.23 [-0.62; 1.08] | 0.29 | -15% | 348 | 0.19 / 0.13 | -1.87..0.77 |
| C | -4.6% | -0.36 [-1.15; 0.42] | 0.82 | -37% | 2102 | -0.53 / -0.15 | -2.35..0.19 |
| D | -2.2% | -0.38 [-1.10; 0.38] | 0.84 | -21% | 1270 | -0.67 / -0.29 | -2.17..-0.05 |
| E | -3.3% | -0.24 [-1.07; 0.61] | 0.70 | -39% | 954 | -0.32 / -0.18 | -2.09..0.17 |
| F | 2.6% | 0.28 [-0.55; 1.16] | 0.26 | -21% | 37 | 0.27 / 0.29 | -1.45..0.58 |
| G | 0.1% | 0.05 [-0.82; 0.87] | 0.45 | -17% | 68 | 0.02 / 0.20 | -1.90..0.47 |
| H | -0.2% | -0.00 [-0.78; 0.81] | 0.48 | -12% | - | - | -1.82..0.33 |

Mua-giữ 1/N trong TEST: Sharpe 0.72, CAGR 7.7%, MaxDD -20%. Sharpe ngẫu nhiên TEST: trung bình -0.25, phân vị 95 = 0.43: **chỉ A (0,53) vượt phân vị 95 của tín hiệu ngẫu nhiên trong TEST (0,43; xác suất ngẫu nhiên >= A là 3%)**, nhưng CI của A vẫn bao 0 và placebo dịch vòng cho p = 0,30 (không phân biệt được với may rủi).
Cửa TEST: A qua cả 4 điều kiện TEST (Sharpe > 0, P<=0 = 0,09, không sụp, DD trong 1,5x), nhưng không qua cửa DEV-VAL nên kết luận cuối vẫn KHÔNG ĐẠT theo quy tắc đã đăng ký; không nâng hạng sau khi thấy kết quả.

## 5. Phân rã thăm dò (post-hoc, KHÔNG phải cửa, không dùng để chọn)
Đóng góp trung bình %/năm theo lớp (sau chi phí), DEV-VAL / TEST: A: FX -0.76/0.53, chỉ số 0.68/0.52, kim loại 3.24/5.27. E: FX -0.28/-2.26, chỉ số -2.43/-4.33, kim loại -0.46/3.85. C: FX -3.49/-3.6. B: FX -2.15/2.96, chỉ số -1.86/-0.55. Edge (nếu có) của trend nằm ở vàng/bạc trong giai đoạn giá kim loại tăng mạnh; FX D1 sau chi phí không sinh lời trong mẫu này. Đây là 1 mẫu 18 năm với 1 chế độ kim loại, không đủ để khẳng định.

## 6. Hạn chế
- TEST chỉ 5,2 năm: CI Sharpe rộng ±0,8; không thể phân biệt Sharpe 0,5 với 0.
- Bộ chỉ số chỉ có từ 2012 (đa số), nên DEV chủ yếu là FX + kim loại; TEST giàu chỉ số hơn: so sánh DEV-TEST không cùng cấu trúc vũ trụ.
- Số thử nghiệm 64 đã đếm, nhưng quyết định thiết kế trước đó (chọn vũ trụ, chi phí, markup) không đếm được; DSR vẫn lạc quan.
- Swap MT5 chỉ là ảnh chụp hiện tại; lịch sử dùng lãi suất 3M công khai (EUR/GBP thiếu từ 2026, giữ giá trị cuối).
- Không đo vi cấu trúc ngày nội phiên; D1 không phản ánh trượt giá khi tin tức.
- Cổ tức chỉ số giả định 2% hằng số; kim loại không tính chi phí lưu kho.

## 7. Khuyến nghị cho điều phối viên
1. Tạo thẻ registry cho A-H với trạng thái "đã kiểm, không đạt"; ghi rõ số thật từ `R10_candidates.json`. Không đưa vào paper-trade như nguồn lợi nhuận.
2. A (trend) có thể giữ ở vai trò đa dạng hoá/ theo dõi paper nhẹ (vì Sharpe dương ở cả hai đoạn, tương quan thấp với mua-giữ) với kỳ vọng không có edge; không dùng vốn thật.
3. Loại D, C, E, B (D1, FX/chỉ số) khỏi danh mục đề xuất; G không có kỹ năng dự đoán (AUC 0,50).
4. Cần đoạn dữ liệu dài hơn, nhiều tài sản hơn (đối chiếu MULTI_ASSET: Sharpe ~0,55 trên 35 tài sản 1990-2026) trước khi kết luận về trend; hướng hữu ích nhất là danh mục đa tài sản chậm kèm bộ lọc rủi ro, không phải thêm kịch bản D1 trên FX.

## 8. Tái lập
`cd data/research/program/R10/code; PYTHONPATH=../pylib python3 build_panel.py; python3 run.py dev; python3 run.py test; python3 post.py` (cần numpy/pandas/scipy/numba/lightgbm/sklearn; matplotlib cài ở `../pylib`). Hình: `fig_A..H.png`, `fig_all.png`; sổ lệnh `ledger_*_test.csv.gz` (cột segment DEV/VAL/TEST); lợi suất ngày `R10_daily_returns.csv.gz`.
