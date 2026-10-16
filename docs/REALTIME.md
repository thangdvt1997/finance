# REALTIME — đẩy dữ liệu (push) cho UI master + client (2026-10-12)

Mục tiêu: thay polling bằng subscription có kiểm soát: nhanh hơn, ít tải hơn. Mã: `services/api-gateway/src/api_gateway/realtime.py` (hub), SDK `services/web-ui/app/src/lib/realtime.js`
(bản sao BYTE-GIỐNG ở `services/client-ui/app/src/lib/realtime.js`; kiểm: `cmp` hai file), hook `useLiveQuote.js`. Legacy `/v1/stream` giữ nguyên (UI cũ vẫn chạy).

## 1. Kiến trúc
```
EA -> mt-bridge --XADD--> Redis Streams (md.quotes, md.bars, account.*, mt.account_status, alerts.out, news.enriched)
                                   |  (MỘT vòng XREAD duy nhất trong gateway, không phụ thuộc số kết nối)
                         api-gateway Hub:  QuoteEngine (gộp nguồn, stale, im lặng) + candle forming + state tài khoản
                                   |  tuần tự hoá MỘT lần/ topic, chia sẻ chuỗi cho mọi người đăng ký
              flush 50 ms (throttle q 250 ms, c 500 ms, a 200 ms) -> Conn.latest (gộp, bản mới nhất) / Conn.rel (reliable, seq)
                                   |  writer: gom thành MỘT khung/ kết nối, send_timeout 5 s (chậm -> đóng 'slow')
                    WS /v1/rt  |  SSE /v1/rt/sse   (nginx: /api/v1/rt, /c/api/v1/rt)   [permessage-deflate do uvicorn/websockets]
```
- Backpressure: topic latest-state chỉ giữ bản MỚI NHẤT mỗi kết nối (tin cũ bị bỏ = `rt_dropped_total{reason="coalesced"}`); topic reliable tràn `RT_QUEUE_MAX` -> bỏ hàng đợi và gửi snapshot `reset` (client tự đồng bộ lại).
- Quote engine: nhiều nguồn/ symbol -> một quote chuẩn theo `RT_SOURCE_PRIORITY` (nguồn TƯƠI ưu tiên cao nhất thắng; mọi nguồn quá `RT_STALE_S`=20 s -> `q:1` stale). Tên nguồn KHÔNG bao giờ ra ngoài.
  Im lặng: symbol không có tick > `RT_SILENT_S`=90 s -> sự kiện `sys {k:"silent"}` (master) + gauge `rt_silent_symbols`; có tick lại -> `resumed`.
- Nến đang hình thành: khởi tạo/ghi đè bởi `md.bars` (EA gửi cả nến đang đổi), cập nhật theo từng tick (h/l/c); M1-H1 tự mở nến mới theo UTC khi tick vượt biên (H4/D1 chờ md.bars vì theo giờ broker).
- Hết phiên: kết nối sống tối đa `RT_MAX_AGE_S` (client 1800 s, master 3600 s) rồi server gửi `bye reauth` + đóng 4401; SDK kết nối lại -> nginx `auth_request` kiểm phiên (hết hạn => 401, không vào được). Thu hồi tức thì: `POST /v1/rt/kick {"user_id"}` (master/service) — auth có thể gọi sau revoke.

## 2. Giao thức `rt.v1` (JSON, UTF-8)
Kết nối: `GET /api/v1/rt?topics=q:EURUSD,a:123` (WS) — auth do nginx (cookie phiên -> `X-User-Id/X-Role/X-Accounts/X-Auth-Secret`); gateway kiểm Origin/Host (RT_CHECK_ORIGIN).
SSE (một chiều, đăng ký cố định trong URL): `GET /api/v1/rt/sse?topics=...`.

Topic (regex trong `realtime.py: TOPIC_RE`): `q:<SYM>` giá | `c:<SYM>:<M1|M5|M15|H1|H4|D1>` nến | `a:<ACCOUNT>` trạng thái tài khoản (balance/equity/margin/positions/orders) |
`e:<ACCOUNT>` sự kiện tài khoản (deals đã đóng, trạng thái EA) | `n` tin quan trọng (importance med/high) | `sys` cảnh báo + trạng thái EA + silent/resumed (CHỈ master).
`q c a` = latest-state (gộp, `q` seq có thể nhảy cóc — bình thường). `e n sys` = reliable (seq liên tục, ring `RT_RING`=256, resume được).

Server -> client (mọi tin dữ liệu nằm trong khung `b`; `hello/hb/bye` đứng riêng):
| `t` | Nội dung |
|---|---|
| `hello` | `{v:1, ep, sid, hb, now, max_age, role, limits}` — `ep` = epoch của hub (đổi khi gateway restart -> mọi seq làm lại) |
| `b` | `{st: epoch_ms lúc gửi, m:[tin...]}` |
| `snap` | `{k, q:seq, ep, d, reset?, resumed?}` snapshot đầu khi đăng ký (hoặc sau tràn hàng đợi `reset:true`); `d:null` = chưa có dữ liệu |
| `d` | `{k, q:seq, d}` delta |
| `ok` | `{k:[topic ok], e:[[topic,code]...]}` hoặc `{u:[topic đã huỷ]}`; code: `forbidden` (đồng nhất cho không tồn tại/của người khác), `bad_topic`, `too_many_topics` |
| `pong` | `{c: t client, s: epoch_ms server}` |
| `hb` | `{st}` mỗi `hb` giây khi rảnh |
| `bye` | `{c: reauth|kicked|slow|rate|shutdown}` rồi đóng (4401/4403/1013/1008/1001) |
| `err` | `{c:"too_big"}` |
Dữ liệu `d`: quote `{s,b,a,t:tick_ms,q:0|1 stale}`; nến `{s,f:tf,t:ts_open_ms,o,h,l,c,v}`; tài khoản = payload `account_snapshot` (đã scrub tên nguồn);
sự kiện tài khoản `{k:"deals",deals:[...]}` | `{k:"status",status,reason,...}`; sys `{k:"alert"|"ea_status"|"silent"|"resumed",...}`.

Client -> server: `{"op":"sub","topics":[...],"resume":{"e:123":57},"ep":"<ep>"}` | `{"op":"unsub","topics":[...]}` | `{"op":"ping","t":<client_ms>,"r":<rtt_ms lần trước>}` |
`{"op":"lat","s":[ms,...]}` (≤50 mẫu độ trễ một chiều gateway->trình duyệt, đã hiệu chỉnh offset). Giới hạn: ≤50 topic/lệnh, `RT_MAX_TOPICS`=120/kết nối, `RT_MSG_RATE`=20 tin/s (burst 40), tin ≤4 KB.
Phát hiện mất tin: topic reliable mà `q != last+1` -> SDK gửi lại `sub` kèm `resume`+`ep` (ring đủ -> phát lại phần thiếu; không đủ/ep khác -> `snap reset`).

## 3. Phân quyền / an toàn
| Điều | Cơ chế |
|---|---|
| Danh tính | chỉ tin `X-User-Id/X-Role/X-Accounts` khi `X-Auth-Secret` khớp (như REST); giả mạo -> đóng 1008 |
| IDOR | `a:` và `e:` chỉ cho `account ∈ phiên` (master: tất cả); sai -> `forbidden` đồng nhất; `sys` chỉ master; tin của tài khoản khác không bao giờ vào Conn của client |
| Giới hạn | `RT_MAX_CONNS` 2500 toàn cục, `RT_MAX_CONNS_USER` 6 (client) / `RT_MAX_CONNS_MASTER` 30 theo user; nginx `limit_conn ws_conn`; topic 120/kết nối; tốc độ tin đến 20/s |
| CSWSH | cookie SameSite=Strict + kiểm `Origin` vs `Host/X-Forwarded-Host` ở gateway |
| Nguồn dữ liệu | quote chuẩn không có trường nguồn; payload khác qua `scrub_obj` khi `HIDE_SOURCES` |
| READ-ONLY | không có thao tác đặt lệnh trên kênh này |

## 4. Cấu hình (env, allowlist `api-gateway: RT_*` trong `infra/ops/service_env.manifest`)
`RT_ENABLED=1`, `RT_QUOTE_MS=250`, `RT_CANDLE_MS=500`, `RT_ACCOUNT_MS=200`, `RT_MAX_CONNS`, `RT_MAX_CONNS_USER`, `RT_MAX_CONNS_MASTER`, `RT_MAX_TOPICS`, `RT_MAX_AGE_S`, `RT_MAX_AGE_MASTER_S`, `RT_HB_S=15`,
`RT_SEND_TIMEOUT_S=5`, `RT_MSG_RATE`, `RT_MSG_BURST`, `RT_QUEUE_MAX=400`, `RT_RING=256`, `RT_STALE_S=20`, `RT_SILENT_S=90`, `RT_SOURCE_PRIORITY`, `RT_STREAMS`, `RT_CHECK_ORIGIN=1`, `RT_ALLOWED_ORIGINS`,
`RT_EXTRA_STREAMS` (chỉ cho container kiểm thử tải). Tắt khẩn cấp: `RT_ENABLED=0` + recreate gateway (UI tự rơi về REST polling).

## 5. SDK + UI
`realtime.js`: một kết nối/ tab, topic refcount, đăng ký lại + resume sau khi nối lại, backoff mũ có jitter (0,5 s -> 30 s), ping 15 s, im >2,5×hb -> nối lại, tab ẩn >30 s -> đóng (tiết kiệm tải) và nối lại khi hiện,
hiệu chỉnh offset đồng hồ từ ping/pong để đo độ trễ một chiều (gửi `lat` mỗi 30 s), WS lỗi liên tiếp -> rơi sang SSE. Hook `useLiveQuote(symbol)` -> `{bid, ask, t, stale, dir}`; `useLiveTopic(topic)` cho dữ liệu khác.
Hook: `useLiveQuote/useLiveQuotes/useLiveTopic/useLiveCandle/useRealtimeStatus/useRealtimeLive` (`lib/useLiveQuote.js`); `lib/rtAccounts.js` (a:/e: -> cache react-query). 3 file trên + `realtime.js` BYTE-GIỐNG ở web-ui và client-ui (cmp). Suy giảm êm: rt không mở => polling cũ chạy như trước.
Lưu ý giao thức: đăng ký lại topic ĐÃ đăng ký không phát lại snapshot, nên SDK khi phát hiện mất tin reliable gửi `unsub` rồi `sub`+`resume` (cùng lô).
UI đã dùng: xem §8.

## 6. Độ trễ đầu-cuối (đo bằng metric, p50/p95 xem §7)
Chặng: EA -> bridge (`mtbridge_ea_to_bridge_seconds`, gồm lệch đồng hồ EA) -> bus (bridge xử lý: `mtbridge_ingest_seconds`) -> hub (`rt_bus_to_gateway_seconds`, Event.ts -> đọc) ->
fan-out (`rt_flush_seconds`, throttle ≤250 ms là độ trễ CÓ CHỦ ĐÍCH) -> WS (`rt_send_seconds`) -> trình duyệt (`rt_client_net_seconds` do SDK báo, `rt_client_rtt_seconds`). storage-writer: group lag từ redis-exporter.

## 7. Metric, dashboard, cảnh báo
Metric `rt_*` (xem `realtime.py`; số lần thử kết nối là `rt_conn_attempts_total{result}`). Dashboard Grafana `ts-realtime` (`infra/grafana/gen_dashboard_rt.py` -> `dashboards/realtime.json`); luật `infra/prometheus/rules_rt.yml` (10 luật `Rt*`); đo p50/p95 từng chặng: `python infra/perf/rt_latency_report.py` (chạy trên VPS, xem docstring). (Chi tiết + số đo: mục "Kết quả đo" cuối tài liệu.)

## 8. Trạng thái triển khai / kết quả đo
(được cập nhật sau khi triển khai và kiểm thử tải)
**UI đã chuyển sang push (2026-10-12)**
- web-ui: `useQuotesLatest` (-> Watchlist page/widget, quote-card, ticker-tape, topbar, SymbolList, Overview) nạp giá rt vào kho `lib/stream.js` qua `lib/rtbridge.js` (legacy `/v1/stream` vẫn chạy, bị bỏ qua cho symbol đang có giá rt <5 s); REST `/quotes/latest` 60 s -> 240 s khi rt live. `useAccounts` (Accounts, Overview, account-mini, positions-open): a:<id> gộp vào cache, poll 15 s -> 120 s. `ChartCell`: nến đang hình thành c:SYM:TF (M1..D1), đường legacy onTick/onBar bị bỏ qua khi rt tươi <5 s.
- client-ui: `useQuotes` (Market, Alerts) + `notify.jsx` AlertEngine: giá rt phủ lên kết quả REST (poll 30/15 s -> 120/90 s khi live); `useAccountSnaps`: a:<id> + e:<id> của CHÍNH tài khoản trong /accounts (deal mới/reset -> invalidate journal-*/equity của tài khoản đó), poll 15 s -> 120 s; `Market.jsx`: nến live c:SYM:TF, poll bars 60 s -> 180 s.
- nginx: web-ui `= /api/v1/rt`, `= /api/v1/rt/sse` và chuyển tiếp `= /c/api/v1/rt[/sse]` sang client-ui; client-ui `= /c/api/v1/rt[/sse]` (auth_request, kiểm Origin, `limit_conn crt_conn 20`, cookie không xuống gateway).
**Còn polling (chưa chuyển):** `useOverview` 30 s, `useEquity`, `useRisk*`, `useJn*`/`journal-accounts` 60 s (đã có invalidate theo e:<id> ở client-ui), news/calendar/alerts (topic `n`/`sys` chưa nối UI), `useSystem` 10 s, bars REST (chỉ giảm tần suất), `top-movers`/sparkline (dùng bars). Legacy `/v1/stream` còn phục vụ tin/cảnh báo/expert.
Kiểm thử: build vite web-ui + client-ui OK trên VPS; `nginx -t` OK cả hai; mô phỏng SDK với WebSocket giả (hello/snap/gap->resync+resume/reauth/đổi ep) OK; chưa có vitest trong repo nên chưa có test đơn vị trong CI.

## Kết quả đo (2026-10-12)
Môi trường: VPS dùng chung 64 vCPU; gateway TẠM `perf-ws-gw` (cùng image, `--cpus 2 --memory 1g`, mã nguồn hiện hành mount đè), bộ phát `perf-ws-pub` XADD vào stream riêng `rt.perf`
(200 tick/s / 5 symbol PERF1..5 + 20 sự kiện reliable/s), bộ tải `perf-ws-load` (4-6 tiến trình, 3 CPU) — `infra/perf/run_ws_load.sh`, `infra/perf/ws_load.py`.
Mỗi kết nối: 5 topic `q:` + 1 `e:`; 5% kết nối "chậm" (không đọc socket); ramp 100 kết nối/s; đo 60 s sau ramp; throttle quote 250 ms (sản xuất). Độ trễ = đồng hồ client - `d.t` (giờ tick gốc, cùng host).
CPU = `docker stats` mỗi 5 s (100% = 1 lõi; gateway là 1 tiến trình asyncio nên trần ~100%). Máy còn chạy tải của agent khác (k6) nên số có nhiễu vài chục %.

| Kết nối | CPU p50 / max | RAM max | tin/s | kB/s | độ trễ tick->client p50 / p95 / p99 | snap đầu p95 | mất tin (seq gap q: / e:) | flush p95 |
|---|---|---|---|---|---|---|---|---|
| 500 (trước tối ưu) | 31% / 45% | 93 MiB | 8 660 | 904 | 68 / 103 / 145 ms | 58 ms | 0 / 0 | 5 ms |
| 1000 (trước) | 55% / 92% | 124 MiB | 16 916 | 1 790 | 110 / 342 / 421 ms | 108 ms | 0 / 0 | 25 ms |
| 2000 (trước) | 90% / 105% | 187 MiB | 28 670 | 3 024 | 193 / 703 / 800 ms | 422 ms | 0 / 0 | 25 ms |
| 500 (sau tối ưu) | 40% / 57% | 90 MiB | 8 790 | 976 | 57 / 86 / 94 ms | 66 ms | 0 / 0 | 5 ms |
| 1000 (sau) | 39% / 79% | 121 MiB | 16 685 | 1 767 | 82 / 155 / 264 ms | 65 ms | 0 / 0 | 10 ms |
| 2000 (sau) | 71% / 101% | 183 MiB | 32 666 | 3 446 | 124 / 388 / 534 ms | 215 ms | 0 / 0 | 25 ms |
| 3000 (sau) | 91% / 102% | 250 MiB | 39 843 | — | 181 / 625 / 831 ms | 618 ms | 0 / 0 | 50 ms |

(Độ trễ p50 ~60 ms ở tải nhẹ gồm cả độ cũ của tick tại lúc flush 250 ms + lịch chạy của bộ tải.) Mọi kết nối được nhận (0 lỗi), 0 khoảng nhảy seq của topic reliable `e:`; khoảng nhảy seq của `q:` là gộp có chủ đích.
**Bão hòa**: ~2000-3000 kết nối trên MỘT tiến trình gateway (CPU ~90-100% một lõi, p95 vượt ~0,6 s ở 3000; ngưỡng p95 < 1 s vẫn giữ tới 3000). Khuyến nghị: dưới ~2000 kết nối/ tiến trình; nếu cần hơn -> chạy thêm gateway (hub độc lập, mỗi cái đọc bus riêng) sau nginx.
Kết nối chậm: bài riêng (100 kết nối, 60% đọc chậm — thực tế 60 kết nối chậm, 120 topic/kết nối, 4000 tick/s): cả 60 kết nối chậm bị server đóng `slow` (rt_closed_total{reason="slow"}=60) sau khi bộ đệm TCP đầy, 37 041 tin gộp (coalesced) thay vì dồn hàng đợi,
RAM gateway 74 MiB, kết nối nhanh không bị ảnh hưởng (p95 86 ms). Với tải vừa (5 topic) kết nối chậm gần như vô hại vì bộ đệm TCP đủ chứa; bộ nhớ vẫn bị chặn trên (mỗi topic chỉ giữ 1 tin mới nhất).

**Nút thắt tìm được + tối ưu** (cProfile gateway ở 2000 kết nối, `infra/perf/gw_profile.py`): `asyncio.wait_for` + `asyncio.sleep(0.01)` cho MỖI khung (~780 k lần/100 s: hàng chục giây timer/heap/call_at). Sửa: heartbeat và hết tuổi phiên do `sweep()` (1 s) điều khiển
(`Conn.hb_due`), writer chỉ `await conn.wake.wait()`, bỏ sleep 10 ms (flush đồng bộ nên mọi topic cùng lượt đã vào cùng khung). Trước -> sau ở 2000 kết nối: CPU p50 90% -> 71%, p95 độ trễ 703 -> 388 ms, tin/s 28,7 k -> 32,7 k; ở 1000: p95 342 -> 155 ms.
Còn lại: `socket.send` (~10%), serialize khung websockets, prometheus `inc` (~5%) — không đáng tối ưu thêm trước khi cần > 3000 kết nối.

**Lỗi tìm thấy qua kiểm thử và đã sửa** (realtime.py): (1) `QuoteEngine.update` xoá symbol khỏi `silent` trước `sweep` -> sự kiện `sys {k:"resumed"}` KHÔNG BAO GIỜ phát; (2) tràn hàng đợi reliable xoá cả snapshot đầu của topic q/c/a nằm trong cùng hàng đợi mà không gửi lại -> nay resync gửi trạng thái hiện tại cho mọi topic;
(3) kết nối rảnh chỉ kiểm tuổi sau mỗi nhịp hb -> `reauth` trễ tới 15 s (nay đúng hạn, ~4,1 s với max_age 4 s). Thêm: stream thử nghiệm (`RT_EXTRA_STREAMS`) định tuyến theo `ev.type` (account_snapshot/account_status/deals/bar, mặc định quote) để e2e không chạm stream thật.

**Unit** `services/api-gateway/tests/test_realtime.py`: 40/40 PASS (QuoteEngine, throttle/coalesce, nến forming, reliable seq/ring/resume/overflow, IDOR, giới hạn, kick, max_age, scrub nguồn, WS/SSE qua TestClient).
**E2E bảo mật** `tests/e2e/test_realtime_security.py` (chạy `sh /root/qa-e2e/run_rt_security.sh`, gateway tạm + stream `rt.sec`): 47/47 PASS — A không nhận a:/e:/deals/status của B, forbidden đồng nhất (tồn tại = không tồn tại), sys chỉ master, master thấy cả hai,
header thiếu/sai secret/role anon/lạ -> 403 lúc bắt tay, sai/không API key -> đóng 1008, Origin lạ -> 403, kết nối thứ 7 của một user bị từ chối (6/user), 120 topic/kết nối, kick đúng user (client gọi kick = 403), tin >4 KB -> `too_big`, spam 600 tin -> `bye rate` + 1008, tin rác không làm sập,
hết tuổi -> `bye reauth` + 4401, SSE: không/sai key 401, header giả 403, chỉ topic của mình; qua nginx thật (web-ui `/api/v1/rt`, client-ui `/c/api/v1/rt`, web-ui `/c/api/v1/rt`): không phiên -> 401, header giả bị từ chối 401. Chưa kiểm qua nginx KHI ĐÃ ĐĂNG NHẬP (cần phiên thật).

## 9. Kết quả đo (2026-10-12, VPS dùng chung, load average ~10)
Môi trường: gateway TẠM `perf-ws-gw` (cùng image, `--cpus 2`), nguồn tick tổng hợp vào stream riêng `rt.perf` (200 tick/s, 5 topic/kết nối, 5% kết nối "chậm" không đọc socket), 60 s đo mỗi mức, không nén. Script: `infra/perf/ws_load.py`.
| Kết nối | tin/s | CPU gateway p50 / max (1 lõi=100%) | RAM max | tick->client p50 / p95 / p99 | snapshot đầu p95 | mất tin (gap seq) | kết nối lỗi |
|---|---|---|---|---|---|---|---|
| 500 | 8.790 | 40% / 57% | 90 MiB | 57 / 86 / 94 ms | 66 ms | 0 | 0 |
| 1000 | 16.685 | 39% / 79% | 121 MiB | 82 / 155 / 264 ms | 65 ms | 0 | 0 |
| 2000 | 32.666 | 71% / 101% | 183 MiB | 124 / 388 / 534 ms | 215 ms | 0 | 0 |
| 3000 | 39.843 | 91% / 102% | 250 MiB | 181 / 625 / 831 ms | 618 ms | 0 | 0 |
Kết luận: 500-2000 kết nối chạy thoải mái (CPU ≤ ~1 lõi, p95 < 0,4 s, gồm ~250 ms throttle chủ đích); bão hoà ở ~2000-3000 vì Python đơn tiến trình (flush p50 25 ms ở 3000). Trần cấu hình `RT_MAX_CONNS`=2500. Muốn hơn: bật nén
chỉ khi băng thông là nút thắt, hoặc chạy nhiều replica gateway (mỗi replica một hub).
Độ trễ từng chặng trên hệ thống thật (10 phút, `infra/perf/rt_latency_report.py`): EA->bridge p50 375 / p95 488 ms (gồm lệch đồng hồ EA); bridge ingest 2,5 / 4,8 ms; bridge XADD 2,5 / 4,8 ms; bus->hub 38 / 411 ms (p95 bị kéo bởi lúc VPS bận);
fan-out flush 0,3 / 0,8 ms; send ws 0,5 / 0,9 ms; client net (ít mẫu) 25 / 85 ms; RTT 19 / 160 ms. tick->gateway ~7,8 s là do nguồn tick giá thật đến chậm/polling (không phải hub).
Kiểm thử: unit `tests/test_realtime.py` + `test_authz.py` 56/56 PASS; e2e bảo mật `tests/e2e/test_realtime_security.py` 47/47 PASS (IDOR a:/e:, sys chỉ master, header giả 1008/403, giới hạn kết nối/user, hết tuổi -> bye reauth 4401, kick, Origin lạ, tin quá lớn/spam, SSE, và qua nginx web-ui/client-ui không phiên -> 401).
Ghi chú: `tests/test_gateway.py::test_system_fallback_from_redis_and_freshness` đang FAIL (khẳng định `age_seconds < 5` phụ thuộc thời gian/dữ liệu, không liên quan realtime).
