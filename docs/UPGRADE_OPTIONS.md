# UPGRADE_OPTIONS — lộ trình nâng cấp & lựa chọn (tổng hợp 2026-10-12)

Nguồn: docs/research/{PLATFORM_BENCHMARK, ARCH_AUDIT, DATA_AND_TOOLING_MARKET, PRO_WORKFLOW_GAPS, METHODS_SURVEY, BACKTEST_STUDY, MULTI_ASSET_BACKTEST, INFO_SIGNALS_STUDY}.md. Ràng buộc: gói 0 đồng; build/deploy/test CHỈ trên VPS; hệ thống READ-ONLY + paper (mô phỏng); mọi giao dịch thật chỉ sau cổng pháp lý G1-G3.

## Hiện trạng (đã xong) — lúc viết 2026-10-12; trạng thái hiện hành xem README.md/CHANGELOG.md
Thu thập giá/tin/lịch (+actual/forecast, cửa sổ rủi ro tin)/COT/chuyên gia; MT4+MT5 read-only (EA biên dịch sạch, chờ tài khoản demo thật); analytics (chỉ báo, screener, tương quan); nlp (FinBERT + ViSoBERT); paper-trader (mô phỏng, risk engine, kill-switch); web UI full-viewport 11 trang; ops: Prometheus 17 luật, Gatus/Dozzle/ntfy, backup mã hoá + PITR, Redis ACL, role DB hẹp, release/rollback. Điểm trưởng thành ~3,1/5.

## A. Việc cần NGƯỜI DÙNG làm (chặn các hạng mục khác)
1. Sao khoá `/root/.tradingsys-backup.key` ra ngoài VPS; cung cấp đích off-site (`infra/backup/offsite.env`).
2. Đăng ký key miễn phí (docs/FREE_STACK.md): OANDA practice, TrueFX, Alpaca, Tiingo, Marketaux, (FRED, BLS tuỳ chọn) → đặt vào infra/.env trên VPS.
3. Mở tài khoản demo MT4/MT5 (wizard cần thông tin cá nhân) hoặc đưa tài khoản demo broker → bật dữ liệu MT thật.
4. Telegram bot token + chat id (hiện cảnh báo qua ntfy).
5. Đổi mật khẩu web-ui (đã từng lộ trong output công cụ + 2 phút hở auth khi deploy nginx).
6. Gửi phương thức giao dịch riêng → đưa vào quy trình backtest → paper → duyệt.
7. G1-G3 (luật sư: forex bán lẻ, CTCK API/robot, ToS broker) trước mọi giao dịch thật.

## B. Nâng cấp TIẾP THEO (gói 0 đồng), xếp ưu tiên
| # | Hạng mục | Giá trị | Công sức | Ghi chú |
|---|---|---|---|---|
| 1 | Cảnh báo giá/điều kiện do người dùng tự đặt (UI) | Cao | M | dùng alert-service ĐÃ LÀM 2026-10-12 (service alert-rules, /v1/user/*) |
| 2 | Rủi ro tài khoản MT: margin/đòn bẩy/drawdown ngày + VaR/ES + stress test | Cao | M | Riskfolio-Lib, snapshot MT có sẵn |
| 3 | Báo cáo ngày/tuần PDF/HTML tự động (Jinja2+WeasyPrint) → ntfy/Telegram | Cao | M | |
| 4 | Hiệu suất paper: CI Sharpe, so benchmark, TCA, giám sát suy giảm (CUSUM) | Cao | M | QuantStats/empyrical |
| 5 | Hash-chain cho journal paper + strategy card + tiêu chí chuyển giai đoạn | Cao | S-M | chặn tối ưu-rồi-chạy |
| 6 | Watchlist đa nhóm + layout lưu server (bảng user_prefs) | TB | M | ĐÃ LÀM 2026-10-12 (service alert-rules, /v1/user/*) |
| 7 | Cổ phiếu VN: heatmap ngành, khối ngoại/tự doanh, screener cơ bản | Cao với VN | L | ĐÃ LÀM 2026-10-12 (service vn-market, /v1/vn/*, trang "Chứng khoán VN"; xem docs/VN_MARKET.md). Còn thiếu: realtime trong phiên + tự doanh + BCTC (cần SSI FastConnect/DNSE) |
| 8 | Nhật ký giao dịch + analytics tài khoản kiểu Myfxbook từ lịch sử MT | TB | M | ĐÃ LÀM 2026-10-12 (service journal, `/v1/journal/*`, EA gửi lịch sử deal; kiểm chứng bằng fixture/mô phỏng, chưa có deal thật — xem services/journal/README.md) |
| 9 | PWA, cmd-K, phím tắt, hiển thị nguồn/độ trễ trên mọi bảng | TB | S | ĐÃ LÀM 2026-10-12 (service alert-rules, /v1/user/*) |
| 10 | SSO/MFA: Caddy + Authelia hoặc Cloudflare Access (Named Tunnel) thay basic auth | Cao (bảo mật) | M | cần domain |
| 11 | Hardening còn lại: DB/Redis/Prometheus/Grafana, tách mạng, lockfile 4 service còn lại | TB | M | ARCH_AUDIT |
| 12 | Observability: OpenTelemetry traces, Postgres exporter, SLO | TB | M | |
Không làm: order-flow FX, TradingView Advanced Charts, marketplace tín hiệu, thay UI bằng OpenBB Workspace, copy-trade theo chuyên gia, carry/mean-reversion/news trading.

## C. Khi CÓ NGÂN SÁCH (ước giá, kiểm lại trước khi mua)
| Gói | USD/tháng | Thêm | Lợi ích |
|---|---|---|---|
| (ii) | ~90 | Twelve Data Grow ($79, real-time US+FX) + VPS Windows nhỏ (~$10) | dữ liệu real-time hợp pháp; chạy MT thật ổn định |
| (iii) | ~400-450 | + Trading Economics ($149) + Databento CME ($199+phí sàn) + Marketaux Standard ($49) | consensus chuẩn, tick futures |
Ưu tiên chi đầu tiên: VPS Windows (MT thật) → đồng bộ dữ liệu real-time → consensus lịch.

## D. Phương án giao dịch (STRATEGY_OPTIONS.md)
A theo dõi+cảnh báo (đang chạy) → B trend chậm đa tài sản (paper đang forward test; backtest: Sharpe 0,55 CI 0,21-0,87, không thắng 60/40 có ý nghĩa, DSR 0,87 → lớp đa dạng hoá, không phải alpha) → C cổ phiếu VN long-only → D bán tự động có duyệt tay (sau G1-G3). Quy trình bắt buộc: backtest trung thực → paper ≥8-12 tuần → so với backtest → duyệt → vốn nhỏ.
