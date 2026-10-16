# CHANGELOG — theo giai đoạn

Nguồn: `git log` (18 commit, 2026-10-11 → 2026-10-12) đối chiếu với các tài liệu chuyên đề. Dự án chưa gắn phiên bản số; các mốc dưới đây là **giai đoạn phát triển**, mới nhất ở trên. Trạng thái triển khai thật trên VPS nằm ở [KIEN_TRUC.md](KIEN_TRUC.md) và [README.md](../README.md). Các thay đổi sau commit cuối (2026-10-12) có thể chưa được commit: xem `git status`.

## Giai đoạn 8 — Hoàn thiện, hợp nhất tài liệu (2026-10-13 → 2026-10-14, đang làm)
- Hợp nhất tài liệu cho người dùng và người vận hành: `README.md` viết lại, mới: `docs/KIEN_TRUC.md`, `docs/GLOSSARY.md`, `docs/ADR/` (17 quyết định), `docs/CHANGELOG.md`, `docs/THIRD_PARTY_ALL.md`, `docs/INDEX.md`; `docs/HUONG_DAN_SU_DUNG.md` viết lại đầy đủ (master + client).
- Rà chéo tài liệu/thực tế: sửa các chỗ lỗi thời (đăng nhập Basic Auth → phiên `auth`, số container 25 → 36, cổng Grafana 3300, Redis ACL…) — danh sách ở cuối `docs/INDEX.md`.
- Chạy song song (không thuộc commit này): rà QA, bảo mật, vận hành, QA giao diện bởi các tác vụ khác.

## Giai đoạn 7 — Nền tảng master/client (2026-10-12, commit "auth service + provisioning", "WIP snapshot", "Terminal framework…")
**Master/client và truy cập**
- Dịch vụ **`auth`**: đăng nhập master/client (argon2id, khoá tạm, TOTP), phiên cookie, ghép cặp EA, audit hash-chain, vai trò phụ; nginx `auth_request`; gateway phân quyền whitelist + lọc theo tài khoản; 134 kiểm tra e2e ([AUTH.md](AUTH.md), [CLIENT_PLATFORM.md](CLIENT_PLATFORM.md)). Basic Auth lùi về dự phòng (`AUTH_BASIC_FALLBACK`, mặc định tắt).
- **mt-bridge cấp phát động** (đọc tài khoản từ `auth`, HMAC mặc định bật, thu hồi tức thì), **EA v1.1** (PairCode, sức khoẻ EA, xử lý 202/403/429); biên dịch sạch MT4 build 1492 / MT5 build 6253.
- **client-ui** (PWA `/c/`, vi/en): tổng quan, vị thế & lệnh chờ, rủi ro, nhật ký, thị trường, tin & lịch, bản tin AI, cảnh báo, thông báo, danh mục, cài đặt, giới hạn tự đặt; đồng bộ cài đặt giữa thiết bị.
- **Quản trị đội tài khoản (master)**: nhóm/tag/bulk 2 bước/import CSV, mẫu luật + engine tuân thủ, sự cố, vai trò (support/analyst/auditor), "xem như khách" có lý do + hết hạn, báo cáo theo khách ([FLEET_MGMT.md](FLEET_MGMT.md)).
**Giao diện master (web-ui)**
- Khung **Terminal/workspace/widget** kéo-thả; **biểu đồ chuyên nghiệp** (nhiều ô, replay, mẫu, 20k nến, công cụ vẽ, loại biểu đồ Renko/Kagi/P&F…, chỉ báo trong Web Worker); trang **thông tin thị trường** (sức mạnh tiền tệ, bản đồ nhiệt, movers, tương quan & rủi ro, phiên, nhịp thị trường, vị thế lớn & đồng thuận — [MARKET_INTEL.md](MARKET_INTEL.md)); hệ thống UX (cài đặt, thông báo, Ctrl-K v2, tour, thuật ngữ, xuất/in, design system — design system: trang `#/design`, xem [services/web-ui/README.md](../services/web-ui/README.md)); **ẩn tên nguồn** ([UI_NO_SOURCES.md](UI_NO_SOURCES.md)).
**Dữ liệu và phân tích**
- **Realtime hub** WS/SSE `rt.v1` ([REALTIME.md](REALTIME.md)); **cache nhiều tầng** ([PERFORMANCE.md](PERFORMANCE.md)).
- **track-record chuyên gia** (chấm điểm chống look-ahead, hoán vị, BH-FDR, hash-chain) + nguồn chuyên gia/ý kiến mở rộng + đồng thuận có trọng số ([EXPERT_TRACKRECORD.md](EXPERT_TRACKRECORD.md)).
- **briefing** — bản tin AI cục bộ có trích dẫn (llama.cpp, Qwen3.5-9B, không internet).
- Backtest cổ phiếu VN: momentum không có alpha, không đưa vào paper ([research/VN_BACKTEST.md](research/VN_BACKTEST.md)).
- Thiết kế tương lai: mặt phẳng điều khiển L0–L4 ([CONTROL_PLANE_DESIGN.md](CONTROL_PLANE_DESIGN.md)) — chỉ thiết kế, chưa có mã.

## Giai đoạn 6 — Hardening, vận hành, nhật ký, chứng khoán VN (2026-10-12, commit "vn-market, journal, hardening…")
- **vn-market**: HOSE/HNX/UPCoM cuối ngày, heatmap ngành, khối ngoại, screener, sự kiện doanh nghiệp ([VN_MARKET.md](VN_MARKET.md)).
- **journal**: nhật ký giao dịch kiểu Myfxbook (tổng quan, kỷ luật, MAE/MFE, review tuần) — kiểm chứng bằng fixture/mô phỏng, chưa có deal thật.
- **Hardening** ([HARDENING.md](HARDENING.md)): tách 5 mạng, secret theo service, 12 role DB hẹp, Redis ACL, exporter, SLO ([SLO.md](SLO.md)), retention + nén Timescale ([DATA_RETENTION.md](DATA_RETENTION.md)), tracing Jaeger/OpenTelemetry, lockfile có hash; backup mã hoá + PITR + restore-test ([DR_RUNBOOK.md](DR_RUNBOOK.md)).
- Quét CVE và nâng image: Redis 8.10, Prometheus 3.13, Grafana 12.4, Alertmanager 0.34… ([SECURITY_SCAN.md](SECURITY_SCAN.md)).

## Giai đoạn 5 — Crypto, đa tài sản, rủi ro, báo cáo (2026-10-11 → 12)
- **Crypto** (ccxt, 29 mã 24/7), registry loại tài sản; paper có chất lượng + hash-chain + strategy card + giám sát suy giảm; D1 backfill lịch sử + `yahoo_daily`; chiến lược `slow_trend_*_v2` khớp backtest.
- **web-ui**: chỉ báo/vẽ/Fibonacci/tín hiệu; **alert-rules** + watchlist + PWA; **risk-monitor** (VaR/ES/stress/margin/drawdown); **reporter** (báo cáo ngày/tuần HTML+PDF).
- Lộ trình nâng cấp ([UPGRADE_OPTIONS.md](UPGRADE_OPTIONS.md)).

## Giai đoạn 4 — Mô phỏng, nghiên cứu, cảnh báo giá (2026-10-11)
- **paper-trader** (mô phỏng, risk engine, kill-switch), cửa sổ rủi ro tin + calendar actual/forecast, backtest đa tài sản ([research/MULTI_ASSET_BACKTEST.md](research/MULTI_ASSET_BACKTEST.md)), kiểm toán kiến trúc ([research/ARCH_AUDIT.md](research/ARCH_AUDIT.md)).
- **analytics** (TA-Lib, screener, tương quan) và **nlp** (FinBERT + ViSoBERT ONNX); nghiên cứu phương pháp/tín hiệu thông tin ([STRATEGY_OPTIONS.md](STRATEGY_OPTIONS.md), [research/](research/)).

## Giai đoạn 3 — Vận hành và độ tin cậy (2026-10-11)
- Hardening đợt đầu: Redis ACL, role `ts_writer`, backup + PITR, release/rollback, nginx `real_ip`, cắt bus, kịch bản CI ([CI_CD.md](CI_CD.md)); độ tin cậy (XAUTOCLAIM, dispatcher cảnh báo), sửa chất lượng dữ liệu; nguồn dữ liệu miễn phí ([FREE_STACK.md](FREE_STACK.md)); bộ QA ([QA_REPORT.md](QA_REPORT.md)).
- **web-ui** layout full-viewport (100dvh, lưới co giãn, thanh bên thu gọn).

## Giai đoạn 2 — Giao diện, lab MT, công cụ vận hành (2026-10-11)
- Thêm **web-ui** (React/Vite, giao diện terminal); alert rules, backup, tunnel Cloudflare; nguồn dữ liệu đã kiểm thật; khảo sát OSS ([OSS_REUSE.md](OSS_REUSE.md)).
- **MT lab** (MT4/MT5 trong Wine): EA biên dịch sạch, chạy end-to-end tới Postgres; công cụ ops (Gatus, Dozzle, ntfy, docker-socket-proxy).
- Sửa triển khai: cấu hình mt-bridge, nối token API, Dukascopy/GDELT chịu lỗi, vnstock 4, hồ sơ chuyên gia.

## Giai đoạn 1 — Nền tảng v0.1 (2026-10-11)
- `libs/common` (Event, Bus Redis Streams), 7 microservice (storage-writer, market-collector, news-collector, expert-collector, mt-bridge, alert-service, api-gateway), hạ tầng compose (Redis, TimescaleDB, Prometheus, Grafana), hợp đồng ([CONTRACTS.md](CONTRACTS.md)) và kế hoạch + cổng pháp lý ([PLAN.md](../PLAN.md)).

---

## Chưa làm / còn dở (tại 2026-10-14)
Xem bảng đầy đủ ở [README.md](../README.md#trạng-thái-hiện-tại). Tóm tắt: chưa có tài khoản demo MT thật kết nối broker; chưa có key miễn phí (OANDA/TrueFX/Alpaca/Tiingo/Marketaux/FRED/BLS); chưa cấu hình Telegram; chưa có đích sao lưu off-site chính thức/khoá sao lưu cất riêng; cổng pháp lý G1–G3 chưa xong; không có thực thi lệnh (cố ý).
