# R3 - Machine learning / AI cho giao dịch (2026-10-15)

Kết luận ngắn: **không có bằng chứng ML/AI tạo edge hướng giá trên D1 sau chi phí với dữ liệu của ta**. Phần đáng dùng: dự báo biến động (rủi ro), meta-labeling như bộ lọc (chỉ khi đã có tín hiệu gốc có edge), quy trình purged CV. Không nên đầu tư RL/deep/foundation model cho hướng giá.

## 1. Khảo sát phương pháp (mức tin cậy: T = cao, V = vừa, Th = thấp)
| Nhóm | Bằng chứng | Dùng? |
|---|---|---|
| Meta-labeling (López de Prado, *Advances in Financial ML* 2018) | Ý tưởng hợp lý: mô hình phụ quyết định vào/ra + định cỡ lệnh cho tín hiệu gốc. Chỉ nâng chất lượng nếu tín hiệu gốc có precision>ngẫu nhiên; không "tạo" edge từ không. (V) | Chỉ sau khi có tín hiệu gốc sống sót (hiện: trend đa tài sản). Thử làm bộ lọc, đo bằng DSR |
| GBM (LightGBM/XGBoost) trên feature kỹ thuật | Tabular mạnh nhất cho dữ liệu nhỏ; nhưng SNR giá D1 cực thấp - xem thí nghiệm dưới (T, do ta đo) | Dùng cho dự báo biến động/ phân loại chế độ; không cho hướng |
| Deep (LSTM/TCN/Transformer) | Nhiều bài báo báo cáo lợi nhuận, thiếu nhất quán/ không tái lập; dữ liệu giá nhỏ nên overfit; cần GPU để thử đúng. (Th-V) | Không (CPU-only, chi phí/ rủi ro overfit cao) |
| Foundation model chuỗi thời gian (Chronos, TimesFM, Moirai) | Hai bài 2026: Noguer i Alonso & Pereira Franklin, arXiv 2606.27100 (Chronos, Chronos-2, TimesFM-2.5, Moirai-2 trên 5 cổ phiếu Mỹ): lợi thế so với random walk nhỏ và hiếm (DM test chỉ bác bỏ ở Chronos/AMZN và Moirai-2/GOOG). Cheung & Kwon, arXiv 2607.12248: TimesFM zero-shot thấp hơn base rate "luôn tăng"; LoRA giảm sai số điểm nhưng không có edge hướng. (V, theo snippet tìm kiếm, chưa đọc toàn văn) | Không chạy: cần torch + tải trọng số từ hub (không có sẵn trên VPS); bằng chứng ngoài cho thấy không đáng. Có thể thử sau như đặc trưng biến động |
| RL (FinRL, SB3) | FinRL-Meta (arXiv 2211.03107) tự nêu 3 trở ngại: SNR thấp, survivorship bias, backtest overfitting; có bài về xử lý backtest overfitting cho RL crypto (arXiv 2209.05559). Kết quả RL rất nhạy seed/siêu tham số, tái lập kém. (V) | Không cho tiền thật; chỉ dùng như thí nghiệm khoa học nếu có môi trường chi phí thực tế |
| LLM-as-analyst | Rủi ro lookahead qua kiến thức tiền huấn luyện (mô hình "đã biết" tương lai), không kiểm thử được trung thực trên quá khứ trước ngày cắt dữ liệu. (V) | Dùng để tóm tắt/ phân loại tin & giải thích, KHÔNG làm nguồn tín hiệu giao dịch. Chỉ forward-test |

Rủi ro chung: (a) leakage (nhãn nhìn tương lai, scale toàn mẫu, đặc trưng trùng cửa sổ nhãn); (b) overfit qua nhiều lần thử (dùng DSR/PBO); (c) CV thường K-fold trộn thời gian - bắt buộc purged + embargo (López de Prado, AFML ch.7); (d) so với baseline "luôn tăng" chứ không chỉ 50% (xem 2607.12248: "directional accuracy lies"); (e) chi phí giao dịch.

## 2. Thí nghiệm tái lập (số thật)
Mã: `data/research/program/R3/lgbm_wf.py` (kết quả `results.json`, `run.log`). Chạy: `cd data/research/program/R3 && python3 lgbm_wf.py` (cần `pip install lightgbm scikit-learn`; ~vài phút CPU).
- Dữ liệu: D1 SPY (1993-, db_d1) và vàng GC (2000-) tới 2026-02-26. **Không chạm tập TEST khoá** (cắt 2026-03-01 < ranh giới test 2026-03-11). FX D1 của ta chỉ ~730 bar (từ 2023-12) - quá ngắn cho ML, bỏ.
- Feature: log-return 1-60 ngày, vol 5/20/60, tỉ lệ vol, khoảng cách MA50/200, biên độ ngày, RSI14, thứ trong tuần. Nhãn: dấu return ngày kế tiếp; hồi quy log|r| ngày kế tiếp.
- Walk-forward mở rộng (huấn luyện lại mỗi năm, 5 năm đầu làm warm-up), purge+embargo 5 phiên (~10 ngày lịch) giữa train và test. LightGBM nhỏ (7 lá, 150 cây, regularize mạnh). Chi phí giả định 1-2 bp/chiều (SPY 1bp, GC 2bp).
- Baseline: luôn tăng (base rate), naive "dấu hôm nay = dấu ngày mai", hoán vị 500 lần dự báo, buy&hold.

| | SPY (7081 ngày, 1998-2026) | GC (4836 ngày, 2006-2026) |
|---|---|---|
| Accuracy LightGBM | 52,28% | 51,70% |
| Base rate "luôn tăng" | 53,85% | 52,87% |
| Naive (dấu hôm trước) | 49,26% | 48,18% |
| AUC | 0,510 | 0,506 |
| p (so "luôn tăng", nhị thức) | 0,008 (mô hình **kém hơn** base) | 0,10 |
| Sharpe gộp long/short | 0,32 | 0,18 |
| Sharpe ròng long/short | 0,25 | 0,04 |
| Sharpe buy&hold | 0,36 | 0,62 |
| p hoán vị Sharpe | 0,156 | 0,647 |
| Vòng quay vị thế/ngày | 0,51 | 0,55 |
| Spearman dự báo |r| ngày kế (LightGBM) | 0,442 | 0,223 |
| Spearman naive (vol20) | 0,368 | 0,239 |

Diễn giải trung thực:
1. **Hướng giá: không có edge.** AUC ~0,51; accuracy thấp hơn việc luôn đoán "tăng"; Sharpe long/short ròng không vượt buy&hold và không khác hoán vị ngẫu nhiên (p 0,16 và 0,65). Phù hợp tài liệu (2606.27100, 2607.12248).
2. **Biến động: có tín hiệu nhưng phần lớn đã nằm trong vol 20 ngày** (SPY 0,44 vs 0,37, tăng nhẹ; vàng 0,22 vs 0,24, không tăng). Dùng để đặt cỡ lệnh/ vol-targeting, không phải để kiếm lợi nhuận trực tiếp. Chưa kiểm định thống kê chênh lệch này (cảnh báo: chưa DM test).
3. Hạn chế: 1 cấu hình siêu tham số (không tinh chỉnh, để tránh overfit nhưng cũng chưa dò), chi phí giả định, chỉ 2 tài sản, chưa làm DSR/PBO, không thử H4. Kết quả âm tính này không loại trừ edge ở khung nhỏ/ đặc trưng vi cấu trúc, nhưng ta chưa có bằng chứng.

## 3. Khuyến nghị cho dự án
- Không triển khai ML dự báo hướng D1 (không edge). Không dùng Chronos/TimesFM/RL/deep làm tín hiệu giao dịch.
- Đáng làm (rẻ, CPU): (1) LightGBM/HAR dự báo biến động cho vol-targeting & bộ lọc rủi ro, kiểm bằng DM test so HAR; (2) meta-labeling thử trên trend đa tài sản (R1) với purged CV + DSR; (3) chuẩn hoá khung purged walk-forward + embargo + baseline "luôn tăng" + hoán vị thành thư viện dùng chung cho lab AI Trading.
- Foundation model: nếu muốn xác nhận cục bộ, cần cài torch CPU + tải trọng số (miễn phí) - ưu tiên thấp.
- Dữ liệu: cần lịch sử D1/H4 FX dài (đang chỉ ~2,8 năm) trước khi nghiên cứu ML FX nghiêm túc.

## Nguồn
- arXiv 2606.27100 (Pretrained Time-Series Foundation Models for Financial Return Forecasting); arXiv 2607.12248 (When Directional Accuracy Lies, TimesFM LoRA); arXiv 2211.03107 (FinRL-Meta); arXiv 2209.05559 (DRL crypto, backtest overfitting); López de Prado, *Advances in Financial Machine Learning* (2018). Hai bài 2026 và FinRL chỉ đọc qua tóm tắt tìm kiếm, chưa đọc toàn văn.
