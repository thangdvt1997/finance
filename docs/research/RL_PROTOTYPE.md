# D2 - Prototype học tăng cường (RL) trên nến H1, mô phỏng paper

Ngày 2026-10-15. Nghiên cứu offline; không đặt lệnh; TEST khoá không mở (chỉ nạp split train/val, có assert; dữ liệu <= 2026-03-06).

## Thiết lập
- Mã: `services/pattern-research/pattern_research/rl/` (`env.py` môi trường gym-like có gymnasium tuỳ chọn, `algos.py`, `run.py`), test `tests/test_rl.py`. Chạy: `python -m pattern_research.rl.run out.json` (~110 s, 1 CPU, nice).
- Dữ liệu: H1 EURUSD, XAUUSD, US500 (kho `data/research/patterns`). Lưu ý: kho chỉ có từ 2023-12 (EURUSD) / 2024-05 (XAU, US500) nên "dev đến hết 2023" không khả thi; dùng đúng ranh giới chung `splits.json`: train đến 2025-07-27, val 2025-08-01..2026-03-05.
- Hành động {flat, long, short}; thưởng = vị thế x lợi suất nến kế - chi phí x |đổi vị thế|. Chi phí = nửa spread + trượt giá mỗi chiều theo bảng COSTS của `backtest.py` (sàn spread bi quan, không dùng spread demo).
- Đặc trưng (chỉ gồm giá đến hết nến t): lợi suất 1/3/6/12/24 chuẩn hoá theo vol, vol, z so MA24, giờ, thứ.
- Thuật toán: stable-baselines3 cần torch (không có trên VPS, không cài để tránh nặng/tài nguyên chung) nên dùng phương án dự phòng: (1) ES chính sách tuyến tính 3 hành động, (2) Q-learning bảng (27 trạng thái x vị thế).
- Walk-forward: val chia 3 khối ~2,5 tháng; mỗi khối huấn luyện lại trên mọi dữ liệu trước khối (trừ 5 ngày embargo), dự đoán khối đó, ghép OOS. 10 seed mỗi (thuật toán, mã), báo cáo toàn bộ phân bố, không chọn seed.
- So sánh: mua&giữ (cùng khoảng, có chi phí vào), ngẫu nhiên (200 chuỗi {flat,long,short} đều), DSR (Bailey-López de Prado) với N = 60 lần thử (2 thuật toán x 3 mã x 10 seed), phương sai Sharpe qua các lần thử.

## Kết quả (Sharpe thường niên OOS sau chi phí)
| Mã | Mua&giữ | Ngẫu nhiên (TB) | ES TB / trung vị [min,max], >0 | Q TB / trung vị [min,max], >0 | DSR trung vị ES / Q |
|---|---|---|---|---|---|
| EURUSD | 0,46 (+1,7%) | -6,29 | 0,44 / 0,57 [-0,30; 1,26], 7/10 | -0,90 / -0,48 [-3,70; 0,70], 2/10 | 0,03 / 0,00 |
| XAUUSD | 2,75 (+44,6%) | -0,80 | 1,72 / 1,71 [1,17; 2,25], 10/10 | -0,08 / -0,31 [-2,03; 2,26], 4/10 | 0,17 / 0,01 |
| US500 | 1,02 (+7,9%) | -3,73 | 0,78 / 0,76 [0,20; 1,15], 10/10 | -0,45 / 0,00 [-3,21; 0,80], 2/10 | 0,05 / 0,00 |

Hình: `rl_prototype_sharpe.svg` (mỗi chấm một seed, vạch đỏ = mua&giữ). Số liệu thô: `rl_prototype_result.json` (sha256 fb2f71fe...f21).

## Kết luận trung thực
- RL KHÔNG có edge sau chi phí. Q-learning bảng âm/ngang 0 gần như mọi nơi (chỉ 2-4/10 seed dương, in-sample cũng âm: không học được gì). ES dương nhưng chỉ vì học thiên lệch mua (long bias) trong giai đoạn val tăng giá (vàng +45%): ES thua mua&giữ ở cả XAUUSD và US500, chỉ hơn mua&giữ ở EURUSD ở 60% seed với mức sai khác nằm trong dao động giữa seed. DSR trung vị <= 0,17 (cần ~0,95): không phân biệt được với may rủi sau trừ 60 lần thử.
- Mốc "ngẫu nhiên" rất âm vì chi phí giao dịch; không phải mốc tốt để khoe, mốc đúng là mua&giữ.
- Cảnh báo overfitting/hạn chế: chỉ ~2 năm dữ liệu H1, 3 khối val (~8 tháng) và một chế độ giá duy nhất (vàng/chỉ số tăng); khác biệt in-sample vs OOS lớn ở vàng (2,75 vs 1,72). Chi phí dùng sàn bi quan; chưa có spread động. Không mở test khoá. Không kết luận RL "vô dụng" nói chung, chỉ rằng prototype nhỏ này không chứng minh được edge; không đủ cơ sở dùng cho paper/live.
