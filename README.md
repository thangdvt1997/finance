# tradingsys — ứng dụng master hỗ trợ client MT4/MT5 (chỉ đọc + mô phỏng)

**tradingsys** là một nền tảng **master** theo dõi thị trường và hỗ trợ các **client** — mỗi client là một tài khoản **MT4 hoặc MT5**. Master (người vận hành) thấy toàn bộ đội tài khoản, thị trường, rủi ro, báo cáo; client (chủ tài khoản) chỉ thấy tài khoản của chính mình trong một ứng dụng điện thoại gọn nhẹ.

> **Giai đoạn hiện tại: CHỈ ĐỌC + MÔ PHỎNG (paper).** Hệ thống **không đặt lệnh, không có nút mua/bán, không dùng tiền thật, không thu mật khẩu giao dịch/investor của MT**. Số liệu mô phỏng dùng tiền ảo. Mọi chỉ báo/tín hiệu/tin/bản tin AI chỉ để tham khảo, **không phải khuyến nghị đầu tư**. Việc chuyển sang thực thi bị chặn bởi các cổng pháp lý G1–G3 trong [PLAN.md](PLAN.md) và mới chỉ có **thiết kế** ([docs/CONTROL_PLANE_DESIGN.md](docs/CONTROL_PLANE_DESIGN.md)), chưa có mã.

Mục lục toàn bộ tài liệu: **[docs/INDEX.md](docs/INDEX.md)** · Kiến trúc: [docs/KIEN_TRUC.md](docs/KIEN_TRUC.md) · Hướng dẫn người dùng: [docs/HUONG_DAN_SU_DUNG.md](docs/HUONG_DAN_SU_DUNG.md) · Vận hành: [docs/VAN_HANH.md](docs/VAN_HANH.md) · Thuật ngữ: [docs/GLOSSARY.md](docs/GLOSSARY.md) · Lịch sử: [docs/CHANGELOG.md](docs/CHANGELOG.md).

## Tính năng chính theo vai trò

| Vai trò | Làm được gì |
|---|---|
| **Master** | Terminal nhiều workspace/widget kéo-thả; biểu đồ chuyên nghiệp (nhiều ô, công cụ vẽ, chỉ báo, replay, 20k nến); thông tin thị trường (sức mạnh tiền tệ, bản đồ nhiệt, movers, tương quan, phiên, nhịp thị trường, COT); tin + lịch kinh tế (forecast/actual) + cửa sổ rủi ro tin; chuyên gia + **track record khách quan**; chứng khoán VN cuối ngày; crypto 29 mã; tài khoản/rủi ro (VaR/ES/stress)/nhật ký giao dịch; mô phỏng tiền ảo có hash-chain; cảnh báo/watchlist; báo cáo ngày/tuần PDF+HTML; bản tin AI cục bộ; **quản trị đội tài khoản** (nhóm/tag, thao tác hàng loạt, nhập CSV, luật tuân thủ, sự cố, vai trò support/analyst/auditor, xem-như-khách có lý do, audit hash-chain) |
| **Client** | Ứng dụng PWA `/c/` (vi/en): tổng quan tài khoản, vị thế + lệnh chờ, rủi ro, nhật ký, thị trường, tin & lịch, bản tin AI, cảnh báo + thông báo đẩy, **giới hạn tự đặt** (siết ngay, nới sau 24 giờ), danh mục nhiều tài khoản. Chỉ cài **một EA chỉ đọc**; không nhập mật khẩu MT ở đâu |

## Kiến trúc trong một hình

```
 Nguồn dữ liệu miễn phí ──► collector ×3 ─┐                                   ┌─► web-ui  (MASTER, nginx+React)
 Terminal MT4/MT5 + EA ──HTTPS ra──► mt-bridge ─┤                               │
 (chỉ đọc, ký HMAC)                              ▼                               │
                                        Redis Streams (bus)                      │
                                                 │                               │
              nlp · analytics · track-record · risk-monitor · journal · paper-trader · alert-rules · reporter · briefing
                                                 │                               │
                                  storage-writer ▼                               │
                                        TimescaleDB (12 role hẹp)                │
                                                 │                               │
              auth ◄── nginx auth_request ──► api-gateway (REST + WS/SSE realtime, phân quyền, cache) ─┴─► client-ui (CLIENT, PWA /c/)
```
36 container (project compose `tradingsys`), 5 mạng Docker tách lớp, không port nào bind 0.0.0.0. Chi tiết, sơ đồ mermaid, bảng 36 container: **[docs/KIEN_TRUC.md](docs/KIEN_TRUC.md)**; 17 quyết định kiến trúc: [docs/ADR/](docs/ADR/README.md).

## Cách truy cập

Hệ thống chạy trên VPS `<VPS_IP>` (project Docker Compose `tradingsys`, **chia sẻ máy với hệ thống khác** — chỉ thao tác container `tradingsys-*`), ra Internet qua **Cloudflare quick tunnel**.

| Cần | Làm |
|---|---|
| **Lấy link website** | Trên VPS: `cat /root/trading-system/data/tunnel_url.txt` (dạng `https://xxxx.trycloudflare.com`). **Link đổi mỗi khi dịch vụ `tradingsys-tunnel` khởi động lại.** |
| **Đăng nhập master** | Mở link → trang đăng nhập → *master*, tên `admin`. Mật khẩu ban đầu nằm ở `<SECRETS_DIR>/auth_master_admin.txt` trên VPS (chỉ root đọc; **không có trong repo/tài liệu**); đổi bắt buộc ở lần đầu; nên bật TOTP. Basic Auth cũ chỉ còn là đường dự phòng (`AUTH_BASIC_FALLBACK`, mặc định tắt). Chi tiết: [docs/AUTH.md](docs/AUTH.md) |
| **Đăng nhập client** | `<link>/c/` → nền tảng MT + số tài khoản + passcode do master cấp (hoặc mã ghép cặp để tự đặt mật khẩu) |
| **Công cụ vận hành** (chỉ `127.0.0.1`, qua SSH tunnel) | Gatus `:8590`, Dozzle (log) `:8591`, ntfy `:8592`, Grafana `:3300`, Jaeger `:16686`, gateway `:8480`, web-ui `:8580`, client-ui `:8581`, mt-bridge `:8490` |
| **Triển khai** | Từ laptop: `./deploy.sh "<lệnh compose>"` (luôn dùng `deploy.sh`; build/test chạy **trên VPS**, không chạy trên laptop) |
| **Kiểm thử** | `bash tests/e2e/deploy.sh` rồi `sh /root/qa-e2e/run_remote.sh test_flow.py` ([docs/VAN_HANH.md](docs/VAN_HANH.md) mục 14) |

## Trạng thái hiện tại

Cập nhật 2026-10-14 (đối chiếu VPS: 36/36 container chạy).

| Đã làm và đang chạy | Chưa làm / hạn chế | Cần NGƯỜI DÙNG |
|---|---|---|
| Thu thập giá FX/vàng/ETF/cổ phiếu Mỹ/crypto, tin, lịch (forecast/actual), COT, chuyên gia, chứng khoán VN cuối ngày | **Chưa có tài khoản demo/live MT thật** kết nối broker: EA đã biên dịch sạch (MT4 b1492, MT5 b6253) và chạy trong lab Wine, chưa thử với server broker thật | Mở tài khoản demo MT4/MT5 (cần thông tin cá nhân) và cài EA |
| Auth master/client (phiên, TOTP, ghép cặp), phân quyền gateway, chống IDOR (134 kiểm tra e2e) | **Không thực thi lệnh** (cố ý). Mặt phẳng điều khiển L0–L4 chỉ là thiết kế | Cổng pháp lý **G1** (forex), **G2** (chứng khoán/robot), **G3** (ToS broker) bằng văn bản |
| Master: Terminal, biểu đồ pro, thông tin thị trường, đội tài khoản/luật/sự cố/vai trò, báo cáo theo khách | Realtime trong phiên và tự doanh cho cổ phiếu VN (nguồn miễn phí không có); BCTC lịch sử point-in-time; mô phỏng chưa áp T+2/trần-sàn/margin call VN | Quyết định có chi tiền cho dữ liệu trả phí hay không (hiện: gói 0 đồng) |
| Client: PWA vi/en, giới hạn tự đặt, Web Push (khi có khoá VAPID) | Web Push cần cấu hình khoá VAPID; form tạo quy tắc máy chủ cho client chưa có trong UI | Cấu hình VAPID nếu muốn đẩy khi app đóng |
| Paper-trader (tiền ảo, hash-chain, strategy card, benchmark) | **Chưa đủ dữ liệu để kết luận** (cần hàng năm); nghiên cứu: xu hướng chậm Sharpe 0,55 nhưng không thắng 60/40; momentum VN không có alpha | Gửi phương pháp giao dịch riêng nếu muốn đưa vào quy trình backtest → paper → duyệt |
| Track-record chuyên gia khách quan | **Chưa chuyên gia nào vượt baseline ngẫu nhiên** (0/99) — kết quả thật, không phải lỗi | — |
| Bản tin AI cục bộ có trích dẫn (06:15, 16:30 VN) | Chậm (~3 phút/bản), cần 16 GB RAM; chưa đo chất lượng dài hạn | — |
| Hardening: 5 mạng, 12 role DB hẹp, Redis ACL, secret theo service, SLO, backup mã hoá + PITR + restore-test, giám sát (Prometheus/Gatus/Grafana/Jaeger/ntfy) | Backup off-site chính thức chưa có đích; khoá sao lưu cần cất riêng; Telegram chưa cấu hình (cảnh báo qua ntfy); cảnh báo giấy phép (Redis/Grafana/TimescaleDB/vnstock…) — [docs/THIRD_PARTY_ALL.md](docs/THIRD_PARTY_ALL.md) | Cất khoá sao lưu `/root/.tradingsys-backup.key` ngoài VPS; cung cấp đích off-site; Telegram bot token + chat id; key miễn phí (OANDA, TrueFX, Alpaca, Tiingo, Marketaux, FRED, BLS) vào `infra/.env` |
| Tunnel Cloudflare quick | Địa chỉ **đổi khi restart**; chưa có tên miền/Named Tunnel/Cloudflare Access | Cân nhắc tên miền + Named Tunnel nếu muốn link cố định |

Việc dở dang và lộ trình nâng cấp: [docs/UPGRADE_OPTIONS.md](docs/UPGRADE_OPTIONS.md), [docs/HANDOFF_2026-10-12.md](docs/HANDOFF_2026-10-12.md) (ảnh chụp trạng thái 10-12), [docs/CHANGELOG.md](docs/CHANGELOG.md).

## Nguyên tắc dự án

1. **Chỉ đọc → mô phỏng → (chỉ sau G1–G3) mới nghĩ tới live.**
2. Không thu mật khẩu MT; EA luôn **gọi ra**, không mở cổng vào.
3. **Gói 0 đồng**: nguồn/công cụ miễn phí, tích hợp OSS thay vì viết lại.
4. **Không hiển thị tên nguồn dữ liệu** trên giao diện/báo cáo/thông báo.
5. Thà "chưa đủ mẫu"/im lặng còn hơn kết luận sai.
6. Build/test/deploy **chỉ trên VPS**; laptop chỉ sửa file + git.

## Cấu trúc repo

```
libs/common/       thư viện dùng chung (Event, Bus, bộ lọc ẩn nguồn)
services/<tên>/    alert-rules, alert-service, analytics, api-gateway, auth, briefing, client-ui, expert-collector,
                   journal, market-collector, mt-bridge, news-collector, nlp, paper-trader, reporter, risk-monitor,
                   storage-writer, track-record, vn-market, web-ui   (mỗi service có README.md riêng)
mt-agent/          EA MQL4/MQL5 chỉ đọc + lab Wine
infra/             docker-compose (3 file), DB schema + 17 migration, backup, ops, prometheus, grafana
tests/e2e/         kiểm thử đầu-cuối trên VPS      research/  mã + kết quả backtest/nghiên cứu
docs/              tài liệu (bắt đầu từ docs/INDEX.md)      PLAN.md  kế hoạch + cổng pháp lý
```

## Giấy phép phần mềm bên thứ ba
Có thành phần không phải OSS thuần (TimescaleDB TSL, Redis RSAL/SSPL/AGPL, Grafana AGPL, vnstock "chỉ cá nhân", mô hình ViSoBERT chưa khai báo): **[docs/THIRD_PARTY_ALL.md](docs/THIRD_PARTY_ALL.md)**. Mã tự viết trong repo chưa có tệp LICENSE.
