# pattern-engine

Nhận diện **kịch bản vào lệnh Sell** (KB-1..KB-4, xem `plan1/` và `docs/PATTERNS_SELL.md`) trên **nến đã đóng**, độc lập mã và khung thời gian. **CHỈ thông tin / paper**: không gửi lệnh, SL/TP chỉ là gợi ý (hệ thống READ-ONLY).

```
bars (ts_ro) ─> pattern-engine ──INSERT──> pattern_signals (ts_pattern: chỉ SELECT/INSERT)
                  │  ZigZag-ATR đa thang -> máy trạng thái KB-1..4 (spec/*.yaml)
                  ├─ stream `pattern.signals` (event `pattern.signal`)  ─> gateway WS (client thấy armed/triggered)
                  └─ GET /patterns, /patterns/spec  ─(proxy)─> api-gateway /v1/patterns, /v1/patterns/spec
```

## Máy trạng thái
`forming` (sóng dẫn + hồi đạt) → `armed` (đủ mọi bước cấu trúc, chờ nến kích hoạt) → `triggered` (nến kích hoạt ĐÓNG) | `invalid` (huỷ: vượt đỉnh, quá hạn, phá đáy không có nến kích hoạt, cấu trúc mất…). `triggered`/`invalid` là trạng thái cuối. Mỗi `(setup_id, symbol, tf, state)` phát đúng 1 lần (DB UNIQUE + bộ nhớ).

- **Không look-ahead**: `Detector.feed(bar_i)` chỉ dùng nến ≤ i; cấu trúc chốt ở nến i−1, nến i chỉ là nến kích hoạt/huỷ. Test `tests/test_no_lookahead.py` chứng minh kết quả tại nến i không đổi khi thêm/đổi nến tương lai.
- **Không repaint**: pivot ZigZag đã xác nhận là append-only; sự kiện đã phát bất biến, đổi ý chỉ bằng sự kiện `invalid` mới.
- **Chuẩn hoá ATR**: swing = ZigZag đảo chiều ≥ k×ATR14 (đa thang `zigzag_atr: [2, 3]`), mọi ngưỡng theo ATR hoặc độ dài sóng — không dùng pip cố định → dùng được mọi mã/khung.
- **Tham số ở `spec/*.yaml`** (dung sai, huỷ kịch bản, điểm kích hoạt, `sl_buffer_atr`, `tp_r`); ghi đè qua `overrides:` trong file cấu hình runtime. Thêm kịch bản = thêm YAML + lớp mẫu hình trong `patterns.py`.

## Payload `pattern.signal`
`{pattern, tf, symbol, state, side:"sell", score(0..100), levels{entry, sl, tp_1r, tp_2r, tp_3r, r, atr, + neckline|support|resistance|high_5...}, steps[{id,label,ok,detail}], ts (lúc nến đóng), bar_ts (ts_open), setup_id, reason, info_only:true}`.

## Chạy
- Biến môi trường: `REDIS_URL`, `DATABASE_URL` (ts_ro), `PATTERN_DB_RW_URL` (ts_pattern; thiếu → chỉ RAM), `PATTERN_CONFIG` (`pattern-engine.example.yaml`), `PATTERN_SPEC_DIR`, `ENABLED`.
- Trước khi `up`: `infra/db/create_pattern_role.sh` (áp migration `018_pattern_signals.sql` + tạo `POSTGRES_PATTERN_PASSWORD`).
- Test (trên VPS, không chạy trên laptop): `sh infra/ops/run_tests.sh pattern-engine` hoặc `services/pattern-engine/tools/dev_sync.sh "pytest -q"`.

## Công cụ dev (`tools/`)
`export_fixture.py` (tick → M15, nguồn công khai), `yahoo_to_csv.py` (dự phòng), `replay.py` (phát lại CSV + `--trace`), `inspect_pivots.py`, `leg.py` (thống kê sóng dẫn), `dev_sync.sh` + `put_jump.js` (đồng bộ/chạy trên VPS qua bastion).

## Golden test & hạn chế
Xem `tests/fixtures/README.md` (nguồn nến, cách ánh xạ giờ ảnh→UTC, nến kỳ vọng) và `docs/PATTERNS_SELL.md` §Hiệu chỉnh. Mẫu golden chỉ 3 ví dụ → tham số đã hiệu chỉnh KHÔNG được coi là có edge; cần backtest rộng (giai đoạn B/C).
