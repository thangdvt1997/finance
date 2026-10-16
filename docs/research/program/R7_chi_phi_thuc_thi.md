# R7 — Chi phí & thực thi (MT5 demo MetaQuotes-Demo)

Ngày: 2026-10-15. Phạm vi: spread/ slippage/ swap/ commission, ảnh hưởng theo cặp, khung, giờ, tin tức; khung nào sống được sau chi phí. Chỉ đọc dữ liệu (parquet MT5 native + `symbol_info` của terminal demo); KHÔNG mở phần test khoá, không dùng lợi nhuận val/test.
Mã: `data/research/program/R7/` (`r7_analyze.py`, `r7_tables.py`, `sym_specs.py`, `specs_raw.json`, `r7_raw.pkl`). Bảng CSV nhỏ: `docs/research/program/R7_data/`.

## 1. Kết luận ngắn (mức tin cậy: trung bình, chặn trên bởi chất lượng dữ liệu demo)
1. **Khung M1-M15 chết sau chi phí** với mọi cặp (trung vị): biên độ trung bình của nến M15 chỉ ~7x spread, M5 ~4x, M1 ~1,6x. Muốn bù chi phí cần Sharpe gộp (trước phí) hàng chục đơn vị — vô lý. Không nghiên cứu thêm scalping/ intraday cực ngắn.
2. **H1 chết ở hầu hết cặp**: chi phí = ~14% biên độ nến ở majors (kịch bản stress; FX toàn nhóm 42%); Sharpe gộp cần ~0,8-1,5 nếu giữ 10 nến/lệnh. Chỉ 3/126 mã ở mức "biên", không mã nào "sống được".
3. **H4 biên**: Sharpe gộp cần ~0,2 (cơ sở) đến ~0,4 (stress) cho trung vị; chỉ chỉ số Mỹ (US500/US30/USTEC) sống được (cần <=0,1).
4. **D1 và W1 sống được** ở các mã thanh khoản (FX majors, vàng, chỉ số chính): cần Sharpe gộp chỉ ~0,01-0,05 để hoà vốn chi phí (giữ ~10 nến). Phần lớn chi phí là ĐẦU VÀO chấp nhận được; vấn đề thật là CÓ EDGE GỘP hay không (nghiên cứu R1/R10), không phải spread.
5. **Cặp nên tránh** (chi phí/biên độ cao dù khung lớn): exotic (TRY, ZAR, RUB/RUR, HUF, CZK, MXN, PLN, THB...) — D1 cần Sharpe gộp 1-5. Cặp rẻ nhất: USDJPY, EURUSD, AUDSGD, GBPUSD, GBPJPY, EURJPY, USDCAD; chỉ số: US500, US30, USTEC, DE40, JPN225; vàng XAUUSD.
6. **Swap/carry trên demo KHÔNG đáng tin** (xem mục 6): swap EURUSD long -0,7 điểm là giá trị hệ thống chứ không phản ánh chênh lệch lãi suất thật. Không dùng làm bằng chứng carry; muốn kiểm carry phải dùng lãi suất chính sách (dữ liệu công khai) hoặc swap của broker live.
7. **Mô hình chi phí đề nghị cho backtest (R10)**: spread = trung vị ở bảng, stress = p90, +1 pip FX/ +0,3 điểm% vàng-chỉ số cho slippage tin tức/ rollover, commission 0 (demo) nhưng thử nhạy cảm thêm 0,7 pip/lot khứ hồi (loại ECN); nhân đôi chi phí còn lại không phá kết luận ở D1/W1 (xem phép tính tuyến tính mục 4).

## 2. Dữ liệu và phương pháp
- Spread: cột `spread` (điểm) của nến M1 native, cửa sổ tin cậy **2024-09-01..2025-08-31** (126 mã còn lại sau loại EURMXN do D1 lỗi, ann_vol=5,3). Bỏ nến spread=0 (không có tick). Mô tả mức: trung vị, p90 (stress), tỷ lệ spread=0, tỷ lệ phút bùng spread (>3x trung vị của giờ đó).
- Biên độ nến (high-low trung bình) theo khung M1/M5/M15/H1/H4/D1/W1 chỉ lấy đoạn **train 2023-10..2025-07-25** (không chạm val/test). Chi phí khứ hồi = 1 spread (mua ở ask, bán ở bid).
- Chi phí/biên độ `c = spread / biên độ nến`. Với lệnh hai đầu 1R=biên độ trung bình thì tỉ lệ thắng hoà vốn = (1+c)/2.
- "Sharpe gộp cần để hoà vốn chi phí" = (chi phí khứ hồi % x số lệnh/năm) / biến động năm D1; giả định **giữ 10 nến/lệnh** (số lệnh/năm = số nến/năm / 10). Là thước đo thứ tự, không phải dự báo lợi nhuận. Phân loại: `song_duoc` <=0,10; `bien` 0,10-0,30; `chet` >0,30 (kịch bản stress p90).
- Swap: `symbol_info` của terminal demo (`mtlab-mt5`, chỉ đọc; 12 296 mã). Quy ra %/năm = swap(điểm) x point x 365 / giá.

## 3. Spread theo cặp (trung vị, cửa sổ tin cậy)
Bảng đầy đủ 126 mã: `R7_spread_theo_ma.csv`. Trích (điểm theo point của mã; bp = % của giá x 100):

| Mã | trung vị (pip) | p90 (điểm) | bp | ghi chú |
|---|---|---|---|---|
| USDJPY | 0,5 | 19 | 0,34 | 22% phút bùng |
| EURUSD | 0,4 | 12 | 0,36 | rất ổn định |
| GBPUSD | 0,7 | 20 | 0,54 | |
| AUDUSD | 0,9 | | 1,39 | |
| USDCHF | 1,3 | | 1,52 | |
| EURJPY / GBPJPY | 2,0 / 2,2 | | 1,2 / 1,1 | |
| XAUUSD | 15 điểm | 33 | 0,51 | |
| US500 | 50 điểm | 50 | 0,85 | spread cố định trên demo |
| US30 / DE40 | 120 / 60 | | 0,28 | |
| USDTRY | 103 pip | | rất cao | exotic |

Quan sát quan trọng về **chất lượng dữ liệu**: spread demo đổi chế độ theo thời gian. EURUSD H1: trung vị 3 điểm (2024-09..2025-03), **8 điểm (2025-04..2025-08)**, 2 điểm (2025-09..11), rồi **=0 ở 80-100% nến từ 2026-01** và =0 hoàn toàn từ 2026-07 (M1 spread 98% =0). Tức là spread lịch sử demo không phải số đo liên tục; chỉ cửa sổ 2024-09..2025-08 dùng được, và ngay trong đó có thay đổi chế độ x2-3 (nên dùng p90 làm kịch bản stress).

## 4. Theo khung (trung vị theo nhóm; chi tiết `R7_tong_hop_khung.csv`, `R7_chi_phi_theo_khung_ma.csv`, `R7_majors_theo_khung.csv`)
FX majors (10 cặp):

| Khung | biên độ/spread | chi phí/biên độ (stress) | tỉ lệ thắng hoà vốn 1R | Sharpe gộp cần (cơ sở / stress) |
|---|---|---|---|---|
| M1 | 1,6x | 131% | >100% | 48 / 92 |
| M5 | 3,9x | 53% | 77% | 9,5 / 18 |
| M15 | 7,0x | 30% | 65% | 3,2 / 6,1 |
| H1 | 14x | 14% | 57% | 0,8 / 1,5 |
| H4 | 30x | 6,8% | 53% | 0,20 / 0,38 |
| D1 | 76x | 2,6% | 51,3% | 0,03 / 0,06 |
| W1 | 172x | 1,2% | 50,6% | 0,007 / 0,013 |

Phân loại 126 mã theo khung (stress): M1/M5/M15: 126 chết; H1: 3 biên, 123 chết; H4: 4 sống (US500, US30, US30M, USTEC), 16 biên, 106 chết; D1: 33 sống, 50 biên, 43 chết; W1: 98 sống, 20 biên, 8 chết (`R7_phan_loai_khung.csv`). Sharpe gộp cần D1 cho từng cặp (cơ sở/stress): USDJPY 0,008/0,032; EURUSD 0,013/0,038; GBPUSD 0,019/0,054; XAUUSD 0,008/0,018; US500 0,013/0,013.
Tính tuyến tính: nhân chi phí lên 2-3x (slippage, commission, tin tức) làm Sharpe cần ở D1 majors lên ~0,03-0,15 — vẫn thấp so với trần Sharpe thực tế của trend đa tài sản (~0,5, theo nghiên cứu trước), nhưng ở H1 lên 2-5 (không khả thi).
Lưu ý "10 nến/lệnh" là giả định; nếu chiến lược lật vị thế mỗi 1-2 nến (mean-reversion nhanh) chi phí tăng 5-10x và loại thêm cả H4.

## 5. Theo giờ, ngày, tin tức (`R7_spread_theo_gio_utc.csv`)
- Giờ UTC (spread so với trung vị cặp): FX trung vị toàn nhóm **21h = 3,4x, 22h = 2,4x, 23h = 1,3x**, còn lại ~1,0x; EURUSD 21h = 5,25x, 22h = 3,0x; USDJPY 21h = 7,2x, 22h = 3,8x. Tức **rollover (khoảng 21-23 UTC) nở spread 2-7x**: tránh vào/ra lệnh ở khung giờ này; chiến lược D1 (đóng nến cùng rollover) nên vào lệnh ngay sau khi spread về bình thường (>= 00:00 UTC). Vàng nở ít (1,1-1,2x); chỉ số gần như phẳng (US500 giảm xuống 0,6x lúc 15-19 UTC; spread gần cố định trên demo).
- Thứ trong tuần: phẳng (1,0 trung vị).
- Tin tức (NFP, thứ Sáu đầu tháng 12:25-13:45 UTC): tỉ số spread NFP/thứ Sáu thường = **1,0 trung vị (0,5-1,4)** => demo KHÔNG nở spread khi tin; ngược với thực tế live (EURUSD live thường 3-10x vài giây quanh NFP). Tỷ lệ phút bùng >3x giờ-trung-vị ~1,2% trung vị, cao ở USDJPY (22%), USDCAD (40%), USDSGD (38%) nhưng chủ yếu là rollover.
- Kết luận thực thi: backtest phải cộng slippage/tin tức thủ công (mô hình bảo thủ), lọc lệnh +-15 phút quanh tin 3 sao (lịch kinh tế đã có ở INFO_SIGNALS_STUDY) và vào/ra tránh 21-23 UTC.

## 6. Swap / carry proxy (`R7_swap_carry.csv`)
- 100 mã có swap bật (mode điểm/ margin ccy). Trung vị swap hai chiều **âm** (-0,5%/năm), trung bình -4,7%/năm; chỉ 41/100 mã có ít nhất một chiều dương; tổng long+short luôn âm (markup của broker).
- Các giá trị sai lệch thực tế: EURUSD long -0,23%/năm, short -0,33%/năm (chênh lãi suất EUR-USD thật ~1-2%); USDJPY gần 0 (thực tế ~+4%/năm cho long USDJPY); CHFHUF swap hàng chục nghìn điểm (đơn vị lỗi). Thang tương đối đúng chiều với các cặp exotic (ZARJPY long +36%/năm, TRYJPY long +13%/năm, USDMXN long +8%/năm) nhưng đi kèm spread 133-506 bp và vol cao: `carry/vol` 1,0-1,3 chỉ là "proxy lý thuyết", chưa tính rủi ro sụp giá (tail crash).
- Với majors, lợi tức swap tốt nhất ≈ 0 (AUDUSD long +3,6%/năm, NZDUSD long +1,7%/năm, AUDCAD +2,6%) — hoà vốn spread sau 1-4 ngày; nhưng số liệu demo đáng ngờ.
- Kết luận: carry chưa kiểm định được bằng swap demo; đề xuất R10 dùng lãi suất chính sách công khai (FRED/BIS, 0 đồng) để dựng carry proxy, và chỉ đối chiếu swap broker live trước khi nạp vốn thật.

## 7. Giới hạn (nói thẳng)
1. **Demo ≠ live**: spread demo mịn/ cố định (US500 p90=trung vị=50), không nở theo tin, thời gian gần đây =0, hai chế độ x2-3 trong cửa sổ. Spread live có thể lớn hơn 1,5-3x ở majors, nhiều hơn ở exotic, và nở mạnh khi tin; không có dữ liệu slippage, từ chối lệnh (requote), hoặc độ sâu sổ lệnh.
2. Không có dữ liệu commission (demo = 0; live ECN thường 0,5-0,7 pip khứ hồi/lot), không có dữ liệu tick nên không đo slippage.
3. Spread cột nến M1 là snapshot cuối phút (không phải trung bình); H1 spread khác M1 (thấp hơn) — dùng M1.
4. Giả định 10 nến/lệnh và biên độ = high-low là thô; chi phí thật của chiến lược cụ thể phải tính từ số lệnh thật trong R10.
5. EURMXN bị loại (D1 lỗi giá). Phép loại này không ảnh hưởng kết luận khác.
6. Swap demo không đáng tin (mục 6).

## 8. Khuyến nghị cho chương trình
- Khung ưu tiên nghiên cứu/ paper: **D1 và W1** (rồi H4 chỉ với chỉ số Mỹ, vàng là biên); loại M1-M15; H1 chỉ như bộ lọc/ thời điểm vào.
- Cặp ưu tiên: EURUSD, USDJPY, GBPUSD, USDCAD, AUDUSD, EURJPY, GBPJPY, XAUUSD, XAGUSD, US500/US30/USTEC/DE40/JPN225; loại exotic khỏi danh mục tích cực.
- Mô hình chi phí R10: spread trung vị + p90 stress, +slippage 1 pip (FX) hoặc 0,3 bp đối với chỉ số/ vàng khi vào lệnh trong rollover/ tin, nhạy cảm commission 0-0,7 pip; báo cáo kết quả ở cả hai mức.
- Tái lập: `python3 data/research/program/R7/r7_analyze.py && python3 data/research/program/R7/r7_tables.py` (cần `specs_raw.json` xuất bằng `sym_specs.py` trong `mtlab-mt5`).
