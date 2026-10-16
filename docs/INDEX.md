# INDEX — mục lục tài liệu tradingsys

Cập nhật 2026-10-15. Bắt đầu từ [../README.md](../README.md) (tổng quan, trạng thái thật thà). Mỗi mục: một dòng mô tả. Nhãn: **[mới]** = tài liệu hợp nhất 2026-10-14; *(lịch sử)* = ảnh chụp thời điểm, có thể lỗi thời một phần.

## Tôi là NGƯỜI DÙNG (master hoặc client, không cần biết lập trình)
| Tài liệu | Mô tả |
|---|---|
| [HUONG_DAN_SU_DUNG.md](HUONG_DAN_SU_DUNG.md) | Hướng dẫn đầy đủ: master (đăng nhập, Terminal, biểu đồ, thông tin, chuyên gia, VN, rủi ro, mô phỏng, cảnh báo, báo cáo, quản trị đội), client (cài EA, ghép cặp, các trang), cách đọc số, FAQ **[mới/viết lại]** |
| [GLOSSARY.md](GLOSSARY.md) | Thuật ngữ tài chính (equity, drawdown, Sharpe…) và hệ thống (EA, HMAC, ghép cặp…) **[mới]** |
| [../services/client-ui/README.md](../services/client-ui/README.md) | Ứng dụng PWA của client: trang, i18n vi/en, đồng bộ cài đặt, `?mock=1` |
| [../mt-agent/README.md](../mt-agent/README.md) | Cài EA chỉ đọc MT4/MT5 cho client, bảng trạng thái EA, bảo mật |
| [samples/](samples/) | Báo cáo mẫu ngày/tuần (HTML+PDF) |

## Tôi là NGƯỜI VẬN HÀNH
| Tài liệu | Mô tả |
|---|---|
| [LOCAL_LLM.md](LOCAL_LLM.md) | LLM local (llama.cpp, `la`, router, mở rộng node), digest tự sinh `handoff/DIGEST.md`, đo token `handoff/TOKENS.md` (infra/ops/digest.sh, tokens_report.py) |
| [VAN_HANH.md](VAN_HANH.md) | Sổ tay vận hành: truy cập công cụ, log, sức khoẻ, deploy/rollback, sao lưu, mật khẩu, khoá API, thêm tài khoản MT, sự cố, checklist, QA, quản trị đội |
| [DR_RUNBOOK.md](DR_RUNBOOK.md) | Sao lưu mã hoá, PITR, khôi phục thảm hoạ, nhật ký diễn tập |
| [BACKUP_OFFSITE.md](BACKUP_OFFSITE.md) | Sao lưu off-site (script backup_offsite.sh, dry-run mặc định; đích do người dùng cấp) |
| [DATA_RETENTION.md](DATA_RETENTION.md) | Nén và giữ lại dữ liệu Timescale theo bảng |
| [OBSERVABILITY.md](OBSERVABILITY.md) | Prometheus, Grafana, Jaeger, Gatus, log, cảnh báo |
| [SLO.md](SLO.md) | Mục tiêu mức dịch vụ + luật burn-rate |
| [CI_CD.md](CI_CD.md) | Lockfile, kịch bản CI trên VPS, release/rollback, đề xuất SSO |
| [FREE_STACK.md](FREE_STACK.md) | Nguồn dữ liệu miễn phí, khoá API cần đăng ký, nguồn nào tự bật khi có key |
| [DATA_SOURCE_PRIORITY.md](DATA_SOURCE_PRIORITY.md) | Thứ tự ưu tiên nguồn nến D1 và quy tắc gộp |
| [DATA_CLEANUP_LAB.md](DATA_CLEANUP_LAB.md) | Đề xuất dọn dữ liệu lab lẫn trong DB thật + migration đơn vị giá VN (chưa chạy) |
| [../infra/README.md](../infra/README.md) | Cấu trúc compose, mạng, công cụ OSS vận hành (Gatus/Dozzle/ntfy), cổng |
| [../mt-agent/LAB.md](../mt-agent/LAB.md) | Lab MT4/MT5 trong Wine để biên dịch và thử EA |
| [../tests/e2e/](../tests/e2e/) | Kiểm thử đầu-cuối chạy trên VPS |

## Tôi là KIẾN TRÚC SƯ / LẬP TRÌNH VIÊN
| Tài liệu | Mô tả |
|---|---|
| [KIEN_TRUC.md](KIEN_TRUC.md) | Sơ đồ thành phần, luồng dữ liệu (giá/tin/tài khoản/cảnh báo/báo cáo), mạng-bảo mật, bảng 37 container **[mới]** |
| [ADR/README.md](ADR/README.md) | 17 quyết định kiến trúc (Bối cảnh/Quyết định/Hệ quả) **[mới]** |
| [CONTRACTS.md](CONTRACTS.md) | Nguồn chân lý: envelope, streams, payload, DB, quy ước từng giai đoạn |
| [CLIENT_PLATFORM.md](CLIENT_PLATFORM.md) | Mô hình master/client, bảng, API provisioning mt-bridge ↔ auth |
| [AUTH.md](AUTH.md) | Auth: mô hình đe doạ, luồng, bảng quyền, vận hành, rủi ro còn lại |
| [FLEET_MGMT.md](FLEET_MGMT.md) | Đội tài khoản: vai trò, API quản trị, bulk/CSV, mẫu luật, sự cố |
| [REALTIME.md](REALTIME.md) | Hub realtime `rt.v1` (WS/SSE), topic, backpressure, SDK |
| [PERFORMANCE.md](PERFORMANCE.md) | Cache 5 tầng, an toàn không cache chéo, đo trước/sau |
| [MARKET_INTEL.md](MARKET_INTEL.md) | Endpoint `/v1/intel/*`, trang và widget thông tin thị trường |
| [EXPERT_TRACKRECORD.md](EXPERT_TRACKRECORD.md) | Phương pháp chấm uy tín chuyên gia; hợp đồng API `services/track-record/CONTRACT.md` |
| [VN_MARKET.md](VN_MARKET.md) | Chứng khoán VN: nguồn, quy tắc (phí, thuế, biên độ), giới hạn |
| [UI_NO_SOURCES.md](UI_NO_SOURCES.md) | Quy tắc ẩn tên nguồn; bộ lọc trung tâm `tscommon.sources` |
| [../services/web-ui/README.md](../services/web-ui/README.md) | web-ui: Terminal/widget, biểu đồ pro, hệ thống UX, giao diện quản trị đội, design system, QA |
| [../services/*/README.md](../services/) | README từng service (api-gateway, analytics, paper-trader, risk-monitor, journal, reporter, nlp, briefing, mt-bridge, …); `auth` chỉ có tài liệu ở AUTH.md; `track-record` ở CONTRACT.md |
| [OSS_REUSE.md](OSS_REUSE.md) | Khảo sát OSS để tái dùng, quyết định giữ/thay/bỏ |
| [THIRD_PARTY_ALL.md](THIRD_PARTY_ALL.md) | Giấy phép hợp nhất + cảnh báo AGPL/RSAL/TSL/"chỉ cá nhân" **[mới]** |
| [../services/web-ui/THIRD_PARTY.md](../services/web-ui/THIRD_PARTY.md) | Giấy phép frontend (gốc) |
| [CHANGELOG.md](CHANGELOG.md) | Lịch sử theo giai đoạn **[mới]** |

## Tôi lo BẢO MẬT / TUÂN THỦ
| Tài liệu | Mô tả |
|---|---|
| [HARDENING.md](HARDENING.md) | Container read-only, secret theo service, 5 mạng, bảng service→role DB, Redis ACL |
| [AUTH.md](AUTH.md) | Mô hình đe doạ đăng nhập/phiên/IDOR, TOTP, audit hash-chain |
| [SECURITY_SCAN.md](SECURITY_SCAN.md) | Quét CVE (Trivy) và nâng image |
| [CONTROL_PLANE_DESIGN.md](CONTROL_PLANE_DESIGN.md) | **Thiết kế** (chưa có mã) kênh lệnh L0–L4: ký lệnh, kill-switch 4 tầng, 4-eyes, STRIDE, pháp lý |
| [../PLAN.md](../PLAN.md) | Kế hoạch gốc + cổng pháp lý G1 (forex), G2 (CK/robot), G3 (broker) |
| [ADR/](ADR/README.md) | ADR-004 (chỉ đọc trước), 006 (không lưu mật khẩu MT), 013 (ký lệnh), 014 (tách mạng/role) |

## Tôi làm NGHIÊN CỨU / CHIẾN LƯỢC
| Tài liệu | Mô tả |
|---|---|
| [STRATEGY_OPTIONS.md](STRATEGY_OPTIONS.md) | Phương án giao dịch tổng hợp từ 3 nghiên cứu (đánh giá trung thực) |
| [UPGRADE_OPTIONS.md](UPGRADE_OPTIONS.md) | Lộ trình nâng cấp xếp ưu tiên; việc cần người dùng *(một phần lịch sử)* |
| [research/METHODS_SURVEY.md](research/METHODS_SURVEY.md) | Khảo sát văn liệu phương pháp giao dịch, pháp lý, T+2 |
| [research/BACKTEST_STUDY.md](research/BACKTEST_STUDY.md) | Backtest FX/vàng 2002–2026 |
| [research/PATTERN_SELL_BACKTEST.md](research/PATTERN_SELL_BACKTEST.md) | Backtest trung thực Kịch bản Sell KB-1..KB-4 (walk-forward, test khoá, baseline ngẫu nhiên): không có edge sau chi phí |
| [research/MULTI_ASSET_BACKTEST.md](research/MULTI_ASSET_BACKTEST.md) | Xu hướng chậm đa tài sản 1990–2026: Sharpe 0,55, không thắng 60/40 |
| [research/VN_BACKTEST.md](research/VN_BACKTEST.md) | Momentum cổ phiếu VN: không có alpha |
| [research/INFO_SIGNALS_STUDY.md](research/INFO_SIGNALS_STUDY.md) | Tin/COT/ý kiến có dự báo được không (kết luận: không) |
| [research/ARCH_AUDIT.md](research/ARCH_AUDIT.md) | Kiểm toán kiến trúc → hardening |
| [research/PLATFORM_BENCHMARK.md](research/PLATFORM_BENCHMARK.md) | So sánh với terminal thương mại/OSS |
| [research/PRO_WORKFLOW_GAPS.md](research/PRO_WORKFLOW_GAPS.md) | Khoảng trống quy trình chuyên nghiệp |
| [research/DATA_AND_TOOLING_MARKET.md](research/DATA_AND_TOOLING_MARKET.md) | Thị trường dữ liệu và công cụ |
| [research/UI_BACKLOG.md](research/UI_BACKLOG.md) | Backlog giao diện |
| [research/UI_FINAL_QA.md](research/UI_FINAL_QA.md) | QA giao diện cuối master + client: trang × độ phân giải × lỗi × đã sửa, điểm, tồn đọng (2026-10-14) |
| [research/openbb_mcp_spike.md](research/openbb_mcp_spike.md) | Spike OpenBB MCP |
| [sources/](sources/) | Danh mục nguồn dữ liệu đã khảo sát (ngân hàng trung ương, nội bộ/hàng hoá, vĩ mô, mạng xã hội, Việt Nam) |
| [../services/paper-trader/README.md](../services/paper-trader/README.md) | Mô phỏng: chiến lược, strategy card, hash-chain |

## Báo cáo kiểm thử và ảnh chụp trạng thái
| Tài liệu | Mô tả |
|---|---|
| [QA_REPORT.md](QA_REPORT.md) | Kiểm thử toàn hệ thống, vòng 1–5 (Vòng 5 = danh sách mục đã đóng/còn mở 2026-10-15) *(số liệu theo thời điểm)* |
| [HANDOFF_2026-10-12.md](HANDOFF_2026-10-12.md) | Trạng thái bàn giao 10-12 *(lịch sử, đã có ghi chú cập nhật)* |
| [handoff/PROGRESS.md](handoff/PROGRESS.md) | Tiến độ theo giờ + `handoff/*_status.md` (PE, SCAN, MT5, FEED, FEED_ALL, SEC) |
| [handoff/STABILIZATION_REPORT.md](handoff/STABILIZATION_REPORT.md) | **Báo cáo ỔN ĐỊNH HOÁ 2026-10-15**: bảng nhóm A..J, pass/fail trước-sau, lỗi đã sửa (commit), lỗi còn lại, lệnh chạy lại (chi tiết từng nhóm `handoff/stabilize/*.md`, lỗi phiên khác `handoff/QA_ISSUES.md`) |
| [research/PATTERN_DATA.md](research/PATTERN_DATA.md) | Dữ liệu lịch sử 7 mã × 21 khung MT5 cho Kịch bản Sell |
| [PATTERNS_SELL.md](PATTERNS_SELL.md) | Đặc tả Kịch bản Sell KB-1..KB-4, quét live, paper |
| [AI_TRADING.md](AI_TRADING.md) | Tab "AI Trading": mục tiêu/ràng buộc, API+registry YAML, cách thêm kịch bản/mô hình, trạng thái GĐ A-D, khảo sát ý tưởng AI + backlog 27 mục, cách tái lập backtest |
| [DATA_KEEPER.md](DATA_KEEPER.md) | data-keeper: giám sát phủ dữ liệu 162 mã, LLM cục bộ chẩn đoán (fallback tất định), API /v1/data/*, trang "Dữ liệu" |
| [AI_CLASSROOM.md](AI_CLASSROOM.md) | AI Training Class: chuyên gia dạy AI một kịch bản (hỏi sâu, học 1 hiểu 10, quét ví dụ + gắn nhãn, test trung thực); lõi P2a + backend P2b (SQLite bền, vai expert, API/SSE, worker quét); hợp đồng API UI: [handoff/AI_CLASSROOM_API.md](handoff/AI_CLASSROOM_API.md) |
| [HANDOFF_VPS_2026-10-14.md](HANDOFF_VPS_2026-10-14.md) | **Bàn giao mới nhất** — phiên VPS 10-14: trạng thái từng mảng, việc kế tiếp, việc cần người dùng (tiến độ: handoff/PROGRESS.md) |

---

## Kết quả rà soát chéo (2026-10-14): mâu thuẫn và lỗi thời đã phát hiện

| # | Phát hiện | Nơi | Xử lý |
|---|---|---|---|
| 1 | **Đăng nhập**: nhiều tài liệu vẫn nói website sau Basic Auth, trong khi thực tế là đăng nhập phiên (`auth`, từ 10-12) và Basic Auth mặc định **tắt** | README gốc, HUONG_DAN_SU_DUNG, VAN_HANH §1/§6, bảng sự cố, §13, services/web-ui/README, CI_CD, CLIENT_PLATFORM, HANDOFF | Đã sửa/ghi chú; `AUTH_BASIC_FALLBACK` giữ làm dự phòng |
| 2 | **Cổng Grafana**: tài liệu ghi `:3000`, trên VPS là `127.0.0.1:3300` (`GRAFANA_PORT=3300`, trong container 3000) | VAN_HANH §1/§3, `infra/.env.example` (vẫn 3000 làm mặc định) | VAN_HANH đã sửa; `.env.example` giữ mặc định 3000 (đúng cho máy mới) |
| 3 | **Số container**: HARDENING ghi 25, infra/README ghi "15 service", prometheus "7 service" — thực tế **36 container**, Prometheus scrape 18 service Python | HARDENING, infra/README, CONTRACTS | Đã thêm ghi chú trỏ về KIEN_TRUC §5 |
| 4 | **Redis "không auth"** trong infra/README — thực tế Redis ACL theo user | infra/README | Đã sửa |
| 5 | **infra/README** mô tả deploy `/opt/trading-system` "chưa deploy" — thực tế đã chạy ở `/root/trading-system`, deploy bằng `deploy.sh` (3 file compose; chỉ chạy file chính sẽ đảo ngược nâng cấp image) | infra/README | Đã ghi chú |
| 6 | **CONTRACTS** danh sách service dừng ở v0.1 (thiếu auth, client-ui, track-record, briefing…) | CONTRACTS | Đã thêm con trỏ tới KIEN_TRUC |
| 7 | **T+2 / trần-sàn** (cổ phiếu VN): VN_MARKET nói mô phỏng chưa áp; một số mô tả suy ra mô phỏng đủ thực tế | HUONG_DAN, VN_MARKET, PRO_WORKFLOW_GAPS V1 | Thống nhất: **cấu hình `settlement_days=2`, mô phỏng CHƯA áp T+2/biên độ/margin call**; chưa thấy văn bản chuyển T+1 |
| 8 | **Giấy phép Redis**: OSS_REUSE nói "chưa xác minh phiên bản"; SECURITY_SCAN ghi Redis 8 có AGPLv3; cache vẫn chạy 7.4.5 (RSAL/SSPL) | OSS_REUSE, SECURITY_SCAN, compose | Đã xác minh bằng `redis-server --version` trên VPS và ghi vào THIRD_PARTY_ALL |
| 9 | **vnstock/vnai** (giấy phép "cá nhân", không OSI) **có trong image `market-collector` đang chạy** nhưng OSS_REUSE chỉ nói chung | OSS_REUSE, market-collector Dockerfile | Đánh dấu ĐỎ trong THIRD_PARTY_ALL; build `WITH_VNSTOCK=0` để loại |
| 10 | **Docs được yêu cầu nhưng không tồn tại**: `docs/WIDGETS.md`, `docs/DESIGN_SYSTEM.md` | — | Nội dung widget/design system nằm trong `services/web-ui/README.md` và trang `Design` (`#/design`); INDEX trỏ về đó |
| 11 | **`services/auth` và `services/track-record` không có README** | services/ | Chuyển hướng: AUTH.md, CLIENT_PLATFORM.md, `track-record/CONTRACT.md`, EXPERT_TRACKRECORD.md |
| 12 | **Số trang web-ui**: UPGRADE_OPTIONS "11 trang", HANDOFF "14 trang" — thực tế hơn 30 trang (master, kể cả trang tự đăng ký) | UPGRADE_OPTIONS, HANDOFF | Đã ghi chú "lịch sử"; HUONG_DAN mô tả hiện hành |
| 13 | **Thang điểm "trưởng thành 3,1/5"** và danh sách "việc tiếp theo" trong UPGRADE_OPTIONS là ảnh chụp 10-12 | UPGRADE_OPTIONS | Đã ghi chú; trạng thái hiện hành ở README |
| 14 | **Số liệu QA_REPORT** (số kiểm thử, pass/fail) theo thời điểm; không đối chiếu lại ở đợt này | QA_REPORT | Chỉ đánh dấu *(lịch sử)* — QA chạy song song bởi tác vụ khác |
| 15 | **Mô tả "đăng nhập chuyển tiếp"** trong HANDOFF (mục 1 việc dở) đã xong: auth/client-ui/briefing đang `healthy` | HANDOFF | Đã ghi chú đầu tệp |

Chưa xác minh được trong đợt này (cần người vận hành kiểm): luật tuân thủ đội TK hoạt động với tài khoản MT thật (chưa có tài khoản thật); Web Push thật (cần khoá VAPID); nội dung Timescale License hiện hành; hiệu lực thực tế của bản tin AI (chất lượng dài hạn).
