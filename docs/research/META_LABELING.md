# C1 — Meta-labeling trên tín hiệu KB-1..KB-4 (báo cáo trung thực)

Ngày 2026-10-15 · Nghiên cứu offline, READ-ONLY, không đặt lệnh · **TẬP TEST KHOÁ KHÔNG ĐƯỢC MỞ** (chỉ dùng sổ lệnh walk-forward dev+val `wf_oos_trades.parquet` và nến < 2026-03-11; `test_access.log` không có dòng mới) · Mã: `services/pattern-research/pattern_research/metalabel/` · Kết quả số: `docs/research/meta_labeling/results.json` · Tái lập: `python3 -m pattern_research.metalabel.run` (~40 giây, nice, 2 luồng).

## 0. Trả lời thẳng

**Lọc ML KHÔNG cứu được edge.** Mô hình có chút kỹ năng xếp hạng (AUC ngoài mẫu 0,539, CI95 [0,526; 0,551] — nhỏ nhưng khác 0,5), nên giữ lại 50% lệnh "tốt nhất" làm lỗ ít hơn (GBM: −0,055 R so với −0,105 R lấy tất cả; p so với chọn ngẫu nhiên cùng cỡ = 0,0005). Nhưng **mọi cấu hình đều ≤ 0 sau chi phí**, trừ một ô (logit top 10%: +0,003 R, CI [−0,066; +0,077], không khác 0) mà **GBM top 10% cùng nhóm lại −0,115 R** → mâu thuẫn = nhiễu/đa so sánh; Deflated Sharpe 0,11; khi chi phí ×2 là −0,052 R. Trên VAL riêng (404 lệnh, giai đoạn gần nhất) tất cả cấu hình đều âm.

## 1. Thiết kế

- **Ứng viên**: 8.290 lệnh KB-1..4 dev+val (sổ lệnh walk-forward đã có, R đã trừ spread/trượt/phí). Nhãn `y = (R > 0)`. Tỉ lệ thắng nền 36,9%.
- **Đặc trưng (27)**, chỉ dùng nến ≤ nến tín hiệu (có test chống nhìn tương lai): ATR/giá, tỉ lệ ATR hiện tại/trung bình 100 nến, hạng ATR 250 nến (regime biến động), ATR nhanh/chậm, độ nén 10 nến (biên độ/ATR), khoảng cách tới đáy/đỉnh 50 nến (S/R, theo ATR), volume z-score 50 nến, xu hướng (giá − SMA50)/ATR, return 10 nến/ATR, giờ (sin/cos), thứ, phiên Á/Âu/Mỹ, khung, điểm engine, SL/ATR, KB (one-hot), nhóm tài sản. **Tin kinh tế: KHÔNG có dữ liệu lịch tin trong kho → không dùng** (ghi rõ, chưa thử).
- **Mô hình** (tham số cố định, không tinh chỉnh để khỏi tự lừa): Logistic L2 (C=0,05, chuẩn hoá) và LightGBM nhỏ (200 cây, 8 lá, min_child 100, subsample 0,8, lambda 5). ONNX: bỏ qua (không có hiệu quả để xuất; chưa cần vì không dùng được).
- **Chọn lệnh**: giữ top q ∈ {50%, 25%, 10%} theo điểm mô hình, xếp hạng TRONG từng khối đánh giá (không dùng nhãn; ngưỡng tuyệt đối không ổn định giữa các năm). 2 mô hình × 3 q = **6 thử nghiệm** (dùng cho DSR/PBO).
- **Purged K-fold (K=8) + embargo 5 ngày**: loại khỏi train mọi lệnh có khoảng [vào, thoát] chồng khoảng test ± embargo. Là điểm OOF (train có cả dữ liệu tương lai của khối) nên chỉ mang tính tham khảo.
- **Walk-forward (bằng chứng chính)**: khối đánh giá = từng năm 2012..2024, 2025H1, VAL; train = các lệnh ĐÃ ĐÓNG trước khối − 5 ngày. 6.994 lệnh được đánh giá (từ 2012 vì cần ≥ 400 lệnh train).
- **Đối chứng**: (a) "lấy tất cả" cùng 6.994 lệnh; (b) ngẫu nhiên: chọn cùng số lệnh mỗi khối, 2.000 hoán vị → p; (c) chi phí ×2 (R − chi phí thêm); (d) DSR (n_trials = 6, `backtest.deflated_sharpe`); (e) PBO bằng CSCV 16 nhóm theo quý (`backtest.pbo_cscv`).

## 2. Kết quả walk-forward 2012+ (R/lệnh sau chi phí)

| Cấu hình | n | E[R] | CI95 | Win | PF | E[R] sổ lệnh "gross" | Chi phí ×2 | Ngẫu nhiên cùng cỡ | p | DSR |
|---|---|---|---|---|---|---|---|---|---|---|
| **Lấy tất cả** | 6.994 | −0,105 | [−0,133; −0,077] | 36,8% | 0,82 | −0,024 | — | — | — | — |
| Logit top 50% | 3.496 | −0,084 | [−0,121; −0,049] | 39,1% | 0,84 | −0,019 | −0,150 | −0,105 | 0,07 | 0,00 |
| Logit top 25% | 1.748 | −0,092 | [−0,142; −0,042] | 40,1% | 0,81 | −0,030 | −0,154 | −0,105 | 0,30 | 0,00 |
| Logit top 10% | 700 | +0,003 | [−0,066; +0,077] | 45,4% | 1,01 | +0,058 | −0,052 | −0,105 | 0,006 | 0,11 |
| GBM top 50% | 3.496 | −0,055 | [−0,093; −0,017] | 39,8% | 0,89 | +0,014 | −0,124 | −0,105 | 0,0005 | 0,00 |
| GBM top 25% | 1.748 | −0,065 | [−0,115; −0,016] | 40,8% | 0,86 | −0,004 | −0,126 | −0,105 | 0,05 | 0,00 |
| GBM top 10% | 700 | −0,115 | [−0,188; −0,038] | 40,1% | 0,76 | −0,061 | −0,168 | −0,105 | 0,61 | 0,00 |

AUC OOS: logit 0,539 [0,526; 0,551]; GBM 0,539 [0,524; 0,553]. Purged K-fold OOF: AUC 0,547/0,549; top 10% −0,020 / −0,026 R (CI chứa 0), top 50% −0,069 / −0,063 R. PBO (CSCV) = 0,006 — **đừng đọc là "có edge"**: PBO chỉ đo xếp hạng giữa 6 cấu hình có ổn định không (GBM top 50% luôn hơn GBM top 10%), không đo lợi nhuận có thật hay không; các cấu hình tương quan mạnh và quý không có lệnh được điền 0.

Hình: `docs/research/meta_labeling/exp_r.svg` (R/lệnh + CI), `docs/research/meta_labeling/equity.svg` (tổng R tích luỹ — mọi đường đều đi xuống).

## 3. Vì sao "ít lỗ hơn" mà vẫn không phải edge

1. Đặc trưng quan trọng nhất (GBM, gain, trong mẫu): `sl_atr` 22%, `atr_rel` 16%, `compress10` 12%, `vol_rank` 11%. Lệnh SL rộng (theo ATR) và biến động tương đối lớn có **chi phí cố định chiếm ít R hơn** → mô hình chủ yếu học "lệnh rẻ chi phí", không học hướng giá. Dấu hiệu: cải thiện nằm ở phần chi phí; khi đẩy chi phí ×2 mọi cấu hình về âm.
2. Trước chi phí chỉ có GBM top 50% (+0,014) và logit top 10% (+0,058) dương, đều rất mỏng và không bền: GBM top 10% (cùng nhóm) âm.
3. Kết quả theo thời gian không ổn định: VAL (404 lệnh, gần nhất) lấy tất cả −0,215 R, các cấu hình lọc −0,06..−0,27 R (CI đều rộng, 5/6 cấu hình có CI chứa 0 nhưng không có cấu hình nào dương).
4. 6 thử nghiệm, chọn ô tốt nhất sau khi xem kết quả (logit top 10%) là đa so sánh điển hình; DSR 0,11 xác nhận.

## 4. Hạn chế / việc chưa làm

- Không có lịch tin kinh tế (thiếu dữ liệu miễn phí đã nhập); đặc trưng tin chưa thử.
- Lệnh có thể chồng nhau giữa mã/khung; thống kê theo lệnh, không mô phỏng vốn. Chưa mô hình swap.
- Tập ứng viên là đầu ra của walk-forward cũ (TP 2R); không chạy lại detector với tham số khác.
- **Chưa đánh giá trên TEST khoá và sẽ không làm khi chưa có người dùng duyệt.** Kết quả dev+val không ủng hộ việc đốt tập test cho meta-labeling này (không có cấu hình nào đáng đánh giá cuối).
- Không xuất ONNX: không có mô hình nào đủ tốt để đưa vào paper.

## 5. Kết luận

Meta-labeling với đặc trưng giá/biến động/phiên/S-R chỉ cho kỹ năng xếp hạng rất nhỏ (AUC ≈ 0,54), giảm lỗ nhưng **không biến KB-1..4 thành chiến lược có lãi sau chi phí**. Trạng thái: `research`, verdict `no_edge`.
