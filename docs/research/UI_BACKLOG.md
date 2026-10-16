# UI_BACKLOG — nghiên cứu sản phẩm/UX để nâng MASTER + CLIENT lên chuyên nghiệp (2026-10-12)

Người sở hữu: Product/UX Researcher. Phạm vi: giao diện + backlog tính năng cho hệ thống READ-ONLY (theo dõi/hỗ trợ), chưa có thực thi lệnh. Không phải khuyến nghị đầu tư.
Quy tắc nền: không đặt/sửa/đóng lệnh ở bất kỳ UI nào; không thu mật khẩu giao dịch/investor; không hiển thị tên nguồn dữ liệu (docs/UI_NO_SOURCES.md); mọi thứ miễn phí (FREE_STACK.md); VPS-only build.

## 0. Phương pháp và độ tin cậy (đọc trước)
- Đã đọc: PLATFORM_BENCHMARK.md, CLIENT_PLATFORM.md, HUONG_DAN_SU_DUNG.md (mục 3-4), ảnh master `services/web-ui/docs/clients/*` (Tổng quan fleet/heatmap sức khoẻ EA/danh sách/drawer chi tiết) và ảnh client `services/client-ui/docs/*` (Tổng quan, Rủi ro, Nhật ký). Không mở UI thật, không chạy build/test (đúng quy tắc). Kiểm tra mã chỉ bằng grep tên tệp: **chưa thấy** i18n (vi/en), nhập hàng loạt, vai trò phụ (analyst/support) ở web-ui/client-ui; công cụ vẽ biểu đồ ĐÃ có (`components/chart/drawings*.js`) nên mục #4 của PLATFORM_BENCHMARK coi như xong.
- Web research (WebSearch, 2026-10): kết quả phần lớn là blog/affiliate/trang so sánh của chính hãng → **mọi mô tả tính năng sản phẩm bên ngoài là "theo nguồn thứ cấp, chưa xác minh bằng cách dùng thử"**, trừ khi ghi "chính hãng". Không đăng nhập được FTMO/FundedNext/Myfxbook dashboard thật. Tôi KHÔNG sao chép mã/UI; chỉ học ý tưởng chức năng.
- Phát hiện quan trọng về luật prop-firm: các nguồn **mâu thuẫn** về drawdown (static vs trailing EOD, 1-Step vs 2-Step, quy tắc consistency, thời điểm reset ngày). => Bộ luật phải **cấu hình được theo từng mẫu**, KHÔNG hard-code "luật FTMO". Mặc định thận trọng: daily loss tính theo EQUITY (gồm lãi/lỗ treo, swap, commission); sàn trailing EOD chỉ cập nhật theo số dư đóng ngày.

## 1. Hiện trạng (từ ảnh + tài liệu) — để không đề xuất trùng
Master (web-ui) ĐÃ CÓ: trang Khách hàng (Tổng quan/Danh sách/Nhật ký kiểm toán/Thông báo), KPI fleet (tổng, trực tuyến, mất kết nối, chờ ghép, đình chỉ, equity tổng, exposure ước tính, vi phạm ngưỡng rủi ro), bản đồ nhiệt sức khoẻ EA (đổi chế độ: sức khoẻ/độ trễ dữ liệu/margin/drawdown), drawer chi tiết (cấp lại passcode, mã ghép cặp, xoay token, đình chỉ, ép đăng xuất, xem như khách hàng, xoá; thống kê nhanh; equity 7 ngày; hồ sơ; kết nối EA: phiên bản, build, độ trễ, đòn bẩy), wizard tạo tài khoản + onboarding, xác nhận 2 bước, ô tìm kiếm Ctrl+K, báo cáo, mô phỏng, đa trang thị trường.
Client (client-ui, PWA /c/) ĐÃ CÓ: Tổng quan (KPI, banner cửa sổ rủi ro tin, đường vốn 1D/7D/30D, vị thế nổi bật), Vị thế & lệnh chờ, Rủi ro (margin, ngân sách rủi ro, drawdown, VaR/ES, exposure, stress test, giải thích chỉ số), Nhật ký (KPI, equity+drawdown, lịch lãi/lỗ, theo mã, nhìn lại tuần + tag + sao + điều rút ra, tab Kỷ luật), Thị trường, Tin & Lịch, Phân tích kỹ thuật, Cảnh báo của tôi (tối đa 20 luật, push), Hồ sơ & bảo mật, dark/light, Web Push.
=> Khoảng trống lớn nhất: (1) master chưa có **thực thể khách hàng/nhóm/tag, luật theo mẫu, quy trình sự cố, báo cáo theo khách hàng, vai trò phụ**; (2) client chưa có **mục tiêu/giới hạn tự đặt, trung tâm thông báo, chi tiết lệnh, sao kê/xuất, đa ngôn ngữ, học liệu theo ngữ cảnh**.

## 2. Nguồn tham chiếu (URL) — viết tắt dùng trong bảng
| Mã | Sản phẩm / nguồn | URL | Mức xác minh |
|---|---|---|---|
| S1 | MetaTrader 5 cho môi giới (vai trò nhân viên: kế toán/dealer/risk, giám sát rủi ro, back-office) | https://www.metatrader5.com/en/brokers | Chính hãng (mô tả cấp sản phẩm) |
| S2 | FTMO — luật daily/max loss theo equity, Best Day (nguồn so sánh) | https://www.myforexfirms.com/blogs/ftmo-review-2026-drawdown-rules-consistency-rule-honest-verdict | Thứ cấp, mâu thuẫn |
| S3 | FundedNext — trailing EOD, consistency, giới hạn rủi ro | https://fortraders.com/blog/fundednext-rules | Thứ cấp, mâu thuẫn |
| S4 | Signalator Local Trade Copier (dashboard on-chart: trạng thái master/receiver, ánh xạ, hoạt động, lỗi/retcode, Telegram, tiny mode) | https://www.mql5.com/pt/market/product/184163 | Trang bán hàng |
| S5 | Tradecopia (độ trễ, trượt giá, hiệu suất từng tài khoản) | https://tradecopia.com/trading-copier-software | Trang bán hàng |
| S6 | Myfxbook — kết nối bằng mật khẩu investor, hồ sơ công/riêng, lịch kinh tế, app/widget | https://www.myfxbook.com/help/?p=300 và https://help.capital.com/hc/en-us/articles/16289731962642-Connecting-your-MetaTrader4-MT4-account-to-MyFxBook | Chính hãng + hướng dẫn broker; chưa xác nhận phân tích theo giờ/ngày |
| S7 | So sánh nhật ký: Edgewonk/TraderSync/Tradervue | https://takeprofitapp.com/en/learn/trade-journal-apps-comparison | Thứ cấp |
| S8 | TradesViz vs TradeZella (tag x symbol, playbook, replay, widget tuỳ biến) | https://www.tradesviz.com/tradesviz-vs-tradezella/ | Chính hãng tự so sánh (thiên vị) |
| S9 | Darwinex: % phân bổ, "Investor Divergence" (chênh lệch giá thực hiện vs bản sao) | https://help.darwinex.com/guide-to-darwin-investment-platform | Chính hãng (help) |
| S10 | eToro: thẻ Performance/Risk/Copiers/Trading, thống kê theo từng tài sản, mô phỏng "what-if" | https://www.financemagnates.com/forex/brokers/etoro-focuses-design-data-cleaner-simpler-stats-page/ | Báo chí (2015, cũ) |
| S11 | TradingView — cảnh báo watchlist (một luật cho nhiều mã, mã thêm sau tự áp dụng) | https://www.tradingview.com/blog/en/watchlist-alerts-on-tradingview-49839 | Chính hãng |
| S12 | Koyfin v3 — Watchlist + Template cột + nhóm tuỳ chỉnh + MyDashboards kéo thả | https://www.koyfin.com/help/release-notes/release-notes-v3-0/amp/ | Chính hãng |
| S13 | OpenBB Workspace — dashboard kéo thả, thư mục, chia sẻ, widget (metric/chart/table/note), Apps = mẫu dashboard, Ctrl+K | https://docs.openbb.co/workspace/analysts/dashboards | Chính hãng (giấy phép: kiểm GitHub) |
| S14 | IG — cảnh báo giá/%/chỉ báo, nhắc sự kiện kinh tế 5-60 phút trước, watchlist kéo thả | https://www.ig.com/ie/trading-platforms/trading-alerts | Chính hãng (alert app mới "sắp có": chưa rõ) |
| S15 | Exness Trade — cảnh báo giá, thông báo vị thế, máy tính margin/spread/swap, lịch tin | https://exness.com/exness-trader-app | Chính hãng |
| S16 | Plus500 — Close at Profit/Loss, trailing, cảnh báo margin/SL/TP | https://www.plus500.com/tradingacademy/tradersguide/risk-management-tools~16 | Chính hãng |
| S17 | SSI iBoard Pro — cảnh báo theo giá/biến động/khối lượng/room ngoại; quản lý (sửa/xoá/tạm dừng); thông báo lệnh khớp | https://www.ssi.com.vn/en/individual-customer/notification-feature-ib-app-pro | Chính hãng |
| S18 | TCInvest (TCBS) — bảng giá thông minh, cảnh báo realtime, tối ưu danh mục Markowitz | https://apps.apple.com/vn/app/tcinvest/id1037255487 | Mô tả App Store |
| S19 | DNSE EntradeX | https://apps.apple.com/vn/app/entrade-x-by-dnse-stocks/id1529981425 | Chỉ xác nhận bảng giá realtime; **cảnh báo/danh mục: chưa xác minh** |
| S20 | FreqUI (Freqtrade) — dashboard nhiều bot, biểu đồ số dư (gồm lãi/lỗ treo + nạp/rút, từ 2026.4) | https://www.freqtrade.io/en/stable/freq-ui/ (đọc qua bản sao gitcode) | Chính hãng/GPL-3 chỉ tham khảo UX |
| S21 | Hummingbot Dashboard (Streamlit; đã ngừng bảo trì → thay bằng Condor) | https://hummingbot.org/dashboard/ | Chính hãng |
| S22 | Ghostfolio (AGPL; hiệu suất theo nhiều khung, allocation, X-Ray rủi ro tập trung) | https://blog.elest.io/ghostfolio-free-open-source-privacy-first-portfolio-wealth-tracker/ | Thứ cấp |
| S23 | Wealthfolio (mục tiêu/goal + theo dõi đóng góp) | https://www.softpedia.com/get/Others/Finances-Business/Wealthfolio.shtml | Thứ cấp yếu |
Không tìm được tài liệu đáng tin: giao diện quản trị MT Manager (chỉ có mô tả cấp sản phẩm S1), FiinTrade/VNDirect/XM/Plus500 chi tiết, cTrader Copy, ZuluTrade, Social Trader Tools, FundedNext/FTMO dashboard thật → **chưa xác minh**.

Thang: Khó D=dễ (≤2 ngày), V=vừa (≤2 tuần), K=khó (>2 tuần). Giá trị C/T/Th. Ưu tiên P0 (làm ngay)–P3 (có thể bỏ). Vai trò M=master, C=client, MC=cả hai. "Kiến trúc" dùng tên dịch vụ trong CLIENT_PLATFORM.md (auth, mt-bridge, alert-rules, api-gateway, journal/analytics, web-ui, client-ui); **chưa đọc mã** nên đề xuất bảng/endpoint chỉ là hướng, kiểm tra trước khi làm.

## 3. MASTER — quản trị đội tài khoản (catalog)
| ID | Hạng mục | Mô tả | Ví dụ (URL) | Giá trị | Khó | Dữ liệu/backend | Đề xuất triển khai | Ưu tiên |
|---|---|---|---|---|---|---|---|---|
| M01 | Thực thể Khách hàng + Nhóm + Tag | Tách "khách hàng" (người) khỏi "tài khoản MT"; 1 khách nhiều TK; nhóm (gói dịch vụ, người phụ trách, chiến lược), tag tự do; lọc/lưu bộ lọc (saved views) | S12 (nhóm/template), S1 (phân quyền theo tầng) | C | V | `clients`, `client_groups`, `account_tags`, `saved_views` (auth DB `ts_auth`) | Thêm cột nhóm/tag ở bảng Danh sách + chip lọc; nhóm làm đơn vị cho luật (M03), báo cáo (M07), vai trò (M09) | P0 |
| M02 | Giám sát drawdown THEO LUẬT (mẫu luật) | Mẫu luật cấu hình được: daily loss (equity, mốc reset theo TZ), max DD static/trailing-EOD, mục tiêu lợi nhuận, min ngày giao dịch, Best-Day %, giới hạn rủi ro/lệnh; thanh tiến độ + "còn bao nhiêu tới vi phạm" + giờ reset | S2, S3 (luật chênh nhau → phải cấu hình) | C | V | `rule_templates`, `account_rules`, tính từ `account.snapshots` + deal; `rule_state` (đỉnh EOD, mốc ngày) | Mở rộng "ngưỡng rủi ro" hiện có; đánh giá trong alert-rules; hiển thị cột "Luật" trong danh sách + heatmap chế độ "Khoảng cách tới luật"; cảnh báo 3 mức 70/90/100% | P0 |
| M03 | Cảnh báo hàng loạt theo nhóm/chính sách | Một chính sách áp cho nhóm (TradingView watchlist-alert: thêm TK sau tự áp dụng); kênh/escalation theo mức | S11 | C | V | `alert_policies(group_id, condition, severity, channel)` | UI "Chính sách cảnh báo" gắn nhóm; dedupe + gộp "N tài khoản vi phạm" để tránh bão thông báo | P0 |
| M04 | Hộp thư sự cố (Incident inbox) | Cảnh báo → sự cố có trạng thái mới/đã nhận/đang xử lý/đóng, người phụ trách, ghi chú, snooze, tự đóng khi hết điều kiện, thời gian xử lý | S4 (nhật ký lỗi/retcode), S1 (giám sát đa dealer) | C | V | `incidents`, `incident_events` | Tab "Sự cố" cạnh "Thông báo"; nút Nhận/Giao/Snooze; liên kết sang drawer khách; tính SLA (M10) | P0 |
| M05 | Sức khoẻ EA/terminal mở rộng | Ngoài trực tuyến/độ trễ: lệch phiên bản EA ("EA cũ" đã có), lệch đồng hồ (skew), số lần khởi động lại, khoảng trống dữ liệu (gap), tick cuối, múi giờ server, tỷ lệ gói tin lỗi 24h | S4, S5 | C | D-V | `/internal/mt-accounts/seen` đã có latency/skew/ea_version → lưu chuỗi thời gian | Sparkline 24h trong drawer; heatmap thêm chế độ "Lệch phiên bản"; cảnh báo "vắng dữ liệu giờ thị trường mở" | P1 |
| M06 | Bảng điều khiển SLA/uptime | Uptime % EA theo khách/nhóm/broker, thời gian mất kết nối trung bình (MTTR), số sự cố/tuần, p50/p95 độ trễ; xuất cho khách | S5 | T-C | V | chuỗi `mt.account_status` đã có trên bus | Trang "SLA" (bảng + biểu đồ cột tuần); đưa số vào báo cáo khách hàng | P1 |
| M07 | Báo cáo định kỳ theo khách hàng | Mẫu PDF/HTML ngày/tuần/tháng: equity, lãi/lỗ, DD, kỷ luật, sự kiện rủi ro, ghi chú của master; lịch gửi; xem trước; lưu lịch sử | S7 (báo cáo), S10 (thẻ hiệu suất/rủi ro) | C | V | `report_schedules`, `report_runs`; Jinja2+WeasyPrint (đã đề xuất ở PLATFORM_BENCHMARK #15) | Trình dựng báo cáo: chọn mẫu → khách/nhóm → lịch → kênh (trong ứng dụng, email nếu có, Telegram); client tải ở mục "Báo cáo" | P0 |
| M08 | Ghi chú CRM + việc cần làm | Ghi chú theo khách (liên hệ lần cuối, cam kết, nhắc việc), @giao việc, lịch sử tương tác, gắn sự cố | (CRM thông dụng; không có ví dụ cụ thể đã xác minh) | T | D-V | `client_notes`, `tasks` | Tab "Ghi chú" trong drawer; widget "Việc hôm nay" ở tổng quan | P1 |
| M09 | Vai trò phụ (analyst / support / auditor) | `master` toàn quyền; `support` chỉ xem + cấp mã ghép cặp trong nhóm được giao; `analyst` chỉ-đọc số liệu ẩn thông tin định danh; `auditor` chỉ xem nhật ký; phạm vi theo nhóm | S1 (kế toán/dealer/risk, quyền theo tầng) | C | V | `portal_users.role` mở rộng + `user_scopes(group_ids)`; gateway kiểm quyền | Ma trận quyền ở trang "Người dùng"; mọi nút nguy hiểm kiểm tra vai trò; test IDOR như CLIENT_PLATFORM | P1 |
| M10 | Nhật ký kiểm toán nâng cao | Bộ lọc (người, hành động, đối tượng, IP), so sánh trước/sau (diff), xuất CSV, chuỗi băm tuỳ chọn (đã nêu), cảnh báo hành vi bất thường của chính admin (xoay token hàng loạt, nhiều lần impersonate), lưu giữ theo chính sách | S1 (kiểm soát nội bộ) | C | V | `audit_log` đã có (hash-chain tuỳ chọn) | Bật hash-chain; thêm tab lọc; xuất; ghi cả "đã xem như khách" + thời lượng | P1 |
| M11 | Onboarding wizard + nhập hàng loạt | Wizard đã có; thêm nhập CSV (nền tảng, số TK, nhãn, khách, nhóm, mẫu luật), xem trước + báo lỗi dòng, sinh mã ghép cặp hàng loạt, in/gửi hướng dẫn cài EA từng khách; checklist "đã cài EA / đã ghép / dữ liệu đầu tiên" | S6 (các bước kết nối) | C | V | `POST /admin/accounts:import` (dry-run + commit) | Nút "Nhập CSV" ở Danh sách; mẫu CSV tải về; cảnh báo trùng (platform+login) | P1 |
| M12 | Thao tác hàng loạt | Chọn nhiều dòng → gán nhóm/tag, đình chỉ/kích hoạt, xoay token, ép đăng xuất, gửi thông báo; xác nhận 2 bước + audit gộp | S1 | T-C | D-V | endpoint batch + audit | Thanh hành động nổi khi chọn; giới hạn tối đa N/lần | P1 |
| M13 | Tìm kiếm toàn cục mở rộng (command palette) | Ctrl+K đã có: thêm tìm khách/TK/ghi chú/sự cố + HÀNH ĐỘNG ("cấp mã ghép cặp cho X", "mở sự cố đang mở") | S13 (Ctrl+K), phổ biến | T | D | Postgres FTS / pg_trgm trên clients/accounts | Mở rộng nguồn tìm + nhóm kết quả theo loại | P2 |
| M14 | Phơi nhiễm gộp toàn fleet | Net theo tiền tệ/mã trên TẤT CẢ tài khoản (chỉ cộng cùng tiền tệ), cảnh báo tập trung (>X% fleet cùng hướng XAUUSD), tương quan giữa tài khoản | S22 (X-Ray tập trung), S18 | T-C | V | tính từ `orders/positions` hiện có | Thẻ "Tập trung rủi ro" ở tổng quan fleet; đừng cộng gộp khác tiền tệ (đã có ràng buộc) | P1 |
| M15 | Phát hiện bất thường hành vi (heuristic, gắn nhãn "gợi ý") | Đột biến lot, symbol mới, tăng số lệnh bất thường, kiểu martingale/lưới, tốc độ tụt DD; điểm "mức chú ý" | S4 (diễn giải lệnh bị bỏ/lỗi) | T | K | từ deal + snapshot | Làm sau M02/M04; luôn hiển thị lý do + ngưỡng, không kết luận | P2 |
| M16 | Thông báo & kênh của master | Trung tâm thông báo (đã có tab) + tuỳ chỉnh theo vai trò/nhóm/giờ yên lặng, trực ca (rota), nhắc leo thang khi không ai nhận trong N phút | S17 (quản lý cảnh báo: sửa/xoá/tạm dừng) | T-C | V | `notification_prefs`, Apprise đã dùng | Cài đặt cá nhân của master; leo thang gắn với M04 | P1 |
| M17 | Xem như khách hàng nâng cao | Đã có impersonate chỉ-đọc: thêm banner không thể ẩn, hết hạn 15 phút, ghi vào audit + thông báo cho khách (tuỳ chính sách) | S1 | T | D | audit đã có | Bổ sung banner + thời hạn + ghi lý do bắt buộc | P1 |
| M18 | Kho tài liệu/cài đặt EA theo khách | Bản EA đúng phiên bản + hướng dẫn từng bước + kiểm tra "Allow WebRequest" | S6 | T | D | `mt-agent/README.md` | Trang "Cài đặt EA" + deep-link từ wizard | P2 |
| M19 | Bảng so sánh/xếp hạng NỘI BỘ (ẩn danh) | So sánh DD/lợi nhuận giữa tài khoản cùng nhóm để master phát hiện ngoại lệ (không công khai cho khách) | S10 (thẻ so sánh) | T | D-V | từ KPI hiện có | Chế độ "so với nhóm" (percentile) trong danh sách | P2 |
| M20 | Bố cục tuỳ biến (widget kéo thả, view lưu) | Người vận hành tự xếp thẻ ở Tổng quan fleet; lưu thành view theo vai trò | S12, S13 | T | V | `user_prefs` (đã đề xuất) + react-grid-layout | Sau khi cố định bộ widget chuẩn; P2 vì chuẩn hoá trước | P2 |

## 4. CLIENT — ứng dụng của chủ tài khoản (catalog)
| ID | Hạng mục | Mô tả | Ví dụ (URL) | Giá trị | Khó | Dữ liệu/backend | Đề xuất triển khai | Ưu tiên |
|---|---|---|---|---|---|---|---|---|
| C01 | Trang chủ "Hôm nay" kiểu một-màn-hình | Thẻ ưu tiên theo mức nghiêm trọng: trạng thái EA/dữ liệu, rủi ro gần ngưỡng, tin sắp tới ảnh hưởng vị thế, lãi/lỗ hôm nay, việc nên xem; ít số hơn, nhiều câu hơn ("Bạn đã dùng 62% hạn mức lỗ ngày") | S15, S10 | C | D-V | dữ liệu đã có (Tổng quan, Rủi ro) | Sắp xếp lại Tổng quan: banner trạng thái → 3 thẻ chính → đường vốn → vị thế; chế độ "đơn giản/chi tiết" | P0 |
| C02 | Mục tiêu & giới hạn TỰ ĐẶT | Khách đặt: lỗ tối đa/ngày, DD tối đa, số lệnh/ngày, giờ không giao dịch, mục tiêu lợi nhuận tháng; thanh tiến độ; báo khi chạm 70/90/100%; có thể bật "giai đoạn nguội" gợi ý nghỉ sau chuỗi lỗ (chỉ nhắc, không chặn) | S16 (cảnh báo SL/TP/margin), S23 (goal), S2 (mô hình luật) | C | V | `client_limits` + đánh giá trong alert-rules (điều kiện `account` đã có); Web Push đã có | Trang "Giới hạn & mục tiêu" (wireframe #5); tái dùng engine luật của M02 với mẫu "tự đặt" | P0 |
| C03 | Trung tâm thông báo (inbox) | Lịch sử mọi cảnh báo/ghi chú từ master/báo cáo; đọc/chưa đọc; lọc theo mức; cài giờ yên lặng; kênh push | S17 (quản lý, tạm dừng) | C | D-V | `alert_rule_events` đã có `/v1/user/rule-events` | Trang `/thong-bao` (push đã trỏ về đó); badge ở thanh điều hướng | P0 |
| C04 | Chi tiết lệnh/vị thế | Trang cho từng lệnh: biểu đồ giá + điểm vào/ra, SL/TP, thời gian giữ, MAE/MFE, R-multiple, phí/swap, ghi chú + tag + ảnh chụp; điều hướng trước/sau | S7, S8 | C | V | deal đã có; MAE/MFE cần nến M1 quanh thời gian giữ (md.bars) | Drawer/trang từ bảng Lệnh trong Nhật ký; ghi chú lưu server | P1 |
| C05 | Thống kê chuyên sâu kiểu Myfxbook/nhật ký | Lãi/lỗ theo giờ-ngày-phiên, theo mã, thời gian giữ, chuỗi thắng/thua, phân phối R, kỳ vọng, rủi ro lụn vốn (risk of ruin) | S6, S7, S8 | C | V | tính từ deal (pandas/QuantStats như PLATFORM_BENCHMARK #13) | Tab "Phân tích" trong Nhật ký; cảnh báo cỡ mẫu nhỏ (<30 lệnh) | P1 |
| C06 | Lịch lãi/lỗ + tuần/tháng (ĐÃ CÓ) → nâng cấp | Thêm tổng tuần, chế độ % thay vì tiền, bấm ngày xem lệnh + ghi chú, huy hiệu ngày vi phạm giới hạn | S8 | T | D | có | Bổ sung cột tổng tuần + chấm đỏ "vượt giới hạn tự đặt" | P1 |
| C07 | Sao kê & xuất dữ liệu | Xuất CSV/PDF lịch sử lệnh, sao kê tháng; chia sẻ có kiểm soát | S6 | C | D-V | deal + báo cáo M07 | Nút Xuất trong Nhật ký; PDF dùng cùng mẫu báo cáo | P1 |
| C08 | Đa ngôn ngữ vi/en | Tách chuỗi, chọn ngôn ngữ ở Hồ sơ, định dạng số/ngày theo locale; thuật ngữ nhất quán | S18 (TCBS dịch 4 ngôn ngữ — chỉ để thấy nhu cầu) | T-C | V | thêm i18n (vd. i18next/Lingui) — chưa thấy i18n trong mã | Bắt đầu bằng trích chuỗi trang Đăng nhập/Tổng quan/Rủi ro; tiếng Việt vẫn là gốc | P1 |
| C09 | Học liệu & thuật ngữ theo ngữ cảnh | Tooltip "?" ngay cạnh chỉ số, mục "Các chỉ số này nghĩa là gì" (đã có ở Rủi ro) mở rộng toàn app; tour 4 bước lần đầu; trang Thuật ngữ tìm kiếm được | S15 (máy tính margin/spread/swap) | T | D | nội dung tĩnh | Component `<Term id>`; máy tính margin/pip chỉ-đọc | P2 |
| C10 | Lịch tin theo vị thế của tôi | Sự kiện tác động cao liên quan mã đang giữ/đã đặt cảnh báo; nhắc trước 5-60 phút (IG); thêm vào cảnh báo cá nhân | S14, S15 | C | D-V | calendar + risk window đã có | Lọc "Ảnh hưởng vị thế của tôi" + nút "Nhắc tôi" tạo luật push | P1 |
| C11 | Cảnh báo giá/điều kiện (ĐÃ CÓ) → UX | Mẫu nhanh ("margin < 200%", "DD ngày > 3%"), tạm dừng/sửa/xoá gọn như S17, lịch sử kích hoạt, thử luật (preview đã có) | S14, S17 | T | D | có | Thư viện mẫu 8 luật + trạng thái "không rõ do dữ liệu cũ" giải thích rõ | P1 |
| C12 | Đa tài khoản (nếu 1 khách nhiều TK) | Bộ chọn tài khoản đã có; thêm trang tổng hợp theo tiền tệ (không cộng gộp khác tiền tệ), so sánh các TK | S22 (allocation) | T | V | `user_accounts` đã có | Chế độ "Tất cả tài khoản" tách theo tiền tệ | P2 |
| C13 | Tóm tắt tuần tự động (digest) | Cuối tuần: 5 dòng nhận xét + 1 điều nên xem lại + liên kết nhật ký; trong app + push | S7 | T-C | D-V | tái dùng M07 | Thẻ đầu trang Nhật ký + push chủ nhật | P1 |
| C14 | Kỷ luật & tâm lý (nhẹ) | Tab "Kỷ luật" đã có: thêm tag cảm xúc/lý do vào lệnh, thống kê "lệnh sau chuỗi lỗ", nhắc nhìn lại; KHÔNG chấm điểm đạo đức | S7 (Tiltmeter của Edgewonk — nguồn thứ cấp) | T | V | nhật ký có | Sau C04; ngôn ngữ trung tính | P2 |
| C15 | Chia sẻ có kiểm soát | Liên kết xem-chỉ-đọc có hạn (che số TK/số dư, chỉ %), ảnh chụp thẻ hiệu suất để gửi cố vấn/người thân | S6 (hồ sơ công/riêng), S9 | T | V | token chia sẻ + che dữ liệu phía server | Mặc định TẮT; hết hạn 7 ngày; ghi audit; không công khai bảng xếp hạng | P2 |
| C16 | PWA: cài đặt, offline-lite, badge | Nút "Cài ứng dụng", cache vỏ + dữ liệu cuối (đánh dấu "dữ liệu lúc …"), huy hiệu số thông báo chưa đọc | thông dụng | T | D | service worker đã có (Web Push) | Trang Hồ sơ → "Cài lên màn hình chính"; trạng thái offline rõ | P1 |
| C17 | Bảo mật tài khoản | Danh sách phiên/thiết bị + đăng xuất từ xa (đã có phiên), TOTP tuỳ chọn, nhật ký đăng nhập của chính mình, đổi mật khẩu cổng | S1 | C | D-V | `portal_sessions` có | Mục "Bảo mật" trong Hồ sơ | P1 |
| C18 | Chế độ hiển thị: đơn giản/chuyên sâu, ẩn số dư | Nút "ẩn số tiền" (che khi ở nơi công cộng), cỡ chữ lớn, giảm chuyển động, dark/light đã có | thông dụng | T | D | local | Công tắc ở thanh trên; lưu `user_prefs` | P1 |
| C19 | Trạng thái dữ liệu minh bạch | Huy hiệu "cập nhật N giây trước / EA ngoại tuyến từ HH:MM" ở mọi trang; hướng dẫn tự xử lý (mở terminal, kiểm tra EA); liên hệ hỗ trợ 1 chạm | PLATFORM_BENCHMARK #24 | C | D | `mt.account_status` | Banner thống nhất + nút "Báo cho quản trị" tạo sự cố M04 | P0 |
| C20 | Liên hệ hỗ trợ / hỏi quản trị | Gửi câu hỏi/ghi chú gắn với lệnh hoặc cảnh báo; master nhận trong M08/M04 | thông dụng | T | V | `support_threads` | Sau M04; không làm chat realtime | P2 |
| C21 | Máy tính rủi ro chỉ-đọc | Tính lot theo % rủi ro/SL, margin cần, pip value — chỉ để tham khảo, không nối lệnh | S15 | T | D | công thức tĩnh | Công cụ trong "Rủi ro" | P2 |
| C22 | Widget màn hình chính | PWA không có widget thật; thay bằng thông báo ghim/badge + Telegram bot tuỳ chọn (miễn phí) | — | Th | K | — | KHÔNG làm widget native; xem mục 8 | P3 |

## 5. TOP 25 VIỆC NÊN LÀM TIẾP (xếp theo Impact/Effort)
Impact 1-5; Effort 1-5 (5=nhiều công); Điểm = Impact×2 − Effort (chỉ để sắp xếp). Chỉ gồm việc nằm trong phạm vi READ-ONLY, miễn phí.
| # | Việc | ID | Vai | Impact | Effort | Vì sao trước |
|---|---|---|---|---|---|---|
| 1 | Banner trạng thái dữ liệu/EA thống nhất + nút "Báo cho quản trị" | C19 | C | 5 | 1 | rẻ nhất, giảm hỏi đáp "sao số đứng yên" |
| 2 | Trung tâm thông báo client (trang đích của push) | C03 | C | 4 | 2 | push đã có nhưng thiếu nơi xem lại |
| 3 | Thực thể khách hàng + nhóm + tag + saved views | M01 | M | 5 | 3 | nền cho luật/báo cáo/vai trò |
| 4 | Mẫu luật drawdown cấu hình được (daily/max/trailing/best-day) | M02 | M | 5 | 3 | giá trị cốt lõi cho đội quản lý; nhiều nguồn mâu thuẫn → phải cấu hình |
| 5 | Giới hạn & mục tiêu tự đặt của client (tái dùng engine M02) | C02 | C | 5 | 3 | khách tự bảo vệ; cùng engine |
| 6 | Hộp thư sự cố + nhận/giao/snooze/tự đóng | M04 | M | 5 | 3 | biến cảnh báo thành quy trình |
| 7 | Chính sách cảnh báo theo nhóm + gộp "N tài khoản" | M03 | M | 4 | 3 | chống bão thông báo khi fleet lớn |
| 8 | Báo cáo định kỳ theo khách (PDF + lịch + xem trong app) | M07 | MC | 5 | 3 | khách thấy giá trị hằng tuần |
| 9 | Sắp xếp lại Tổng quan client kiểu "Hôm nay" | C01 | C | 4 | 2 | UX tức thì, không cần backend mới |
| 10 | TOTP bắt buộc cho master + quản lý phiên/thiết bị cho client | C17 | MC | 4 | 2 | an ninh (admin điều khiển nhiều tài khoản) |
| 11 | Vai trò support/analyst/auditor có phạm vi theo nhóm | M09 | M | 4 | 3 | cho phép chia việc an toàn |
| 12 | Chi tiết lệnh (MAE/MFE, ghi chú, tag) | C04 | C | 4 | 3 | nền cho nhật ký/thống kê |
| 13 | Lịch tin theo vị thế của tôi + nhắc trước sự kiện | C10 | C | 4 | 2 | dữ liệu đã có |
| 14 | Nhập CSV + thao tác hàng loạt | M11/M12 | M | 4 | 3 | cần khi >50 tài khoản |
| 15 | Thống kê chuyên sâu theo giờ/phiên/mã/thời gian giữ | C05 | C | 4 | 3 | khác biệt với app broker |
| 16 | Sức khoẻ EA mở rộng + sparkline 24h + lệch phiên bản | M05 | M | 3 | 2 | dữ liệu `seen` đã có |
| 17 | Nhật ký kiểm toán: hash-chain, lọc, diff, xuất | M10 | M | 4 | 3 | tuân thủ + niềm tin |
| 18 | Xuất sao kê CSV/PDF | C07 | C | 3 | 2 | dùng chung mẫu báo cáo |
| 19 | Đa ngôn ngữ vi/en (bắt đầu 3 trang) | C08 | C | 3 | 3 | mở rộng người dùng |
| 20 | Phơi nhiễm gộp fleet + cảnh báo tập trung | M14 | M | 3 | 3 | rủi ro hệ thống |
| 21 | Bảng SLA/uptime + đưa vào báo cáo | M06 | M | 3 | 3 | chứng minh chất lượng dịch vụ |
| 22 | Digest tuần cho client + thẻ đầu Nhật ký | C13 | C | 3 | 2 | tái dùng M07 |
| 23 | Ghi chú CRM + việc cần làm trong drawer | M08 | M | 3 | 2 | rẻ, hữu ích hằng ngày |
| 24 | PWA: cài, offline-lite, ẩn số dư | C16/C18 | C | 3 | 2 | trải nghiệm di động |
| 25 | Impersonate nâng cao (banner, hết hạn, lý do bắt buộc) | M17 | M | 3 | 1 | an ninh + minh bạch |

Thứ tự gợi ý theo đợt: Đợt 1 (1-2 tuần): #1,2,9,10,25,13. Đợt 2: #3,4,5,6,7. Đợt 3: #8,11,14,17,12,15. Đợt 4: còn lại.
Phụ thuộc: M01 → M02/M03/M07/M09; M02 → C02; M04 ← M03; M07 → C07/C13.

## 6. Tính năng KHÔNG nên làm (và lý do)
1. Đặt/sửa/đóng lệnh, nút "đóng hết", chuyển lệnh từ xa — ngoài phạm vi read-only; chỉ sau cổng pháp lý G1-G3 và có service riêng.
2. Copy-trading/marketplace tín hiệu/bảng xếp hạng công khai tài khoản thật (ZuluTrade/eToro style) — xung đột kết luận trung thực của dự án, rủi ro pháp lý, lộ dữ liệu khách.
3. Mạng xã hội/feed/chat Bloomberg — chi phí kiểm duyệt lớn, không phục vụ mục tiêu.
4. Thu mật khẩu investor/giao dịch qua web kiểu Myfxbook (S6) — dự án đã chọn EA đẩy dữ liệu; thu mật khẩu là rủi ro lớn.
5. "Tín hiệu mua/bán do AI/LLM" hoặc dự báo lãi — vi phạm quy tắc LLM không ra lệnh; chỉ giải thích số liệu.
6. Gamification (chuỗi ngày, huy hiệu, confetti khi thắng) — khuyến khích giao dịch quá mức; chỉ dùng tiến độ giữ kỷ luật, trung tính.
7. Push cho mọi biến động lãi/lỗ tức thời — gây lo âu, vượt giới hạn 20 push/giờ; chỉ ngưỡng + digest.
8. Xếp hạng khách này hơn khách kia công khai cho khách; so sánh chỉ ẩn danh ở phía master (M19).
9. Bộ dựng widget kiểu OpenBB/Koyfin đầy đủ trước khi chuẩn hoá bộ thẻ — tốn công, ít người dùng (M20 để P2).
10. Replay/order-flow/footprint/DOM cho FX; tự viết lại TradingView/Pine; app native (PWA + Telegram đủ) — như PLATFORM_BENCHMARK §6.
11. Thanh toán/thu phí/hoá đơn trong ứng dụng; quảng cáo; SaaS trả phí (FREE_STACK).
12. Hiển thị tên nguồn dữ liệu/nhà cung cấp trong UI, báo cáo, thông báo (UI_NO_SOURCES).
13. "Cam kết/đảm bảo" lợi nhuận, thanh chuyển động "tỷ lệ thắng của chiến lược" có tính quảng cáo; luôn kèm cỡ mẫu và giới hạn.
14. Cho phép client sửa luật của master hoặc tự nới giới hạn đã đặt ngay lập tức (giới hạn tự đặt: nới lỏng chỉ có hiệu lực sau 24 giờ — thiết kế chống bốc đồng, cần xác nhận với người dùng).

## 7. Sơ đồ thông tin (IA) đề xuất
### 7.1 MASTER (web-ui; thanh bên trái 5 nhóm; Ctrl+K toàn cục; badge sự cố mở)
```
Bảng điều khiển (Command center)
  ├─ Tổng quan fleet (KPI, heatmap, vi phạm luật, sự cố mới, việc hôm nay)
  └─ SLA & sức khoẻ (uptime, độ trễ, lệch phiên bản)
Khách hàng
  ├─ Danh sách (lọc nhóm/tag/trạng thái, saved views, chọn nhiều → thao tác hàng loạt, Nhập CSV)
  ├─ Hồ sơ khách 360 (tổng quan | tài khoản | rủi ro & luật | nhật ký | báo cáo | ghi chú | kiểm toán)
  ├─ Nhóm & tag
  └─ Onboarding (wizard, checklist cài EA)
Rủi ro & Cảnh báo
  ├─ Sự cố (inbox: mới/đang xử lý/đóng, giao việc, snooze)
  ├─ Luật & mẫu luật (daily/max/trailing/best-day/tự đặt)
  ├─ Chính sách cảnh báo (theo nhóm, kênh, leo thang)
  └─ Phơi nhiễm gộp
Báo cáo
  ├─ Mẫu & lịch gửi
  ├─ Lịch sử đã gửi
  └─ Sao kê/xuất dữ liệu
Thị trường & Thông tin (giữ hiện có: Thị trường, Chứng khoán VN, Danh sách theo dõi, Phân tích, Bản tin, Tin, Lịch, Chuyên gia)
Quản trị
  ├─ Người dùng & vai trò (master/support/analyst/auditor; phạm vi nhóm)
  ├─ Nhật ký kiểm toán (lọc, diff, xuất)
  ├─ Thông báo cá nhân (kênh, giờ yên lặng, trực ca)
  └─ Hệ thống (giữ hiện có) · Mô phỏng
```
### 7.2 CLIENT (client-ui, PWA mobile-first; thanh dưới 5 mục + "Thêm")
```
Thanh dưới:  Hôm nay | Vị thế | Rủi ro | Nhật ký | Thêm
Hôm nay (trang chủ)
  ├─ Trạng thái EA/dữ liệu · banner tin sắp tới · hạn mức đã dùng
  └─ Đường vốn, vị thế nổi bật, việc nên xem
Vị thế & lệnh chờ → Chi tiết lệnh
Rủi ro
  ├─ Margin, ngân sách, exposure, stress (hiện có)
  └─ Giới hạn & mục tiêu của tôi (mới)
Nhật ký
  ├─ Tổng quan, Lịch lãi/lỗ, Lệnh → Chi tiết lệnh, Thống kê chuyên sâu, Kỷ luật
  └─ Nhìn lại tuần + Digest, Xuất sao kê
Thêm
  ├─ Thị trường (watchlist, biểu đồ, phân tích kỹ thuật)
  ├─ Tin & Lịch (theo vị thế của tôi)
  ├─ Cảnh báo của tôi (mẫu nhanh, lịch sử)
  ├─ Thông báo (inbox)
  ├─ Báo cáo & sao kê
  ├─ Học liệu & thuật ngữ, máy tính chỉ-đọc
  └─ Hồ sơ & bảo mật (ngôn ngữ vi/en, giao diện, ẩn số dư, phiên/thiết bị, TOTP, liên hệ hỗ trợ)
```

## 8. Năm màn hình then chốt (wireframe bằng chữ)
### W1. MASTER — Fleet command center (desktop 1366)
- Thanh trên: ô tìm Ctrl+K (khách/TK/sự cố/hành động) · chuông (số sự cố mở) · đồng hồ phiên · chuyển sáng/tối · chip vai trò.
- Hàng 1 — KPI (6 ô): Tài khoản | Trực tuyến | Mất kết nối | Vi phạm luật | Sát ngưỡng (≥90%) | Sự cố chưa nhận. Mỗi ô bấm = lọc danh sách.
- Hàng 2 trái (2/3): Heatmap ô vuông theo nhóm (mỗi ô: nhãn, nền tảng, trạng thái, % đã dùng hạn mức luật); bộ chuyển chế độ: Sức khoẻ EA | Độ trễ | Khoảng cách tới luật | Margin | Drawdown | Lệch phiên bản; lọc nhóm/tag ở trên cùng.
- Hàng 2 phải (1/3): "Sự cố cần xử lý" (5 dòng gần nhất; nút Nhận/Giao) + "Việc hôm nay" (từ ghi chú CRM) + thẻ "Tập trung rủi ro" (net XAUUSD toàn fleet).
- Hàng 3: Bảng "Gần vi phạm" (TK, luật, % đã dùng, thời điểm reset, thời gian tới ngưỡng ước tính) + Biểu đồ uptime 7 ngày.
- Hành vi: bấm ô/dòng → mở hồ sơ 360 dạng drawer; phím tắt `g c` danh sách, `i` sự cố; trạng thái trống/lỗi/dữ liệu cũ có huy hiệu rõ; luôn có chú thích "chỉ-đọc".

### W2. MASTER — Hồ sơ khách 360 (drawer rộng → trang)
- Đầu: tên khách, nhóm (chip), tag (chip + thêm), người phụ trách, trạng thái; hành động: Cấp mã ghép cặp, Xoay token, Đình chỉ, Xem như khách (yêu cầu nhập lý do), Tạo báo cáo.
- Tab: Tổng quan (KPI: equity, DD từ đỉnh, P/L hôm nay, margin; sparkline sức khoẻ EA 24h; equity 30 ngày) | Tài khoản (danh sách TK của khách, tiền tệ riêng) | Rủi ro & luật (thanh tiến độ từng luật + lịch sử vi phạm + nút "Áp mẫu luật") | Nhật ký (tóm tắt, lịch lãi/lỗ) | Báo cáo (đã gửi/lịch) | Ghi chú & việc | Kiểm toán (hành động trên khách này).
- Cột phải cố định: "Kết nối EA" (phiên bản, build, độ trễ, skew, lần cuối) + sự cố đang mở của khách.
- Nguy hiểm (xoá, đình chỉ): xác nhận 2 bước, ghi audit; vai trò support thấy nút bị khoá kèm lý do.

### W3. MASTER — Luật & Sự cố (hai khung)
- Trái: Danh sách mẫu luật (tên, loại, số TK đang dùng). Bấm → trình soạn: Loại giới hạn (daily loss % | max DD % | trailing EOD | best-day % | min ngày), Cơ sở tính (equity/balance), Múi giờ + giờ reset, Ngưỡng 70/90/100%, Phạm vi (nhóm/tag/TK), Hành động (thông báo kênh nào, tạo sự cố mức nào). Nút "Xem trước trên dữ liệu 30 ngày" cho thấy sẽ có bao nhiêu TK vi phạm. Cảnh báo cố định: "Luật nhà cái/prop có thể khác nhau — kiểm tra điều khoản chính thức."
- Phải: Hộp sự cố — cột (Mới | Đã nhận | Đang xử lý | Đã đóng); thẻ sự cố: mức, khách/TK, điều kiện, thời gian mở, người phụ trách; thao tác: Nhận, Giao, Snooze 1h/4h/đến mai, Ghi chú, Đóng; tự đóng khi hết điều kiện (hiện nhãn "tự đóng").
- Bộ lọc: nhóm, mức, người phụ trách; chế độ gộp "N tài khoản cùng điều kiện".

### W4. CLIENT — Trang chủ "Hôm nay" (mobile 375)
- Thanh trên: bộ chọn tài khoản (MT5 · 1234…) · chuông có badge · nút ẩn số dư.
- Khối 1 (banner theo ưu tiên, chỉ hiện 1): ví dụ "EA ngoại tuyến từ 14:02 — số liệu có thể cũ [Xem cách xử lý] [Báo quản trị]" hoặc "Tin CPI Mỹ sau 12 phút — bạn đang giữ XAUUSD".
- Khối 2: 3 thẻ lớn: Vốn (equity) + thay đổi hôm nay; Lãi/lỗ đang mở; "Hạn mức hôm nay: đã dùng 38%" (vòng/thanh, bấm → Giới hạn của tôi).
- Khối 3: đường vốn 7 ngày (nhấn giữ xem giá trị) với đường mục tiêu/giới hạn mờ.
- Khối 4: Vị thế nổi bật (3 dòng: mã, hướng, lãi/lỗ) + "Xem tất cả"; bấm → chi tiết lệnh.
- Khối 5: "Nên xem" (tối đa 3): nhìn lại tuần chưa viết, báo cáo mới, cảnh báo đã kích hoạt.
- Thanh dưới: Hôm nay | Vị thế | Rủi ro | Nhật ký | Thêm. Chân trang luôn: "Chỉ theo dõi, không đặt lệnh."

### W5. CLIENT — Giới hạn & mục tiêu của tôi
- Đầu: giải thích 1 dòng ("Bạn tự đặt; hệ thống chỉ nhắc, không chặn lệnh").
- Danh sách thẻ giới hạn: Lỗ tối đa/ngày (đặt 3% — đã dùng 0,9%), Sụt giảm tối đa từ đỉnh (5%), Số lệnh/ngày (10), Khung giờ không giao dịch (22:00–06:00), Mục tiêu lợi nhuận tháng (4%). Mỗi thẻ: thanh tiến độ, nút bật/tắt, nút Sửa; ngưỡng nhắc mặc định 70/90/100%.
- Chế độ "Giai đoạn nguội": sau N lệnh thua liên tiếp hiện nhắc "nghỉ 30 phút?" (chỉ gợi ý).
- Sửa: siết chặt có hiệu lực ngay; NỚI LỎNG có hiệu lực sau 24 giờ (hiện đếm ngược) — cần xác nhận.
- Dưới: Lịch sử chạm giới hạn (ngày, giới hạn, kết quả ngày hôm đó) và liên kết "Thêm cảnh báo".
- Kênh nhận: Web Push (đã có) + trong ứng dụng; giờ yên lặng.

## 9. Rủi ro/giả định và việc cần xác minh
- Mô hình luật drawdown của FTMO/FundedNext thay đổi theo chương trình và thời gian; nguồn thứ cấp mâu thuẫn → luôn cho phép cấu hình + hiển thị công thức + ghi "tham khảo".
- Ngưỡng 24 giờ nới lỏng (W5/mục 6.14) là giả thuyết thiết kế, cần user duyệt.
- Giá trị/độ khó/ưu tiên là đánh giá của người nghiên cứu, chưa có dữ liệu sử dụng thật; tính khả thi backend chưa đọc mã.
- Chưa xác minh: giao diện thật các sản phẩm ngoại trừ mô tả công khai; tính năng DNSE EntradeX/FiinTrade/VNDirect; cTrader Copy, ZuluTrade; phân tích theo giờ/ngày của Myfxbook; giấy phép OpenBB hiện hành.
- Khi triển khai: chạy build/test chỉ trên VPS; kiểm tra IDOR cho mọi endpoint mới (client A không đọc được B); bổ sung ảnh chụp vào services/*/docs sau mỗi tính năng.
