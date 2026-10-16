# journal

Nhật ký giao dịch + analytics tài khoản kiểu Myfxbook/TradeTally cho MT4/MT5 và paper. **READ-ONLY** về giao dịch: chỉ phân tích lịch sử đã đóng; không có đường đặt/sửa/đóng lệnh.

- Nguồn: `account_deals` (EA agent -> mt-bridge -> `account.deals` -> storage-writer) và `paper_fills` (paper-trader). Đọc bằng role `ts_ro`.
- GHI duy nhất `journal_notes` (tag/ghi chú/review tay) bằng role `ts_journal` (`infra/db/create_journal_role.sh`; migration `infra/db/migrations/005_journal.sql`).
- Thống kê (`stats.py`): win rate, profit factor, expectancy, R-multiple (theo giá, cần SL), avg win/loss, payoff, MaxDD đường vốn theo deal (nạp/rút không tính là DD), chuỗi thắng/thua, thời gian giữ, chi phí, lãi/lỗ theo giờ/thứ/phiên/symbol/EA(magic)/hướng, lịch lãi-lỗ theo ngày, bảng đóng góp theo EA.
- Kỷ luật (`discipline.py`): vào lệnh trong cửa sổ rủi ro tin (`tscommon.risk_windows`), vào lại sau lệnh thua, tăng khối lượng sau thua, nhồi lệnh bình quân giá xấu, overtrading (ngày/giờ), thiếu SL, ngày vượt hạn mức lỗ; điểm 0–100. Phát hiện SAU KHI xảy ra.
- MAE/MFE (`excursions.py`) xấp xỉ từ nến (M1/M5/H1/D1 theo thời gian giữ lệnh) + spread tại lúc vào (bps, từ bảng quotes nếu có).
- Review tuần (`review.py`): tổng kết + so tuần trước + kỷ luật + nhận xét theo quy tắc (không dùng LLM).
- API nội bộ (chỉ api-gateway gọi, không publish cổng): xem `docs/CONTRACTS.md` mục "Nhật ký giao dịch". Env: `DATABASE_URL`, `JOURNAL_DB_RW_URL`, `JOURNAL_TZ` (mặc định Asia/Ho_Chi_Minh).
- Test: `sh infra/ops/run_tests.sh journal` (trên VPS). Có test số học tay (PF, expectancy, DD, R, chuỗi, nạp/rút), kỷ luật, paper fills, API và quét tĩnh read-only.
- Giới hạn: deal MT4 chỉ gồm phần lịch sử terminal đang nạp; SL ở deal MT5 lấy từ deal vào lệnh (SL đặt sau khi vào có thể thiếu -> không tính R); thống kê không gồm floating; MAE/MFE từ nến chỉ là xấp xỉ. Paper: phí/spread vào lệnh của vị thế còn MỞ chưa tính (chỉ phân bổ cho phần đã đóng), nên net paper ở đây chỉ gồm phần đã chốt.
