# GLOSSARY — thuật ngữ tài chính và hệ thống

Dành cho người không chuyên. Thuật ngữ trong giao diện cũng có chú giải khi rê chuột (hoặc `g` rồi `h` = Trợ giúp). Sắp theo nhóm; tìm bằng Ctrl+F.

## A. Giao dịch và thị trường

| Thuật ngữ | Nghĩa |
|---|---|
| **MT4 / MT5** | MetaTrader 4/5 — phần mềm giao dịch của sàn môi giới (broker). Hệ thống này chỉ **quan sát** tài khoản MT, không đặt lệnh. |
| **EA (Expert Advisor)** | Chương trình chạy trong MT. EA của hệ thống chỉ đọc: gửi số dư, vị thế, giá… ra ngoài; không có chức năng giao dịch. |
| **Investor password** | Mật khẩu chỉ-xem của tài khoản MT. **Hệ thống không bao giờ yêu cầu** nó (hay mật khẩu giao dịch). |
| **Bid / Ask / Spread** | Giá bán ra (bid) / giá mua vào (ask) / chênh lệch giữa hai giá — chi phí vào lệnh. |
| **Pip / điểm** | Đơn vị nhỏ nhất thường dùng để đo giá ngoại hối (EURUSD: 0,0001). |
| **Nến (candle) / OHLC** | Một ô giá trong một khoảng thời gian: Mở (Open), Cao (High), Thấp (Low), Đóng (Close). Nến xanh = đóng cao hơn mở. |
| **Khung thời gian (M1…D1)** | M1 = 1 phút, M5, M15, H1 = 1 giờ, H4, D1 = 1 ngày. |
| **Tick volume** | Số lần giá nhảy trong nến (ngoại hối không có khối lượng thật tập trung). |
| **Lot** | Đơn vị khối lượng giao dịch (1 lot forex chuẩn = 100.000 đơn vị tiền cơ sở). Cổ phiếu VN: lô 100 cổ phiếu. |
| **Balance / Equity** | Số dư đã chốt / số dư cộng lãi-lỗ đang mở (floating P/L). Equity là con số quan trọng khi đo rủi ro. |
| **Margin / Free margin** | Ký quỹ đang bị giữ cho các vị thế / phần còn lại để mở thêm. |
| **Margin level** | Equity ÷ Margin (%). Càng thấp càng gần bị sàn đóng lệnh. |
| **Stop-out** | Mức margin level mà sàn tự đóng lệnh (khác nhau theo sàn). |
| **Drawdown (DD) / MaxDD** | Mức sụt giảm từ đỉnh gần nhất / sụt giảm lớn nhất trong lịch sử. MaxDD −20% = từng mất 20% so với đỉnh. |
| **Floating P/L** | Lãi/lỗ của lệnh chưa đóng. |
| **Stop loss / Take profit** | Mức giá tự đóng lệnh khi lỗ / khi lời. |
| **Vị thế (position) / Lệnh chờ (pending order)** | Lệnh đang mở / lệnh đã đặt nhưng chưa khớp. |
| **Deal** | Một giao dịch đã khớp/đóng trong lịch sử (nguồn của Nhật ký). |
| **Magic number** | Số định danh MT gắn cho lệnh của một EA; nhật ký dùng để tách đóng góp từng EA. |
| **Hedging / Netting** | MT4: nhiều lệnh ngược chiều cùng mã song song (hedging). MT5 tuỳ tài khoản: gộp thành một vị thế (netting). |
| **Slippage (trượt giá)** | Chênh giữa giá mong muốn và giá khớp thật. |
| **Swap** | Phí/lãi qua đêm khi giữ lệnh. |
| **Long / Short** | Mua kỳ vọng tăng / bán khống kỳ vọng giảm (cổ phiếu VN không bán khống). |
| **ETF** | Quỹ hoán đổi danh mục, giao dịch như cổ phiếu (SPY, E1VFVN30…). |
| **HOSE / HNX / UPCoM** | Ba sàn chứng khoán Việt Nam. Biên độ giá ngày: ±7% / ±10% / ±15%. Trần/sàn = giá tối đa/tối thiểu trong ngày. |
| **VN-Index / VN30** | Chỉ số thị trường chung / rổ 30 cổ phiếu lớn. |
| **T+2** | Cổ phiếu/tiền về tài khoản sau 2 ngày làm việc kể từ khi khớp. Hệ thống giữ cấu hình `settlement_days=2`; **chưa** thấy văn bản chính thức chuyển sang T+1 (cần kiểm tra lại khi có thông báo). Mô phỏng hiện **chưa** áp T+2 (ghi chú trong VN_MARKET.md). |
| **ATO / ATC** | Phiên mở cửa / đóng cửa xác định giá. |
| **Khối ngoại / Tự doanh** | Nhà đầu tư nước ngoài / bộ phận tự đầu tư của công ty chứng khoán (nguồn miễn phí không có tự doanh). |
| **Giá điều chỉnh** | Giá đã trừ ảnh hưởng cổ tức/thưởng/chia tách để so sánh lịch sử. Giá "thô" thì không, nên có cú nhảy giả. |
| **COT (Commitments of Traders)** | Báo cáo vị thế các nhóm đầu cơ/bảo hiểm rủi ro của CFTC (Mỹ), công bố hằng tuần (thứ Sáu, số liệu chốt thứ Ba). |
| **13F** | Báo cáo danh mục quý của quỹ lớn ở Mỹ. |
| **Lịch kinh tế / Forecast / Previous / Actual** | Lịch công bố số liệu vĩ mô: dự báo / kỳ trước / thực tế. |
| **CPI / NFP / FOMC** | Lạm phát Mỹ / bảng lương phi nông nghiệp Mỹ / họp lãi suất Fed — các sự kiện tác động CAO. |
| **Cửa sổ rủi ro tin (risk window)** | Khoảng thời gian quanh sự kiện tác động cao (mặc định 15 phút trước – 30 phút sau) khi giá có thể giật mạnh. |
| **Phiên Tokyo / London / New York** | Ba phiên giao dịch chính trong ngày (tính theo giờ UTC cố định trong hệ thống). |

## B. Chỉ báo và phân tích

| Thuật ngữ | Nghĩa |
|---|---|
| **SMA / EMA** | Trung bình động đơn giản / mũ. EMA20/50/200 là các đường xu hướng thường dùng. |
| **RSI** | Chỉ số sức mạnh tương đối 0–100; ≥70 "quá mua", ≤30 "quá bán" (mô tả, không phải tín hiệu). |
| **MACD** | Chỉ báo động lượng từ hiệu hai EMA. |
| **ATR** | Biên độ biến động trung bình; ATR% = ATR chia giá. |
| **Bollinger Bands / Squeeze** | Dải quanh trung bình động; "squeeze" = dải hẹp lại (biến động thấp). |
| **ADX / +DI / −DI** | Độ mạnh xu hướng (ADX < 20: đi ngang) và hướng. |
| **Stochastic** | Chỉ báo động lượng so vị trí giá trong biên độ gần đây. |
| **Pivot** | Mức hỗ trợ/kháng cự tính từ nến hôm qua. |
| **Fibonacci** | Công cụ vẽ các mức hồi 23,6/38,2/50/61,8%… |
| **Heat (0–100)** | Mức "đáng chú ý" của một mã/khung (xu hướng mạnh, RSI cực đoan, biến động cao) — **không có hướng**. |
| **Bias (−100…+100)** | Độ nghiêng trung bình 5 phiếu (giá trên EMA200, EMA20>EMA50, MACD, RSI>50, +DI>−DI). |
| **Tương quan** | Từ −1 đến +1: cùng đi / ngược nhau / ít liên quan. Không đảm bảo cho tương lai. |
| **Sức mạnh tiền tệ** | Điểm của 8 tiền tệ so với rổ, tính từ 7 cặp quy USD; thiếu cặp thì chỉ tính tập tiền tệ đủ dữ liệu. |
| **Cảm xúc tin (sentiment)** | Điểm −1…+1 do thuật toán chấm từ tiêu đề; thô, hay sai với mỉa mai. |
| **Heatmap / bản đồ nhiệt** | Lưới ô tô màu theo mức tăng/giảm; kích thước theo giá trị giao dịch. |
| **Khẩu vị rủi ro (Pulse)** | Chỉ số 0–100 tổng hợp độ rộng, tâm lý tin, độ bình lặng, xu hướng S&P. |
| **Replay** | Phát lại nến quá khứ từng bước trên biểu đồ để luyện/kiểm tra. |

## C. Rủi ro

| Thuật ngữ | Nghĩa |
|---|---|
| **VaR 95% 1 ngày** | Mức lỗ mà trong 95% số ngày không bị vượt (ước tính lịch sử). Đánh giá thấp rủi ro gap cuối tuần. |
| **ES (Expected Shortfall)** | Lỗ trung bình trong những ngày lỗ vượt VaR. |
| **Stress test** | Giả sử lặp lại biến cố lớn (2008, CHF 2015, Brexit, COVID, 2022, yên 2024…). |
| **Luật tuân thủ (đội TK)** | Giới hạn do master gán: lỗ ngày, drawdown tối đa, margin level, ngày tốt nhất, số lệnh/ngày. Xanh/vàng/đỏ theo mức sử dụng hạn mức. |
| **Kill-switch** | Công tắc dừng khẩn: trong mô phỏng, lỗ ngày/tuần vượt ngưỡng thì tạm dừng; drawdown vượt ngưỡng thì khoá cứng. |
| **Sự cố (incident)** | Điều kiện bất thường được mở tự động (EA offline, vi phạm luật…); có trạng thái open/ack/snoozed/resolved. |

## D. Thống kê và đánh giá chiến lược

| Thuật ngữ | Nghĩa |
|---|---|
| **Backtest** | Chạy một phương pháp trên dữ liệu quá khứ. Tốt trên quá khứ ≠ tốt trong tương lai (quá khớp, thiên lệch sống sót). |
| **Paper trading (mô phỏng)** | Chạy phương pháp bằng **tiền ảo** trên dữ liệu thật theo thời gian thực. |
| **Benchmark / đối chứng** | Mốc so sánh (mua-giữ 60/40…). Thua benchmark thì chưa đáng tin. |
| **CAGR** | Lợi suất năm hoá. |
| **Vol (volatility)** | Độ biến động lợi suất (độ lệch chuẩn năm hoá). |
| **Sharpe** | Lợi suất trên mỗi đơn vị rủi ro (≈0,5 đã khiêm tốn; cần hàng năm dữ liệu để tin). |
| **Sortino / Calmar** | Như Sharpe nhưng chỉ tính rủi ro giảm / chia cho MaxDD. |
| **Profit factor** | Tổng lãi ÷ tổng lỗ của các lệnh. |
| **Expectancy** | Lãi/lỗ kỳ vọng mỗi lệnh. |
| **Win rate / hit-rate** | Tỷ lệ lệnh/quan điểm đúng hướng. |
| **MAE / MFE** | Mức bất lợi/thuận lợi lớn nhất của một lệnh trong lúc mở (ước tính từ nến). |
| **Khoảng tin cậy 95% (CI)** | Dải trong đó giá trị thật nhiều khả năng nằm; càng rộng càng ít chắc chắn. |
| **Wilson / bootstrap / hoán vị** | Ba cách tính khoảng tin cậy và kiểm định mà track-record dùng (không cần giả định phân phối). |
| **p-value / q-value (BH-FDR)** | Xác suất kết quả này xảy ra do ngẫu nhiên / đã hiệu chỉnh khi thử nhiều giả thuyết cùng lúc. |
| **Deflated Sharpe** | Sharpe đã trừ tác động của việc thử nhiều cấu hình (ngưỡng đặt trước 0,95). |
| **Walk-forward / out-of-sample** | Chọn tham số ở giai đoạn trước, kiểm ở giai đoạn sau chưa từng thấy. |
| **Look-ahead (nhìn trước)** | Lỗi dùng thông tin chưa có tại thời điểm quyết định. Hệ thống chống bằng quy tắc "vào ở nến sau thời điểm quan sát". |
| **Thiên lệch sống sót** | Chỉ nhìn các mã/chuyên gia còn tồn tại nên kết quả đẹp giả. |
| **"Chưa đủ mẫu" (insufficient)** | n < 30 quan điểm độc lập: không xếp hạng, không kết luận. Cố ý. |
| **Strategy card** | Tờ mô tả chiến lược: giả thuyết, tham số khoá, kết quả backtest kể cả mục không đạt. |
| **Hash-chain** | Mỗi bản ghi nối với bản trước bằng hàm băm; sửa/xoá/chèn làm chuỗi đứt và báo đỏ. |
| **TCA** | Phân tích chi phí giao dịch: chi phí thực so với giả định. |
| **CUSUM** | Kỹ thuật phát hiện suy giảm hiệu suất dần. |

## E. Hệ thống và kỹ thuật

| Thuật ngữ | Nghĩa |
|---|---|
| **Master / Client** | Master = người vận hành (thấy mọi thứ). Client = chủ một tài khoản MT (chỉ thấy tài khoản mình). |
| **Account ID** | `<nền tảng>:<số tài khoản>`, ví dụ `mt5:12345678`. |
| **Passcode / Mã ghép cặp** | Mật khẩu cổng ban đầu do master cấp / mã dùng một lần (hết hạn 7 ngày) để EA ghép với tài khoản. **Không phải** mật khẩu MT. |
| **Ghép cặp (pairing)** | Bước nối EA đã cài với tài khoản trên hệ thống bằng mã ghép cặp. |
| **HMAC** | Chữ ký số đối xứng EA đính kèm mỗi gói dữ liệu để bridge biết gói không bị giả/sửa. |
| **TOTP / 2FA** | Mã 6 số đổi mỗi 30 giây từ ứng dụng (Google Authenticator…). |
| **Tunnel (đường hầm Cloudflare)** | Cách đưa website ra Internet mà không mở cổng; địa chỉ `*.trycloudflare.com` **đổi mỗi lần tunnel khởi động lại**. |
| **PWA** | Ứng dụng web có thể "thêm vào màn hình chính" trên điện thoại. |
| **Bus / Redis Streams** | Hàng đợi sự kiện giữa các service. |
| **Consumer group** | Nhóm đọc stream để mỗi sự kiện chỉ được xử lý một lần/service. |
| **TimescaleDB** | PostgreSQL mở rộng cho dữ liệu chuỗi thời gian (giá, nến). |
| **Idempotent / UPSERT** | Ghi lặp cùng dữ liệu không tạo bản sao. |
| **Gateway** | Cổng API duy nhất giữa giao diện và dữ liệu, nơi áp phân quyền. |
| **auth_request** | Cơ chế nginx hỏi service auth "request này của ai" trước khi cho qua. |
| **IDOR** | Lỗi cho phép người này đọc dữ liệu người khác bằng cách đổi ID. Có test chặn. |
| **WebSocket / SSE** | Hai cách server đẩy dữ liệu realtime tới trình duyệt. |
| **SWR (stale-while-revalidate)** | Phục vụ bản cũ trong lúc làm mới nền. |
| **ONNX** | Định dạng mô hình AI chạy trên CPU; dùng cho cảm xúc tin. |
| **LLM cục bộ (briefing-llm)** | Mô hình ngôn ngữ chạy ngay trên VPS, không internet, không công cụ; chỉ tóm tắt dữ liệu có đánh số. |
| **ADR** | Architecture Decision Record — tài liệu ghi một quyết định kiến trúc ([ADR/](ADR/)). |
| **SLO** | Mục tiêu mức dịch vụ (ví dụ độ tươi dữ liệu); xem SLO.md. |
| **PITR** | Khôi phục tới một thời điểm cụ thể từ base backup + WAL. |
| **DLQ (stream `dlq`)** | Nơi chứa sự kiện lỗi không xử lý được. |
| **Gate G1–G3** | Ba cổng pháp lý phải xong trước tiền thật: G1 forex bán lẻ VN, G2 giao dịch tự động chứng khoán VN, G3 điều khoản broker/EA. |
| **L0–L4** | Thang bậc năng lực từ "theo dõi" (hiện tại) đến "phân phối tín hiệu" (CONTROL_PLANE_DESIGN.md). |
| **Fixture / FIXTURE** | Dữ liệu thử tạo sẵn để kiểm tra; được gắn nhãn, không phải dữ liệu thật. |
