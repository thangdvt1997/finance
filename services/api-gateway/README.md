# api-gateway

FastAPI chỉ-đọc cho dashboard. Đọc Postgres/Timescale (asyncpg, truy vấn tham số hoá) và Redis Streams (WebSocket).
Auth: header `X-API-Key`, token từ env `API_TOKENS` (CSV). Chưa cấu hình token => từ chối hết (fail-closed); `AUTH_DISABLED=true` chỉ cho dev.
Nên cấp `DATABASE_URL` bằng role DB chỉ có quyền SELECT.

## Endpoints
| Method | Path | Ghi chú |
|---|---|---|
| GET | `/v1/bars?symbol&tf&from&to&order&limit&offset` | limit tối đa 5000 |
| GET | `/v1/quotes/latest?symbols=` | giá mới nhất mỗi symbol (7 ngày gần nhất) |
| GET | `/v1/news?symbol&since` | phân trang |
| GET | `/v1/calendar?from&to&impact=high,med` | |
| GET | `/v1/experts`, `/v1/expert-signals?symbol&status&expert_id`, `/v1/expert-positions` | |
| GET | `/v1/accounts` | snapshot mới nhất mỗi tài khoản (+ `currency`, `orders[]` lệnh chờ đang mở); client chỉ thấy tài khoản của mình |
| GET | `/v1/accounts/{id}/orders?status=open\|removed\|all&limit` | lệnh chờ của 1 tài khoản (client: chỉ tài khoản của mình, 403 đồng nhất) |
| GET/POST/PUT/DELETE | `/v1/user/rules`, `/rule-events`, `/push`, `/push/subscribe\|unsubscribe\|test` | cảnh báo cá nhân + Web Push theo chủ sở hữu (client chỉ bản ghi của mình; ghi cần CSRF); xem `docs/CLIENT_PLATFORM.md` |
| GET | `/v1/alerts?level` | |
| GET | `/v1/symbols` | symbol có dữ liệu + khung có nến (`tfs`), `last_bar`, `last_quote` |
| GET | `/v1/equity-history?account_id&from&to&limit` | balance/equity/margin tăng dần theo thời gian (mặc định 30 ngày, tối đa 5000 điểm) |
| GET | `/v1/system` | service up/down (Prometheus `up{job="services"}` nếu có `PROMETHEUS_URL`, nếu không suy ra từ sự kiện cuối trên bus), độ trễ + số sự kiện từng stream, độ mới từng bảng dữ liệu; cache 5s |
| GET | `/v1/analytics/overview`, `/analytics/symbol/{symbol}?tf`, `/analytics/screener?tf&trend&momentum&volatility&state&rsi_min&rsi_max&adx_min&heat_min&bias_min&bias_max&atr_pctile_min&q&sort&order&limit`, `/analytics/correlation?tf&min_delta`, `/analytics/sessions?symbol` | đọc snapshot bảng `analytics_snapshots` do service `analytics` ghi (role chỉ-đọc vẫn đủ); bảng chưa có => rỗng. Chỉ báo kỹ thuật, không phải khuyến nghị đầu tư |
| GET | `/v1/intel/strength?tf&window`, `/intel/fx`, `/intel/heatmap?group&period`, `/intel/movers?group&period&limit`, `/intel/stats?group&benchmark&window`, `/intel/correlation?symbols&window&method`, `/intel/correlation/rolling?a&b&window&span`, `/intel/distribution?symbol&window`, `/intel/pulse`, `/intel/news?q&symbol&topic&min_importance&sentiment&lang&hours&before&limit`, `/intel/news/topics`, `/intel/news/related?url`, `/intel/calendar/indicators`, `/intel/calendar/history?title&country`, `/intel/cot` | thông tin thị trường TỔNG HỢP tính ở máy chủ từ bars/quotes/news/calendar/expert_positions (module `intel_calc.py` thuần + `intel_data.py` truy vấn + `intel_routes.py`), cache TTL 15–120s; chi tiết `docs/MARKET_INTEL.md`. Thống kê, không phải khuyến nghị; role client được đọc |
| GET | `/v1/overview` | giá, tin, sự kiện 48h (med/high), tín hiệu mở, tài khoản |
| WS | `/v1/stream?streams=md.quotes,news.items,analytics.signals&symbols=EURUSD` | auth bằng header hoặc tin nhắn đầu `{"type":"auth","api_key":"..."}` |
| GET | `/ui` | dashboard tĩnh (không build); nhập API key, lưu sessionStorage |
| GET | `/healthz`, `/readyz`, `/metrics`, `/docs`, `/openapi.json` | không cần key |

Phân trang: `limit` (kẹp theo `MAX_PAGE_SIZE`) + `offset`; trả `{items, limit, offset, count}`.
WebSocket dùng `XREAD` từ thời điểm kết nối (không consumer group, không để lại trạng thái); giới hạn `WS_MAX_CONNECTIONS`.

## Phát triển
`repo.py` có `Repo` Protocol + `InMemoryRepo` (test); `pg_repo.py` là bản Postgres.
Test: `pytest` (không cần Docker/mạng). Build: `docker build -f services/api-gateway/Dockerfile .` từ gốc repo.


## Bộ lọc rủi ro tin (`/v1/risk-windows`)
- `GET /v1/risk-windows?symbol=EURUSD[&horizon_hours=24]` → `state` (`active` | `imminent` | `clear`), `minutes_to_end` (còn bao nhiêu phút trong cửa sổ), `minutes_to_start`, `current[]`, `upcoming[]` (24h tới), `next_window`. Bỏ `symbol` → trạng thái mọi symbol (cấu hình `universe` + symbol có trong DB).
- `GET /v1/risk-windows/status` → tổng quan: symbol đang/sắp trong cửa sổ, sự kiện đang hiệu lực, cửa sổ kế tiếp, cấu hình đang dùng.
- Logic ở `tscommon.risk_windows` (dùng chung với news-collector để alert và API nhất quán); gateway chỉ đọc `calendar_events` và gọi hàm thuần. Cấu hình `risk_windows.yaml` (env `RISK_WINDOWS_CONFIG`).
- `/v1/calendar` và `/v1/overview` trả thêm `extra` (nhóm, nguồn forecast/actual, `surprise`) và ẩn hàng chính thức đã có hàng Fair Economy cùng nhóm (`calendar_view.py`). Cột `calendar_events.extra` tự phát hiện (cần migration 003; chưa áp thì trả `null`).
