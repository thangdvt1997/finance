# DATA_AND_TOOLING_MARKET: quét thị trường dữ liệu và công cụ (2026-10-11)

Phạm vi: so sánh stack hiện tại (Dukascopy, vnstock, Frankfurter, RSS, GDELT, CFTC, SEC; Redis Streams; TimescaleDB; Grafana; React UI; ONNX NLP) với thị trường. Không chạy tính toán local; chỉ đọc file và tra web. KHÔNG thay đổi mã.

## 0. Độ tin cậy số liệu (đọc trước)
- [V] = đã đọc trang giá chính thức hôm nay: Twelve Data, Alpha Vantage, Alpaca, Tiingo, Marketaux, TheNewsAPI, NewsAPI.org (một phần), Norgate (có gói nhưng KHÔNG hiện giá).
- [3P] = chỉ từ bên thứ ba/tổng hợp/kết quả tìm kiếm (trang chính thức chặn 403 hoặc không tải được): Massive (Polygon), EODHD, FMP, Finnhub, Trading Economics, Databento (trích blog chính thức qua tìm kiếm), Benzinga, VPS. Coi là tham khảo, phải kiểm lại trước khi trả tiền.
- "chưa xác minh" = không tìm được nguồn đáng tin: SSI FastConnect, DNSE LightSpeed, FiinQuant/FiinTrade (biểu phí không công khai), MetaApi (trang giá không tải được), OANDA (giới hạn tốc độ hiện hành), TickData (chỉ biết tính theo symbol-năm, tối thiểu đơn 1.000 USD), Norgate (không thấy giá), Tickstory, điều khoản TrueFX.
- Giá thay đổi thường xuyên; mọi con số là USD/tháng tại 2026-10-11.

## 1. Nhà cung cấp dữ liệu

### 1.1 Forex/CFD, tick và bar
| Nhà cung cấp | Phủ | Độ trễ | Lịch sử | Giá / free tier | Giấy phép | Nhận xét |
|---|---|---|---|---|---|---|
| Dukascopy (đang dùng) | FX, kim loại, chỉ số CFD, tick | Tải file theo giờ (độ trễ cụ thể chưa xác minh) | Nhiều năm, tick từ ~2003 | Miễn phí | Điều khoản riêng, hiện trong JForex khi tải; KHÔNG tìm được văn bản công khai (chưa xác minh). Coi là cá nhân/nghiên cứu, không phân phối lại | Tick tốt cho backtest nhưng là giá ECN Thụy Sĩ, không phải giá broker của người dùng. GIỮ |
| TrueFX (Integral) | ~15 cặp FX, tick top-of-book | Real-time (cần tài khoản miễn phí) | Từ 2009, tải theo tháng | Miễn phí | Điều khoản chưa xác minh; coi là cá nhân | Nguồn thứ hai để đối chiếu Dukascopy; rẻ nhất để có "bản sao thứ hai" |
| OANDA v20 | FX, kim loại, CFD chỉ số | Stream real-time (~4 cập nhật/giây theo tài liệu cũ) | Nến từ 2005, S5 đến tháng; 5.000 nến/lần gọi (nguồn bên thứ ba) | Cần tài khoản fxTrade (practice miễn phí theo vignette cũ) | Cá nhân theo thỏa thuận API; giới hạn tốc độ chưa xác minh | Giá của một broker thật, REST sạch. ĐÁNG THÊM làm nguồn thứ hai |
| Massive (trước là Polygon.io) | Cổ phiếu, opts, FX, crypto, chỉ số, futures (thuê bao tách theo loại tài sản) | Real-time ở gói cao; gói rẻ trễ 15 phút/EOD | 2-20+ năm tuỳ gói | [3P] cổ phiếu: Free 5 gọi/phút; Starter 29; Developer 79; Advanced 199. Giá FX riêng: chưa xác minh. Flat-files S3 FX có ở gói Currencies Starter (EOD) | Cá nhân vs doanh nghiệp tách; phân phối lại cần Business | Rất tốt cho cổ phiếu Mỹ; phải kiểm trang giá FX |
| Databento | Futures CME/ICE, cổ phiếu Mỹ, opts, MBO/MBP; không phải FX bán lẻ | Real-time + lịch sử chuẩn tổ chức | Sâu (OHLCV 7 năm ở gói Standard) | [3P, trích blog chính thức] trả theo GB; tặng 125 USD credit lịch sử; CME Standard 199/tháng từ 2026-06-22 (khách cũ 179 giữ 12 tháng); phí sàn cộng thêm | Cá nhân/nội bộ; phân phối lại riêng | Chuẩn vàng cho futures (ES/GC/6E...). Chỉ đáng khi cần tick CME thật |
| Tiingo | Cổ phiếu/ETF 30+ năm, IEX, crypto; tin 3 tháng; FX không thấy trên trang giá | EOD + IEX | 30+ năm | [V] Starter 0 (500 mã/tháng, 50 req/giờ, 1.000/ngày); Power 30; Business nội bộ 50 (499/năm) | [V] "Internal use only"; phân phối lại giá riêng | Rẻ và sạch cho cổ phiếu Mỹ EOD |
| EODHD | 150k+ mã toàn cầu, EOD/intraday/fundamental/news | EOD; WS ở gói cao | 30+ năm | [3P] All-In-One 99,99; Fundamentals 59,99; EOD+Intraday 29,99; "từ 19,99" | Cá nhân; thương mại gói riêng | Phủ toàn cầu rộng theo giá; kiểm lại trang chính thức |
| Twelve Data | Cổ phiếu 20-70+ sàn, FX, crypto, ETF, chỉ báo | WS real-time (gói cao) | Tuỳ | [V] Free/Basic có thử miễn phí (thông số cụ thể chưa đọc được: chưa xác minh); Grow 79 (377 credit/phút, US real-time); Pro 229 (EU real-time, 1.597/phút); Ultra 999. Năm giảm 17% | [V] gói Individual = cá nhân/nội bộ/phi thương mại | Đã dùng trong market-collector |
| FMP | Cổ phiếu, FX, crypto, fundamentals, lịch kinh tế | EOD/intraday | 5 năm gói rẻ | [3P] Starter 22; Premium 59; Ultimate 149 (tính theo năm); trang chính thức 403 | Cá nhân; hiển thị/phân phối khác | Calendar có forecast; tầng nào có: chưa xác minh |
| Alpha Vantage | Cổ phiếu, FX, crypto, kinh tế, tin+sentiment | Real-time/15 phút ở gói trả phí | 20 năm | [V] Free 25 req/NGÀY; trả phí 49,99 (75/phút), 99,99 (150), 149,99 (300), 199,99 (600), 249,99 (1.200); gói 499-2.499 cho thương mại | [V] gói 49-249 cá nhân; thương mại đắt gấp 10 | Free quá nhỏ để vận hành |
| Alpaca | Cổ phiếu/opts/crypto Mỹ | Free: WS real-time chỉ IEX, 30 mã; API trễ 15 phút; 200 gọi/phút | 7+ năm | [V] Free 0; Algo Trader Plus 99 (SIP toàn sàn, OPRA, không giới hạn) | Cá nhân; cần tài khoản Alpaca | Free tier rất hào phóng. News API: trang không nêu (chưa xác minh) |
| Finnhub | Cổ phiếu, FX, crypto, tin, lịch, alt-data | Free ~60 gọi/phút | Tuỳ | [3P] Free ~60/phút (phi thương mại); trả phí từ ~50 đến 1.000+ (nguồn xung đột) | Free: cá nhân | Lịch kinh tế/FX candle ở tầng nào: chưa xác minh |
| Norgate Data | Cổ phiếu Mỹ/AU/CA (có delisted, thành phần chỉ số lịch sử), Futures 30+ năm continuous, Forex EOD từ 1991 | EOD | 1990+ | [V] có gói US Platinum/Gold/Silver, Futures Silver, Forex Silver; giá không hiện: chưa xác minh; chỉ Windows | Cá nhân | Chất lượng survivorship-bias-free tốt nhất cho backtest; bất tiện cho server Linux |
| Barchart, FXCM, Tickstory, TickData | Futures/FX/tick | - | - | TickData tính theo symbol-năm, tối thiểu 1.000 USD [3P]; còn lại chưa xác minh | - | Bỏ qua ở mức này; TickData chỉ khi cần tick tổ chức dài hạn |

### 1.2 Chứng khoán Việt Nam
| Nguồn | Trạng thái | Ghi chú |
|---|---|---|
| vnstock (đang dùng) | Giấy phép riêng (xem OSS_REUSE): bản Cộng đồng cá nhân/học tập, cấm phân phối lại | Giữ cờ TẮT mặc định |
| SSI FastConnect Data | EOD/real-time cổ phiếu + phái sinh; SDK Python/Node/Java/.NET; đăng ký tại chi nhánh/hồ sơ rồi lấy khóa ở iBoard | Biểu phí: chưa xác minh (không công bố). Cần tài khoản SSI |
| DNSE LightSpeed API | Trading API + Market Data cho khách có tài khoản DNSE; SDK Python `dnse` (WebSocket trades/quotes/OHLC, không chính thức) | Miễn phí market data hay không: chưa xác minh. Ứng viên tốt nhất cho real-time hợp pháp |
| FiinQuant / FiinTrade | Python lib, WebSocket tick HOSE/HNX/UPCOM, tích hợp đặt lệnh qua DNSE | Giá không công khai, chưa xác minh |
| VNDirect, TCBS, WiChart, Vietstock, CafeF, HOSE | Chưa kiểm trong lượt này | chưa xác minh; không khuyến nghị cào site tin |

Kết luận VN: đường hợp pháp và rẻ nhất là mở tài khoản DNSE/SSI để dùng API chính thức; FiinQuant nếu cần chất lượng tổ chức (hỏi giá).

### 1.3 Vĩ mô và lịch có consensus
| Nguồn | Giá | Ghi chú |
|---|---|---|
| Fair Economy `ff_calendar_thisweek.json` (đang dùng) | Miễn phí | Có `forecast` (consensus) và `previous`; `actual` thường trống; không thấy điều khoản redistribute, không SLA, giới hạn tốc độ không công bố. Giữ, kèm dự phòng |
| Trading Economics | [3P] Standard 149, Professional 299 (tính theo năm); Enterprise tuỳ biến; giá thực phụ thuộc tính năng/lượng/phân phối | Chuẩn thị trường cho calendar + consensus + 196 nước; trang giá đòi tài khoản |
| FMP / Finnhub / EODHD | xem 1.1 | Rẻ hơn, chất lượng consensus chưa xác minh |
| FRED (St. Louis Fed) | Miễn phí, cần khóa | Chuỗi vĩ mô sạch (kiến thức có sẵn, chưa kiểm hôm nay). ĐÁNG THÊM |
| Econoday | chưa xác minh | Bỏ qua |

ECB/BoE/BoJ/Fed/BLS đã có; chỗ trống thật là actual tức thì và consensus có SLA.

### 1.4 Tin thời gian thực và sentiment
| Nguồn | Giá | Ghi chú |
|---|---|---|
| RSS + GDELT (đang dùng) | Miễn phí | GDELT trễ ~15 phút, nhiễu |
| Marketaux | [V] Free 100 req/ngày (3 bài/req); Basic 29 (2.500/ngày, 20 bài); Standard 49 (10.000, 50 bài); Pro 99 (25.000, 100 bài); Pro 50K 199. Năm giảm ~17% | Tin gắn thực thể + sentiment |
| TheNewsAPI | [V] Free 100/ngày (3 bài); Basic 19 (2.500/ngày) | Tin tổng hợp, không chuyên tài chính |
| NewsAPI.org | [V] Developer free (phát triển); Business 449; Advanced 1.749 | Đắt, bỏ qua |
| Benzinga | [3P] Pro Plus ~457 có API (không chắc); API cần báo giá | Tin tổ chức; chưa xác minh |
| Dow Jones / Reuters | Báo giá doanh nghiệp (chưa xác minh) | Ngoài ngân sách |
| Tiingo News | Có trong Tiingo; lịch sử 3 tháng [V] | Rẻ |
| Alpaca/Finnhub news | Có trong tài khoản miễn phí (phạm vi chưa xác minh) | Dự phòng |

### 1.5 COT, order book, crypto
- CFTC COT: miễn phí, đã dùng. Giữ.
- Crypto/order book: Binance WS + ccxt (MIT) miễn phí; chỉ khi mở sang crypto.
- Sentiment/alt-data (retail positioning, Google Trends...): chưa khảo sát đủ, chưa xác minh.

## 2. Nền nghiên cứu / quant (chi tiết OSS ở OSS_REUSE.md)
| Hạng mục | Miễn phí tốt nhất | Khi nào đổi |
|---|---|---|
| Notebook | marimo (reactive, file .py, diff trong git) hoặc JupyterLab; VS Code Server | Nhóm >3 người: JupyterHub |
| Thí nghiệm/phiên bản dữ liệu | MLflow + DVC; lakeFS chỉ khi dữ liệu cỡ TB | Khi bắt đầu huấn luyện |
| Điều phối | cron + STATE_FILE hiện có; Prefect khi >5 pipeline | Có retrain/báo cáo nhiều bước |
| Cột/phân tích | DuckDB + Parquet + Polars | Khi lịch sử >10 GB |
| Lưu tick lớn | TimescaleDB nén; QuestDB/ClickHouse chỉ khi hàng trăm triệu hàng | Khi nén Timescale không đủ |
| Backtest | vectorbt (nghiên cứu nhanh), Nautilus Trader (event-driven, đường tới live), LEAN | Phase strategy |
| Rủi ro/hiệu suất | QuantStats, Riskfolio-Lib, PyPortfolioOpt, alphalens-reloaded, empyrical-reloaded, pyfolio-reloaded | Phase strategy |
| Qlib/FinRL | Chỉ nghiên cứu | Hoãn |
| LLM an toàn | Ollama (MIT, chạy CPU) với Qwen 1.5B-3B cho tóm tắt tin; vLLM cần GPU nên không hợp VPS CPU [3P]; OpenBB MCP đã spike | LLM chỉ tóm tắt, không ra quyết định; RAG dùng pgvector trong Postgres. Nguồn không thống nhất 1.5B vs 3B: tự thử trên VPS |

## 3. Hạ tầng
| Hạng mục | Miễn phí tốt nhất | Ghi chú |
|---|---|---|
| Proxy + SSO | Caddy + Authelia (nhẹ) hoặc Authentik (đủ OIDC, nặng hơn) | Authelia đủ cho 1 người dùng |
| Quan sát | Prometheus + Grafana đã có; Loki/Tempo + OTel khi cần | Chưa cần ngay |
| Bí mật | SOPS+age hoặc Infisical self-host | SOPS đủ cho 1 repo |
| CI | GitHub Actions hoặc Gitea Actions tự host | - |
| Đẩy thông báo | ntfy tự host (Go, SQLite; Apache-2.0 hoặc GPLv2) + Apprise làm router (xác minh ntfy trong danh sách plugin) cạnh Telegram; PWA: thêm manifest + Web Push cho web-ui | - |
| MT4/MT5 | EA outbound READ-ONLY hiện có là đủ; MetaApi (cloud, trả phí, giá chưa xác minh vì trang giá không tải); bridge OSS 2026 chưa khảo sát kỹ | Không trả MetaApi nếu EA đã ổn |
| VPS Windows/FX | [3P] ForexCheapVPS 4,99-8,99; VPS-Mart ~10; ForexVPS.net Core 25,60 (năm)/40 (tháng); QuantVPS từ 7,95; My Forex VPS từ 19,99 | Chọn gần máy chủ broker (NY4/LD4); độ trễ do nhà cung cấp tự công bố, chưa xác minh |

## 4. MA TRẬN: hiện tại -> miễn phí tốt nhất -> trả phí đáng giá (USD/tháng) -> khi nào nâng cấp
| Thành phần | Hiện tại | Miễn phí tốt nhất | Trả phí đáng giá | Khi nào nâng cấp |
|---|---|---|---|---|
| FX tick/bar | Dukascopy | + TrueFX + OANDA practice (đối chiếu) | Twelve Data Grow 79 [V] (WS) hoặc Massive FX (giá chưa xác minh) | Cần giá real-time <1s hoặc Dukascopy gián đoạn |
| Cổ phiếu Mỹ | chưa có | Alpaca Free [V] + Tiingo Starter [V] | Tiingo Power 30 [V] (EOD) hoặc Alpaca AT+ 99 [V] | Theo dõi >30 mã real-time/SIP |
| Futures/Chỉ số | chưa có | Dukascopy CFD chỉ số | Databento CME 199 [3P]; Norgate (chưa có giá) | Cần nến/tick futures thật |
| VN stocks | vnstock | tài khoản DNSE/SSI API | FiinQuant (báo giá, chưa xác minh) | Cần real-time hợp pháp hoặc phân phối lại |
| Vĩ mô/lịch | Fair Economy + ECB/BoE/BoJ/BLS/Fed | + FRED | Trading Economics Standard 149 [3P] | Cần consensus có SLA và actual tức thì |
| Tin | RSS + GDELT | + Marketaux Free, Alpaca/Finnhub news | Marketaux Basic 29 / Standard 49 [V] | Trễ tin 5-15 phút gây thiệt hại; cần entity-tagging chuẩn |
| COT | CFTC | CFTC | không cần | - |
| Bus | Redis Streams | Redis hoặc Valkey (BSD-3) | - | Replay dài: NATS JetStream |
| DB | TimescaleDB | + DuckDB/Parquet | - | Tick quá lớn: QuestDB/ClickHouse |
| UI/Cảnh báo | Grafana + React + Telegram | + ntfy/PWA | - | - |
| NLP | ONNX en/vi | + Ollama Qwen 1.5-3B tóm tắt | LLM API/GPU (chưa khảo sát) | Tóm tắt tay quá tốn thời gian |
| Bí mật/SSO/CI | .env, token | SOPS+age, Caddy+Authelia, GitHub Actions | Infisical Cloud (chưa xác minh) | >1 người dùng |
| MT bridge | EA READ-ONLY | EA hiện có | VPS Windows 8-40 [3P]; MetaApi (chưa xác minh) | Cần MT chạy 24/7 ngoài máy cá nhân |

## 5. BA GÓI CẤU HÌNH
### (i) 0 đồng
Dukascopy + TrueFX + OANDA practice (FX); Alpaca Free + Tiingo Starter (cổ phiếu Mỹ); FRED + Fair Economy + CFTC + ECB/BoE/BoJ; RSS + GDELT + Marketaux Free + Finnhub Free; vnstock (tắt) hoặc tài khoản DNSE/SSI; DuckDB/Parquet, marimo, MLflow; Caddy+Authelia, SOPS, ntfy, Ollama.
- Được: phủ FX, cổ phiếu Mỹ IEX/trễ, vĩ mô, tin; đủ theo dõi và nghiên cứu.
- Mất: tin trễ 5-15 phút, consensus không SLA, VN real-time chưa chắc hợp pháp, không futures thật, free tier có thể đổi bất cứ lúc nào, giấy phép chỉ cá nhân.

### (ii) ~50-100 USD/tháng
Gói (i) + Twelve Data Grow 79 [V] (real-time US + FX/20+ thị trường, dùng nội bộ) HOẶC Alpaca AT+ 99 [V]; thêm Marketaux Basic 29 nếu còn ngân sách (tối đa 2 trong 3 để không vượt ~100). Ví dụ: Twelve Data Grow 79 + VPS Windows nhỏ ~10 = ~89.
- Được: real-time hợp pháp trong phạm vi cá nhân, SLA mềm.
- Mất: chưa có consensus SLA, futures, tick tổ chức.

### (iii) ~300-500 USD/tháng
Gói (ii) + Trading Economics Standard 149 [3P] + Databento CME 199 [3P] (phí sàn cộng thêm) + Marketaux Standard 49 [V]. Tổng ~400-450 (bỏ Twelve Data nếu dùng Databento cho phần chính). Tuỳ chọn báo giá: FiinQuant, Norgate.
- Được: lịch+consensus chuẩn, tick futures thật, tin có thực thể ổn định.
- Mất/giới hạn: chưa có tin tổ chức (Benzinga/DJ/Reuters ngoài ngân sách); giấy phép vẫn cá nhân/nội bộ, phân phối lại cần thỏa thuận riêng; dư thừa nếu chưa có chiến lược cần.

## 6. NĂM NÂNG CẤP DỮ LIỆU ĐÁNG LÀM NHẤT (theo ROI)
1. Nguồn FX thứ hai miễn phí (TrueFX + OANDA practice) để đối chiếu Dukascopy và chống gián đoạn. 0 USD.
2. FRED + Alpaca Free/Tiingo Starter cho vĩ mô và cổ phiếu Mỹ. 0 USD.
3. Tài khoản DNSE hoặc SSI để dùng API VN hợp pháp thay vnstock. Phí chưa xác minh.
4. Marketaux (Free rồi Basic 29 USD) cho tin gắn thực thể + sentiment nuôi pipeline NLP.
5. Twelve Data Grow 79 (hoặc Alpaca AT+ 99) cho WebSocket real-time, chỉ khi đo được độ trễ hiện tại gây thiệt hại.
Khi vào phase strategy: Trading Economics 149 và Databento 199.

## 7. Cần kiểm lại / người dùng xác nhận
- Trang giá chính thức không tải được: Massive, EODHD, FMP, Finnhub, Trading Economics, MetaApi, OANDA docs. Kiểm tay trước khi trả tiền.
- Điều khoản Dukascopy/TrueFX/Fair Economy về lưu trữ dài hạn và phân phối lại (chưa tìm được văn bản công khai).
- Giá FiinQuant, SSI, DNSE: liên hệ trực tiếp.
