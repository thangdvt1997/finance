# R4 — Phần mềm & hạ tầng OSS (0 đồng) cho nghiên cứu/backtest/thực thi

Ngày: 2026-10-15. Mã + kết quả chạy thử: `data/research/program/R4/` (venv riêng, 1,5 GB; thư mục `data/` bị .gitignore nên mã không vào git). READ-ONLY/PAPER, không đặt lệnh.

## 0. Kết luận thẳng
1. **Không cần viết lại engine nghiên cứu cho nhiều tài sản**: `vectorbt` (quét tham số/ danh mục) và `backtesting.py` (kiểm chứng 1 tài sản, có UI) cho kết quả khớp engine tự viết tới sai khác < 0,01% lợi suất khi cùng giả định (xem §3). Dùng chúng như **bộ kiểm chéo (cross-check)** cho engine của ta, không thay thế engine chi phí MT5 (spread theo nến, slippage, commission riêng) — các thư viện này chỉ hỗ trợ phí tỷ lệ/cố định đơn giản.
2. **Tối ưu danh mục: tích hợp `skfolio` (chính) + `Riskfolio-Lib` (đối chiếu)**; trọng số min-variance / ERC / HRP khớp nhau tới 3 chữ số thập phân giữa 3 thư viện (§4). Không tự viết.
3. **Thực thi/OMS: chưa tích hợp gì lúc này** (đang READ-ONLY). Khi tới giai đoạn paper/live: ứng viên số 1 là **NautilusTrader** (event-driven, cùng mã backtest và live) hoặc **LEAN**; Freqtrade/hummingbot là bot crypto, không hợp FX/CFD MT5. Cầu nối MT5 phải tự viết mỏng (EA đã có trong `mt-agent/lab-feed`) — **không** thư viện nào ở đây có adapter MT5 hạng nhất (độ tin cậy trung bình, dựa trên mô tả tính năng đã biết; chưa tự kiểm từng repo).
4. **Chú ý giấy phép**: `vectorbt` = Apache-2.0 + Commons Clause (cấm bán dịch vụ có giá trị chính là vectorbt) — dùng nội bộ nghiên cứu thì ổn, **không đưa vào sản phẩm phân phối/bán**; `backtesting.py` = **AGPL-3.0** (chạy nội bộ ổn; nếu phơi qua dịch vụ mạng cho người dùng ngoài phải mở mã) — chỉ dùng ở lớp nghiên cứu, không nhúng vào service UI; Freqtrade GPL-3.0.

## 1. Bảng so sánh
Bảo trì = ngày phát hành gần nhất trên PyPI / lần push GitHub (tra trực tiếp 2026-10-15). Độ tin cậy: số liệu giấy phép/ngày/sao là **cao** (API chính thức); cột phù hợp FX/CFD, tốc độ, nối MT5 là **đánh giá** (trung bình), trừ 3 cái có chạy thử (đánh dấu *).

| Công cụ | Giấy phép | Bảo trì (release / push; sao) | Phù hợp FX/CFD | Tốc độ | Nối MT5 | Vai trò đề xuất |
|---|---|---|---|---|---|---|
| vectorbt* (1.1.2; chạy thử 1.0.0) | Apache-2.0 + Commons Clause | 2026-10-09 / 10-14; 9,4k | Tốt cho nghiên cứu tín hiệu; phí chỉ %/cố định, không spread động | Rất nhanh khi vector hoá lưới tham số (numba) | Không (đưa dữ liệu vào bằng pandas) | **Tích hợp** làm công cụ quét tham số/ kiểm chéo |
| backtesting.py* (0.6.6) | AGPL-3.0 | 2026-07-22 / 08-05; 9,1k | 1 tài sản/lần; đơn giản, có biểu đồ tương tác | Nhanh với 1 chuỗi (0,19 s / 13,5k nến) | Không | Kiểm chéo 1 chiến lược; không nhúng vào dịch vụ |
| NautilusTrader (1.231.0, cần Py≥3.12) | LGPL-3.0 | 2026-08-02 / 10-15; 30k | Mạnh, event-driven, tick/ order book, đa tài sản | Rất nhanh (lõi Rust) nhưng dựng dữ liệu phức tạp | Không có adapter MT5 (cần tự viết) | Ứng viên **thực thi/paper** giai đoạn sau |
| QuantConnect LEAN | Apache-2.0 | 10-13; 22k | Có FX/CFD/futures; nặng (.NET, Docker) | Tốt | Không native MT5 | Dự phòng; chi phí vận hành cao với VPS dùng chung |
| bt (1.4.1) | MIT | 2026-10-10 / 10-13; 3k | Phân bổ danh mục/ tái cân bằng theo cây thuật toán; không mô hình spread | Trung bình | Không | Tuỳ chọn cho backtest danh mục dài hạn |
| zipline-reloaded (3.1.1) | Apache-2.0 | 2025-07-19 / 2026-10-14; 2k | Hướng cổ phiếu Mỹ (bundle), kém FX/CFD | Chậm hơn, nặng | Không | Không dùng (Alphalens thì có, xem dưới) |
| Qlib (pyqlib 0.9.7) | MIT | 2025-08-15 / 2026-10-14; 49k | Khung ML định lượng cổ phiếu (Alpha158...), không hướng FX | Tốt cho dữ liệu bảng | Không | Chỉ tham khảo cho nhánh ML (R3), chưa tích hợp |
| Freqtrade (2026.9) | GPL-3.0 | 2026-09-29 / 10-15; 55k | Crypto spot/perp qua ccxt | Tốt (hyperopt) | Không | Không dùng cho MT5; học UX/ FreqUI |
| hummingbot (20260922) | Apache-2.0 | 2026-10-07; 20k | Market-making/ arbitrage crypto | — | Không | Không phù hợp |
| vnpy | MIT | 2026-10-06; 46k | Đa thị trường (chủ yếu CTP/ Trung Quốc, có gateway crypto/IB) | Tốt | Không xác minh | Tham khảo kiến trúc OMS/gateway |
| backtrader | GPL-3.0 | **2024-08-19** (gần như ngừng) | Cũ, chậm | Chậm | Không | Tránh |
| Riskfolio-Lib* (7.4.0; chạy thử 7.0.1) | BSD-3 | 2026-10-04; 4,5k | Danh mục: min-var, ERC, HRP, CVaR, Black-Litterman... | Tốt (cvxpy) | n/a | **Tích hợp** (đối chiếu) |
| skfolio* (1.8.6) | BSD-3 | 2026-10-14; 2,5k | API chuẩn scikit-learn; CV danh mục (walk-forward, CPCV) | Tốt | n/a | **Tích hợp chính** |
| PyPortfolioOpt* (1.6.0) | MIT | 2026-02-26 / 07-07; 6k | Cổ điển (frontier, HRP) | Rất nhanh | n/a | Đối chiếu, nhẹ |
| alphalens-reloaded (0.4.6) | Apache-2.0 | 2025-06-02 / 2026-10-15; 0,7k | Phân tích hệ số (IC, phân vị) — hợp **xếp hạng chéo tài sản** (momentum/carry), kém cho tín hiệu 1 chuỗi | Tốt | n/a | Tuỳ chọn cho R1/R10 (cross-sectional) |
| tsfresh (0.21.2) | MIT | 2026-05-31; 9,5k | Trích đặc trưng chuỗi thời gian cho ML; dễ overfit nếu dùng bừa | Chậm khi nhiều đặc trưng | n/a | Chỉ cho nhánh ML, kèm walk-forward/ DSR |
| quantstats (0.0.86) | Apache-2.0 | 2026-09-27; 7,7k | Báo cáo hiệu suất (tearsheet) | — | n/a | Tuỳ chọn tạo báo cáo HTML |

(* = đã chạy thử trên VPS, mục 3-4.)

## 2. Chạy thử: thiết lập
- Dữ liệu: nến MT5 của ta (`data/research/patterns/bars/*_{D1,H1}.parquet`), 7 tài sản EURUSD, GBPUSD, USDJPY, XAUUSD, US500, BTCUSD, ETHUSD; giao nhau D1 = 615 ngày (2024-05-22 → 2026-10-13); H1 = 13.505 nến chung. Nến D1 FX/CFD mở lúc 21-22h UTC nên quy về ngày giao dịch (mở cửa + 12 h).
- Chiến lược: trend SMA(20)/SMA(100), vị thế +1/−1 toàn vốn, vào ra tại giá đóng nến có tín hiệu, phí 2 bps mỗi chiều đồng nhất (cố ý đơn giản để so sánh công cụ; **không** phải chi phí thật). Giữ số đơn vị cố định giữa các lần đổi vị thế.
- "Khung bt của ta" cho chiến lược trend là engine tham chiếu numba `ref_engine.py` (cùng logic engine vector hoá trong BACKTEST_STUDY); khung `pattern_research/backtest.py` là engine lệnh-theo-lệnh cho kịch bản Sell (SL/TP, spread MT5) nên không áp trực tiếp cho trend chạy liên tục.

## 3. Kết quả đối chiếu (D1, 7 tài sản)
Lợi suất tổng (sau phí 2 bps), số lệnh, sai khác đường vốn lớn nhất so với engine tham chiếu (đơn vị = phần vốn):

| Mã | ref | vectorbt | backtesting.py | max\|Δ\| vbt | max\|Δ\| bt.py |
|---|---|---|---|---|---|
| EURUSD | −1,276% | −1,276% | −1,275% | 0,00002 | 0,00042 |
| GBPUSD | −5,183% | −5,184% | −5,182% | 0,00003 | 0,00041 |
| USDJPY | −0,551% | −0,552% | −0,552% | 0,00002 | 0,00040 |
| XAUUSD | +68,24% | +68,24% | +68,10% | 0,00012 | 0,00202 |
| US500 | +6,64% | +6,63% | +6,59% | 0,00005 | 0,00052 |
| BTCUSD | −36,88% | −36,90% | −35,08% | 0,00018 | 0,02792 |
| ETHUSD | +10,14% | +10,14% | +10,15% | 0,00009 | 0,00096 |

Giải thích sai khác: (a) vectorbt khớp ref tới ~1e-4 (khác nhau do số học phí/làm tròn); số lệnh bằng nhau. (b) backtesting.py khác nhiều hơn vì **không cho kích thước bằng đúng 100% vốn** (phải dùng 0,9999) và với giá lớn (BTC ~100k so với vốn 1 triệu) **làm tròn xuống số đơn vị nguyên** — sai khác BTC 2,8% đường vốn; đếm lệnh ít hơn 1 vì lệnh còn mở cuối kỳ không tính. Kết luận: backtesting.py chỉ nên dùng để xác nhận logic, cần cấu hình vốn lớn/ giá nhỏ nếu muốn khớp số; không phải nguồn "sự thật" về lợi suất. Số liệu trend ở trên **chưa mang ý nghĩa đầu tư** (chỉ 2,4 năm, không kiểm định thống kê).

## 4. Tốc độ & độ dễ dùng
| Thử nghiệm | ref (numba) | vectorbt | backtesting.py |
|---|---|---|---|
| D1, 7 tài sản × 1 tham số (gồm JIT lần đầu) | 0,39 s | 8,15 s (hầu hết là biên dịch numba lần đầu) | 0,22 s (chạy tuần tự 7 lần) |
| H1 (13,5k nến), lưới 64 cặp (fast,slow) × 7 tài sản = 448 chạy | 0,56 s | 2,6–3,3 s (đã khởi động) | 0,19 s/chạy → ngoại suy ~84 s |
| Sai khác lợi suất vbt vs ref trên 448 chạy | | max 0,16 điểm %, trung bình 0,0075 điểm % | |

- vectorbt: ~25 dòng để chạy lưới; đường cong học dốc (multi-index cột, `from_orders`, `targetpercent`). **Ma sát cài đặt**: vectorbt 1.0.0 vỡ khi import với plotly 7 (phải ghim `plotly<6`, mâu thuẫn với skfolio đòi `plotly>=6` — vẫn chạy được nhưng nên tách venv). Python 3.10 của VPS đủ cho vectorbt 1.0.0; bản 1.1.2 yêu cầu ≥3.11.
- Engine numba tự viết nhanh nhất (0,56 s) vì chỉ làm đúng việc cần; ưu thế của vectorbt nằm ở API sẵn thống kê (Sharpe, DD, trade records) và danh mục nhiều cột, không ở tốc độ thô so với engine đã tối ưu.
- backtesting.py: dễ dùng nhất (class Strategy, 15 dòng), chậm khi quét lưới (tuần tự); có `bt.optimize` riêng nhưng chưa thử.

## 5. Tối ưu danh mục (D1, 70% train / 30% OOS, 7 tài sản, long-only)
Min-variance, ERC (risk parity), HRP: trọng số của **skfolio, Riskfolio-Lib và PyPortfolioOpt trùng nhau tới 3 chữ số** (vd min-var: EURUSD 0,387 / GBPUSD 0,237 / USDJPY 0,373, còn lại ≈ 0; ERC: 0,289/0,214/0,296/0,084/0,073/0,026/0,018). Thời gian: skfolio 1,5 s (3 mô hình), Riskfolio 1,6 s, PyPortfolioOpt 0,06 s. OOS (185 ngày, chỉ minh hoạ): min-var −2,2% (DD −2,8%), ERC −2,0%, HRP −1,9% so với 1/N −2,7% (DD −16%) — lợi ích thấy được duy nhất là **giảm DD/vol**, không tạo lợi suất (đúng kỳ vọng vì chỉ chia lại rủi ro; mẫu quá ngắn để kết luận). Dễ dùng: skfolio (API scikit-learn, có `cross_val_predict`/ walk-forward, CPCV) rõ ràng nhất; Riskfolio nhiều mô hình rủi ro (CVaR, CDaR) nhưng API dài dòng và kiểu trả về thay đổi giữa phiên bản; PyPortfolioOpt gọn nhất cho bài cổ điển.

## 6. Nên tích hợp hay tự viết?
| Việc | Quyết định | Lý do |
|---|---|---|
| Quét tham số/ danh mục nhiều tài sản (nghiên cứu) | Tích hợp vectorbt (nội bộ) + giữ engine numba làm chuẩn kiểm chéo | Khớp 1e-4; đã có kiểm thử nhân quả/ placebo ở engine của ta |
| Chi phí MT5 (spread theo nến, swap, slippage) | **Giữ tự viết** | Thư viện không mô hình hoá spread động; đây là nơi edge chết |
| PBO/DSR/bootstrap, walk-forward, test khoá | Giữ tự viết (đã có trong `backtest.py`); có thể đối chiếu skfolio CPCV | Quy trình trung thực của dự án |
| Tối ưu danh mục/ phân bổ rủi ro | **Tích hợp skfolio** (+ Riskfolio đối chiếu) | Khớp 3 thư viện; tiết kiệm công |
| Báo cáo hiệu suất | Tuỳ chọn quantstats | Chỉ để xem nhanh |
| Phân tích hệ số chéo tài sản | alphalens-reloaded khi làm R1/R10 xếp hạng chéo | Cần ≥ vài chục tài sản; hiện chỉ 7 |
| ML đặc trưng | tsfresh/ Qlib chỉ khi R3 chứng minh cần | Rủi ro overfit |
| Thực thi/ OMS (paper → live) | Hoãn; ứng viên NautilusTrader/ LEAN; cầu nối MT5 tự viết qua EA read-only/ paper | Chưa qua cổng pháp lý G1-G3; ngoài phạm vi hiện tại |

## 7. Hạn chế
- Mẫu D1 chỉ 615 ngày (FX/CFD MT5 từ 2024-05); đối chiếu công cụ là kiểm tra **tính đúng của phần mềm**, không phải chứng minh chiến lược có edge (R10 làm việc đó).
- Các nhận định về LEAN/Nautilus/vnpy/Qlib (nối MT5, độ phù hợp) dựa trên mô tả tính năng đã biết, chưa cài và chạy; chỉ vectorbt, backtesting.py, skfolio, Riskfolio-Lib, PyPortfolioOpt được chạy thật.
- vectorbt chạy bản 1.0.0 (pip chọn vì ràng buộc Python 3.10), không phải 1.1.2 mới nhất.

## 8. Tái lập
`cd data/research/program/R4 && ./venv/bin/python run_compare.py` (đối chiếu D1) · `speed_grid.py` (tốc độ H1) · `portfolio_opt.py` (danh mục). Kết quả: `compare_d1.csv`, `timing_*.json`, `portfolio_weights.csv`, `portfolio_oos.csv`. `common.py` (nạp dữ liệu, tín hiệu), `ref_engine.py` (engine tham chiếu numba).
