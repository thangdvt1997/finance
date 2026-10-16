# Phương án giao dịch — tổng hợp từ 3 nghiên cứu (2026-10-11)

Nguồn: `docs/research/METHODS_SURVEY.md` (văn liệu), `docs/research/BACKTEST_STUDY.md` (backtest FX/vàng 2002-2026), `docs/research/INFO_SIGNALS_STUDY.md` (tin, COT, tín hiệu chuyên gia). Đây KHÔNG phải khuyến nghị đầu tư; mọi phương án chỉ bắt đầu sau cổng pháp lý G1-G3 (PLAN.md) và phải qua paper trading.

## Kết luận trung thực
1. **Không có "phương pháp chắc chắn có lãi".** Retail forex/CFD: 68-89% tài khoản lỗ (ESMA/ASIC/FCA). Alpha giảm ~58% sau khi công bố (McLean-Pontiff).
2. **Backtest của chính ta xác nhận điều đó:** trend/momentum/carry/mean-reversion kinh điển trên 7 cặp FX (2002-2026, chi phí + swap bảo thủ): Sharpe -0,13..+0,21, mọi khoảng tin cậy 95% chứa 0, deflated Sharpe tối đa 0,49 (ngưỡng 0,95). Trend dương 2002-2011, âm từ 2012. Thêm vàng/bạc: Sharpe 0,33 nhưng chủ yếu do vàng tăng dài hạn (mua-và-giữ vàng 0,74 còn tốt hơn). Chi phí+swap ăn 0,12-0,24 Sharpe. Kỳ vọng hợp lý: Sharpe ròng 0-0,3, CAGR 0-3% ở vol 10%, drawdown 30-60%.
3. **Thông tin:** giá trị nhất là lịch kinh tế làm *bộ lọc rủi ro* (biên độ 5 phút đầu sau NFP ~7x, FOMC ~10x ngày thường; về bình thường sau ~22-25 phút). COT: 52 kiểm định, không cái nào có ý nghĩa sau hiệu chỉnh → chỉ làm bối cảnh. Tín hiệu chuyên gia/copy-trading: không có bằng chứng độc lập, thiên lệch sống sót, rủi ro martingale. Sentiment tin: bằng chứng chỉ có trên cổ phiếu Mỹ, alpha giảm dần.
4. **Giới hạn nghiên cứu:** dữ liệu FX là giá tham chiếu ECB (không giao dịch được, không bid/ask); chưa kiểm chéo bằng dữ liệu tick; mẫu sự kiện tin chỉ 10.

## Xếp hạng phương án (thực tế, khiêm tốn)
| # | Phương án | Kỳ vọng | Rủi ro/Điều kiện | Tích hợp vào hệ thống |
|---|---|---|---|---|
| A | **Theo dõi + cảnh báo + bộ lọc rủi ro tin, người dùng tự quyết** | Không tạo lợi nhuận tự động; giảm sai lầm (tránh vào lệnh quanh tin, biết bối cảnh) | Thấp; không cần cổng pháp lý cho phần dữ liệu | ĐÃ CÓ nền; thêm: cảnh báo "cửa sổ rủi ro tin" T-15..T+30 (T+45 FOMC/vàng), dữ liệu `actual/forecast` |
| B | **Trend chậm đa tài sản + vol targeting** (vàng, chỉ số, trái phiếu, hàng hóa, FX), rebalance tuần/tháng | Sharpe 0,3-0,6 theo văn liệu CTA; thua năm 2023, nửa đầu 2025; DD 15-30% | Cần ≥20 tài sản đa dạng (FX riêng lẻ không đủ, theo backtest ta); chi phí thấp (ETF/futures) | Service `research` + `paper-trader` (mô phỏng, không tiền thật) |
| C | **Cổ phiếu VN: momentum/value, chỉ long, xoay vòng tháng/quý** | Chưa có bằng chứng độc lập mạnh; thanh khoản và biên độ ±7% hạn chế | T+2 (chưa thấy T+1), không bán khống, API tự động còn vướng chỉ đạo UBCKNN 2023 | Dữ liệu vnstock + backtest + cảnh báo; thực thi tay |
| D | **Bán tự động có duyệt tay** (hệ thống đề xuất, người duyệt từng lệnh) | Giảm lỗi vận hành, không tăng edge | Chỉ sau G1-G3; kill-switch, giới hạn lỗ ngày | Service `strategy` + `execution` (phase sau) |
| E | Phòng thủ: bộ lọc chế độ biến động + vol targeting cho mọi phương án | Giảm drawdown, không tăng lợi nhuận kỳ vọng | — | Dùng analytics sẵn có |
| F | Trend trên VN30 futures | Chưa có bằng chứng độc lập | Chỉ paper | Sau |
Không khuyến nghị: carry FX (MaxDD -56%, lỗ 2008/2015/2020), mean-reversion ngắn hạn (mong manh khi chi phí gấp đôi), giao dịch theo tin, market making, copy-trade theo chuyên gia công khai, bot martingale/grid.

## Đề xuất lộ trình (cần bạn chọn)
1. **Ngay (không cần cổng pháp lý):** hoàn thiện A: bộ lọc rủi ro tin (service/endpoint + banner trên website), bổ sung `actual/forecast` (tìm nguồn hợp lệ), cảnh báo chế độ biến động; Phân tích kỹ thuật đã có.
2. **Nghiên cứu mở rộng trên VPS:** dựng dataset đa tài sản (ETF/futures proxy, chỉ số, trái phiếu, hàng hóa, FX) và chạy walk-forward cho B/E với deflated Sharpe; chỉ giữ cái qua kiểm định.
3. **Paper trading (mô phỏng):** service `paper-trader` ghi lệnh giả theo phương án được chọn vào journal, ít nhất 8-12 tuần, so với backtest; hiển thị trên website.
4. **Sau cổng G1-G3:** bán tự động có duyệt tay (D) với kill-switch/giới hạn lỗ, vốn nhỏ.
Bạn gửi phương thức giao dịch riêng của bạn thì ta đưa vào cùng quy trình kiểm chứng (backtest trung thực → paper → duyệt).
