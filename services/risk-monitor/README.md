# risk-monitor

Rủi ro tài khoản MT4/MT5 (và tài khoản paper, cùng engine) — **READ-ONLY**: chỉ đọc DB (role `ts_ro`) và Redis, chỉ phát cảnh báo lên `alerts.out`. Không có đường nào đặt/sửa/đóng lệnh.

```
account_snapshots / paper_* / bars(D1)  (ts_ro)  ─┐
Redis account.snapshots (metadata: tiền tệ, đòn bẩy, margin_mode) ─┴─> risk-monitor ──> alerts.out ──> alert-service (ntfy/Telegram)
                                                          └─ GET /risk/accounts[/{id}] ─> api-gateway /v1/risk/* ─> web-ui "Tài khoản"
```

## Tính gì (mỗi tài khoản)
- **Margin**: mức margin = equity/margin, margin tự do, khoảng cách tới stop-out (giả định margin yêu cầu không đổi), % bất lợi gross/net tới stop-out. Ngưỡng stop-out/margin-call cấu hình theo broker (`mt:`).
- **Exposure**: theo mã (MT4 hedging: lot mua/bán tách + phần bù trừ; MT5 netting: 1 vị thế/mã), theo tiền tệ (cặp = long BASE/short QUOTE), theo nhóm tài sản, gross/net, đòn bẩy hiệu dụng. Giá trị quy đổi về tiền tệ tài khoản bằng nến D1 gần nhất.
- **Drawdown**: ngày/tuần (UTC), đỉnh/đáy, drawdown từ đỉnh, tối đa, đường underwater. Không loại nạp/rút.
- **VaR/ES 1 ngày**: lịch sử, tham số (σ toàn kỳ) và EWMA λ=0,94; ES 97,5%; 10 ngày bằng căn bậc hai; backtest Kupiec cho VaR95 EWMA. Dựng từ lợi suất D1 áp lên vị thế hiện tại.
- **Tương quan & đóng góp rủi ro** (Euler), số "vị thế độc lập" hiệu dụng, cặp thực chất cùng một cược.
- **Stress**: replay 2008, CHF 2015, Brexit 2016, COVID 2020, 2022, yên 2024 (biến động giá thật từ `bars`) + kịch bản giả định (USD ±5%, vàng −10%, risk-off, gap 3%, bất lợi 10%). Cờ khi equity ≤ 0 hoặc chạm stop-out.
- **Ngân sách rủi ro**: tiêu thụ hạn mức (lỗ ngày/tuần, DD, đòn bẩy, margin tối thiểu, ES/equity, tập trung tiền tệ, số vị thế); warn ≥ 80%, crit ≥ 100%. Phát `alerts.out` khi trạng thái ĐỔI (không lặp).

## Cấu hình
`RISK_CONFIG` (YAML, xem `risk.example.yaml`; mặc định trong `config.py`). Tài khoản paper replay/smoke (`meaningful=false`) vẫn hiển thị nhưng không phát cảnh báo.

## Hạn chế
- Số là ƯỚC TÍNH từ snapshot; số margin/stop-out chính thức là của broker. Margin hedging của broker có thể khác gross/net ở đây.
- Mã MT không có nến D1 trong `bars` (chỉ số/CFD lạ) bị loại khỏi VaR/stress và được ghi trong `warnings`.
- Stress không tính trượt giá, gap, spread giãn; VaR đánh giá thấp rủi ro đuôi/gap cuối tuần.
- Equity MT được lấy mẫu 5 phút (`time_bucket`); DD trong ngày tính trên mẫu này.

## Mẫu luật đội tài khoản (FLEET_MGMT)
Engine `fleet.py` + `rules_engine.py` (hàm thuần): mỗi chu kỳ lấy assignments từ auth (`GET /internal/fleet/rules`), đánh giá từng (tài khoản x assignment) rồi gửi `POST /internal/fleet/results` (lô <= 500, kèm `conditions` kind `budget` từ ngân sách hiện có để hộp sự cố gom nguyên nhân).
- Loại luật: `daily_loss` (theo EQUITY, mốc reset theo `tz`/`reset_hour`), `max_drawdown` (`static|trailing_eod|trailing_intraday`), `margin_level`, `best_day` (xấp xỉ bằng chênh equity theo ngày, gồm nạp/rút nếu có), `max_trades_day` (đếm `account_deals`, bỏ `side='balance'`). Vàng khi usage >= `warn_usage_pct` (mặc định 70), đỏ khi >= 100%; thiếu dữ liệu -> `na` kèm lý do.
- Lịch sử equity cho luật >= 45 ngày (`fleet.history_days`, không đổi `equity_history_days` của ngân sách). Múi giờ: IANA (cần `tzdata`, đã thêm vào lock) hoặc `UTC+3`; thiếu tz dùng offset cố định cho múi không có giờ mùa hè.
- Chuyển trạng thái (xanh->vàng->đỏ, hồi phục) phát đúng 1 lần lên `alerts.out` (state ở Redis hash `risk:rule_state`). Luật `notify_client=true` leo thang cho tài khoản khách đã opt-in (`client_push` từ auth) -> `POST {ALERT_RULES_URL}/internal/notify` (push CHUNG, không lộ số liệu).
- Auth lỗi/404/503: giữ luật cũ tối đa 10 phút, chu kỳ ngân sách cũ không bị ảnh hưởng.
- `GET /risk/rules/status`: engine on/off, số assignment, lần đồng bộ cuối, kết quả gần nhất. Metrics: `risk_rule_status{status}`, `risk_rules_eval_seconds`, `risk_rules_sync_total`, `risk_rules_post_total`, `risk_rules_push_total`.
- Env: `FLEET_INTERNAL_TOKEN` (thiếu = TẮT engine), `FLEET_AUTH_URL` (mặc định `http://auth:8000`), `ALERT_RULES_URL` (mặc định `http://alert-rules:8000`).
- Luật nhà cái/prop firm KHÁC NHAU và thay đổi: cấu hình theo hợp đồng thực tế; đây chỉ là công cụ theo dõi, không đặt/sửa/đóng lệnh.
