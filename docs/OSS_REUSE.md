# OSS_REUSE: kế hoạch tái dùng mã nguồn mở (nghiên cứu 2026-10-11)

Nguyên tắc người dùng chỉ đạo: ưu tiên hệ thống tiên tiến nhất; có OSS phù hợp thì LẤY VỀ + CUSTOM, không viết mới. Tài liệu này chỉ KHẢO SÁT và ĐỀ XUẤT; không sửa code service nào.

## 0. Phương pháp và độ tin cậy
- Số liệu stars/license/push cuối lấy ngày 2026-10-11 từ GitHub REST API (`/repos/{owner}/{repo}`, trường `stargazers_count`, `license.spdx_id`, `pushed_at`).
- API bị giới hạn 60 req/giờ nên một số repo lấy qua: `github.com/{repo}/commits.atom` (ngày commit cuối), `img.shields.io/github/{stars,license}` (stars làm tròn) và file LICENSE thô. Các ô đó ghi (*) = stars làm tròn.
- `NOASSERTION` nghĩa là GitHub không nhận diện được giấy phép (thường là giấy phép tùy biến hoặc open-core); đã đọc LICENSE thô khi cần.
- Mục "chưa xác minh" = chỉ dựa trên kiến thức có sẵn hoặc kết quả tìm kiếm, chưa kiểm tra repo/trang gốc.
- Hiện trạng dự án (đã đọc PLAN.md, CONTRACTS.md, docker-compose.yml, README): Redis Streams, TimescaleDB pg16, Prometheus v2.54.1, Grafana 11.2.0, 7 service Python/FastAPI, mt-bridge READ-ONLY + EA MQL4/MQL5 outbound HTTPS, alert-service Telegram, basic auth/token, không có thực thi lệnh.

## 1. Nền dữ liệu / phân tích tài chính
| Ứng viên | Stars | License | Push cuối | Nhận xét |
|---|---|---|---|---|
| OpenBB (ODP v5, openbb-core 2.x) | ~74k (*) | Apache-2.0 (đã đọc LICENSE: "All files ... Apache 2.0") | commit 2026-10-02 | Nền dữ liệu đa nhà cung cấp, REST API + MCP. Workspace (UI) là dịch vụ riêng của OpenBB Inc., KHÔNG coi là OSS (chưa xác minh điều khoản) |
| ccxt | 44.3k | MIT | 2026-10-08 | Chuẩn cho crypto; không dùng cho forex/MT |
| yfinance | 25.5k | Apache-2.0 | 2026-10-05 | Không chính thức (scrape Yahoo), rủi ro ToS/chặn; chỉ làm nguồn dự phòng |
| Qlib (Microsoft) | 49.3k | MIT | 2026-10-08 | Nghiên cứu ML/factor; để phase chiến lược |
| vnstock | 1.4k | KHÔNG phải OSI: giấy phép riêng "license-2026.09" (đã đọc): bản Cộng đồng miễn phí cá nhân/học tập; cấm phân phối lại và dựng sản phẩm bán truy xuất dữ liệu nếu không thỏa thuận | 2026-10-08 | Giữ cờ mặc định TẮT như hiện tại; production dùng SSI/DNSE |
| Ghostfolio | 9.4k | AGPL-3.0 | 2026-10-11 | Theo dõi danh mục dài hạn, lệch mục tiêu (không phải MT) |
| Wealthfolio | 9.2k | AGPL-3.0 | 2026-10-09 | Như trên, local-first |
| FinceptTerminal | 32.4k | AGPL-3.0 (đã đọc README); README quảng cáo bản Enterprise trả phí | 2026-10-01 | Ứng dụng desktop C++20, không phải thư viện/service để nhúng |

Khuyến nghị:
- OpenBB ODP: THÊM, làm provider tùy chọn (macro, lịch kinh tế, cổ phiếu US, fundamentals) chạy container riêng `openbb-api`, market-collector gọi qua HTTP như một Provider. KHÔNG thay market-collector (nguồn Dukascopy tick, resample, quality gate đã có). Công sức: M. Rủi ro: dependency nặng, nhiều nhà cung cấp cần key (nhiều nguồn miễn phí có hạn mức), thay đổi lớn v4 -> v5 (docs có trang "Migration from V4") nên pin phiên bản. Ưu tiên: P2.
- yfinance, ccxt: GIỮ làm dự phòng/đối chiếu, không thêm sớm. ccxt chỉ khi mở sang crypto.
- vnstock: GIỮ nguyên (tắt mặc định); xem điều khoản trước khi bật; không dùng cho dịch vụ cấp lại dữ liệu cho người khác.
- Qlib: HOÃN tới phase strategy. Ghostfolio/Wealthfolio: BỎ QUA (lệch mục tiêu MT). Fincept: chỉ tham khảo UI (terminal-style), không tích hợp.

## 2. Bus / stream / ingest / lịch
| Ứng viên | Stars | License | Push cuối | Nhận xét |
|---|---|---|---|---|
| Redis Streams (hiện tại, Redis 7) | n/a | Redis 7.x là BSD; từ 7.4 đổi sang RSALv2/SSPL (chưa xác minh phiên bản cụ thể của tag `7-alpine`) | n/a | Đủ cho 1 VPS. Fork Valkey: 27.4k, BSD-3-Clause, push 2026-10-11, thay thế tương thích |
| NATS JetStream (nats-server) | 20.9k | Apache-2.0 | 2026-10-10 | Nhẹ (1 binary), persistence/replay/consumer ack, đa node |
| Redpanda | ~13k (*) | BSL 1.1 (đã đọc) | 2026-10-08 | Kafka-API, nặng, giấy phép hạn chế |
| Redpanda Connect (Benthos) | 8.8k | GitHub không nhận diện (chưa xác minh: lõi Apache-2.0, một số connector enterprise) | 2026-10-09 | Pipeline khai báo YAML, nhiều connector |
| Vector | 22.7k | MPL-2.0 | 2026-10-09 | Thu log/metric, mạnh về observability hơn là ingest thị trường |
| Airbyte | 22.2k | Elastic License 2.0 (đã đọc) | 2026-10-10 | Không OSS thật, nặng, bỏ |
| Dagster | 16.3k | Apache-2.0 | 2026-10-09 | Asset-based, hợp backfill dữ liệu có lịch sử |
| Prefect | 24.0k | Apache-2.0 | 2026-10-10 | Gọn hơn, Python thuần |
| Airflow | 47.1k | Apache-2.0 | 2026-10-11 | Nặng cho 1 VPS |

Khuyến nghị:
- Bus: GIỮ Redis Streams. Lý do: hợp đồng CONTRACTS.md, đã chạy, AOF bật, khối lượng thấp. Thay Redis bằng Valkey (cùng giao thức, đổi image) nếu muốn tránh rủi ro giấy phép: S. NATS JetStream là phương án nâng cấp khi cần replay dài/đa node (M, vì phải đổi tscommon bus); chưa cần ngay. Redpanda: KHÔNG (BSL).
- Collector: GIỮ code tự viết cho nguồn thị trường (ràng buộc ToS/quality). Với RSS/webhook/tin có thể thử Redpanda Connect hoặc Vector làm sidecar đẩy vào Redis stream (S mỗi nguồn), nhưng lợi ích nhỏ so với news-collector hiện có: P3.
- Lịch/backfill: KHÔNG thêm orchestrator ở vòng này (market-collector đã có backfill + STATE_FILE). Khi có nhiều pipeline (Parquet, báo cáo, retrain) thì chọn Prefect (nhẹ) hoặc Dagster: P3, M.
- Airbyte: BỎ (ELv2).

## 3. Lưu trữ chuỗi thời gian
| Ứng viên | Stars | License | Push cuối | Nhận xét |
|---|---|---|---|---|
| TimescaleDB (hiện tại) | 23.7k | GitHub: NOASSERTION (nhân Apache-2.0, phần nén/continuous aggregate thuộc Timescale License, chưa đọc lại bản hiện hành) | 2026-10-11 | Giữ: SQL chuẩn, Grafana datasource sẵn |
| QuestDB | 17.4k | Apache-2.0 | 2026-10-11 | Ingest rất nhanh, SQL mở rộng; chỉ đáng khi tick khối lượng lớn |
| ClickHouse | 50.3k | Apache-2.0 | 2026-10-11 | Phân tích cột cực nhanh; nặng hơn cho 1 VPS |
| DuckDB | 42.1k | MIT | 2026-10-10 | Đọc Parquet trực tiếp, lý tưởng cho lịch sử/backtest |

Khuyến nghị: GIỮ TimescaleDB cho realtime. THÊM DuckDB + Parquet cho lịch sử/xuất dữ liệu (job đêm xuất `md.bars` ra Parquet phân vùng theo ngày/symbol, S). Kiểm tra schema đã bật compression + continuous aggregates (retention) chưa (chưa xác minh, không đọc schema.sql ở vòng này). QuestDB/ClickHouse: chỉ xét nếu tick > hàng trăm triệu dòng; P4.

## 4. UI / giám sát
| Ứng viên | Stars | License | Push cuối | Nhận xét |
|---|---|---|---|---|
| Grafana (hiện có) | 77.2k | AGPL-3.0 | 2026-10-10 | Giữ; image đang 11.2.0, nên cập nhật |
| Apache Superset | 75.1k | Apache-2.0 | 2026-10-11 | BI đầy đủ nhưng nặng (nhiều container) |
| Metabase | 49.6k | AGPL + Commercial (đã đọc LICENSE; thư mục enterprise là thương mại) | 2026-10-11 | PLAN.md ghi Metabase; không cần nếu đã có Grafana |
| Evidence | 7.0k | MIT | 2026-10-09 | Báo cáo bằng Markdown + SQL, build ra HTML tĩnh; hợp báo cáo ngày/tuần |
| Perspective (FINOS) | ~11k (*) | Apache-2.0 | commit 2026-10-03 | Bảng/biểu đồ streaming WASM, phong cách terminal; nhúng được |
| Streamlit | 45.9k | Apache-2.0 | 2026-10-11 | Công cụ nội bộ nhanh |
| Reflex | 28.9k | Apache-2.0 | 2026-10-11 | Web app Python thuần |
| Uptime Kuma | 92.3k | MIT | 2026-10-11 | UI đẹp, cấu hình bằng chuột (khó đưa vào git) |
| Gatus | 12.3k | Apache-2.0 | 2026-10-07 | Cấu hình YAML, hợp GitOps; có endpoint `/metrics` Prometheus (chưa xác minh trong repo) |
| Dozzle | 14.6k | MIT | 2026-10-11 | Xem log container realtime, nhẹ; cần docker.sock |
| Portainer | 38.6k | Zlib | 2026-10-08 | Quản trị docker; thừa với 1 compose, rủi ro docker.sock |
| Loki | 29.0k | AGPL-3.0 | 2026-10-11 | Log tập trung; agent mới là Grafana Alloy (Apache-2.0, 3.6k, 2026-10-10) thay Promtail |

Khuyến nghị:
- GIỮ Grafana làm UI chính (đã provisioning). KHÔNG thêm Metabase/Superset (trùng vai trò, tốn RAM). Sửa PLAN.md bỏ Metabase.
- THÊM Gatus (S) cho kiểm tra healthz/độ trễ từ bên ngoài, đẩy cảnh báo qua ntfy/Telegram. THÊM Dozzle (S) cho log, qua docker-socket-proxy chỉ đọc. P1.
- THÊM Evidence (M) để sinh báo cáo HTML hằng ngày từ Timescale (thay vì tự viết PDF). P2.
- Perspective: thử nhúng làm trang "terminal-style" trong api-gateway (M, P3). Streamlit/Reflex: bỏ qua trừ khi cần công cụ nội bộ.
- Loki + Alloy: P3 (chỉ khi log docker `json-file` không đủ; Dozzle trước).
- Uptime Kuma/Portainer: không chọn.

## 5. Cảnh báo / thông báo
| Ứng viên | Stars | License | Push cuối | Nhận xét |
|---|---|---|---|---|
| Alertmanager | 8.6k | Apache-2.0 | 2026-10-11 | Gom/inhibit/silence cho cảnh báo Prometheus |
| ntfy | 34.7k | Apache-2.0 | 2026-10-10 | Push app điện thoại, tự host, 1 binary |
| Apprise | 17.6k | BSD-2-Clause | 2026-10-05 | Thư viện/API gửi tới 90+ kênh (Telegram, ntfy, email, Slack...) |

Khuyến nghị: THÊM Alertmanager (rules Prometheus -> webhook vào `alerts.out` của alert-service để dùng chung dedupe/route). THÊM Apprise như lớp kênh của alert-service (thay code gửi Telegram thuần bằng URL kiểu `tgram://...`, `ntfy://...`; GIỮ lệnh Telegram chỉ đọc /status). THÊM ntfy làm kênh dự phòng khi Telegram lỗi. Công sức: S-M. Ưu tiên P1.

## 6. Giao dịch (CHỈ KHẢO SÁT, chưa tích hợp thực thi)
Engine backtest/live:
| Ứng viên | Stars | License | Push cuối | Nhận xét |
|---|---|---|---|---|
| QuantConnect LEAN | 22.0k | Apache-2.0 | 2026-10-09 | C#/.NET, nhiều dữ liệu/broker; CLI: lean-cli 327 stars, Apache-2.0, 2026-10-08 |
| NautilusTrader | 29.8k | LGPL-3.0 | 2026-10-11 | Lõi Rust, Python API, event-driven; LGPL cho phép dùng làm thư viện, sửa lõi phải công khai |
| vectorbt | 9.3k | Apache-2.0 + Commons Clause (đã đọc): cấm bán phần mềm/dịch vụ mà giá trị chính là vectorbt | 2026-10-09 | Chỉ dùng nội bộ để quét ý tưởng |
| backtesting.py | 9.0k | AGPL-3.0 | 2026-08-05 | AGPL + nhịp commit chậm: tránh nhúng vào service |

Cầu nối MT4/MT5 (ứng viên tái dùng; chưa cái nào kiểm thử trong dự án):
| Ứng viên | Stars | License | Commit cuối | Nhận xét |
|---|---|---|---|---|
| dceoy/pdmt5 + dceoy/mt5api | 0 / 6 (*) | MIT | 2026-10-07 | Wrapper pandas + FastAPI cho package MetaTrader5 (Windows). Rất ít người dùng nhưng sạch, bảo trì; dùng làm tham chiếu/nền cho REST wrapper |
| lucas-campagna/mt5linux | 229 | MIT | 2026-10-07 | RPyC cho MT5 trên Wine, còn sống |
| gmag11/MetaTrader5-Docker | 401 | MIT | 2025-12-20 | MT5 + Wine docker (phương án B) |
| ariadng/metatrader-mcp-server | 825 (*) | MIT | 2026-03-28 | MCP cho MT5 nhưng có công cụ giao dịch: nếu dùng phải khóa chỉ đọc (investor password + chặn tool ghi) |
| darwinex/dwxconnect | 234 | BSD-3-Clause | push 2025-05-25 (đã 17 tháng) | Chậm bảo trì, chỉ tham khảo; hỗ trợ MT5 chưa xác minh |
| DeadSecure Dockerized MT5 DataBridge | 0 (*) | MIT | 2025-10-04 | Không đáng tin |
| liberatti/mt5bridge, psyb0t/docker-metatrader5-httpapi, mt5-grpc-server (PyPI) | n/a | chưa xác minh | chưa xác minh | Chỉ thấy qua tìm kiếm; psyb0t trả 404 khi mở github.com/psyb0t/docker-metatrader5-httpapi |
| MetaApi | n/a | dịch vụ cloud thương mại; SDK copyfactory commit cuối 2025-03-16 | | Không phù hợp nguyên tắc 0 đồng |
| Trade copier OSS còn sống | | | | KHÔNG tìm thấy dự án mã nguồn mở được bảo trì (chỉ sản phẩm thương mại trên MQL5 Market) -> Phase 8 tự dựng trên BrokerGateway |
| TradingView webhook | fabston ~1.9k (*) MIT, commit cuối 2024-05-01 (cũ); Zypheronz/TradingView-Webhook-MT5-Bridge: github.com trả 404 (chưa xác minh) | | | Tự viết endpoint nhỏ (FastAPI + secret + Redis stream `signals.inbox`) tốt hơn dùng repo cũ |

Khuyến nghị: không đổi gì ở mt-bridge/mt-agent (đã READ-ONLY, tự thiết kế EA outbound, hợp đồng chung). Khi tới phase thực thi: spike 1 tuần LEAN vs NautilusTrader (ưu tiên Nautilus nếu cần Python thuần/LGPL chấp nhận được; LEAN nếu cần hệ sinh thái dữ liệu), vectorbt chỉ để nghiên cứu. Tham khảo pdmt5/mt5api cho REST wrapper Windows (S-M). Cầu nối giao dịch MT4/MT5: vẫn khuyến nghị EA agent chung đã có, không dựa vào repo OSS nhỏ không ai dùng. Ưu tiên P4 (sau gate pháp lý G1-G3).

## 7. Quan sát hệ thống, triển khai, bảo mật
| Ứng viên | Stars | License | Push cuối | Nhận xét |
|---|---|---|---|---|
| grafana/docker-otel-lgtm | 2.0k | Apache-2.0 | 2026-10-09 | Image demo/dev gộp Loki+Grafana+Tempo+Mimir+OTel; không dùng production |
| OpenTelemetry Collector | 7.6k | Apache-2.0 | 2026-10-09 | Chuẩn thu trace/metric; tracing: `trace_id` đã có trong Event envelope |
| Semaphore | 14.3k | MIT | 2026-10-11 | UI chạy Ansible/Terraform; thừa cho 1 VPS |
| Renovate | 22.7k | AGPL-3.0 | 2026-10-11 | Tự động PR cập nhật image/pip (dùng như công cụ, không sửa) |
| Trivy | 38.3k | Apache-2.0 | 2026-10-09 | Quét image/dependency/secret/IaC |
| SOPS | 23.4k | MPL-2.0 | 2026-10-05 | Mã hóa file `.env` bằng age trong git |
| Infisical | 29.7k | MIT lõi + thư mục ee (GitHub: NOASSERTION; chưa đọc kỹ) | 2026-10-10 | Server secret đầy đủ, nặng |
| HashiCorp Vault | 36.4k | BSL (NOASSERTION) | 2026-10-09 | Thay bằng OpenBao: 8.4k, MPL-2.0, 2026-10-10 |
| Caddy | 77.7k | Apache-2.0 | 2026-10-11 | TLS tự động, cấu hình ngắn |
| Traefik | 65.2k | MIT | 2026-10-08 | Mạnh khi nhiều container/label |
| Authelia | 29.2k | Apache-2.0 | 2026-10-11 | SSO + 2FA, forward auth |
| oauth2-proxy | 15.1k | MIT | 2026-10-11 | Nhẹ, ủy quyền bằng IdP bên ngoài (Google/GitHub) |
| authentik | 25.9k | NOASSERTION (lõi MIT + phần enterprise; chưa đọc) | 2026-10-10 | IdP đầy đủ, nặng (Postgres+Redis+worker) |

Khuyến nghị:
- Trivy: THÊM (S), chạy `trivy image` cho 8 image trong CI/cron tuần. P1.
- Renovate: THÊM (S): `renovate.json` cho docker-compose + pip (compose đang ghim prometheus 2.54.1, grafana 11.2.0, redis 7). P1.
- Secrets: SOPS + age cho `.env` (S) thay vì dựng Vault/Infisical; OpenBao chỉ khi cần nhiều bí mật động. P1-P2.
- Reverse proxy + auth: Caddy + Authelia (hoặc oauth2-proxy nếu chỉ cần đăng nhập 1 IdP) thay basic auth/bind 127.0.0.1 cho Grafana và api-gateway (M). P2. Giữ token riêng của api-gateway cho client máy.
- Triển khai: GIỮ `docker compose` + script ssh; Semaphore/Ansible chưa cần (P4).
- OpenTelemetry/LGTM: Prometheus + `/metrics` hiện đủ; Alloy + Loki khi cần log tập trung; Tempo/tracing: P4.

## 8. AI an toàn (chỉ đọc)
- `openbb-mcp-server` (đã đọc docs.openbb.co v5): lệnh `openbb-mcp` chạy FastMCP, mặc định http://127.0.0.1:8001 (streamable-http; hỗ trợ stdio/sse), "exposes all GET endpoints as MCP tools", xác thực Bearer, Python >= 3.10 + openbb-core 2.x. QUAN TRỌNG: tùy chọn `--app` có thể phục vụ BẤT KỲ FastAPI app nào thành MCP tools. api-gateway của dự án là FastAPI chỉ đọc có token -> có thể bọc thành MCP server gần như không viết code (cần spike xác nhận: route nào lộ ra, auth token truyền thế nào). Công sức: S. Rủi ro: tool-poisoning/prompt injection từ nội dung tin; mitigations: chỉ route GET, không có route ghi/thực thi, token tách riêng quyền đọc, nội dung tin đưa vào LLM luôn gắn nhãn "dữ liệu không đáng tin".
- ariadng/metatrader-mcp-server: có công cụ đặt lệnh -> KHÔNG dùng (vi phạm "LLM không ra lệnh"), hoặc chỉ như tham khảo.
- Tóm tắt tin bằng LLM: thêm bước `news-summarizer` đọc `news.items`, ghi `news.summaries`; LLM cục bộ (Ollama, chưa xác minh phiên bản/model phù hợp VPS không GPU) hoặc Groq (free tier, chưa xác minh hạn mức hiện hành). Đầu ra chỉ là text, không gọi tool.

## 9. Bảng tổng hợp quyết định
| Hạng mục | Quyết định | Công sức | Ưu tiên |
|---|---|---|---|
| Bus Redis Streams | GIỮ (cân nhắc Valkey, NATS sau) | S | P3 |
| TimescaleDB | GIỮ + bật nén/CAgg nếu chưa | S | P2 |
| DuckDB + Parquet | THÊM (xuất lịch sử) | S | P2 |
| Grafana | GIỮ, cập nhật image | S | P1 |
| Gatus | THÊM | S | P1 |
| Dozzle (qua socket-proxy) | THÊM | S | P1 |
| Apprise + ntfy + Alertmanager | THÊM | S-M | P1 |
| Trivy + Renovate | THÊM | S | P1 |
| SOPS (age) | THÊM | S | P1 |
| Caddy + Authelia | THÊM, thay basic auth | M | P2 |
| openbb-mcp trên api-gateway (`--app`) | SPIKE | S | P1 |
| Evidence báo cáo | THÊM | M | P2 |
| OpenBB ODP làm provider | THÊM | M | P2 |
| Perspective, Loki+Alloy, Prefect/Dagster | CÂN NHẮC | M | P3 |
| Metabase/Superset/Airbyte/Redpanda | KHÔNG | | |
| LEAN/Nautilus, MT REST, trade copier | HOÃN tới phase thực thi, sau G1-G3 | L | P4 |

## 10. Roadmap tái dùng (quick wins trước)
Đợt A, ĐÁNG LÀM NGAY trong vòng này (đều S, không đụng code service):
1. Trivy quét 8 image + `renovate.json` (ghim/cập nhật image compose).
2. Gatus (YAML) giám sát `/healthz` mọi service + Dozzle qua docker-socket-proxy, thêm bằng file compose phụ `infra/docker-compose.oss.yml` (không sửa compose chính).
3. Apprise làm lớp kênh cho alert-service + ntfy kênh dự phòng; Alertmanager đẩy vào `alerts.out`.
4. SOPS + age mã hóa `.env` (thay vì lưu thô).
5. Spike 1 giờ: `openbb-mcp --app` trên api-gateway (chỉ đọc).
Đợt B (tuần tới): DuckDB/Parquet xuất đêm; Caddy + Authelia; cập nhật Grafana/Prometheus; Evidence báo cáo ngày.
Đợt C: OpenBB ODP provider (macro/lịch); news-summarizer LLM; Perspective; Loki+Alloy; Prefect nếu có nhiều pipeline.
Đợt D (sau cổng pháp lý): spike LEAN vs Nautilus; REST wrapper MT5 tham khảo pdmt5/mt5api; trade copier tự dựng.

## 11. Rủi ro chung / chưa xác minh
- Giấy phép: AGPL (Grafana, Loki, Renovate, Ghostfolio, Wealthfolio, Fincept, backtesting.py, Metabase) chỉ tác động khi sửa mã và cung cấp dịch vụ qua mạng cho người khác; dùng nội bộ nguyên bản ổn. vectorbt (Commons Clause) và vnstock (giấy phép riêng) hạn chế thương mại hóa.
- Chưa xác minh: điều khoản chi tiết TimescaleDB/Infisical/authentik/Redpanda Connect; license Redis theo tag đang dùng; Gatus có metrics Prometheus; phiên bản Ollama/Groq; mt5-grpc-server, liberatti/mt5bridge; số stars của một số repo (*) làm tròn; hỗ trợ MT5 của dwxconnect.
- Mọi ứng viên MT/trading chưa được thử trên tài khoản demo; không thay đổi nguyên tắc READ-ONLY hiện tại.
