# track-record — HỢP ĐỒNG (backend / gateway / UI cùng bám file này)

Service mới `track-record` (Python/FastAPI, port 8000, mạng backend+ops, không publish cổng). Ghi DB bằng role hẹp `ts_trackrec`, đọc dữ liệu khác bằng `ts_ro`.
KHÔNG đặt lệnh, KHÔNG sinh văn bản tự do. Nhãn thực thể KHÔNG chứa tên website/nhà cung cấp (xem docs/UI_NO_SOURCES.md).

## Khái niệm
- **entity** = chuyên gia/nguồn ý kiến. `entity_id` ổn định; `label` trung lập hiển thị được (người/tổ chức có tên thật → tên; luồng tin/loại vị thế → "Luồng tin #n", "Ngân hàng trung ương #n", "Vị thế đầu cơ — EUR"...). `kind` ∈ analyst | central_bank | media | positioning | signal_provider | other. `lang` ∈ vi|en|other.
- **view** (quan điểm có hướng, bất biến): symbol, direction(bullish|bearish), published_at (thời điểm công bố gốc), observed_at (≥ published_at; lúc ta ghi nhận — dùng cho chống look-ahead), invalidation (mức vô hiệu nếu có), horizon_hint (nếu nêu), basis(news|signal|cot), ref (khoá nguồn băm), prev_hash/hash (chuỗi băm toàn cục, append-only).
- **horizon** ∈ 1D | 1W | 1M. Vào lệnh giả định = giá MỞ của nến D1 đầu tiên bắt đầu SAU observed_at (không look-ahead); thoát = đóng nến thứ 1 / 5 / 21 tính từ nến vào.
- **scope** (phân rã): `all`, hoặc asset class (`forex|metal|index|commodity|crypto|stock_us|stock_vn|etf|bond`), hoặc `sym:<SYMBOL>`; thêm `regime` ∈ trend|range|high_vol|low_vol (chế độ thị trường tại lúc công bố, tính từ D1 trước đó, không look-ahead).
- **status**: `rated` (n ≥ min_n, mặc định 30 quan điểm độc lập đã chấm) | `insufficient` (CHƯA ĐỦ MẪU — không xếp hạng, rank=null).
- Điểm uy tín `score` 0-100 = 100 × trung bình hậu nghiệm Beta (tiên nghiệm tâm 0,5; độ mạnh k theo kind) — co về 50 khi ít bằng chứng. `beats_baseline` = true CHỈ khi status=rated, q_value (BH-FDR toàn họ kiểm định) < 0,10 và cận dưới KTC Wilson của hit_rate > 0,5 và KTC bootstrap lợi suất trung bình > 0.
- `weight` (dùng cho đồng thuận) = 1 khi chưa đủ mẫu; khi rated = clamp(1 + 6·(post_mean − 0,5), 0,25, 2,0).

## API nội bộ của service (gateway proxy → `/v1/experts/...`, GET, JSON, chỉ đọc)
Mọi phản hồi có `method_version`, `as_of` (ISO UTC), `disclaimer` (chuỗi cố định: "Chỉ tham khảo, quá khứ không đảm bảo tương lai. Đa số ý kiến công khai không vượt được ngẫu nhiên.").

| Service path | Gateway path | Query |
|---|---|---|
| `GET /track/leaderboard` | `/v1/experts/leaderboard` | `horizon`(1D\|1W\|1M, mặc định 1W), `scope`(mặc định all), `kind`, `lang`, `min_n`(mặc định 30; chỉ để xem, không hạ ngưỡng xếp hạng dưới 10), `include_insufficient`(mặc định true), `limit`(≤200) |
| `GET /track/experts/{entity_id}/track-record` | `/v1/experts/{entity_id}/track-record` | `horizon`, `scope` |
| `GET /track/consensus` | `/v1/experts/consensus` | `window_days`(mặc định 14, ≤90), `scope`, `min_experts`(mặc định 1) |
| `GET /track/feed` | `/v1/experts/feed` | `limit`(≤200, mặc định 50), `symbol`, `direction`, `entity_id`, `before`(ISO) |
| `GET /track/methodology` | `/v1/experts/methodology` | — |
| `GET /track/chain/verify` | (master/service only) `/v1/experts/chain/verify` | — |
| `GET /healthz`, `/metrics` | — | — |

### leaderboard → 
```
{method_version, as_of, disclaimer, horizon, scope, min_n,
 baseline:{hit_rate:0.5, note:"ngẫu nhiên (hướng ngẫu nhiên, hoán vị)"},
 summary:{entities, rated, insufficient, beating_baseline, tests, expected_false_positives, fdr_q:0.10},
 rows:[{entity_id,label,kind,lang, n, n_total, hit_rate, ci_low, ci_high, mean_ret_pct, ret_ci_low, ret_ci_high,
        p_value, q_value, beats_baseline, score, prior_score, weight, status, rank|null, n_needed, last_view_at, symbols_n}]}
```
`n` = số quan điểm độc lập đã chấm ở horizon/scope này; `n_total` = tổng quan điểm; hit_rate/ci/ret/p/q là null khi n=0; khi insufficient vẫn trả n/hit_rate/ci để hiển thị "n=…/30".
### track-record →
```
{method_version, as_of, disclaimer, entity:{entity_id,label,kind,lang,first_view_at,last_view_at,n_total},
 card:{...như một row leaderboard cho horizon/scope được chọn},
 horizons:{"1D":{card},"1W":{card},"1M":{card}},
 by_scope:[{scope, n, hit_rate, ci_low, ci_high, mean_ret_pct, status}],      // theo asset class + top symbol
 by_regime:[{regime, n, hit_rate, ci_low, ci_high, mean_ret_pct}],
 rolling:[{t, n, hit_rate, ci_low, ci_high}],                                  // hit-rate tích luỹ theo thời gian (cửa sổ tích luỹ, Wilson)
 equity:{points:[{t, cum_ret_pct, rand_p05, rand_p50, rand_p95}], note},       // "nếu theo ý kiến" (tổng lợi suất log %, không phí) + dải ngẫu nhiên (hoán vị hướng)
 recent:[{view_id, symbol, direction, published_at, invalidation, state:"pending"|"resolved", outcome:{"1D":{ret_pct,hit}|null,"1W":..., "1M":...}}],
 chain:{head_hash, verified}}
```
### consensus →
```
{..., window_days, rows:[{symbol, asset_class, n_experts, bullish:{n, weight}, bearish:{n, weight},
   net_weighted(-1..1), net_unweighted(-1..1), agreement(0..1), level:"none"|"weak"|"consensus", latest_at,
   top:[{entity_id,label,direction,weight,status,published_at}]}]}
```
`level`: consensus khi n_experts ≥ 3 và |net_weighted| ≥ 0,6; weak khi |net_weighted| ≥ 0,3; còn lại none. Mỗi expert chỉ tính quan điểm MỚI NHẤT trong cửa sổ trên mỗi symbol.
### feed → `{..., items:[{view_id, entity_id, label, kind, symbol, asset_class, direction, published_at, invalidation, horizon_hint, status, weight}], next_before}`

## Redis (tiền tố `tr:`) — service ghi, expert-collector đọc
`tr:weights` = hash `entity_id -> json {"w":float,"score":float,"n":int,"status":"rated|insufficient","hit":float|null,"beats":bool}` cập nhật mỗi lần chấm lại (kèm `tr:weights:ts`).

## Bảng DB (migration infra/db/migrations/016_track_record.sql, role ts_trackrec)
`tr_entities`, `tr_views` (append-only: trigger chặn UPDATE/DELETE + role chỉ INSERT/SELECT), `tr_outcomes` (view_id,horizon → entry_ts, entry_px, exit_ts, exit_px, ret_log, hit; có thể tính lại), `tr_scorecards` (entity_id, scope, horizon → thống kê), `tr_runs` (nhật ký chấm).
Metric Prometheus: `trackrec_views_total{basis}`, `trackrec_entities{status}`, `trackrec_rated_beating_baseline`, `trackrec_last_scoring_timestamp`, `trackrec_chain_verified`, `trackrec_scoring_seconds`.
