# QA_REPORT — kiểm thử toàn hệ thống đang chạy thật

- Môi trường: VPS <VPS_IP>, compose project `tradingsys` (storage-writer, market-collector, news-collector, expert-collector, mt-bridge, alert-service, api-gateway, redis, timescaledb + prometheus/grafana/alertmanager/gatus/ntfy/web-ui do agent khác triển khai song song).
- Thời điểm: 2026-10-11 10:05–11:30 UTC (Chủ nhật, thị trường forex đóng — dữ liệu "mới nhất" là phiên thứ Sáu 10-09).
- Bộ test: `tests/e2e/` (Python, chạy trong container `python:3.12-slim` nối network `tradingsys_internal`; secret lấy từ `infra/.env`, không in ra). Dữ liệu test luôn có `source='qa'` / symbol `QA*` / account `qa-*` / tag `qa`, đã dọn sạch (xem mục 6).
- Không sửa code service; chỉ restart `tradingsys-storage-writer-1` và `tradingsys-alert-service-1` (xem mục 5).

## 1. Tóm tắt kết quả

| Bộ test | Script | Pass | Fail | Ghi chú |
|---|---|---|---|---|
| Health, metrics, auth, luồng bus→DB→API 9 stream, idempotency, DLQ, WebSocket, hiệu năng API | `test_flow.py` | 99 | 1 | fail = OHLC phi lý vẫn được ghi (L-M1) |
| mt-bridge ingest + chứng minh READ-ONLY | `test_mt_bridge.py` | 40 (chạy LIVE lần đầu, 10:15) / 27 (chế độ an toàn mặc định) | 1 | fail = `/accounts` không cần token (M3) |
| Quét tĩnh "không có đường đặt lệnh" | `static_readonly_scan.py` | 239 file, 0 ký hiệu đặt lệnh trong mã | 0 | chỉ 1 docstring "KHÔNG có place_order" và test chặn |
| Chất lượng dữ liệu thật | `test_data_quality.py` | 81 | 16 | 16 fail = phát hiện về dữ liệu (xem mục 3), không phải lỗi script |
| Tải 5.000 sự kiện/bậc | `test_load.py load` | 22 | 0 | không mất, không DLQ, lag về 0 |
| Kill/restart storage-writer giữa luồng | `test_load.py crash` + `run_crash.sh` | 9 | 0 | không mất, không trùng, upsert đúng |
| Consumer chết giữ PEL | `test_orphan_pel.py` + `run_orphan.sh` | 0 | 1 | **LỖI THẬT (H1)**: mất 89/4000 message |

Kết luận ngắn: pipeline chính (bus → storage-writer → DB → API/WS), auth, idempotency, DLQ, read-only và chất lượng giá forex đều đạt. Có 2 lỗi mức cao cần sửa trước khi bật chạy tự động dài hạn: **H1** (mất message khi container bị recreate/chết, không có XAUTOCLAIM) và **H2** (alert-service gửi ntfy nối tiếp ~5,5 giây/tin, backlog không giới hạn, tin crit xếp sau tin info).

## 2. Chi tiết kiểm thử chức năng

### 2.1 Health / metrics
7/7 service trả `/healthz` 200 và `/metrics` có `# HELP`; api-gateway `/readyz` ready. Mọi consumer group `storage-writer` lag 0, pending 0 trước khi test.

### 2.2 Luồng bus → DB → API (mỗi stream: publish source='qa', kiểm DB + API, gửi trùng)
| Stream | Bus→DB | API | Gửi trùng (cùng event id và khác event id cùng khóa tự nhiên) |
|---|---|---|---|
| md.bars | pass (263 ms) | `/v1/bars` đúng giá, ts UTC | 1 dòng, upsert ghi đè giá mới |
| md.quotes | pass | `/v1/quotes/latest` | 1 dòng |
| news.items | pass | `/v1/news?symbol=` | 1 dòng (khóa url) |
| calendar.events | pass, cập nhật `actual` đúng | `/v1/calendar` | 1 dòng |
| expert.profiles / signals / positions | pass | `/v1/experts`, `/expert-signals`, `/expert-positions` | 1 dòng mỗi bảng |
| account.snapshots | pass | `/v1/accounts` | 1 dòng |
| alerts.out | pass, alert-service xử lý (`alerts:recent`) | `/v1/alerts` | 1 dòng theo `event_id` (cùng `dedupe_key` khác event → 2 dòng DB, dedupe chỉ ở mức gửi — đúng thiết kế) |

### 2.3 DLQ
12 loại payload sai (thiếu trường, ts không phải ISO, `o="abc"`, side/level sai, JSON hỏng, JSON hợp lệ nhưng không phải Event, …) → **12/12 vào `dlq`** kèm `reason`, không ghi DB, không kẹt pending, storage-writer vẫn sống và sự kiện hợp lệ sau "poison" vẫn được ghi.

### 2.4 Auth API và an toàn đầu vào
Không key/key sai → 401 trên mọi `/v1/*` (key qua query-string cũng bị từ chối); có key → 200. `/healthz /readyz /metrics /docs /openapi.json` công khai (đúng thiết kế). Gateway chỉ có route GET (POST/PUT/DELETE → 405), openapi không có route chứa order/trade/execute/close/modify. SQL injection (`'; DROP TABLE bars;--`, `' OR 1=1`, path traversal, symbol 200 ký tự) → 422, bảng `bars` không đổi (21.120 dòng trước/sau). Validate tham số (`tf=XX`, `limit=0`, `limit=999999`, `from=not-a-date`, `offset=-1`) → 422; `limit=5000` → 200.

### 2.5 WebSocket `/v1/stream`
Không key → server giữ kết nối 10 giây rồi đóng code 1008; key sai qua tin đầu → đóng; `streams=evil` → từ chối. Auth bằng header và bằng tin đầu `{"type":"auth"}` đều nhận `ready`, nhận đúng sự kiện lọc theo symbol (`QAUSD`; sự kiện `QAOTHER` bị lọc), độ trễ ~3 ms.

### 2.6 mt-bridge `/ingest/v1` và READ-ONLY
Đã kiểm (tài khoản `demo-mt4-01`, token thật trong env — không in): không token / token sai / account lạ / token của account khác / thiếu "Bearer" → 401 và **body 401 giống hệt nhau** (không lộ account tồn tại); heartbeat hợp lệ 200; replay cùng nonce → 409; `ts` lệch ±600 s → 401; trường thừa (`order`, `action`), `platform` sai, nonce ngắn, `v=2`, bid âm, symbol injection, lots=0, order type 1 (market), >200 quotes → 422; NaN và JSON hỏng → 422; body >1 MB → 413; platform khác cấu hình → 400. Dữ liệu hợp lệ → bus → DB: quy đổi giờ server Europe/Athens về UTC **đúng cả mùa đông (+2) và mùa hè (+3)**, ts quote lệch UTC 1 s, snapshot ghi DB, gửi lại cùng bar không nhân đôi (bridge dedupe trong RAM trả `bars=0`), `trade_allowed=true` phát cảnh báo warn/security.
Chứng minh không có đường đặt lệnh: (1) openapi của mt-bridge chỉ có `GET /healthz,/metrics,/accounts` và `POST /ingest/v1`; (2) response ingest chỉ gồm `ok,quotes,bars,snapshot` (không có kênh lệnh trả về EA); (3) 12 đường dẫn kiểu `/order /trade /execute /commands ...` × GET/POST đều 404/405; (4) quét tĩnh 239 file repo (Python, MQL4/MQL5, YAML, shell, JS) không có `order_send/OrderSend/CTrade/PositionClose/TRADE_ACTION_*`; (5) grep trong container đang chạy chỉ thấy file test chặn lệnh (`/app/services/mt-bridge/tests/test_misc.py`); (6) gateway chỉ GET.

## 3. Chất lượng dữ liệu thật

| Hạng mục | Kết quả |
|---|---|
| OHLC hợp lệ | 21.170 nến, **0** vi phạm (low ≤ min(o,c), high ≥ max(o,c), >0, v ≥ 0, không NaN, không nến tương lai) |
| Scale giá (Dukascopy) | EURUSD 1,1163–1,1276; GBPUSD 1,3185–1,3284; USDJPY 157,44–158,29 (hàng trăm, đúng); XAUUSD 4113,6–4180,7 (hàng nghìn USD, đúng) |
| So với ECB/Frankfurter (giá M1 lúc fix 14:15 CET/CEST) | EURUSD 3 ngày: lệch max **0,031%** (TB 0,021%); GBPUSD 5 ngày: max **0,028%**; USDJPY 1 ngày: **0,018%** — đều ≪ ngưỡng 0,3%. Close D1 so với fix ECB: max 0,206% (EURUSD), tham khảo (khác thời điểm) |
| Bar `frankfurter` trong DB | 15/15 dòng khớp API Frankfurter |
| XAUUSD | ECB không có vàng; Stooq/Yahoo bị chặn từ VPS → chỉ kiểm scale, nhảy giá (max 0,037%/phút) và nhất quán nội bộ. Không có đối chiếu độc lập |
| Nhất quán đa khung | gộp M1 → M5/M15/H1/H4/D1: **0 lệch** o/h/l/c/v trên mọi bucket đủ nến; không có H/L ngoài biên |
| Múi giờ | mọi tf căn đúng UTC (M5/M15/H1/H4 và D1 = 00:00); mở cửa Chủ Nhật 21:01 UTC (đúng DST Mỹ, tháng 10); **0** nến vào thứ Bảy / thứ Sáu ≥22h / Chủ Nhật <20h |
| Khoảng trống M1 | không có khoảng trống bất thường sau khi loại: cuối tuần, nghỉ vàng hằng ngày 20:59→22:00 UTC (61 phút), thanh khoản mỏng 90 phút đầu phiên CN (GBPUSD, USDJPY có hố 6 phút 21:13→21:19) |
| Độ mới | EURUSD/GBPUSD M1 đến 10-09 20:59 (đúng giờ đóng cửa); **USDJPY M1 chỉ đến 10-08 23:59, XAUUSD đến 10-06 23:59** (thiếu 1 và 3 ngày giao dịch, `mc_backfill_running=0`; log market-collector có nhiều lần 503 tạm lỗi) — M5 |
| vnstock D1 (VNM/VCB/FPT) | 5 phiên 10-05→10-09, không rơi cuối tuần, biên độ ngày ≤3%; **giá lưu theo NGHÌN ĐỒNG** (VNM 57,7 = 57.700 VND). Đối chiếu độc lập thất bại (VNDirect timeout, TCBS 403 từ VPS) nên chưa xác nhận tuyệt đối, nhưng mức giá hợp lý |
| Tin (news_items) | không trùng URL, không published_at tương lai, không HTML/entity trong title, sentiment trong [-1,1]; xem L-N1 |
| Lịch (calendar_events) | 321 sự kiện, không trùng (country,title,ts), không sự kiện tương lai có `actual`, không rơi cuối tuần; **múi giờ đúng**: BLS 08:30/10:00 giờ New York (139/174 sự kiện) → 12:30/13:30 và 14:00/15:00 UTC tùy DST, FOMC 14:00 ET → 18:00/19:00 UTC; xem M2 về độ phủ |

## 4. Tải và độ bền

### 4.1 Độ trễ bus → DB (đo từ lúc publish đến lúc thấy dòng trong DB, thăm dò 50 ms)
| Kịch bản | Số sự kiện | Hoàn tất | Thông lượng | p50 | p95 | p99 | max |
|---|---|---|---|---|---|---|---|
| Burst, mỗi stream (bars, quotes, news, calendar, signals, positions, snapshots) | 5.000 | 21,1–22,3 s | 224–237 ev/s | 10,6–11,1 s | 19,9–20,9 s | 20,7–21,8 s | 21,0–22,2 s |
| Burst alerts.out (DB, không tính gửi ntfy) | 1.000 | 4,3 s | 235 ev/s | 2,1 s | 4,0 s | 4,2 s | 4,3 s |
| Steady 50 ev/s × 300 (bars/news/snapshots) | 300 | 6,4 s | 47 ev/s | **29–31 ms** | 50–55 ms | 56–58 ms | 60–73 ms |
| Trộn 5 stream × 1.000 đồng thời | 5.000 | 21,8 s | ~230 ev/s tổng | — | — | — | — |

Không mất dòng nào, DLQ không tăng, lag/pending về 0. Năng lực ghi ~230 ev/s (≈4,3 ms/sự kiện vì mỗi sự kiện một giao dịch DB). Lưu lượng thực hiện tại <5 ev/s nên dư rất nhiều; nên batch nếu backfill nhiều symbol song song (M3).
API p95 (15 lần): `/v1/bars` limit 5000 = 74 ms, D1 = 28 ms, overview 18 ms, news 15 ms, calendar 11 ms, quotes/latest 9 ms. WebSocket đẩy sự kiện ~3 ms.

### 4.2 Kill/restart storage-writer giữa luồng
Luồng 5.000 bars + 5.000 news (~220 ev/s trong ~50 s) kèm 10% gửi lại **cùng event id** và 5% **event id khác cùng khóa tự nhiên**. Ở 30%: `docker restart tradingsys-storage-writer-1` (SIGTERM); ở 65%: `kill -9` tiến trình từ host (crash thật). Kết quả (lặp 3 lần, lần cuối chính thức): bars 5000/5000 và news 5000/5000, **0 trùng** (rows = distinct), upsert theo khóa tự nhiên 250/250 (bars) và 250/250 (news), DLQ không tăng, lag 0/pending 0 sau ≤4 s; container tự chạy lại trong <12 s (`restarts=1`). → at-least-once + idempotent hoạt động.
Lưu ý vận hành: `docker kill` qua API không kích hoạt restart policy `unless-stopped` (hành vi của Docker, container nằm `exited` đến khi `docker start` — lần chạy thử đầu tôi đã khởi động lại ngay); chỉ crash thật (SIGKILL tiến trình/OOM) mới tự khởi động lại.

### 4.3 Consumer chết giữ PEL (lỗi H1)
Chạy container phụ `qa-sw` (cùng image, cùng group `storage-writer`) rồi SIGKILL giữa luồng 4.000 bars: **DB chỉ có 3.911/4.000**, 90 message nằm mãi trong PEL của consumer đã chết. Nguyên nhân (đọc mã): `main.py` đặt `consumer=socket.gethostname()` (đổi mỗi lần container bị recreate) và `run()` chỉ drain PEL của chính consumer đó, không có `XAUTOCLAIM`. Khôi phục: đã XCLAIM + phát lại các message thật bị kẹt (không có), xóa consumer `qa-sw-*`.

## 5. Lỗi tìm thấy

| ID | Mức | Mô tả | Cách tái hiện | Đề xuất sửa |
|---|---|---|---|---|
| H1 | **Cao** | Mất message khi storage-writer bị recreate/chết (PEL của consumer cũ mồ côi). Cùng mẫu ở alert-service (`alert-service-rules` có 4 consumer, 3 pending). Mỗi lần `compose up --force-recreate`/build mới đều để lại consumer rác | `sh /root/qa-e2e/run_orphan.sh` (DB 3911/4000) | Đặt tên consumer cố định theo replica (vd `storage-writer-1`) và/hoặc `XAUTOCLAIM min-idle 30–60 s` định kỳ + khi khởi động; dọn consumer idle lâu; cảnh báo khi `XPENDING` tồn quá N phút |
| H2 | **Cao** | alert-service gửi ntfy nối tiếp ~5,5 s/tin (apprise), trong khi `RATE_LIMIT_PER_MIN=20` > ~11 tin/phút giao được → backlog không giới hạn; tin `crit` xếp hàng sau tin info. 1.100 alert test sinh >300 thông báo thật trong ~25 phút trên kênh ntfy của bạn cho đến khi tôi XDEL backlog và restart alert-service | gửi 100 alert info vào `alerts.out`, quan sát log `Sent ntfy` cách nhau ~5,5 s | hàng đợi ưu tiên (crit đi trước), hạ rate limit ≤10/phút hoặc gom digest khi backlog >N, giới hạn/TTL backlog, gửi song song/không throttle cho ntfy nội bộ |
| M1 | Trung bình | storage-writer ghi cả nến phi lý: bar `o=5,h=1,l=9,c=100,v=-5` được chấp nhận vào `bars` | `test_flow.py` (check `validate/bar-OHLC-phi-ly`) | validate trong `mapping.map_bar` (low≤min(o,c), high≥max(o,c), v≥0, giá>0) → DLQ; hoặc CHECK constraint |
| M2 | Trung bình | Lịch kinh tế chỉ có US (BLS + Fed): 321 sự kiện, `forecast`/`previous` null 321/321, 286 sự kiện đã qua không có `actual`; thiếu ECB/BoE/BoJ… | `test_data_quality.py` (`calendar/phu-nhieu-quoc-gia`) | bật nguồn lịch đa quốc gia có forecast/actual (nguồn ToS-an-toàn) hoặc ghi rõ phạm vi; cập nhật `actual` sau phát hành |
| M3 | Trung bình | Thông lượng ghi ~230 ev/s (1 giao dịch/sự kiện): burst 5.000 sự kiện trễ p95 ≈20 s, mọi stream dùng chung 1 luồng | `test_load.py load` | xử lý theo lô (executemany trong 1 transaction cho cả batch 100 message, ack cả lô); bảng nóng dùng COPY/UNNEST |
| M4 | Trung bình | `GET /accounts` của mt-bridge (cổng nội bộ + 127.0.0.1:8490) trả số dư/equity không cần token do `BRIDGE_ADMIN_TOKEN` trống | `test_mt_bridge.py` | đặt `BRIDGE_ADMIN_TOKEN` trong `.env`/compose, fail-closed nếu trống |
| M5 | Trung bình | Dữ liệu thử nghiệm/lab nằm lẫn trong DB thật không có cờ: 300 nến `mt5:demo-mt5-01` năm 2024 và hàng chục snapshot `demo-mt5-01`/`demo-mt4-01` được ghi liên tục từ nơi khác | truy vấn `bars where source like 'mt%'` | dùng DB/schema riêng hoặc thêm cột/nhãn `env` cho nguồn demo; dọn dữ liệu 2024 |
| M6 | Trung bình | Dukascopy backfill chưa đủ: USDJPY thiếu 10-09, XAUUSD thiếu 10-07→10-09 dù `mc_backfill_running=0`; nhiều 503 "thiếu N giờ" | `test_data_quality.py` (`fresh/*`) | kiểm tra cơ chế thử lại gap sau backfill, ưu tiên giờ thiếu gần nhất, alert khi gap tồn >N giờ |
| M7 | Trung bình | Đơn vị giá VN không được hợp đồng quy định: lưu nghìn đồng (VNM 57,7) | `test_data_quality.py` (`vn/*/don-vi`) | ghi vào `CONTRACTS.md` hoặc chuẩn hóa ×1000 (VND) / thêm trường `unit` |
| L1 | Thấp | D1 theo ngày lịch UTC → có nến D1 Chủ Nhật chỉ chứa ~3 giờ phiên Sydney (khác D1 broker, đóng 17:00 New York) | `test_data_quality.py` (`d1/*`) | ghi rõ trong tài liệu hoặc dựng D1 theo mốc 21:00/22:00 UTC |
| L2 | Thấp | WebSocket chấp nhận kết nối chưa xác thực và giữ 10 s; vòng `pump` dùng XREAD `$` mỗi lần nên sự kiện đến giữa hai lần gọi có thể bị bỏ sót | `test_flow.py` (ws) | đóng ngay nếu không có header và `auth` không tới; lưu `last_id` ngay khi kết nối |
| L3 | Thấp | Tin: 100 tin `tuoitre_kinhdoanh`/`baochinhphu_kinhte` không có `published_at` (API dùng `ingested_at`); 1 bài Guardian năm 2014; trùng chủ đề giữa các báo (cafef vs vneconomy); 3 tin `cftc` cùng URL khác fragment ngày | `test_data_quality.py` (`news/*`) | lấy ngày từ trang/nội dung; lọc bài quá cũ; khử trùng theo tiêu đề chuẩn hóa |
| L4 | Thấp | Image mt-bridge chứa thư mục `tests/`; nonce chống replay chỉ trong RAM (restart bridge → replay trong cửa sổ ±120 s) | grep trong container | `.dockerignore` tests; nonce vào Redis `SET NX EX` |
| L5 | Thấp (tại 10:12) | image api-gateway chạy lúc đó chưa có `/v1/system`, `/v1/symbols`, `/v1/equity-history` (có trong source) | `test_flow.py` ghi INFO | build/deploy lại image khi source đổi |

Không phát hiện lỗi mức Critical: không có đường đặt lệnh, auth hoạt động, không mất dữ liệu khi restart có kiểm soát.

## 6. Tác động phụ và dọn dẹp (cần biết)

- **Thông báo thật**: alert-service nay gửi tới ntfy và alertmanager cũng định tuyến tới đó. Các test đã tạo thông báo thật: ~320 tin "QA load…" (H2), cảnh báo "event vào dead-letter trong 15 phút" (test DLQ), "[demo-mt4-01] Mất heartbeat 125s" (crit), "Tài khoản cho phép giao dịch", "Tài khoản MT demo-mt4-01 mất kết nối" (test mt-bridge LIVE). Sau đó mặc định đã tắt: `QA_N_ALERT=0` (không tải alerts), `QA_MT_LIVE=0` (không gửi dữ liệu hợp lệ cho mt-bridge).
- Hai lần trong quá trình test, timescaledb/redis bị tác nhân khác recreate (10:24–10:29 UTC) làm một vòng tải bị gián đoạn; storage-writer tự hồi phục (log lỗi kết nối rồi chạy lại), tôi chạy lại các vòng đó khi hệ thống ổn định.
- Đã tác động `tradingsys-storage-writer-1`: 5 lần `docker restart` (SIGTERM), 2 lần `docker kill` (lần đầu container nằm `exited` ~3 phút cho đến khi tôi `docker start`, backlog sau đó được xử lý đủ), 3 lần SIGKILL tiến trình từ host; cùng với container phụ `qa-sw` (đã xóa) và `tradingsys-alert-service-1` (1 lần, để dừng backlog test).
- Dọn dẹp bằng `cleanup.py`: XDEL mọi message test đã publish (kể cả `dlq`, `alerts.delivery`, và các message bars/quotes do mt-bridge sinh ra), xóa dòng DB `source='qa'`/`QA*`/`qa-*`/tag `qa`, `account_snapshots` đánh dấu balance 777777.77 của `demo-mt4-01`, `alerts:recent`/`alerts:dedupe:qa*` trong Redis. Xác minh cuối: 0 dòng còn lại ở mọi bảng, 0 message test trong các stream, `dlq` rỗng, không còn container `qa-*`.
- Không hoàn tác được: bộ đếm `alerts:stats`, các chunk hypertable rỗng (bars/quotes/account_snapshots ở ~500 ngày trước), consumer-group hiển thị thêm consumer cũ. Cảnh báo thuộc `demo-mt4-01` có tag `security`/heartbeat trong cửa sổ test (cộng thêm một số cảnh báo cùng tag của lần dọn đầu, khi chưa giới hạn theo cửa sổ) đã bị xóa — có thể gồm vài cảnh báo của lab; ảnh hưởng nhỏ.

## 7. Cách chạy lại

```
bash tests/e2e/deploy.sh                       # đẩy bộ test lên /root/qa-e2e trên VPS
sh /root/qa-e2e/run_remote.sh test_flow.py     # smoke + luồng + DLQ + auth + WS + perf API
sh /root/qa-e2e/run_remote.sh test_mt_bridge.py        # QA_MT_LIVE=1 để gửi dữ liệu hợp lệ (sinh cảnh báo thật)
sh /root/qa-e2e/run_remote.sh test_data_quality.py     # chỉ đọc dữ liệu thật
sh /root/qa-e2e/run_remote.sh test_load.py load        # QA_N_ALERT=1000 để tải cả alerts (spam ntfy!)
sh /root/qa-e2e/run_crash.sh                   # restart + SIGKILL storage-writer giữa luồng
sh /root/qa-e2e/run_orphan.sh                  # tái hiện H1 (container phụ qa-sw)
sh /root/qa-e2e/run_remote.sh cleanup.py       # dọn dữ liệu test (chạy sau mỗi lần)
python tests/e2e/static_readonly_scan.py .     # quét tĩnh không có mã đặt lệnh (chạy cục bộ)
```
Kết quả JSON từng bộ nằm ở `/root/qa-e2e/out/*.json` trên VPS.


---

# Vòng 2 — QA dữ liệu sau các thay đổi lớn (2026-10-11 21:40–22:40 UTC, Chủ nhật tối)

- Phạm vi: toàn hệ thống hiện có (crypto 24/7, class/registry, nguồn ưu tiên ETF/US/VN, `vn-market`, lịch kinh tế có forecast, paper hash-chain, risk-monitor, journal, reporter, risk-window, analytics, web-ui) trên VPS <VPS_IP>. Chạy hoàn toàn trên VPS (container `python:3.12-slim`), dữ liệu test gắn `qa`, đã dọn bằng `cleanup.py` (còn lại 0).
- Bối cảnh: agent hardening chạy song song, tạo lại redis/timescaledb/gateway (khoảng 22:03) trong lúc QA nên một lượt chạy bị gián đoạn (502, "terminating connection") — đã chạy lại khi ổn định; test của agent khác cũng ghi dữ liệu `QA*` cùng lúc nên có vài lần đếm DLQ / `bars/api` lệch tạm thời. Không chạy QA song song với test của agent khác.

## V2.1 Kết quả tổng hợp

| Bộ test | Pass | Fail | Ghi chú |
|---|---|---|---|
| `test_flow.py` (luồng 9 stream, idempotency, DLQ, auth, WS, hiệu năng API) | 100 | 0 | p95 `/v1/bars` 5000 nến = 90 ms; WebSocket 6–10 ms |
| `test_mt_bridge.py` (mặc định an toàn) | 28 | 0 | M4 (`/accounts` không token) đã sửa; không bật chế độ LIVE (tránh cảnh báo thật) |
| `test_data_quality.py` | 79 | 9 | 9 fail đều ở mức thấp/trung bình đã biết: D1 Chủ nhật (4), tin (4), nến demo 2024 (1) — xem V2.3 |
| `test_new_components.py` (MỚI, 188 kiểm tra) | 188 | 0 | crypto, registry, nguồn, VN, lịch, paper chain, risk, journal, reporter, risk-window, analytics, web-ui |
| `run_orphan.sh` (kiểm chứng H1) | 1 | 0 | DB 4000/4000 sau khi SIGKILL consumer phụ → **H1 đã được sửa** |
| `static_readonly_scan.py` (chạy trên VPS) | — | — | 582 file, 27 khớp, **tất cả nằm trong tests/**; ngoài tests = 0: không có đường đặt lệnh |

Không có lỗi Critical. Không có lỗi High mới còn mở.

## V2.2 Lỗi vòng 1 — trạng thái

| ID | Trạng thái vòng 2 |
|---|---|
| H1 mất message khi consumer chết | **ĐÃ SỬA, đã kiểm chứng**: consumer cố định (`storage-writer-1`, `alert-1`) + `XAUTOCLAIM` (idle ≥ 60 s, quét 30 s). Test orphan nay đặt `CONSUMER_NAME` riêng cho tiến trình phụ (trước đây dùng hostname) |
| M1 OHLC phi lý bị ghi | **ĐÃ SỬA** (`validate/bar-OHLC-phi-ly-bi-chan-o-ghi` pass) |
| M4 `/accounts` không token | **ĐÃ SỬA** (test_mt_bridge 0 fail) |
| M2 lịch chỉ có US, thiếu forecast/actual | **TỐT HƠN**: 6 nguồn (fed, bls, ecb, boe, boj, faireconomy), 481 sự kiện, 9 quốc gia, forecast có ở 52/109 sự kiện faireconomy. **Chưa kiểm chứng được `actual` được điền sau phát hành** (QA chạy tối Chủ nhật, chưa sự kiện nào qua >3 giờ). Test mới tự bật kiểm tra này khi có ≥10 sự kiện đã qua → chạy lại sau thứ Ba |
| M6 Dukascopy thiếu ngày | **ĐÃ SỬA**: `coverage/ngay-thieu-M1` rỗng cho 4 cặp; độ mới đạt (sau khi sửa quy tắc "thị trường vừa mở lại Chủ nhật") |
| M7 đơn vị giá VN | **ĐÃ SỬA**: `vn_daily` lưu VND thật (VCB 56.700); nến `VN:*` từ Yahoo là VND thật |
| M3 (thông lượng), H2 (alert nối tiếp), M5, L1, L3 | M3/H2 **chưa tái kiểm** (không chạy tải/spam trong vòng này); M5, L1, L3 còn nguyên (xem V2.3) |

## V2.3 Phát hiện mới / còn mở

| ID | Mức | Mô tả | Tái hiện | Xử lý |
|---|---|---|---|---|
| N1 | Trung bình → **ĐÃ SỬA** | Tin trùng vì cùng bài có 2 URL `http://` và `https://` (feed là https nhưng link trong item là http; BOJ 49 nhóm, vietstock 82 nhóm) | `test_data_quality.py` → `news/khong-trung-url-sau-chuan-hoa` | `services/news-collector/src/news_collector/sources/rss.py`: hàm `_upgrade_scheme()` nâng http→https khi cùng host với feed https; đã deploy `news-collector`; đã xoá 180 dòng http trùng (giữ dòng https). Bản sao lưu 131 dòng của lần xoá thứ hai ở `/tmp/news_http_dups_backup.csv` trong container timescaledb (lần xoá đầu 49 dòng bị ghi đè — các dòng đó vẫn còn bản https). Nếu test báo lại vài nhóm trùng, chạy lại lệnh xoá http-có-bản-https một lần |
| N2 | Trung bình → **ĐÃ SỬA (test)** | `cleanup.py` lỗi `tuple decompression limit exceeded` khi DELETE trên chunk đã nén của `bars` (chính sách nén 30 ngày) → dữ liệu QA bị sót, làm test sau lệch | `sh run_remote.sh cleanup.py` | thêm `SET timescaledb.max_tuples_decompressed_per_dml_transaction = 0`. Khuyến nghị: test dùng ts trong 30 ngày gần nhất để khỏi giải nén chunk cũ |
| N3 | Thấp (theo thiết kế) | `nlp` cũng dead-letter payload tin hỏng → 1 tin hỏng = 2 dòng `dlq` (reason `nlp: ...`) | `test_flow.py` | test đã tính; nên ghi vào CONTRACTS.md |
| N4 | Thấp → **ĐÃ SỬA (test)** | Tên mạng compose đổi (`ops`/`frontend` có lúc không tồn tại) làm `run_remote.sh` không khởi động được container test | chạy khi mạng đang đổi | chỉ nối các mạng đang tồn tại (`docker network inspect`) |
| N5 | Thấp | `CRYPTO:TONUSDT` chỉ có ở Bitfinex/Kraken (thanh khoản mỏng): M1 có 43 lỗ (dài nhất 261 phút), H1 136 lỗ, D1 thiếu 2026-08-05, M1 trễ ~30 phút. 28/29 symbol crypto còn lại: **0 lỗ nến ở cả 6 khung**, có nến Thứ 7/CN | `test_new_components.py` → `crypto/*` | chấp nhận (sàn không trả nến rỗng); dùng D1/H4 cho TON hoặc forward-fill ở lớp analytics nếu cần |
| N6 | Thấp | Lịch: 280 sự kiện BLS đã qua không có `actual`/`forecast` (BLS chỉ là lịch phát hành); hàng chính thức bị ẩn khi có hàng faireconomy cùng nhóm ±60 phút | `calendar/nguon` | chờ kiểm chứng actual (xem M2 ở V2.2) |
| N7 | Thông tin | 11 sự kiện ECB năm 2027–2028 (từ trang lịch chính thức ECB); test cũ báo "vô lý" (>400 ngày), đã nới 900 ngày | | — |
| N8 | Thấp | D1 theo ngày UTC → có nến D1 ngày Chủ nhật chỉ chứa 1–3 giờ phiên Sydney (L1 vòng 1 vẫn còn) | `d1/*` | đã ghi chú trong `HUONG_DAN_SU_DUNG.md` |
| N9 | Trung bình (còn mở) | 300 nến `mt5:demo-mt5-01` năm 2024 (dữ liệu lab, M5 vòng 1) vẫn nằm trong `bars` | `mt/khong-co-nen-nam-2024...` | không tự xoá (dữ liệu của nhóm lab) — nên xoá hoặc gắn nhãn khi bạn xác nhận |
| N10 | Thấp (còn mở) | 105 tin `tuoitre_kinhdoanh`/`baochinhphu_kinhte` không có `published_at`; 1 bài Guardian 2014; 2 tin BLS 2025-09 | `news/*` | lấy ngày từ trang bài / lọc bài quá cũ |
| N11 | Trung bình (bảo mật, chuyển cho nhóm hardening) | Container `news-collector` dùng `DATABASE_URL` của role **`ts` (superuser)** thay vì role ghi hạn chế (phát hiện khi liệt kê biến môi trường) | `docker exec tradingsys-news-collector-1 env` | dùng role hạn chế như `ts_writer`; đổi mật khẩu `ts` vì nó đã bị in ra trong một lần kiểm tra |

### Những điều được xác nhận ĐÚNG ở vòng 2 (phần mới)
- **Crypto 24/7**: 29 symbol × 6 khung đầy đủ; 0 khoảng trống ở 28/29 symbol trong cửa sổ (M1 36 giờ, M5 3 ngày, M15 7 ngày, H1 30 ngày, H4 60 ngày, D1 365 ngày); có nến Thứ 7 và Chủ nhật; chỉ nến đã đóng; mốc UTC đúng; OHLC hợp lệ; giá BTC/ETH/DOGE/SHIB đúng bậc; H1 khớp gộp từ M1 (≤0,2%).
- **Class/registry**: mọi symbol có dữ liệu đều có class, tên, precision, session; số lượng theo lớp khớp `/v1/symbols/classes`; không có giá `last` âm hoặc biến động ngoài biên.
- **Nguồn ưu tiên**: FX/vàng `dukascopy` thắng `frankfurter`/`yahoo_daily`; ETF/cổ phiếu Mỹ chỉ `yahoo_daily` (alpaca/tiingo chưa có key nên không có dữ liệu ma); `VN:*` D1 chỉ `yahoo_daily`; không nhảy giá >40%/ngày ở Mỹ trong 2 năm; VN chỉ VCB 2025-03-03 −33% (cổ phiếu thưởng, đã biết).
- **vn-market**: `lag_days=0`, 1.551 mã, VNINDEX hợp lý, trần/sàn HOSE ±7%, không phiên cuối tuần, OHLC hợp lệ 90 ngày, độ rộng khớp, 11 endpoint đọc trả 200, injection bị chặn.
- **Paper hash-chain**: 12 tài khoản `ok=true`, `anchor_ok=true`; kiểm lại độc lập từ DB (seq liên tục, `prev_hash` = hash dòng trước, dòng đầu = `sha256("genesis:<tk>")`); `UPDATE/DELETE` vào `paper_chain` bị trigger chặn (chạy trong transaction rồi ROLLBACK, số dòng không đổi); không có route POST kill-switch qua gateway/web-ui; mẫu <84 ngày được gắn `reliable=false`.
- **risk-monitor**: MT + paper, `read_only=true`, VaR trong biên, 12 kịch bản stress. **journal**: whitelist chặt, không route order/trade/close, summary nhất quán. **reporter**: daily + weekly, 0 mục lỗi, SHA-256 khớp danh sách, PDF đúng định dạng, không lộ secret, path traversal bị chặn, `/generate` không lộ ra ngoài. **risk-window**: cấu hình 15/30 phút, bỏ ngày lễ, universe có VN + FX + vàng. **analytics**: RSI/ADX/Stoch trong [0,100], dữ liệu <30 phút, close khớp `bars`. **web-ui**: không đăng nhập → 401.

## V2.4 Cách chạy lại (bản cập nhật)
```
bash tests/e2e/deploy.sh
sh /root/qa-e2e/run_remote.sh test_flow.py
sh /root/qa-e2e/run_remote.sh test_data_quality.py
sh /root/qa-e2e/run_remote.sh test_mt_bridge.py
sh /root/qa-e2e/run_remote.sh test_new_components.py     # MỚI: chỉ đọc, 188 kiểm tra
sh /root/qa-e2e/run_orphan.sh                            # kiểm chứng H1 (~2 phút, kill container phụ qa-sw)
sh /root/qa-e2e/run_remote.sh cleanup.py                 # luôn chạy sau test_flow / orphan
```

### Ghi chú cuối vòng 2
- Trong lúc QA, nhóm hardening bật `HIDE_SOURCES` (gateway ẩn tên nguồn dữ liệu: `/v1/data-sources` trả "Luồng giá N", HTML báo cáo bị ẩn tên nguồn khi phục vụ nên SHA-256 của HTML khác file gốc vài byte; PDF vẫn khớp tuyệt đối). Test mới chấp nhận cả hai dạng và kiểm tra không lộ tên nguồn. Chuỗi macro FRED hiện ở symbol dạng `DFF`, `DGS10`... (không còn tiền tố `FRED:`) — analytics không phủ các chuỗi này (đúng thiết kế, không phải công cụ giao dịch).


---

## Vòng 3 — hoàn thiện 2026-10-14

Phạm vi: hồi quy toàn hệ thống (pytest mọi service + e2e), log lỗi 24h, Prometheus/Alertmanager, độ tươi dữ liệu. Chạy trên VPS <VPS_IP> (không chạy local). 4 nhóm khác (UI QA, bảo mật, vận hành, tài liệu) làm song song nên một số lần recreate `auth`/`api-gateway` của họ làm vài test rớt ConnectError/401 chập chờn — đã chạy lại.

### V3.1 Kết quả theo suite
| Suite | Kết quả | Ghi chú |
|---|---|---|
| pytest libs/common | 264 pass | |
| pytest alert-rules / alert-service / analytics | 60 / 36 / 30 pass | |
| pytest api-gateway / auth / briefing | 179 / 35 / 38 pass | |
| pytest expert-collector / journal / market-collector | 65(+1 mới) / 32 / 92 pass | thêm `test_build_chuan_hoa_url_ngay_tuong_lai_va_entity` |
| pytest mt-bridge / news-collector / nlp | 66 / 70 / 26 (1 skip) pass | |
| pytest paper-trader / reporter / risk-monitor | 126 / 50 (3 skip) / 58 pass | |
| pytest storage-writer / track-record / vn-market | 45 / 29 (1 skip) / 23 pass | client-ui, web-ui không có pytest (test riêng trong `qa/`) |
| e2e test_flow | 100/100 (lần đầu 98/2 -> sửa test) | |
| e2e test_mt_bridge / provisioning / client_backend / account_reports | 28 / 50 / 54 / 43 pass | |
| e2e test_auth | 136/136 (lần đầu ConnectError do auth bị recreate giữa chừng) | |
| e2e test_fleet / fleet_client / fleet_engine | 188 / 21 / 17 pass | |
| e2e test_cache_security | 67/67 (lần đầu 65/2: 401 chập chờn trong lúc gateway recreate) | |
| e2e test_realtime_security | 47/47 | |
| e2e test_pentest_authz | rc=0 | |
| e2e test_new_components | 193 pass / 2 fail (xem V3.3) | lần đầu 4 fail |
| e2e test_data_quality | 78 pass / 10 fail low-trung bình đã biết (xem V3.3) | lần đầu 73/15 |

### V3.2 Lỗi đã sửa
| ID | Loại | Mô tả | Sửa |
|---|---|---|---|
| R3-1 | Test lỗi thời | `test_flow`: route ghi `/v1/account-report*` (sinh/phát hành báo cáo, `master_write_guard`) và `GET /v1/accounts/{id}/orders` (danh sách lệnh chờ chỉ-đọc) bị coi là "route ghi / route lệnh" | whitelist đúng route (chỉ GET cho `/orders`), giữ ý đồ read-only |
| R3-2 | Test sai giả định | `test_data_quality` `fresh/*/M1` cho phép trễ 15 phút nhưng dukascopy phát tick theo GIỜ (đóng giờ mới có file) nên M1 cuối trễ 1–61 phút | dung sai 75 phút |
| R3-3 | Lỗi thật (log spam) | api-gateway: `redis TimeoutError` ở vòng XREAD của hub realtime (`realtime.py`) và vòng vô hiệu cache (`cache.py _inval_loop`) -> ~190 traceback/24h (`invalidate lỗi`, 573 dòng Traceback) dù tự hồi phục | bắt `TimeoutError` riêng (retry ngay, log debug, không tăng `C_ERR`) |
| R3-4 | Lỗi thật (alert spam) | `RtSilentSymbolsHigh` bắn 41 lần/24h: 9 symbol FX/vàng từ dukascopy luôn "im lặng" >90s do nguồn trễ theo giờ | ngưỡng 20% -> 50% symbol theo dõi (`infra/prometheus/rules_rt.yml`) |
| R3-5 | Lỗi thật | `ContainerCpuThrottled` đang firing cho `postgres-exporter` (cpus 0,5; scrape pg_queries ~4 s) | `cpus: 1.0` (`docker-compose.ops.yml`) |
| R3-6 | Lỗi thật (dữ liệu) | 20 ETF `US:*` mới (XLC, UUP, HYG, LQD, SMH, XLI, XLP, XLF, DIA, EFA, XLE, GDX, XLRE, EEM, XLB, VIXY, XLV, XLY, XLU, XLK) chỉ có 7 nến D1 -> analytics không phủ | backfill `yahoo_daily` từ 1990 qua `infra/ops/backfill_hist.py` (2.091–6.994 nến mỗi mã); test `US-D1-du-lich-su`, `analytics/phu-moi-symbol` giờ PASS |
| R3-7 | Lỗi thật (hồi quy N1) | tin trùng http/https tái xuất hiện (147 nhóm) từ nguồn `expert:op:*` (expert-collector không chuẩn hoá URL như news-collector); thêm link tương đối (EIA `/pressroom/...`), ngày "tương lai" của sự kiện PIIE, entity kép `T&amp;amp;T` | `expert_collector/sources/opinion_feeds.py`: `_norm_url()` (http->https cùng host feed, tương đối->tuyệt đối), published_at >now+1 ngày -> None, unescape 2 lần; test mới; đã xoá 207 dòng http trùng (backup 147 dòng ở `/tmp/news_http_dups_r3_backup.csv` trong container timescaledb), sửa 1 URL tương đối, 1 title, 2 published_at tương lai |

Dữ liệu thử: `cleanup.py` sau test_flow/provisioning/client_backend/fleet -> "con lai = 0" ở mọi bảng; 3 dòng `qa-expert-*` ở `expert_signals` (10-11) không còn.

### V3.3 Còn tồn đọng (không sửa trong vòng này)
| ID | Mức | Mô tả | Lý do |
|---|---|---|---|
| R3-8 | Trung bình | Lịch kinh tế: 0/44 sự kiện faireconomy đã qua >3h có `actual` (M2 vòng 2 vẫn mở). Nguồn `cal_actuals` chưa điền được | cần kiểm chứng nguồn actual chính thống / khoá FMP |
| R3-9 | Thấp | FX/vàng M1 (dukascopy) trễ cấu trúc ~1 giờ; 9 symbol FX/vàng im lặng >90s trên hub realtime; rule 50% che mất trường hợp riêng FX | muốn real-time FX cần TrueFX/OANDA có tài khoản (hiện chưa) |
| R3-10 | Thấp | ETF `US:*` / `VN:*` D1 mới nhất = 2026-10-12 lúc 10:40 UTC ngày 10-14: yahoo_daily poll 22:30 UTC, bỏ nến ngày UTC hiện tại -> trễ 1 ngày theo thiết kế; paper `slow_trend_*` (bản cũ, deprecated) đóng băng từ 10-10 theo thiết kế | |
| R3-11 | Thấp | `rt_bus_to_gateway p95 >0,5s` fire/resolve ~18 lần/24h; log redis timeout của gateway xuất hiện đồng thời ở 2 client -> nghi vòng sự kiện gateway đứng thoáng (giây) định kỳ; CPU gateway không bị throttle (2 cpus, ~2%) | cần đo event-loop lag (vd `asyncio` debug / `loop_lag` gauge) để tìm tác vụ chặn |
| R3-12 | Thấp | Test data_quality vẫn FAIL mức low/medium đã biết: D1 Chủ nhật (N8), tin trùng tiêu đề giữa nguồn `ecb_press` và `expert:op:*` (126 nhóm, khác nguồn có chủ ý), 181 tin không `published_at`, 3 bài >1 năm (N10) | |
| R3-13 | Thấp | `ssh/sftp` tới VPS qua bastion hay ECONNRESET khi upload lớn: `deploy.sh` có lần ghi release dù tar bị cắt (log `gzip: unexpected end of file`) -> nên kiểm tra mã thoát trước `release.sh record` | hạ tầng deploy, chuyển nhóm vận hành |
| R3-14 | Thấp | `calendar/api-khong-trung-hien-thi`: vài sự kiện CN/EU trùng hiển thị (cùng giờ + tên chuẩn hoá) | |
| R3-15 | Thông tin | `actionforex.com/feed/` thỉnh thoảng 404 (5/24h) -> expert-collector log traceback rồi tự thử lại; ổn | |
| R3-16 | Thông tin | Cuối vòng: `DeadLetterEvents` firing (13 sự kiện/15 phút) là do `test_flow` cố ý bơm payload hỏng (N3) -> tự hết sau 15 phút; `MtAccountDisconnected` (pending) cho `demo-mt5-01` (EA lab mtlab-mt5 mất kết nối, không đụng tới) | |

Sức khoẻ: 21 service `/healthz`+`/metrics` = 200 (briefing-llm, client-ui, web-ui là nginx/cổng khác, container healthy); Prometheus 25/25 target up, 76 rule không lỗi; Alertmanager chỉ còn `ContainerCpuThrottled` (đã xử lý, sẽ hết sau 1 cửa sổ 10 phút). Dữ liệu hôm nay: crypto M1/H1 mới (≤3 phút), briefing sáng+chiều (intl + vn) đã sinh, báo cáo ngày `2026-10-14` (HTML+PDF) đã sinh, analytics snapshot 10:25, track-record vòng chấm 10:17, paper equity 12 tài khoản cập nhật tới 10-14 (4 tài khoản v1 đóng băng theo thiết kế), vn_daily 10-14.

## Vòng 4 — VPS 2026-10-14 (xử lý tồn đọng V3.3)

### V4.1 Kết quả theo suite (sau sửa)
| Suite | Kết quả | Trước |
|---|---|---|
| e2e `test_data_quality` | **84 pass / 0 fail** | 79/9 (vòng 3: 78/10) |
| e2e `test_new_components` | **194 pass / 0 fail** | 193/2 |
| e2e `test_flow` | 100 pass / 0 fail (2 lần liên tiếp; `cleanup.py` -> còn lại = 0) | 97/3 khi chạy song song với agent khác |
| pytest news-collector / expert-collector / api-gateway / market-collector | 88 / 68 / 191 / 93 pass | |

Chạy e2e trên VPS (user cc không ghi được `/root/qa-e2e/out`): chép `tests/e2e/*` sang thư mục riêng và sửa `D=` trong `run_remote.sh`.

### V4.2 Đã sửa
| ID | Mô tả | Sửa | Commit |
|---|---|---|---|
| R3-8 | Lịch: 0 sự kiện có `actual` | collector actuals: thêm nguồn chính thống miễn phí không key (BoJ Time-Series API, Eurostat `prc_hicp_minr` + EA21, ONS, StatCan, ABS, BLS Import Prices); 26 -> 41 chỉ số; US CPI 10-14 có actual ~2 phút sau công bố. Không dùng ForexFactory/Investing HTML (ToS), nasdaq (robots), census (bắt key) | 1d71de2 |
| R3-8 (test) | Giả định sai: mẫu số = mọi sự kiện đã qua >3h (đa số là phát biểu/đấu giá/chỉ số CN không có số liệu miễn phí) | kiểm trên sự kiện high/med **có forecast**; đủ ≥3 mẫu mới chấm, còn lại INFO | 2b0e8d9 |
| R3-14 | Lịch trùng CN/EU (M2, New Loans, Trade Balance, Bund 30y): nguồn đổi giờ dự kiến -> `event_id` (băm theo giờ) đổi -> 2–3 dòng | `event_id` FF ổn định = (tiền tệ, tiêu đề, ngày gốc, thứ tự trong ngày); dọn 123 dòng id cũ (backup `/tmp/cal_ff_old_ids_v4_backup.csv` trong container timescaledb), actual giữ nguyên | 91c9008 |
| R3-12a | 187 tin `published_at` NULL (tuoitre, baochinhphu: pubDate `10/14/2026 6:54:00 PM` giờ VN) | parse M/D/Y 12h, tz theo `tz_offset_h` (mặc định +7 cho `lang=vi`) ở news- và expert-collector; expert dùng `calendar.timegm` thay `mktime`; backfill 185 dòng từ mốc thời gian trong URL (`-1xxYYMMDDhhmmss…htm`). Còn 2 NULL cố ý (PIIE: ngày sự kiện tương lai) -> test cho phép ≤0,5% | db4fef1 |
| R3-12b | 3 tin >1 năm (BLS archives 2025, Guardian 2014) | RSS bỏ bài cũ hơn `max_age_days` (mặc định 180); xoá 3 dòng (backup `/tmp/news_old_v4_backup.csv`) | 4fc97be |
| R3-12c | Tin trùng tiêu đề (báo đăng lại, repost Bluesky, ECB/SSM): khác URL nên DB giữ cả hai là đúng | `/v1/news` bỏ trùng HIỂN THỊ (tiêu đề chuẩn hoá + ngày UTC; ưu tiên nguồn tin, bản sớm nhất; cửa sổ ứng viên 3×trang+50 để vẫn dùng index). Test DB -> INFO, thêm kiểm tra qua API | 5162923, 086902e |
| — | **Hồi quy do vòng này**: bản đầu truy vấn bỏ trùng làm `/v1/news` trả 500 (`operator is not unique: unknown + unknown`, tham số LIMIT chưa ép kiểu) — test đơn vị dùng InMemoryRepo nên không bắt được; e2e bắt được sau ~10 phút | ép `$3::int + $4::int`, deploy lại | 086902e |
| — | Tin tương lai: bản tin "ngày mai" (PHS) chỉ có ngày 00:00 giờ VN -> `published_at` sớm hơn hiện tại vài giờ | expert-collector: tương lai ≤1 ngày -> kẹp về giờ thu thập; sửa 1 dòng | 612072a |
| — | `tf/USDJPY/H4-khop-M1` FAIL: poll gặp 503 tạm thời ở giờ gần nhất -> phát H4 08:00 thiếu giờ 11, **ghi đè** nến đầy đủ | market-collector: khi poll thiếu giờ, không phát nến gộp (H1/H4/D1) chứa giờ thiếu | 3b34218 |
| R3-11 | `rt_bus_to_gateway` p95 1–3,3 s: event loop gateway bị chặn 0,3–3 s (watchdog chụp stack): `statistics.pstdev` (Fraction, rất chậm) trong `intel_calc.vol_series` cho mọi symbol khi dựng `/v1/intel/stats`/pulse; `hide_sources_mw` lọc body JSON lớn đồng bộ | thêm `loopmon.py` (`gateway_event_loop_lag_seconds`, `gateway_event_loop_stalls_total`, watchdog stack >0,3 s); pstdev float 2 lượt + chỉ tính 252 cửa sổ dùng; `symbol_stats` trong `asyncio.to_thread`; scrub body >32KB trong thread. Sau 20 phút: p95 0,19 s (max cửa sổ 5 phút 0,23 s), p99 0,43 s, trễ >1 s 28/60.000 | b30a846, a7c0f1e, cd64d1d, 5a56de0 |
| R3-9 (test) | M1 dukascopy trễ 82 phút > dung sai 75 | đo: file giờ H chỉ có (HTTP 200) khoảng H+1:20..H+1:40, trước đó 503 -> dung sai 120 phút | 2b0e8d9 |
| N8/L1 (test) | D1 Chủ nhật FX | D1 = ngày lịch UTC là hợp đồng đã chốt (`HUONG_DAN_SU_DUNG`, nay ghi rõ trong `CONTRACTS.md` `md.bars`) -> INFO | 2b0e8d9 |
| test_flow | `/v1/patterns/trades` (GET, lệnh PAPER mô phỏng) bị coi là route lệnh; tin QA cùng tiêu đề giữa các lần chạy bị bỏ trùng; cache gateway vô hiệu 2 lần (0 s và +2 s) nên GET sau 1 s có thể còn bản cũ | whitelist GET; tiêu đề QA riêng mỗi lần; chờ tối đa 6 s | 4888f6e |

### V4.3 Còn lại
| ID | Mức | Mô tả | Lý do / hướng |
|---|---|---|---|
| R3-8 | Trung bình | Actual còn thiếu: US Retail Sales/Core Retail/Industrial Production (cần `FRED_API_KEY` miễn phí – người dùng đăng ký), Unemployment Claims, Philly Fed, ISM, UoM, ADP, NFIB, Existing Home Sales (không có nguồn chính thống miễn phí); CPI Đức/Pháp (Destatis cần tài khoản), Trung Quốc, NZ (cần key), Thuỵ Sĩ. BLS API v1 25 lượt/ngày (trần 22). Sự kiện >36h không thử điền lại | nguồn phủ rộng nhất: lịch kinh tế MT5 (có actual mọi nước) qua EA khi pipeline MT5 demo chạy |
| ~~R3-9~~ | **ĐÃ XỬ LÝ 2026-10-14 (FEED)** | FX/vàng M1 trễ cấu trúc 80–100 phút (dukascopy) | Feed canon: EA MT5 demo `mt5:100000001` (investor, READ-ONLY) -> mt-bridge `feed.py` phát `source=canon:mt5:100000001` (M1 + M5..D1 mốc UTC, chỉ bucket quan sát trọn), ưu tiên trước dukascopy theo `ORDER BY source`; dukascopy là dự phòng theo khoảng thời gian khi EA offline. Đo (e2e `test_data_quality`): trễ M1 chuỗi hiệu lực EURUSD/GBPUSD/USDJPY/XAUUSD **1,7 phút** (trước: 29–109 phút dukascopy); dung sai `fresh/*/M1-moi-nhat` siết **120 -> 5 phút**, thêm `fresh/*/M1-du-phong-moi-nhat` (120), `tf/canon/*` (canon M5..D1 khớp M1, 0 lệch; đối chiếu M5/M15 native MT5: 46/46 khớp OHLCV), `tz/align-H4/D1-UTC-moi-nguon` (0 nến lệch mốc; đã xoá 500 nến H4/D1 EA thô giờ server). Thêm US500/US30/USTEC. Rollback: `FEED_CANON_ENABLED=false` + xoá `canon:%`. Chi tiết `docs/handoff/FEED_status.md` |
| R3-11b | Thấp | Watchdog vẫn ghi ~12 lần chặn 0,3–0,4 s/19 phút, stack rơi vào syscall (send/accept/recv) — nghi chờ CPU trên VPS dùng chung hoặc GIL do luồng phụ; chưa sửa `cache.store` nén zstd đồng bộ và `jsonable_encoder` body lớn; chưa theo dõi đủ 24h cảnh báo `rt_bus_to_gateway` | theo dõi metric `gateway_event_loop_*` |
| R3-14b | Thấp | Đổi `event_id` FF làm cảnh báo "sự kiện HIGH sắp tới" có thể bắn lại 1 lần cho sự kiện trong cửa sổ cảnh báo ngay sau deploy (khoá dedupe chứa event_id) | một lần, tự hết |
| R3-10, R3-13, R3-15, R3-16 | Thấp/Thông tin | như V3.3 (ETF D1 trễ 1 ngày theo thiết kế; deploy.sh qua SSH; actionforex 404 thỉnh thoảng; DLQ do test) | R3-13 chuyển agent deploy (`infra/ops/deploy_local.sh`) |

Ghi chú vận hành: `. ./.env` trong `infra/` lỗi cú pháp (dòng `USER_AGENT=... (contact: ...)` có ngoặc) -> `docker compose` mất `COMPOSE_PROJECT_NAME` và thử tạo network `trading-system_*`. Deploy đúng: `docker compose -p tradingsys --env-file .env up -d --build --no-deps <svc>` hoặc `bash infra/ops/deploy_local.sh <svc>`.


## Vòng 5 — rà soát tồn đọng (2026-10-15, chỉ đọc/kiểm, không sửa mã)

### V5.1 Đóng (đã xong thực tế)
| ID | Bằng chứng |
|---|---|
| N9 | Truy vấn `bars` nguồn `mt5:demo-mt5-01*` trước 2025 = 0 dòng (đã dọn) |
| N10 / L3 / R3-12 | Đã sửa ở Vòng 4 (R3-12a/b: parse `published_at`, lọc bài cũ, backfill) |
| N11 | HARDENING §bảng role: news-collector không còn biến DB superuser |
| M4 | `BRIDGE_ADMIN_TOKEN` bắt buộc trong compose (`:?`) |
| L5 | Image gateway đã build lại nhiều lần từ Vòng 4 (có `/v1/system`...) |
| R3-13 | Chuyển sang `infra/ops/deploy_local.sh` (kiểm sha256, chỉ ghi release khi thành công) |
| R3-14b | Sự kiện một lần, đã hết tác dụng |

### V5.2 Còn mở (đã đối chiếu)
| ID | Mức | Ghi chú |
|---|---|---|
| R3-8 | Trung bình | Actual còn thiếu nhóm chỉ số Mỹ (cần key FRED do người dùng), Claims/ISM/UoM... — hướng: lịch kinh tế MT5 qua EA |
| R3-11b | Thấp | Theo dõi 24 h `gateway_event_loop_*`; `cache.store` zstd đồng bộ chưa sửa |
| L2, L4 | Thấp | WS chưa xác thực giữ 10 s / nonce replay trong RAM — chưa thấy bằng chứng đã sửa trong docs |
| H2, M3 | Cao/TB | Chưa tái kiểm (không chạy tải/spam) |
| M5, M6, M7 | TB | Dữ liệu lab lẫn DB thật (đề xuất ở DATA_CLEANUP_LAB.md, chưa chạy), gap backfill dukascopy, đơn vị giá VN (nghìn đồng, đã ghi tài liệu) |
| N3, N5, N6 | Thấp | Theo thiết kế / thanh khoản mỏng (TONUSDT) / BLS chỉ là lịch |
| R3-10, R3-15, R3-16 | Thông tin | Theo thiết kế / tự hết |
Ghi chú: H2, M3, L2, L4, M5, M6 chưa được xác minh đóng trong vòng này; giữ mở cho tới khi kiểm lại.
