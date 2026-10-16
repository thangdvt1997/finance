# Plan: Hệ thống giao dịch tự động (MT4/MT5, báo cáo, thu thập dữ liệu)
Ngày: 2026-10-11 · Nguyên tắc: tích hợp OSS có sẵn, stack 0 đồng, không viết lại, paper trước live, LLM không ra lệnh.

## 0. Cổng quyết định (phải xong trước khi dùng tiền thật)
- G1 Pháp lý forex: NHNN chưa cấp phép sàn forex nào; Nghị định 340/2025 (hiệu lực 9/2/2026) phạt đến 250 triệu cho phái sinh ngoại hối không phép. Chế tài với cá nhân chưa rõ. -> hỏi luật sư, đọc nguyên văn NĐ.
- G2 Chứng khoán VN: UBCKNN 2023 yêu cầu dừng đặt lệnh robot; SSI/DNSE vẫn bán API. -> hỏi bằng văn bản công ty chứng khoán.
- G3 Chọn broker MT5 (ưu tiên MT5 hơn MT4), hỏi rõ ToS về API/EA/VPS.
Trong lúc chờ G1-G3: chỉ làm phase 1-3 (dữ liệu, backtest, demo/paper), không đụng tiền thật.

## 1. Kiến trúc
Data ingestion -> Bus (Redis Streams/NATS) -> Signal/Strategy (chỉ ĐỀ XUẤT) -> RISK ENGINE (cổng cứng) -> Execution/OMS (idempotent) -> MT5 bridge / broker API VN
Journal bất biến (Postgres/Timescale) -> Grafana/Metabase -> Telegram + báo cáo PDF/HTML. Kill-switch là tiến trình độc lập. LLM chỉ tóm tắt tin/giải thích báo cáo.

## 2. Thành phần và OSS tích hợp
| Vai trò | Chọn | Ghi chú |
|---|---|---|
| Backtest nhanh | vectorbt (free) + Backtesting.py | kiểm license trước khi đóng gói |
| Backtest chính xác + live | QuantConnect LEAN hoặc NautilusTrader | chọn 1 sau spike 1 tuần |
| Điều khiển MT5 | package Python MetaTrader5 trên Windows VPS + REST mỏng có auth | phương án A |
| Phương án rẻ | gmag11 MetaTrader5-Docker + mt5linux (Wine) | phương án B, cần test 1-2 tuần demo |
| MT4 (nếu bắt buộc) | darwinex/dwxconnect (EA bridge) | cân nhắc chuyển MT5 |
| Chứng khoán VN | DNSE LightSpeed SDK (chính), SSI FastConnect (dự phòng) | cần OTP, chờ G2 |
| Chỉ báo | TA-Lib + pandas-ta-classic | |
| Dữ liệu forex | Dukascopy (tick), HistData (M1), dữ liệu MT5 của broker | |
| Dữ liệu VN | vnstock (cá nhân, không thương mại) | production: SSI/DNSE |
| Vĩ mô | FRED, BIS, CFTC COT, GDELT, lịch BLS/Fed | Fair Economy JSON chỉ dùng cá nhân |
| Lưu trữ | Parquet + DuckDB (lịch sử), Timescale (realtime) | |
| Giám sát | Prometheus, Grafana, Metabase, Telegram bot | |
| Journal | TradeTally (self-host) + báo cáo tự sinh | kiểm bản self-host |
Bỏ: backtrader, PyAlgoTrade, oanda/v20-python, DWX ZeroMQ (archived), IEX Cloud (đóng). Freqtrade chỉ nếu làm crypto.
Tự viết (nhỏ, bắt buộc): risk engine, OMS idempotent, REST wrapper MT5, kill-switch, EA đẩy equity/vị thế.

## 2b. Hỗ trợ cả MT4 và MT5 (yêu cầu bổ sung 2026-10-11)
Nguyên tắc: lõi hệ thống KHÔNG biết MT4/MT5. Mọi thứ đi qua một lớp `BrokerGateway` chung, mỗi nền tảng một adapter.
Giao diện chung: get_account, get_positions, get_orders, place_order(client_id), modify, close, get_rates(symbol, tf, range), get_ticks, subscribe_quotes, health. Mô hình dữ liệu chuẩn hóa (symbol, lot, ticket, magic, time UTC) để chiến lược/risk/báo cáo dùng chung.
| | MT5 adapter | MT4 adapter |
|---|---|---|
| Cách nối | package Python MetaTrader5 (Windows) hoặc Wine+mt5linux | EA bridge (MT4 không có package Python chính hãng) |
| Dữ liệu | copy_rates/copy_ticks trực tiếp | EA đẩy bar/tick qua socket/WebRequest hoặc ghi file |
| Lệnh | order_send | EA nhận lệnh từ server, thực thi, báo kết quả |
| OSS tận dụng | mt5linux, gmag11 Docker | darwinex/dwxconnect (hỗ trợ MT4; MT5 chưa xác minh) |
Phương án thống nhất (đề xuất, cần spike 1 tuần): một EA agent mỏng viết cho cả hai (MQL4 + MQL5, chung phần include/giao thức), kết nối RA ngoài (outbound) tới bridge server bằng WebSocket/HTTP polling, không mở cổng vào VPS. MT5 vẫn có thêm đường Python chính hãng để lấy dữ liệu lịch sử nhanh. Lợi ích: một giao thức, một cách triển khai, cùng kill-switch tầng EA cho cả hai.
Khác biệt phải xử lý trong adapter/risk:
- MT4: hedging theo ticket, không có netting; MT5: có thể netting hoặc hedging tùy tài khoản -> chuẩn hóa khái niệm "position"; risk engine tính exposure đúng cho cả hai.
- Tên symbol/hậu tố, contract size, múi giờ server, độ sâu lịch sử khác nhau theo broker -> bảng mapping theo từng tài khoản.
- WebRequest chỉ chạy trong EA/script, đồng bộ, dễ timeout -> bắt buộc idempotency (magic + comment + client_order_id) và tra lại vị thế trước khi retry.
- Mỗi terminal chỉ 1 tài khoản; N tài khoản = N terminal (mỗi cái thư mục riêng). MT4 trên Wine kém ổn định hơn MT5 -> MT4 ưu tiên chạy Windows VPS.
- Backtest dùng engine chung (LEAN/Nautilus/vectorbt) với dữ liệu chuẩn hóa; Strategy Tester của MT4/MT5 không phải nguồn chân lý (WebRequest không chạy trong tester).
- Bộ test hợp đồng (contract tests): cùng một kịch bản chạy qua adapter MT4 và MT5 trên demo, kết quả phải khớp.
Hệ quả lịch trình: Phase 3 mở rộng thêm 2 tuần (viết EA agent MQL4/MQL5 + hai adapter + contract tests). Phase 8 trade copier làm được chéo MT4<->MT5 nhờ lớp chung.

## 3. Lộ trình
Phase 0 (tuần 1): chốt G1-G3, chọn broker, đăng ký demo MT5, repo + docs/SYSTEM.md.
Phase 1 (tuần 1-3) Dữ liệu: ingest Dukascopy/HistData/vnstock/MT5 -> Parquet; chuẩn hóa múi giờ/symbol/nến cuối tuần; đối chiếu 2 nguồn; cảnh báo nguồn rỗng/lỗi. Thu thập vĩ mô + lịch + tin (GDELT/RSS).
Phase 2 (tuần 3-5) Backtest: vectorbt quét ý tưởng; spike LEAN vs Nautilus (chọn 1); mô hình spread/slippage/phí; walk-forward out-of-sample.
Phase 3 (tuần 4-8, đã mở rộng cho MT4+MT5) Kết nối MT4 và MT5 demo qua BrokerGateway (xem 2b); spike EA agent chung vs dwxconnect cho MT4; contract tests hai adapter. Chi tiết gốc (MT5): dựng phương án A (và thử B song song); REST bridge, auth token, mỗi tài khoản 1 terminal; đo ổn định 1-2 tuần; EA đẩy equity/drawdown/vị thế.
Phase 4 (tuần 6-8) Risk + OMS + kill-switch: client_order_id/magic, đối soát vị thế khi khởi động, giới hạn lỗ ngày/lô/số lệnh/whitelist; kill-switch EA tầng 1 + server tầng 2 + lệnh Telegram; test thật trên demo.
Phase 5 (tuần 7-9) Báo cáo & giám sát: Grafana (equity, DD, độ trễ, lỗi), Metabase, báo cáo PDF/HTML hằng ngày/tuần, heartbeat báo khi bot im lặng, journal.
Phase 6 (tuần 9-13) Paper trading >= 4 tuần trên demo, so sánh với backtest, sửa lệch. LLM: tóm tắt tin + nhận xét báo cáo (chỉ đọc).
Phase 7 Go-live (chỉ khi qua G1-G3): vốn nhỏ, tăng dần; investor password cho giám sát, master chỉ cho bridge; VNC/RDP sau VPN.
Phase 8 (sau): trade copier (EA master/slave tự dựng hoặc qua bridge), chứng khoán VN qua DNSE, đa tài khoản.

## 4. Hạ tầng
- VPS Linux sẵn có <VPS_IP>: engine, DB, monitoring. Windows VPS ~30-40 USD/tháng cho MT5 (phương án A), đặt gần máy chủ broker, tự đo ping.
- Secret trong vault/env, không vào git; API key chỉ quyền giao dịch, không rút.

## 5. Rủi ro
P0: pháp lý forex/chứng khoán; không kill-switch; lộ key/OTP; lệnh trùng/lệch trạng thái; sàn lừa đảo; LLM đặt lệnh.
P1: overfitting, bỏ qua chi phí, dữ liệu cũ, máy đơn không watchdog, Wine hỏng sau cập nhật, nguồn dữ liệu không chính thức (yfinance/vnstock) đổi/chặn, thuế & lưu chứng từ.

## 6. Checklist go-live
Pháp lý xác nhận bằng văn bản; backtest có chi phí + walk-forward; paper >= 4 tuần; kill-switch thử thật; giới hạn lỗ/vị thế/lệnh; idempotency + đối soát; key an toàn; heartbeat Telegram; sao lưu journal + runbook; điều khiển dừng từ điện thoại; vốn nhỏ; LLM không có quyền execution.

## 7. Chưa xác minh (cần kiểm tra khi triển khai)
ToS Dukascopy/HistData/OANDA/Yahoo; phí SSI/DNSE; hiệu lực chỉ đạo robot 2023 và T+1; license vectorbt/OpenBB/StockSharp; broker LEAN/Nautilus hỗ trợ; dwxconnect hỗ trợ MT5 đến đâu; EULA broker về API/copier/VPS; auto-login MT5 trên Wine; giá/tier MetaApi.
