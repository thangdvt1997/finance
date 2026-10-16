# PLATFORM BENCHMARK — so sánh nền tảng giao dịch/phân tích với hệ thống của ta (2026-10-11)

Phạm vi: hệ thống READ-ONLY (theo dõi + thu thập + chuyên gia + MT4/MT5), chưa thực thi lệnh. Không phải khuyến nghị đầu tư.
Phương pháp: đọc PLAN/CONTRACTS/STRATEGY_OPTIONS/README (web-ui, analytics, alert-service) + tìm web (WebSearch, nguồn thứ cấp). **Kết quả tìm kiếm chủ yếu là trang đánh giá/affiliate; giá và tính năng bên dưới là ước lượng, ghi "chưa xác minh" khi không có nguồn chính thức.** Không truy cập được trang giá chính thức của hầu hết nhà cung cấp.

## 1. Bức tranh thị trường (rút gọn, có mức tin cậy)

### 1.1 Nhóm chuyên nghiệp / đắt tiền (để học hỏi, KHÔNG để cạnh tranh)
| Nền tảng | Điểm mạnh đáng học | Giá (ước lượng, chưa xác minh chính thức) |
|---|---|---|
| Bloomberg Terminal | Tin + dữ liệu + chat (IB) + hàng nghìn function; squawk; mọi thứ liên thông bằng mã | ~24-32k USD/người/năm (nguồn thứ cấp; không công bố giá) |
| LSEG Workspace (Refinitiv) | Dữ liệu + tin Reuters + Excel add-in | ~12-24k USD/người/năm (ước lượng) |
| FactSet | Phân tích cơ bản, screening, Excel/API, mô-đun hóa | ~12-40k USD/người/năm (ước lượng rộng) |
| TradingView | Biểu đồ + 80+ công cụ vẽ (theo quảng cáo), Pine Script, screener, replay, cảnh báo đa điều kiện, layout lưu cloud, mạng xã hội ý tưởng | Free; Essential ~12,95 / Plus ~29,95 / Premium ~59,95 / Ultimate ~199,95 USD/tháng (trả theo năm); cảnh báo 20/100/400/1000 theo gói (nguồn thứ cấp, hơi mâu thuẫn) |
| Koyfin | Dashboard phân tích cơ bản/vĩ mô/định giá, screener, rẻ hơn Bloomberg nhiều | Plus ~25 / Pro ~65 USD/tháng (nguồn của đối thủ, chưa xác minh) |
| Finviz Elite | Screener + heatmap ngành kinh điển, cảnh báo, backtest đơn giản, dữ liệu realtime | ~39,5 USD/tháng hoặc ~299,5/năm (nguồn thứ cấp) |
| TrendSpider | Tự động nhận diện mẫu hình/đường xu hướng đa khung, scanner, backtest không code | ~50-175 USD/tháng theo gói (nguồn không thống nhất) |
| Trade Ideas | Scanner realtime + AI "Holly" (chỉ thị trường Mỹ, không hợp ta) | ~89-254 USD/tháng |
| StockCharts | ChartLists, Point&Figure, scan ngôn ngữ riêng | chưa tra cứu |
| Bookmap / Quantower / Sierra Chart / ATAS | Order-flow: heatmap thanh khoản, footprint, DOM, replay tick; cần dữ liệu L2/tick từ sàn futures/crypto | Sierra ~26-56 USD/tháng + phí dữ liệu; ATAS ~40 EUR/tháng(?); Quantower ~70 USD/tháng(?); Bookmap cơ bản free, add-on trả phí — **đều chưa xác minh** |
| cTrader / MT5 | Market Depth (chỉ phản ánh thanh khoản của CHÍNH broker), Strategy Tester, Signals/Copy, cảnh báo, EA | miễn phí qua broker |
| Myfxbook / Darwinex / eToro | Phân tích tài khoản qua investor password (gain, DD, win%, lô, thời gian giữ, theo giờ/symbol), bảng xếp hạng, copy | Myfxbook có gói free giới hạn; Darwinex/eToro chi tiết chưa xác minh |
| Portfolio Visualizer | Phân tích danh mục: phân bổ, tương quan, backtest tài sản, Monte Carlo | free + trả phí (chưa xác minh) |

### 1.2 OSS tương đương
| OSS | License | Dùng cho ta | Ghi chú |
|---|---|---|---|
| OpenBB (Open Data Platform + Workspace) | Nguồn mâu thuẫn (AGPL vs "permissive" ngày 25/8/2026) — **kiểm GitHub trước khi dùng** | Lớp dữ liệu vĩ mô/giá qua 1 API; ta đã có spike MCP (`openbb_mcp_spike.md`) | Workspace hosted có gói free; bản tự host trả phí (nguồn thứ cấp: ~2.400 USD/năm, chưa xác minh) → chỉ nên lấy ODP làm lớp dữ liệu |
| Lightweight Charts (đang dùng) + plugin vẽ | Apache-2.0 | Công cụ vẽ: plugin cộng đồng (lightweight-charts-drawing ~68 tool, line-tools) — độ bảo trì chưa xác minh | TradingView **Advanced Charts** miễn phí chỉ cho dự án công khai có ghi công, không cho dùng cá nhân/riêng tư → KHÔNG dùng được |
| Grafana | AGPL-3 | Đã có; tốt cho time-series/hệ thống, không cho giao diện thị trường | |
| Apache Superset / Metabase | Apache-2.0 / AGPL (embed Metabase trả phí) | BI/báo cáo ad-hoc nội bộ nếu cần | Không thay web-ui |
| Ghostfolio | AGPL-3 | Theo dõi danh mục dài hạn (cổ phiếu/ETF/crypto), web self-host Docker (Postgres+Redis) | Hỗ trợ mã VN chưa xác minh |
| Wealthfolio | AGPL-3 | Desktop local-first (Rust/Tauri); sync trả phí | Ít hợp server của ta |
| FreqUI (Freqtrade) | GPL-3 | Mẫu UX dashboard bot/lệnh | Ta không làm crypto bot; chỉ tham khảo |
| QuantConnect LEAN / vnpy / Lumibot | Apache/MIT | Backtest/thực thi (giai đoạn sau) | Ngoài phạm vi theo dõi |
| Apprise, ntfy | OSS | Đã dùng Apprise | |

### 1.3 Công cụ Việt Nam (độ tin cậy thấp: tìm kiếm không trả về trang tính năng chính thức)
Xác minh được: Simplize có gói Professional ~599k VND/tháng (~5,99 triệu/năm) gồm "bộ lọc cổ phiếu nâng cao", xuất Excel/PDF, so sánh ngành (trang giá không ghi ngày). FireAnt có chỉ báo "thống kê khối ngoại" (khung daily). TCBS/TCInvest mô tả: bảng giá realtime + "bộ lọc thông minh", StockWatch/MarketWatch (dòng tiền theo ngành), TCAnalysis (lọc + biểu đồ). 24hmoney đăng bản tin dòng tiền hằng ngày (khối ngoại/tự doanh/cá nhân) — nội dung biên tập. SSI iBoard: realtime + cảnh báo theo mã. **Chưa xác minh** heatmap/gói giá/khối ngoại-tự doanh ở từng app; FiinPro/FiinTrade/WiChart/VNDirect/Vietstock/CafeF: không tìm được tài liệu hiện hành (FiinPro 2016: có room ngoại + khối ngoại realtime HOSE + 35 chỉ báo).
Mẫu chung (suy luận từ mô tả sản phẩm, không phải thống kê sử dụng): người dùng VN dùng nhiều nhất **(1) bảng giá realtime tùy biến theo nhóm, (2) bộ lọc cổ phiếu cơ bản+kỹ thuật, (3) dòng tiền khối ngoại/tự doanh/cá nhân, (4) heatmap ngành và VN-Index, (5) tin doanh nghiệp/BCTC/cổ tức, (6) định giá (P/E, P/B, so sánh ngành), (7) cảnh báo giá**.
Dữ liệu: khối ngoại realtime có trong bảng giá SSI/DNSE (API đăng ký); tự doanh do sở công bố (HOSE từng ngừng 3/2022, sau đó UBCK đề nghị công bố lại — hiện trạng chưa xác minh); vnstock miễn phí theo 1 fork chỉ lộ trường khối ngoại ở snapshot bảng giá, lịch sử dòng tiền ngoại còn hạn chế (chưa xác minh với bản chính thức).

## 2. Trạng thái hiện tại của ta (từ README)
Có: 9 trang (Tổng quan, Thị trường nến+volume realtime, Tin tức, Lịch kinh tế, Chuyên gia, Tài khoản MT4/MT5 READ-ONLY, Cảnh báo, Hệ thống, **Phân tích**: heatmap trạng thái, screener, chỉ báo trên nến TA-Lib, tương quan, phiên); tối/sáng; responsive 375px; WebSocket realtime; cảnh báo điều kiện (RSI cắt, EMA200, phá đỉnh/đáy, ATR, tương quan) → Telegram + Apprise, dedupe, digest; NLP sentiment tin; lịch kinh tế (nguồn miễn phí hiện không có actual/forecast); Grafana; basic auth + nginx; paper-trader (mô phỏng).

## 3. BẢNG GAP — tính năng chuyên nghiệp phổ biến
Giá trị cho mục tiêu (theo dõi + thông tin + chuyên gia + MT4/5): C=cao, T=trung bình, Th=thấp. Khó: D=dễ (≤2 ngày), V=vừa (≤2 tuần), K=khó (>2 tuần).

| # | Tính năng | Ta có? | Giá trị | Khó | Cách làm tốt nhất / OSS | Dữ liệu trả phí? |
|---|---|---|---|---|---|---|
| 1 | Watchlist đa nhóm (tạo/đổi tên/kéo thả: VN, FX, vàng, chuyên gia) | Một phần (bảng giá cố định; chưa thấy nhóm do người dùng tạo) | C | D-V | Lưu JSON phía server (bảng `user_prefs`) | Không |
| 2 | Bộ lọc/screener | Một phần (lọc theo trạng thái kỹ thuật) | C | V | Thêm bộ lọc cơ bản VN (P/E, P/B, ROE, vốn hóa, thanh khoản, %khối ngoại) + lưu bộ lọc; dữ liệu vnstock; tham khảo UI TCBS/Simplize/Finviz | Cơ bản: free (vnstock, không chính thức); ổn định: có thể trả phí |
| 3 | Đa biểu đồ / đa khung, đồng bộ crosshair | Một phần (1 biểu đồ) | T-C | V | Nhiều instance Lightweight Charts + đồng bộ crosshair | Không |
| 4 | Công cụ vẽ + lưu | Chưa | T | V | Plugin vẽ cộng đồng cho LWC v5, lưu JSON theo symbol. KHÔNG dùng Advanced Charts | Không |
| 5 | Replay | Chưa | Th-T | V | Phát lại nến từ `bars` bằng timer client | Không |
| 6 | Cảnh báo giá/điều kiện đa kênh | Có (Telegram+Apprise, dedupe, digest); thiếu cảnh báo GIÁ do người dùng tự đặt qua UI và điều kiện kết hợp | C | V | UI tạo luật → DB → alert-service đánh giá từ `md.quotes`; và/hoặc, hết hạn, lặp lại | Không |
| 7 | Lịch + tin realtime + squawk | Một phần: lịch có nhưng thiếu `actual/forecast`; tin RSS/GDELT; chưa squawk | C | V | Actual/forecast: FMP (free ~250 req/ngày; calendar có trong free chưa xác minh), Trading Economics (trả phí); cảnh báo "cửa sổ rủi ro tin" T-15..T+30; squawk hạ ưu tiên | Actual ổn định: có thể trả phí |
| 8 | Phân tích cơ bản + định giá VN (BCTC, P/E-P/B lịch sử, so sánh ngành, cổ tức, room ngoại) | Chưa | C (cổ phiếu VN) | K | vnstock + BCTC; Parquet/DuckDB; trang "Doanh nghiệp" | Nên trả phí nếu dùng nghiêm túc |
| 9 | Heatmap ngành/thị trường (treemap ngành × vốn hóa × %thay đổi) | Một phần (heatmap trạng thái kỹ thuật, không phải treemap ngành) | C (VN) | V | ECharts treemap (đã dùng ECharts); cần phân ngành cho mã VN | Phân ngành free (vnstock) hoặc bảng tự duy trì |
| 10 | Dòng tiền khối ngoại/tự doanh/cá nhân | Chưa | C (VN) | V-K | Snapshot bảng giá có trường khối ngoại; tự lưu lịch sử hằng ngày từ nay; tự doanh phụ thuộc công bố của sở (chưa xác minh) | Realtime ổn định: tài khoản SSI/DNSE |
| 11 | Order-flow / depth (heatmap thanh khoản, footprint, DOM) | Chưa | Th | K | FX/CFD không có sổ lệnh tập trung; DOM MT5 chỉ là thanh khoản broker. Cần L2/tick futures (đắt). **Bỏ.** | Có (đắt) |
| 12 | Nhật ký giao dịch (journal) + thẻ/ghi chú | Chưa | C | V | Dựng từ deal MT investor; TradeTally self-host (đã trong PLAN) hoặc tự viết bảng + ghi chú | Không |
| 13 | Phân tích tài khoản kiểu Myfxbook (gain, DD, win%, profit factor, lãi/lỗ theo giờ/phiên/symbol) | Một phần (equity + vị thế) | C | V | Tính từ lịch sử deal qua mt-bridge bằng pandas + QuantStats (OSS) | Không |
| 14 | Phân tích danh mục (phân bổ, tương quan, exposure theo tiền tệ) | Một phần (tương quan) | T | V | Netting exposure MT4/MT5; QuantStats/riskfolio-lib; Ghostfolio nếu cần theo dõi dài hạn | Không |
| 15 | Báo cáo PDF/HTML định kỳ | Chưa tự động (Grafana + Telegram) | C | D-V | Jinja2 + WeasyPrint → Telegram/email ngày/tuần; tóm tắt tin bằng NLP sẵn có | Không |
| 16 | Mobile app / PWA | Responsive 375px, chưa PWA | T | D | manifest + service worker; web push hoặc Telegram | Không |
| 17 | Chia sẻ / đăng ký, nhiều người dùng | Basic auth 1 lớp | Th-T | V | Chỉ khi mở cho người khác: Authelia/Keycloak sau reverse proxy | Không |
| 18 | API / webhook | API gateway nội bộ (key); nhận webhook Alertmanager; chưa webhook ra, chưa token theo người dùng | T | D | Webhook ra từ alert-service (Apprise); OpenAPI của FastAPI | Không |
| 19 | Dark/light | Có | — | — | — | — |
| 20 | Phím tắt | Chưa | Th-T | D | tinykeys: "/" tìm mã, "g m" đổi trang | Không |
| 21 | Layout tùy biến lưu được | Chưa | T | V | react-grid-layout + JSON server (chung bảng `user_prefs` với watchlist) | Không |
| 22 | Tìm kiếm toàn cục kiểu cmd-K (mã/tin/chuyên gia) | Chưa | T | D | cmdk + Postgres FTS | Không |
| 23 | Cảnh báo rủi ro tài khoản (margin level, DD ngày) | Một phần (snapshot có margin_level) | C | D | Luật alert-service trên `account.snapshots` | Không |
| 24 | Hiển thị độ tươi/nguồn dữ liệu trên mọi bảng giá | Một phần (trang Hệ thống) | C | D | Badge "dữ liệu trễ N phút + nguồn" — terminal chuyên nghiệp có, app VN thường thiếu | Không |

## 4. XẾP HẠNG ƯU TIÊN (Impact/Effort) — 20 hạng mục
Impact 1-5, Effort 1-5 (5 = nhiều công).

| Hạng | Hạng mục | Impact | Effort | Dữ liệu trả phí? |
|---|---|---|---|---|
| 1 | Cửa sổ rủi ro tin + `actual/forecast` trên lịch (phương án A STRATEGY_OPTIONS) | 5 | 2 | Tùy nguồn (FMP free hạn chế; Trading Economics trả phí) |
| 2 | Cảnh báo giá/điều kiện do người dùng đặt trên UI (đa điều kiện, hết hạn) | 5 | 2 | Không |
| 3 | Cảnh báo rủi ro tài khoản (margin, DD ngày, vị thế quá lớn) | 4 | 1 | Không |
| 4 | Watchlist đa nhóm + layout lưu (`user_prefs`) | 4 | 2 | Không |
| 5 | Báo cáo PDF/HTML ngày/tuần (WeasyPrint + Jinja2) | 4 | 2 | Không |
| 6 | Phân tích tài khoản kiểu Myfxbook + journal từ deal MT (QuantStats) | 5 | 3 | Không |
| 7 | Badge độ tươi dữ liệu/nguồn + cmd-K + phím tắt | 3 | 1 | Không |
| 8 | Heatmap ngành VN dạng treemap (ECharts) | 4 | 3 | Không (phân ngành vnstock) |
| 9 | Dòng tiền khối ngoại/tự doanh (tự lưu lịch sử từ snapshot) | 4 | 3 | Realtime ổn định có thể cần tài khoản SSI/DNSE |
| 10 | Screener cơ bản VN (P/E, P/B, ROE, thanh khoản) + lưu bộ lọc | 4 | 3 | Không (vnstock, không chính thức) |
| 11 | Đa biểu đồ/đa khung + đồng bộ crosshair | 3 | 3 | Không |
| 12 | PWA + web push | 3 | 1 | Không |
| 13 | Công cụ vẽ (plugin LWC) + lưu | 3 | 3 | Không |
| 14 | Trang Doanh nghiệp VN: BCTC, định giá lịch sử, cổ tức, room ngoại | 4 | 4 | Nên trả phí để ổn định |
| 15 | Webhook ra + token API theo người dùng | 2 | 1 | Không |
| 16 | Exposure theo tiền tệ/danh mục (netting MT4/MT5) | 3 | 3 | Không |
| 17 | Replay nến | 2 | 2 | Không |
| 18 | Lịch sự kiện doanh nghiệp VN (cổ tức, ĐHCĐ, phát hành) + công bố thông tin | 3 | 3 | Không (ToS nguồn chưa xác minh) |
| 19 | SSO/đa người dùng (Authelia) | 2 | 3 | Không |
| 20 | Squawk (TTS/âm thanh tin quan trọng) | 2 | 3 | Không |

Lựa chọn trả phí đáng giá (nếu muốn): (a) nguồn lịch kinh tế có `actual` (Trading Economics/FMP gói trả phí) — rẻ mà tác động lớn nhất cho bộ lọc rủi ro tin; (b) dữ liệu VN ổn định (SSI FastConnect Data/DNSE/FiinQuant; giá chưa xác minh) nếu làm cổ phiếu VN nghiêm túc; (c) TradingView Premium cho cá nhân (~60 USD/tháng, nguồn thứ cấp) như công cụ xem biểu đồ ngoài, không tích hợp được. Không đáng: Bloomberg/LSEG/FactSet cho quy mô này.

## 5. Khoảng cách LỚN NHẤT để giống một terminal chuyên nghiệp
1. **Độ phủ + chất lượng dữ liệu**: terminal có dữ liệu realtime có giấy phép, bid/ask thật, tick, actual/forecast, BCTC, khối ngoại/tự doanh; ta dùng nguồn miễn phí/không chính thức (ECB tham chiếu, vnstock, RSS) — nghiên cứu của ta cũng ghi nhận giới hạn này. Chỉ thu hẹp bằng tiền hoặc tài khoản broker/CTCK.
2. **Không gian làm việc cá nhân lưu được** (watchlist, layout, cảnh báo, vẽ): ta chưa có trạng thái người dùng phía server.
3. **Phân tích cơ bản/định giá cổ phiếu VN**: thứ người dùng VN dùng nhiều nhất, ta hầu như chưa có.
4. **Vòng khép kín journal → phân tích → báo cáo định kỳ**.
Ít quan trọng hơn thoạt nhìn: số công cụ vẽ, ngôn ngữ script (Pine), mạng xã hội.

## 6. ĐỪNG LÀM (không đáng)
- Order-flow/footprint/heatmap thanh khoản cho FX/CFD (không có sổ lệnh tập trung; L2 futures đắt).
- Tự viết lại biểu đồ kiểu TradingView/Pine Script; xin Advanced Charts (không dùng được cho mục đích riêng).
- Mạng xã hội/ý tưởng công khai, marketplace tín hiệu riêng (xung đột kết luận trung thực về copy-trade).
- Chat kiểu Bloomberg IB, mô phỏng function code Bloomberg.
- Thay web-ui bằng OpenBB Workspace (trùng chức năng; chỉ lấy ODP làm nguồn dữ liệu).
- Scanner intraday cổ phiếu Mỹ (Trade Ideas); "AI trade idea" sinh lệnh (LLM không ra lệnh — quy tắc dự án).
- App native (PWA + Telegram đủ).
- GUI backtest kiểu TrendSpider/StrategyQuant: backtest của ta cho thấy edge nhỏ; đầu tư vào dữ liệu và quản trị rủi ro trước.

## 7. Chưa xác minh
Mọi mức giá ở mục 1 (nguồn thứ cấp); giấy phép OpenBB sau 8/2026; calendar có trong gói free FMP; hiện trạng công bố tự doanh HOSE/HNX; tính năng và giá FiinPro/FiinTrade/WiChart/VNDirect/Vietstock/CafeF/SSI iBoard/24hmoney/FireAnt; độ bảo trì plugin vẽ LWC v5; Ghostfolio hỗ trợ mã VN; hiện trạng web-ui thực tế so với README (không mở giao diện thật, theo quy tắc không chạy local).

Nguồn (thứ cấp): pricingsaas.com/companies/tradingview; quantroutine.com/tools/tradingview-free-vs-pro; costbench.com, multiples.vc (giá Bloomberg/LSEG/FactSet); daytradingz.com, toolradar.com (Finviz/Trade Ideas/TrendSpider); openbb.co/pricing; tradingview.com/free-charting-libraries; github.com/deepentropy/lightweight-charts-drawing; simplize.vn/pricing; tcbs.com.vn; help.fireant.vn; atas.net/blog/best-heatmap-trading-software-2026; openalternative.co (Ghostfolio/Wealthfolio); devtoolpicks.com (Metabase/Grafana/Superset).
