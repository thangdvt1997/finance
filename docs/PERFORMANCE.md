# PERFORMANCE — cache nhiều tầng + đo trước/sau (2026-10-12)

Mục tiêu: dịch vụ NHANH và tải trang nhanh hơn bằng các tầng cache, **không bao giờ cache chéo người dùng**. Mọi đo đạc/triển khai chạy trên VPS (không chạy trên laptop).

## 1. Các tầng
| Tầng | Vị trí | Phạm vi | TTL/kiểm soát | Tắt khẩn cấp |
|---|---|---|---|---|
| T1 Redis cache gateway | `api_gateway/cache.py` (ASGI middleware) + instance riêng `redis-cache` (512 MB, allkeys-lru, không AOF/RDB; user `ts_cache` chỉ `cache:*`) | dữ liệu dùng chung (khoá theo vai trò) + dữ liệu theo tài khoản (khoá theo vai trò + tập tài khoản) | quotes 1,5 s · bars M1 5 s … D1 300 s (lịch sử `to` > 2 ngày: 1 h) · symbols 30 s · news 20 s · calendar 30 s · analytics 20–60 s · intel 30–3600 s · vn 10–60 s · overview/accounts 2 s · equity/risk accounts 5 s; SWR (còn phục vụ bản cũ khi làm mới nền); single-flight; vô hiệu hoá theo bus | `CACHE_ENABLED=0` + recreate gateway, hoặc **tức thì**: `docker exec tradingsys-redis-cache-1 redis-cli --user ts_admin SET cache:ctl:off 1` (xoá key để bật lại) |
| T2 micro-cache nginx | `services/web-ui/nginx/default.conf.template` (location regex whitelist) + `cache-zones.conf`; tmpfs 128 MB | chỉ route DÙNG CHUNG; khoá = `vai trò + URI+query` | TTL = `X-Accel-Expires` do gateway đặt (≈ ½ TTL T1, tối thiểu 1 s); `proxy_cache_lock`, `use_stale updating error timeout 5xx`, `background_update` | `API_PROXY_CACHE=off` (recreate web-ui) hoặc **tức thì** `docker exec tradingsys-web-ui-1 touch /tmp/ts-cache-off` (xoá file để bật lại) |
| T3 cache auth_request | nginx `auth_cache` | CHỈ trang/tài nguyên tĩnh (không `/api/*`) | 200 có vai trò master/client, 2 s, theo (cookie, lớp URI); không lưu anon/401/không cookie | gỡ `proxy_cache auth_cache` |
| T4 HTTP chuẩn | gateway + nginx | ETag/If-None-Match → 304 (gateway, nginx static); `Cache-Control` đúng; `gzip_static` (nén sẵn lúc build) | static có hash: `public, max-age=31536000, immutable`; font/ảnh: 7 ngày + SWR 1 ngày; `index.html`/`sw.js`: `no-cache`; API dùng chung: `private, max-age=¼TTL, stale-while-revalidate=2×TTL`; API theo tài khoản: `private, no-store` | — |
| T5 DB | `PgRepo.bars` | bars không `from`: ghi nhớ khoảng lịch sử | xem §5 | — |

Brotli: image `nginxinc/nginx-unprivileged` không có module brotli (đã kiểm `nginx -V`: có `gzip_static`, `http_v2`, `http_v3`, không brotli) → dùng gzip -9 nén sẵn + `gzip_static`; Cloudflare nén Brotli ở edge. HTTP/2/3: do Cloudflare đảm nhận ở phía trình duyệt (tunnel → origin HTTP/1.1 keep-alive); không cần đổi origin.

## 2. An toàn dữ liệu (kiểm bằng test)
- **Không cache chéo**: khoá Redis = `(phạm vi, đường dẫn, query chuẩn hoá)`; phạm vi `m` (master/service), `c` (client — chỉ route dùng chung), `c.<băm tập tài khoản>` (route theo tài khoản). `user_id` không nằm trong khoá. Entry chỉ được ghi sau khi app trả 200 cho đúng phạm vi → quyết định phân quyền (CLIENT_ALLOW, account ∈ accounts) đã nằm trong khoá.
- **Danh tính do nginx đặt**: middleware cache tự kiểm `X-API-Key` + `principal_from_headers` (X-Auth-Secret khớp) TRƯỚC khi tra cache; giả/thiếu → bỏ qua cache, app trả 401/403 như cũ. nginx ĐÈ `X-User-Id/X-Role/X-Accounts`; khoá nginx dùng `$auth_role` (từ auth_request, client không đè được).
- **Không cache**: `/me`, `/user/*`, `/journal/*`, `/paper/*`, `/system`, `/alerts`, `/data-sources`, `/reports*`, mọi non-200 / non-JSON; route theo tài khoản không đi qua cache nginx (`X-Accel-Expires: 0`, `Cache-Control: private, no-store`).
- **`private`, không `public`** cho dữ liệu cần đăng nhập → Cloudflare/CDN không lưu và phát cho người chưa đăng nhập (chủ động lệch khỏi đề xuất `public`).
- **Fail-open**: lỗi Redis/giải nén → đi thẳng app, mạch hở 3 s; cờ `cache:ctl:off` bỏ qua cả request đang bay.
- **Thu hồi phiên**: `/api/*` luôn hỏi service auth (không cache) → thu hồi hiệu lực như cũ; cache 2 s chỉ áp dụng trang tĩnh.
- Test: `services/api-gateway/tests/test_cache.py` (khoá, TTL/SWR, stampede, fail-open, kill-switch, IDOR theo tài khoản, giả header/thiếu secret/thiếu API key, route cấm không lọt qua cache master, `/me`), `test_pg_span.py`, e2e `tests/e2e/test_cache_security.py` (67 kiểm tra qua nginx thật: khoá theo vai trò, 3 client đan xen không rò chéo, giả `X-Role/X-Accounts/X-API-Key`, route chỉ-master, Cache-Control/ETag/304/gzip, thu hồi phiên ≤ 4 s, stampede 60 request đồng thời ≤ 2 MISS), `tests/e2e/test_auth.py` vẫn xanh (IDOR nginx/WebSocket).

## 3. Vô hiệu hoá + precompute
- Luồng bus `md.bars` (khoá `bars:<symbol>:<tf>`), `news.items/news.enriched`, `calendar.events`, `analytics.signals`, `briefing.items`, `expert.*` → tăng version (`cache:ver:*`, TTL 7 ngày) bằng user `ts_cache`; entry ghi version lúc tính, lệch → coi là miss. Bump lần 2 sau 2 s (storage-writer có thể ghi DB sau sự kiện). Đọc bus bằng client chỉ-đọc `ts_gateway` (ts_cache không đọc được stream).
- Làm nóng trước hạn (refresh-ahead, chu kỳ 2 s, tối đa 6 song song): URL "nóng" quan sát được (90 s gần nhất) + danh sách seed (symbols, quotes, analytics overview, intel strength/fx/heatmap/movers/pulse, correlation D1, overview master) cho master và client; request thật chỉ còn đọc cache. Warmer dựng request tổng hợp từ principal đã xác thực (không bao giờ sao chép cookie/header của người dùng).

## 4. Số đo trước/sau
Phương pháp: k6 (`infra/perf/bench.js`, container `perf-k6`) + Playwright 1.49 (`infra/perf/pageload.mjs`) trên VPS; ngăn xếp A/B RIÊNG (`infra/perf/ab_stack.sh`: `perf-web-*` → `perf-gw-*`, cùng DB/auth thật) để cô lập khỏi việc recreate web-ui/api-gateway của agent khác (baseline trên stack chung bị nhiễu: web-ui/gateway bị recreate nhiều lần giữa lúc đo). TRƯỚC = gateway không cache + nginx cấu hình git HEAD; SAU = cache T1–T4. Mỗi endpoint một kịch bản, nghỉ giữa các kịch bản để hàng đợi xả.

### 4.1 API thẳng vào gateway (30 VU đồng thời, 10 s/endpoint) — p50/p95 (ms), RPS
| Endpoint | TRƯỚC p50 / p95 | TRƯỚC RPS | SAU p50 / p95 | SAU RPS |
|---|---|---|---|---|
| `/v1/overview` | 380 / 810 | 67 | 47 / 128 | 514 |
| `/v1/bars?tf=H1&limit=500` | 7330 / 9640 | 8 | 44 / 114 | 465 |
| `/v1/bars?tf=M1&limit=500` | 1190 / 1370 | 27 | 47 / 110 | 483 |
| `/v1/symbols` | 7480 / 20050 | 8 | 46 / 107 | 546 |
| `/v1/quotes/latest` | 222 / 328 | 133 | 44 / 103 | 567 |
| `/v1/news?limit=50` | 1100 / 1360 | 29 | 47 / 106 | 546 |
| `/v1/calendar?limit=100` | 448 / 578 | 68 | 44 / 116 | 540 |
| `/v1/analytics/overview` | 4100 / 4350 | 10 | 54 / 132 | 311 |
| `/v1/intel/strength` | 99 / 193 | 252 | 51 / 116 | 510 |
| `/v1/intel/heatmap` | 242 / 1970 | 56 | 50 / 111 | 498 |
| `/v1/vn/overview` | 630 / 1260 | 44 | 52 / 653 | 173 |
| `/v1/risk/accounts` | 15660 / 31020 (lỗi 50%) | 6 | 50 / 138 | 489 |
| hỗn hợp kiểu dashboard | 358 / 25030 (lỗi 11%) | 19 | 54 / 129 | 466 |

### 4.2 Qua nginx (đường thật của trình duyệt; 30 VU) — SAU = cache gateway + micro-cache nginx + auth_request cache cho tĩnh
| Endpoint | TRƯỚC p50 / p95 | TRƯỚC RPS | SAU p50 / p95 | SAU RPS |
|---|---|---|---|---|
| `/api/v1/overview` | 478 / 889 | 55 | 64 / 127 | 292 |
| `/api/v1/bars` H1 | 860 / 10877 | 11 | 79 / 102 | 412 |
| `/api/v1/bars` M1 | 1370 / 1487 | 24 | 105 / 389 | 184 |
| `/api/v1/symbols` | 7525 / 18616 | 8 | 99 / 162 | 311 |
| `/api/v1/quotes/latest` | 240 / 394 | 119 | 28 / 60 | 907 |
| `/api/v1/news` | 1115 / 1305 | 29 | 102 / 299 | 224 |
| `/api/v1/calendar` | 537 / 625 | 58 | 66 / 223 | 367 |
| `/api/v1/analytics/overview` | 4137 / 4760 | 10 | 193 / 309 | 169 |
| `/api/v1/intel/strength` | 112 / 304 | 207 | 27 / 71 | 877 |
| `/api/v1/vn/overview` | 616 / 847 | 46 | 82 / 301 | 288 |
| `/` (index.html) | 45 / 91 | 598 | 0,9 / 80 | 3464 |
| JS bundle (`/assets/*.js`) | 905 / 1596 | 33 | 6,5 / 10,4 | 4202 |
| hỗn hợp dashboard | 693 / 6759 | 23 | 80 / 155 | 389 |

### 4.3 Tải cao: 200 VU đồng thời trực tiếp gateway (12 s/endpoint)
| Endpoint | TRƯỚC p50 / p95 · RPS | SAU p50 / p95 · RPS | Lỗi |
|---|---|---|---|
| overview | 2849 / 5919 · 69 | 204 / 899 · 561 | 0% |
| quotes/latest | 1522 / 2352 · 142 | 246 / 983 · 606 | 0% |
| bars M1 | 7810 / 15155 · 39 | 256 / 696 · 467 | 0% |
| bars H1 | (7330 ở 30 VU, sụp ở 200) | 201 / 4804 · 382 | 0% |
| news / calendar / heatmap | — | 295 / 3175 · 287 · 231 / 1006 · 647 · 277 / 694 · 439 | 0% |
Ở 200 VU, ngăn xếp TRƯỚC không còn xả được hàng đợi (hàng trăm request hết thời gian 20 s ở nginx và vẫn bị gateway xử lý tiếp); SAU không lỗi.

### 4.4 Thời gian tải trang (Playwright/Chromium 1.49, trung vị 4 vòng, trang `/`; cache trình duyệt rỗng = cold, tải lại = warm)
| Chỉ số | TRƯỚC cold | SAU cold | TRƯỚC warm | SAU warm |
|---|---|---|---|---|
| DOMContentLoaded (ms) | 138 | 108 | 46 | 39 |
| load (ms) | 315 | 285 | 48 | 41 |
| LCP (ms) | 477 | 418 | 245 | 267 |
| Tổng thời gian chờ API (19–20 request, ms) | 1533 | 1091 | 1610 | 284 |
| API chậm nhất (ms) | 531 | 122 | 380 | 71 |
| Byte truyền (KB) | 643 | 637 | 51 | 14 |
Trang tải nhanh sẵn (phần lớn là SPA tĩnh nhỏ, 1 người dùng) nên cải thiện tuyệt đối khiêm tốn; lợi lớn nằm ở API khi nhiều người/nhiều tab, và ở tải lại (API chờ 1,6 s → 0,28 s, tĩnh gần như 100% từ cache trình duyệt).

### 4.5 Hit ratio (production, vài phút sau bật)
`gateway_cache_requests_total`: bars 1299 hit + 717 stale / 201 miss; quotes/symbols/analytics/intel > 50% hit từ phút đầu (warmer + single-flight ~450 request chờ chung 1 lần tính). Dashboard Grafana "Cache & Latency" theo dõi liên tục.

Ghi chú đo: ngăn xếp A/B riêng (`perf-*`) dùng cùng DB/Redis/auth thật nên còn nhiễu từ tải của các agent khác; "TRƯỚC" = gateway không cache (ảnh production, tắt Redis cache) + nginx cấu hình git HEAD (ảnh gateway "trước" đã có sửa `PgRepo.bars` nên số bars_h1 "trước" thấp hơn thực tế cũ: trên stack production cũ đo được p50 7,5–12 s ở 50 VU). Đã loại các lần đo bị gián đoạn do web-ui/api-gateway của agent khác recreate giữa chừng.

## 5. DB (Timescale)
- `bars` là hypertable chunk 7 ngày, ~1920 chunk (dữ liệu từ 1989); khoá chính `(symbol, tf, ts_open, source)` đã phục vụ tốt truy vấn thường gặp (M1 500 nến: 1 ms; D1: 50 ms).
- **Phát hiện**: `/v1/bars?tf=H1&limit=500` không `from` với chuỗi chỉ có 174 nến duyệt cả 1920 chunk: 1,9–4,1 s/truy vấn, 770k buffer (`EXPLAIN ANALYZE`: DeferredChunkAppend, Chunks Visited 1920). Cách xử lý: `PgRepo.bars` ghi nhớ nến cũ nhất khi kết quả desc/offset=0 ngắn hơn `limit` (đã thấy toàn bộ lịch sử) rồi thêm cận `ts_open >=` cho các truy vấn sau (TTL 10 phút; backfill cũ hơn cận có thể trễ ≤ 10 phút). Truy vấn có cận: ~3 ms. Không thêm index/cagg mới: truy vấn symbols (67 ms), quotes_latest (16 ms), price_snapshot (58 ms), accounts_latest (20 ms) đều nhanh ở DB; phần chậm là CPU Python của gateway (pydantic response_model 500 dòng + quét `hide_sources` JSON) — T1 loại bỏ phần này ở các lần hit. Cagg `bars_daily_stats` quá chậm cho việc dò min (490 ms) nên không dùng.
- Pool asyncpg: `min 2 / max 20` (`PG_POOL_MAX`), `max_inactive_connection_lifetime=300`; prepared statement cache mặc định của asyncpg (100) đã bật.

## 6. Khuyến nghị cho UI (phối hợp agent UX "E")
- React Query: `staleTime` ≈ TTL T1 theo loại (quotes 1–2 s, bars theo khung, news 20 s, calendar 30 s, symbols 60 s); `gcTime` dài hơn; dedupe truy vấn cùng khoá; `refetchOnWindowFocus` chỉ cho quotes/overview.
- Prefetch bars khi hover mã/khung; dùng `If-None-Match` mặc định của trình duyệt (ETag đã có) — không thêm `cache: "no-store"` cho GET dùng chung.
- Giữ `quotes/latest?symbols=` cố định thứ tự (khoá chuẩn hoá theo query đã sắp xếp nhưng giá trị CSV thì không); gom 1 truy vấn/trang thay vì N truy vấn/mã.
- Service worker: `stale-while-revalidate` cho `/assets/*`, `/sw.js`+`index.html` `no-cache`; KHÔNG cache `/api/*` theo tài khoản (`Cache-Control: private, no-store` đã báo); route dùng chung có `max-age` ngắn nên SW có thể tôn trọng header.
- `modulepreload`: Vite đã sinh; thêm `<link rel=preload>` cho font/chunk đầu tiên nếu LCP chậm.

## 7. Vận hành
- Bật: `bash infra/ops/redis_acl_render.sh` (sinh `REDIS_CACHE_PASSWORD`, `users.acl`, `users-cache.acl`) → `deploy.sh "up -d redis-cache"` → `deploy.sh "up -d --build --no-deps api-gateway web-ui"`. Rollback: `infra/ops/rollback.sh` hoặc `CACHE_ENABLED=0`.
- Giám sát: Grafana "Cache & Latency" (`ts-cache-latency`, sinh bởi `infra/grafana/gen_dashboards.py`), cảnh báo `GatewayCacheHitRatioLow`, `GatewayCacheErrors`, `GatewayCacheCircuitOpen`, `GatewayCacheDisabled` (`infra/prometheus/rules.yml`). Metric: `gateway_cache_requests_total{policy,result}`, `gateway_cache_request_seconds`, `gateway_cache_redis_seconds`, `gateway_cache_errors_total`, `gateway_cache_invalidations_total`, `gateway_cache_refresh_total`, `gateway_cache_circuit_open`.
- Đo lại: `sh infra/perf/ab_stack.sh build && sh infra/perf/ab_stack.sh up` rồi `sh infra/perf/run_bench.sh <nhãn> MODE=gw BASE=http://perf-gw-after:8000 ...`; `sh infra/perf/run_pageload.sh <nhãn>`; dọn: `sh infra/perf/ab_stack.sh down`.
- Rủi ro còn lại: client-ui (nginx riêng `/c/api/`) chưa có micro-cache nginx (vẫn hưởng T1); TTL 20–60 s nghĩa là dữ liệu có thể cũ tới TTL (nến đóng được vô hiệu hoá theo sự kiện); warmer tạo tải nền ổn định (≤ 6 truy vấn song song) cho các khoá nóng.

## 8. Hành vi tinh chỉnh sau khi đo tải (200 VU)
- Vô hiệu hoá theo sự kiện KHÔNG áp dụng cho nến M1/M5/M15 (collector phát lại mỗi lần poll → làm mất cache liên tục); chúng dùng TTL 5/10/20 s. H1/H4/D1, news, calendar, analytics, briefing, expert vẫn vô hiệu hoá theo sự kiện.
- Khi bị vô hiệu hoá/hết hạn mềm: phục vụ bản cũ (STALE, SWR) + làm mới nền — request không bao giờ phải chờ tính lại nếu entry còn trong cửa sổ stale.
- Refresh-ahead chỉ cho khoá có TTL ≥ 10 s (TTL ngắn dựa vào SWR + single-flight; tránh đốt CPU event loop).
- Redis cache lỗi: mạch chỉ mở sau 5 lỗi liên tiếp (timeout socket 800 ms); trong lúc lỗi/mạch hở vẫn single-flight trong tiến trình (không đọc/ghi Redis) → DB không bị dồn.
- Giới hạn còn lại: gateway là 1 tiến trình Python (event loop) — trần ≈ 500–650 RPS/instance cho nội dung đã cache; muốn cao hơn cần nhiều worker/replica (cache Redis đã dùng chung được).
