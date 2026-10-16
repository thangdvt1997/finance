# pattern-scan — quét live kịch bản Sell -> ảnh -> thông báo -> PAPER

**CHỈ thông tin / mô phỏng. Không có đường tới lệnh thật** (`tests/test_no_real_execution.py`). Ảnh/thông báo không chứa tên nguồn dữ liệu.

```
pattern-engine --pattern.signals--> pattern-scan --(ts_pscan)--> pattern_scan_events / pattern_scan_media
       (bù: bảng pattern_signals, ts_ro)  |  nến bars (ts_ro) -> pattern_render PNG
                                          |-- ntfy (topic tradingsys-patterns, kèm ảnh): armed / triggered / đóng lệnh paper
                                          |-- triggered -> pattern_paper_trades + pattern_paper_ledger (hash-chain, append-only)
                                          '-- API /scan/* -> api-gateway /v1/patterns/{live,setup,media,trades,stats,examples}
```
Quy tắc paper, phân quyền, API: `docs/PATTERNS_SELL.md` §7, `docs/CONTRACTS.md`.

## Vận hành
```
infra/db/create_pscan_role.sh                                   # migration 019 + role ts_pscan (POSTGRES_PSCAN_PASSWORD -> infra/.env)
cd infra && docker compose -p tradingsys up -d --build --no-deps pattern-scan
```
Cấu hình: `pattern-scan.example.yaml` (mount :ro; sửa rồi restart). Biến: `PATTERN_NTFY_TOPIC`, `PATTERN_CLICK_URL` (link mở trang Kịch bản), `PATTERN_SCAN_ENABLED`.
Đăng ký nhận thông báo: app ntfy -> server ntfy của hệ thống (qua tunnel 127.0.0.1:8592) -> topic `tradingsys-patterns`.
Metrics: `pattern_scan_events_total`, `pattern_scan_render_total`, `pattern_scan_paper_trades_total`, `pattern_scan_paper_open`, `pattern_scan_notify_total`.

## Thư viện ví dụ
`examples/` (mount `/examples`): `<id>.png` + `<id>.json` {kind, pattern, title, symbol, tf, ts, note}. Mẫu chuẩn sinh từ fixture 3 ảnh mẫu bằng chính pipeline live:
`python tools/build_examples.py ../pattern-engine/tests/fixtures/xauusd_m15_gcf.csv examples` (cần cài pattern-engine, pattern-render, pattern-scan).
Ví dụ backtest của pattern-research có thể thả cùng định dạng vào đây.

## Test
`sh services/pattern-scan/tools/test.sh` (container tạm, chỉ mount mã cần thiết).
