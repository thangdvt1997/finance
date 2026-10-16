# TRADING_PLAN — Phương án giao dịch hợp lý nhất theo chứng cứ (2026-10-15)

Tổng hợp R1–R11 (chương trình nghiên cứu). Chỉ READ-ONLY + PAPER. Giao dịch thật chỉ sau cổng pháp lý G1–G3.

## 1. Kết luận thẳng
**Không có phương án nào đủ bằng chứng để kỳ vọng lợi nhuận dương sau chi phí.** 8/8 ứng viên R10 trượt tiêu chí đã đăng ký trước; kịch bản KB-1..4, price action/SMC (R2), ML dự báo hướng (R3), COT (R5), momentum/stat-arb crypto (R9), momentum cổ phiếu VN (R8) đều không có edge. Phương án khả thi là **phòng thủ**: một diversifier trend chậm kỳ vọng thấp, bộ lọc rủi ro, cảnh báo, và quản trị vốn nghiêm ngặt; mọi thứ qua paper forward-test trước khi nói đến tiền thật.

## 2. Bảng xếp hạng (kỳ vọng sau chi phí; mọi số có CI rộng, haircut ≥50% theo decay sau công bố — R1)
| # | Phương án | Bằng chứng | Kỳ vọng sau chi phí | Quyết định |
|---|---|---|---|---|
| 1 | Trend chậm đa tài sản D1/W1, vol-target 7,5–10% (R10-A) | Sharpe 0,27 (CI −0,26..0,78) 2008-20; 0,53 test khoá 2021-26; DSR 0,19; PBO 0,62; lợi suất chủ yếu từ vàng/bạc; thua mua-giữ 1/N (0,49/0,72) | Sharpe 0,2–0,5, maxDD −28..−30% | **Đưa vào paper forward-test** vai trò diversifier, không hứa lợi nhuận |
| 2 | Mua-giữ rổ đa dạng (chỉ số + kim loại 1/N; E1VFVN30 cho VN) | Sharpe 0,49–0,72 (R10); 0,40 (R8) | thị trường beta, DD lớn | **Mốc so sánh bắt buộc** cho mọi chiến lược; không phải "chiến lược giao dịch" |
| 3 | Low-vol / low-vol+momentum cổ phiếu VN long-only | Sharpe 0,42/0,61, không phân biệt được với E1VFVN30; chưa hiệu chỉnh đa kiểm định | giảm DD, edge chưa chứng minh | Theo dõi paper (ứng viên giảm rủi ro) |
| 4 | Carry (funding BTC / swap FX) | funding còn ~3%/năm, dưới lãi tiền gửi; swap demo không tin được; R10-F âm | ≈0 | Loại làm nguồn lợi nhuận; funding/basis chỉ làm bộ lọc rủi ro |
| 5 | FVG H4 2R (R2) | +0,093R chỉ nếu limit khớp ngay; −0,055R nếu đòi xuyên 0,15 ATR | không chắc | Backlog; cần dữ liệu khớp limit thật |
| 6 | Cross-sectional momentum, TSMOM nhiều khung, mean-reversion, Donchian, meta-labeling, ensemble (R10 B–H) | Sharpe âm 2008-20; vòng quay 44–98 lần/năm giết edge | âm | **Loại** |
| 7 | KB-1..4, Sweep/Wyckoff/BOS, ML dự báo hướng, COT, momentum/stat-arb crypto, Elliott | kỳ vọng ≤0 hoặc không khác ngẫu nhiên | ≤0 | **Loại** |

Vốn tối thiểu: lot tối thiểu và spread khiến vốn <1.000 USD khó giữ rủi ro ≤0,5%/lệnh trên nhiều mã (R6); khuyến nghị paper với vốn ảo 10.000 USD.

## 3. Khung nào, thị trường nào sống được (R7)
- Chỉ **D1/W1** (và H4 trên US500/US30/USTEC) sống sau chi phí; M1–H1 chết (biên độ nến chỉ ~1,6–7 lần spread).
- Mã rẻ: majors FX (EURUSD, GBPUSD, USDJPY, USDCAD, AUDUSD, EURJPY, GBPJPY), XAUUSD, US500, US30, USTEC, DE40, JPN225. Tránh exotic.
- Vào lệnh sau 00:00 UTC (rollover 21–23 UTC spread nở 2–7 lần); backtest tự cộng slippage quanh tin.
- Giới hạn: spread demo đổi chế độ, không có slippage/swap tin cậy → cần đo trên paper forward.

## 4. Quản trị rủi ro (R6) — áp dụng cho mọi paper
- Rủi ro/lệnh 0,25% (tối đa 0,5%) khi chưa có edge; 0,5–1% (trần 1%) chỉ khi đã qua walk-forward + test khoá. Kelly tối đa 1/4.
- Tổng rủi ro nóng ≤3% (paper 2%); mỗi nhóm tương quan ≤1,5%.
- Vol mục tiêu trend 7,5–10%/năm; giảm đòn ×0,5 / ×0,25 tại DD 8% / 12% / 16%.
- Kill switch: DD 20% từ đỉnh → đóng hết, review thủ công. Lỗ ngày/tuần −2%/−4%. 5 lệnh thua liên tiếp → nghỉ phiên. E[R] 250 lệnh gần nhất âm → giảm về 0,25% hoặc dừng.
- Kiểm tra stress: mọi vị thế gap 6 ATR ngược chiều, tổng thiệt hại ≤20% vốn (SNB 2015 −13,9% USDCHF/ngày).

## 5. Quy trình chuyển giai đoạn
1. **Backtest trung thực**: đăng ký giả thuyết trước, walk-forward, test khoá mở 1 lần, PBO/DSR, baseline ngẫu nhiên + mua-giữ (khung R10/R11 `scenario_runner.py`).
2. **Paper forward ≥12 tuần** (trend chậm D1 cần dài hơn để có đủ rebalance; tối thiểu 6 tháng để đánh giá), sổ lệnh hash-chain, so với kỳ vọng backtest.
3. **So sánh & duyệt**: paper ≥ 50% Sharpe backtest, DD ≤1,5× backtest, không vi phạm giới hạn rủi ro; người dùng duyệt.
4. **Vốn nhỏ thật**: chỉ sau G1–G3 (pháp lý), rủi ro 0,25%/lệnh, kill switch bật.
Kịch bản mới của người dùng đi vào bước 1 qua `scenario_template/*.yaml` (R11).

## 6. Hạ tầng/phần mềm (R4)
- Tích hợp: **vectorbt** (kiểm chéo/quét tham số nội bộ, Apache-2.0+Commons Clause, không phân phối), **skfolio** (tối ưu danh mục; Riskfolio để đối chiếu). Tách venv vì xung đột plotly.
- Giữ tự viết: mô hình chi phí MT5, PBO/DSR, walk-forward, test khoá. Không nhúng backtesting.py (AGPL) vào service.
- Hoãn OMS/thực thi (không công cụ nào có adapter MT5 sẵn). HAR/LightGBM chỉ cho dự báo biến động (R3).

## 7. Nguồn chuyên gia/dữ liệu cần thêm (R5, R7, R8, R9)
- CFTC COT chỉ làm bối cảnh vị thế đông đúc, không phải tín hiệu vào lệnh.
- Nguồn miễn phí: ECB SPF, Philadelphia Fed SPF, BoE survey, FRED/ALFRED — cần đọc ToS trước khi bật.
- Lãi suất chính sách công khai để dựng carry thật (thay swap demo).
- Lịch sử FX dài hơn (hiện chỉ ~730 bar D1 ở một số chuỗi) và dữ liệu khớp lệnh/tick để kiểm FVG.
- VN: dữ liệu realtime hợp lệ (DNSE/SSI) cần người dùng đăng ký.

## 8. Việc cần người dùng
- Duyệt kế hoạch: paper trend chậm D1 + mốc mua-giữ; không đầu tư tiền thật khi chưa qua G1–G3.
- Gửi kịch bản mới (YAML + ảnh) khi sẵn sàng.
- Tài khoản môi giới/API VN (SSI/DNSE) nếu muốn dữ liệu VN realtime; xác nhận pháp lý crypto nếu quan tâm.
- Đọc ToS các nguồn dữ liệu quan điểm trước khi bật.

## 9. Hạn chế của chính bản kế hoạch
Test khoá R10 (5,2 năm) có CI ±0,8; "mới" so với nguồn dữ liệu nhưng các nghiên cứu trước đã thấy cùng giai đoạn thị trường. Dữ liệu MT5 demo chưa đối chiếu nguồn thứ hai. Nhiều tài liệu học thuật chỉ xác minh qua tóm tắt (ghi rõ trong từng báo cáo R1–R11). 64 thử nghiệm đã tính vào DSR, nhưng toàn chương trình còn nhiều phép thử ngoài R10.
