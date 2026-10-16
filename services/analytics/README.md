# analytics

Phân tích kỹ thuật theo symbol × khung H1/H4/D1 từ bảng `bars`. **Chỉ báo kỹ thuật, không phải khuyến nghị đầu tư**: service chỉ mô tả trạng thái và phát cảnh báo điều kiện, không có tín hiệu mua/bán, không đặt lệnh (hệ thống READ-ONLY).

## Kiến trúc
```
bars (ts_ro, chỉ đọc) ─> analytics ──upsert──> analytics_snapshots (ts_analytics)  ─> api-gateway /v1/analytics/* ─> web-ui "Phân tích"
                            ├─ analytics.signals  (event `analytics.snapshot`: tóm tắt chu kỳ, top heat)
                            └─ alerts.out         (cảnh báo điều kiện, dedupe_key ổn định) ─> alert-service
```
- **Chỉ báo = TA-Lib** (BSD; wheel manylinux/win có sẵn thư viện C, không cần gcc trong `python:3.12-slim`): RSI14, MACD(12,26,9), ATR14, Bollinger(20,2), EMA20/50/200, ADX14 (+DI/−DI), Stochastic(14,3,3). Pivot cổ điển là mã của dự án (5 dòng). Không tự cài lại công thức.
- Thiếu H4/D1 trong DB thì gộp từ H1 (`resample_missing`).
- **Trạng thái** (`states.py`) theo quy tắc nguyên văn (mỗi trạng thái có `rule`): giá trên/dưới EMA200, EMA xếp tăng/giảm, ADX≥25 / <20, RSI≥70 / ≤30, MACD hist, Stochastic, squeeze (độ rộng Bollinger phân vị ≤20 trong 120 nến), ATR% phân vị ≥80 / ≤20, giá ngoài dải Bollinger.
- **heat** 0..100 (không có hướng) = 0.35·ADX(0..50) + 0.25·|RSI−50|·2 + 0.25·phân vị ATR% + 0.15·|%B−0.5|·2. **bias** −100..+100 = trung bình 5 phiếu (giá>EMA200, EMA20>EMA50, MACD hist>0, RSI>50, +DI>−DI): độ nghiêng của chỉ báo.
- **Tương quan** Pearson trên log-return D1, cửa sổ 30 ngày + cửa sổ 30 ngày liền trước (phát hiện đổi chiều). **Phiên** (UTC cố định, chỉnh trong YAML): biên độ/return trung bình Tokyo/London/NY và biên độ H1 trung bình theo giờ, 30 ngày.
- **Cảnh báo** (bật/tắt trong YAML): RSI cắt ngưỡng, nến chạm EMA200, đóng cửa vượt đỉnh/đáy N ngày, ATR% vượt phân vị 95, tương quan đổi dấu bất thường. Phát hiện theo cạnh giữa 2 nến cuối, `dedupe_key = an:<luật>:<symbol>:<khung>:<hướng>:<nến>` nên 1 điều kiện chỉ báo 1 lần/nến kể cả khi restart; alert-service dedupe thêm theo khoá này.

## Quyết định lưu trữ
Cần ghi bảng mới mà `storage-writer` thuộc nhóm khác, nên analytics có kết nối ghi riêng bằng role hạn chế `ts_analytics` (chỉ SELECT/INSERT/UPDATE/DELETE trên `analytics_snapshots`, không DDL, không đụng bảng khác). Đọc nến bằng `ts_ro`. Bảng + role: `infra/db/migrations/002_analytics.sql` và `infra/db/create_analytics_role.sh` (idempotent). Không có `ANALYTICS_DB_RW_URL` thì service vẫn phát sự kiện/cảnh báo nhưng không lưu.

### Hợp đồng bảng `analytics_snapshots(kind, key, ts, payload jsonb, updated_at)` (khoá chính kind+key, giữ bản mới nhất)
| kind | key | payload |
|---|---|---|
| `summary` | `SYMBOL:TF` | symbol, tf, bar_ts, close, heat, bias, trend(up/down/side), momentum, volatility, squeeze, atr_percentile, rsi, adx, atr_pct, macd_hist, stoch_k, bb_pctb, ema200_dist_pct, states[{code,label,tone,rule,group}], disclaimer |
| `detail` | `SYMBOL:TF` | như summary + indicators{}, pivot{p,r1,r2,s1,s2}, series{t(epoch s), ema20/50/200, bb_*, rsi, macd*, stoch_*, adx, atr} (`series_points` điểm cuối) |
| `correlation` | `D1` | symbols[], matrix[][], matrix_prev[][], window, as_of |
| `sessions` | `SYMBOL` | sessions{tokyo/london/newyork:{avg_range_pct, avg_return_pct, avg_abs_return_pct, days}}, hourly[24] |

Event `analytics.snapshot` trên stream `analytics.signals` (payload: generated_at, symbols, snapshots, alerts_published, top_heat[], disclaimer). Gateway cho phép stream này qua WebSocket.

## Cấu hình
`ANALYTICS_CONFIG` (YAML, mẫu `analytics.example.yaml`: chu kỳ, khung, lookback, danh sách symbol, phiên, bật/tắt từng cảnh báo + ngưỡng). Env: `DATABASE_URL` (ts_ro), `ANALYTICS_DB_RW_URL` (ts_analytics), `REDIS_URL`, `ENABLED`, `PORT`. HTTP: `/healthz`, `/metrics` (`analytics_cycles_total`, `analytics_cycle_seconds`, `analytics_snapshots`, `analytics_alerts_published_total`, `analytics_last_success_timestamp`), `/status` (kết quả chu kỳ gần nhất).

## Triển khai
```bash
cd infra
./db/create_analytics_role.sh        # migration 002 + role ts_analytics (+ POSTGRES_ANALYTICS_PASSWORD vào .env)
docker compose -p tradingsys --env-file .env -f docker-compose.yml -f docker-compose.ops.yml -f docker-compose.tools.yml up -d --build analytics api-gateway web-ui
```
Chu kỳ đầu chạy sau ~10 giây; trang "Phân tích" trống tới khi có snapshot.

## Phát triển
`pytest` trong `services/analytics` (không cần Docker/mạng). Test đối chiếu RSI với bảng Wilder, EMA/ATR/RSI/Bollinger với cài đặt thuần Python độc lập. Build: `docker build -f services/analytics/Dockerfile .` từ gốc repo.
