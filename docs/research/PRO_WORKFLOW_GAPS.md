# Khoảng trống so với quy trình chuyên nghiệp — module/tính năng còn thiếu (2026-10-11)

Vai trò: chuyên gia tài chính (rủi ro, danh mục, vận hành bàn giao dịch). Đây KHÔNG phải khuyến nghị đầu tư. Hệ thống hiện READ-ONLY + paper-trader mô phỏng; mọi mục dưới đây là công cụ quan sát/kiểm soát, không tạo lệnh.

Nguyên tắc: tái dùng OSS (không viết lại), stack 0 đồng, tính toán chạy trên VPS (không chạy trên máy local), đọc dữ liệu bằng role chỉ-đọc, bảng mới theo mẫu `analytics_snapshots`/`paper_*` (append-only khi là sổ sách).

## 0. Hiện trạng đã có (để khỏi làm trùng)
- `paper-trader`: engine, risk (`RiskEngine`: size/gate/check_account, cửa sổ tin chặn lệnh), execution mô phỏng spread/slippage/swap, portfolio, `perf.stats` (equity, benchmark), bảng `paper_accounts/orders/fills/positions/equity/events` append-only bằng trigger.
- `analytics`: chỉ báo kỹ thuật, tương quan 30 ngày, phiên, cảnh báo → `alert-service`.
- `research/`: backtest + deflated Sharpe, bootstrap CI, sensitivity, random baseline, chi phí.
- Hạ tầng: Prometheus/Grafana/Gatus/alertmanager, backup pg + restore test, `mt-agent` read-only, `account_snapshots`, `expert_*`.
- Thiếu (phần lớn bên dưới): rủi ro danh mục dạng phân phối (VaR/ES, stress), phân bổ hiệu suất, TCA thực vs mô hình, journal hành vi, báo cáo tự động, audit hash-chain/4-eyes, vòng đời chiến lược (strategy card, gate, decay), đặc thù VN (thuế/phí/margin).

## 1. Bảng ưu tiên tổng hợp
Độ khó: S (<=2 ngày), M (~1 tuần), L (2-4 tuần). Ưu tiên: P0 làm trước khi paper có ý nghĩa/trước tiền thật; P1 trong 1-2 tháng; P2 khi đã có nhiều dữ liệu; P3 tuỳ chọn.

| # | Module | Ưu tiên | Khó | Service chủ | Dữ liệu vào/ra | OSS chính |
|---|---|---|---|---|---|---|
| R1 | Rủi ro dạng phân phối: VaR/CVaR(ES) lịch sử + Monte Carlo/bootstrap | P0 | M | `risk-report` (mới) hoặc mở rộng `analytics` | đọc `paper_equity`, `paper_positions`, `bars`; ghi `risk_snapshots` | Riskfolio-Lib, arch (EWMA/GARCH), numpy |
| R2 | Stress test lịch sử + kịch bản | P0 | M | `risk-report` | `bars`/Parquet 2008, 2015-01 CHF, 2020-03, 2022; ghi `risk_scenarios` | tự viết mỏng + Riskfolio-Lib |
| R3 | Concentration/tương quan/beta/factor exposure | P1 | M | `risk-report` | ma trận tương quan, exposure theo tiền tệ gốc/ngành/tài sản | Riskfolio-Lib, statsmodels |
| R4 | Margin/leverage monitor + khoảng cách tới stop-out | P0 | S-M | `risk-report` + `mt-bridge` (account_snapshots) | `account_snapshots` (equity, margin, free margin) | Prometheus rules (đã có) |
| R5 | Drawdown analytics + vol-target/Kelly phân số sizing (tư vấn) | P1 | S | `paper-trader/risk.py` + `risk-report` | `paper_equity` | QuantStats/empyrical-reloaded |
| R6 | Position limit & risk budget dashboard (tận dụng RiskConfig) | P1 | S | `api-gateway` + `web-ui` | cấu hình risk + exposure thực | — |
| P1 | Chỉ số hiệu suất đầy đủ + so benchmark + rolling | P0 | S | `perf-report` (mở rộng `perf.py`) | `paper_equity` + benchmark | QuantStats, empyrical-reloaded |
| P2 | Attribution (theo tài sản/chiến lược/long-short, alpha vs beta) | P1 | M | `perf-report` | `paper_fills`, `paper_positions` | pyfolio-reloaded, statsmodels |
| P3 | TWR/MWR (khi có nạp/rút) | P2 | S | `perf-report` | bảng `cashflows` (mới) | empyrical, numpy-financial |
| P4 | TCA: slippage thực vs mô hình, phí, swap | P0 | M | `tca` (mô-đun trong `perf-report`) | `paper_fills` (giá giả định) vs quote/bar tại thời điểm; sau này fill demo thật | tự viết nhỏ; Nautilus/LEAN có mô hình chi phí tham khảo |
| J1 | Trade journal tự động (MT4/MT5 history) | P1 | M | `journal` (mới) hoặc TradeTally | `mt-bridge` history → `journal_trades` | TradeTally (self-host), Edgewonk/Tradervue (thương mại, tham khảo) |
| J2 | Tag setup/cảm xúc, review tuần, post-mortem | P1 | S-M | `journal` + `web-ui` | `journal_tags`, `journal_reviews` | TradeTally |
| J3 | Kiểm tra kỷ luật (tuân thủ kế hoạch, revenge trading) | P1 | M | `journal` | quy tắc trên chuỗi lệnh (xem §4) | tự viết |
| J4 | Checklist pre-trade bắt buộc | P0 (trước live) | S | `web-ui` + `execution` (sau) | `pretrade_checks` | — |
| B1 | Báo cáo tự động ngày/tuần/tháng | P0 | M | `reporter` (mới) | đọc view tổng hợp; xuất HTML/PDF | Quarto/Evidence, WeasyPrint, Jinja2 |
| B2 | Kênh phát: Telegram/email/ntfy | P0 | S | `alert-service` (có sẵn) | `reports.out` | Apprise |
| B3 | Báo cáo tuân thủ/kiểm toán + gói bàn giao kế toán | P2 | M | `reporter` | journal + thuế/phí | WeasyPrint |
| A1 | Nhật ký bất biến hash-chain/WORM | P0 | S-M | `libs/common` + trigger DB | thêm cột `prev_hash,row_hash` | pgaudit, `pg_hashchain` ý tưởng, MinIO Object Lock (WORM) |
| A2 | 4-eyes thay đổi tham số, change management chiến lược | P1 | M | `config-gov` (mới) hoặc Git PR | `config_changes` | Git + PR review, SOPS (đã có), Unleash/Flipt (flag) |
| A3 | Kill-switch nhiều tầng + runbook sự cố | P0 (trước live) | M | EA tầng 1, server tầng 2, Telegram tầng 3 | `killswitch_state` | tự viết (PLAN §4) |
| A4 | Versioning cấu hình + snapshot cấu hình theo từng run | P0 | S | `paper-trader` | hash cấu hình lưu vào `paper_events` | Git, DVC (tuỳ chọn) |
| L1 | Strategy card + tiêu chí chuyển giai đoạn (research→paper→live) | P0 | S | docs + bảng `strategies` | `strategy_cards`, `stage_gates` | MLflow (registry), Markdown template |
| L2 | Giám sát suy giảm alpha (live/paper vs backtest) | P1 | M | `drift-monitor` (trong `perf-report`) | so khớp phân phối return, CUSUM | `river`/ruptures, scipy |
| L3 | Champion/challenger, A/B song song | P2 | M | `paper-trader` nhiều account | `paper_accounts.strategy` đã hỗ trợ | MLflow |
| L4 | Thư viện thí nghiệm (tham số, dữ liệu, seed, kết quả) | P1 | S-M | `research` | MLflow tracking (sqlite/postgres) | MLflow, DVC |
| V1 | Thuế/phí/T+2/ký quỹ VN trong mô phỏng + sổ kế toán | P1 (cho phương án C) | M | `paper-trader/execution.py` + `reporter` | bảng phí cấu hình theo CTCK | vnstock (dữ liệu), cấu hình YAML |
| V2 | Cảnh báo pháp lý/tuân thủ trong UI & báo cáo | P0 | S | `web-ui` | banner + `compliance_log` | — |

## 2. Rủi ro & danh mục
**Vì sao quan trọng.** Hệ thống hiện kiểm soát rủi ro theo ngưỡng (size/gate/lỗ ngày) nhưng chưa trả lời "ngày tệ nhất có thể mất bao nhiêu" hay "nếu lặp lại 2015 thì sao". Backtest của dự án đã cho Sharpe ~0 và drawdown 30-60% cho FX; đuôi dày (carry mất -56%) nên số liệu phân phối + kịch bản là bắt buộc, không thay bằng độ lệch chuẩn.

**R1 VaR/CVaR/ES.** Tính ES 97,5% (chuẩn Basel FRTB thay VaR 99%) và VaR 95/99 theo 3 cách: lịch sử, EWMA-parametric, bootstrap theo khối (stationary bootstrap) để giữ tự tương quan. Hiển thị cả "ES/NAV" và so với giới hạn lỗ ngày. Lưu ý: VaR dưới ước lượng cho FX/vàng khi gap cuối tuần; luôn kèm backtest VaR (Kupiec/Christoffersen: số lần vượt so với kỳ vọng). Tích hợp: job hằng ngày đọc `paper_equity`+`paper_positions`+`bars`, ghi `risk_snapshots(account_id, ts, method, var95, var99, es975, horizon)`; phát `alerts.out` khi ES/NAV vượt ngưỡng. OSS: Riskfolio-Lib (BSD-3, có CVaR/EVaR/drawdown risk measures, báo cáo Jupyter/Excel), arch cho volatility.

**R2 Stress & kịch bản.** Hai lớp: (a) replay lịch sử cho vị thế hiện tại: 2008-09/10, 2015-01-15 (CHF), 2016 Brexit, 2020-03, 2022 (USD tăng/lãi suất), cắt ngày 2024-08-05 yen carry; (b) kịch bản giả định: USD +/-5%, vàng -10%, vol x2, tương quan -> 1, spread x5 trong 30 phút tin, gap qua cuối tuần, broker không thể cắt lỗ (slippage vô hạn ở stop). Output: scenario P&L theo tài khoản/vị thế, và "khoảng cách tới stop-out" (R4). Dữ liệu: bars + Parquet lịch sử trong `research/`. Làm bằng bảng tham số (shock theo tài sản) để người không viết code chỉnh được. Khó: M.

**R3 Concentration/tương quan/factor.** Cộng exposure theo từng tiền tệ (EUR long ở hai cặp thực chất là một vị thế), theo nhóm tài sản, theo chiến lược; HHI và số "bet độc lập" hiệu dụng (từ PCA/eigen của ma trận tương quan). Factor exposure cho cổ phiếu VN: beta so VN-Index/VN30, size/value nếu có dữ liệu. Với FX/vàng: beta so DXY, so US10Y real yield. OSS: Riskfolio-Lib (risk contribution, risk parity), statsmodels (OLS/rolling beta).

**R4 Margin/leverage monitor.** Đọc `account_snapshots`: equity, margin used, free margin, margin level, đòn bẩy hiệu dụng = notional/equity; cảnh báo khi margin level < ngưỡng (ví dụ 300%/200%) và ước lượng bao nhiêu pip nữa chạm stop-out theo mức stop-out của broker (thường 20-50%, phải ghi theo từng broker). Cho tài khoản MT hedging cần tính margin hedge. Đã có Prometheus rules; thêm rule cho margin level.

**R5 Drawdown + sizing.** Underwater curve, thời gian hồi phục, top-N drawdown, Ulcer index; ước lượng xác suất drawdown vượt X% bằng Monte Carlo trên return paper. Sizing: vol-target (đã có trong risk.py hướng này), Kelly phân số (đề xuất tối đa 1/4-1/2 Kelly và chỉ như trần tham chiếu, vì ước lượng edge rất nhiễu; với edge ~0 như kết quả backtest, Kelly -> 0). Hiển thị cho người xem, không tự áp dụng.

**R6 Giới hạn & ngân sách rủi ro.** Trang "Risk budget": hạn mức/tiêu thụ (lỗ ngày, tuần, drawdown từ HWM, exposure theo tiền tệ, số lệnh mở, đòn bẩy) dạng thanh tiêu thụ, đỏ khi >80%. Dữ liệu từ `RiskConfig` + `paper_equity`.

## 3. Hiệu suất & phân bổ
**P1** Sharpe/Sortino/Calmar/Omega, tail ratio, profit factor, expectancy theo lệnh, win-rate + payoff, rolling 30/90 ngày, so benchmark (mua-và-giữ vàng, 60/40, cash), information ratio, up/down capture, kèm khoảng tin cậy (bootstrap) và deflated Sharpe khi đã thử nhiều biến thể (đã có trong `research/`: nên đưa chung thư viện). Đừng báo số điểm không kèm CI: Sharpe đo trên < 1 năm không có nghĩa thống kê. OSS: QuantStats (Apache-2.0; bản gốc bảo trì thưa, có nhánh `quantstats-lumi`), empyrical-reloaded + pyfolio-reloaded (còn phát hành nhưng ít hoạt động) — chỉ dùng làm thư viện tính, không phụ thuộc cứng; ghim phiên bản.

**P2 Attribution.** Tách lợi nhuận theo tài sản, chiến lược, long/short, thời điểm (phiên), và tách alpha/beta (hồi quy so benchmark; Newey-West). Brinson cho cổ phiếu VN nếu có benchmark ngành. Đóng góp vào biến động (risk contribution) song song với đóng góp lợi nhuận.

**P3 TWR/MWR.** Chỉ cần khi có nạp/rút tiền thật: TWR loại bỏ ảnh hưởng dòng tiền (đánh giá chiến lược), MWR/IRR phản ánh trải nghiệm của chủ vốn. Paper account vốn cố định nên chưa cần; tạo bảng `cashflows` sớm để khỏi sửa sổ sau.

**P4 TCA.** So sánh slippage mô hình (`execution.fill_price`) với (a) giá bar/quote thực quanh thời điểm lệnh; (b) về sau, fill thật trên tài khoản demo/live. Chỉ số: implementation shortfall, spread thực đã trả, slippage theo giờ/phiên/tin, tỷ lệ từ chối/requote. Kết luận hay gặp: chi phí+swap ăn 0,12-0,24 Sharpe (đã đo), nên TCA là phép kiểm "mô hình chi phí có quá lạc quan không". Bảng `tca_fills`. Làm sớm vì nó điều chỉnh mọi con số backtest.

**Thuế/phí.** Tính net-of-fee-and-tax ở mọi báo cáo (xem §8). Phí qua đêm/swap tách riêng khỏi P&L giao dịch.

## 4. Nhật ký & quản trị giao dịch (kể cả giao dịch tay của người dùng)
- **J1 Trade journal tự động.** Ưu tiên không dựng từ đầu: TradeTally (self-host Docker, Node/Postgres/Vue, import CSV + API một số broker; chưa thấy hỗ trợ MT4/MT5 trực tiếp -> chuyển lịch sử MT sang CSV hoặc viết importer; kiểm tra giấy phép trong LICENSE trước khi đóng gói). Phương án thay thế: bảng `journal_trades` riêng trong Postgres lấy từ `mt-bridge` (ticket, magic, symbol, side, volume, open/close, SL/TP, comment) + Grafana/Metabase; mã nguồn đóng Edgewonk/TraderSync/Tradervue chỉ để tham khảo tính năng (chi phí, không tự lưu trữ).
- **J2 Gắn thẻ + review.** Mỗi lệnh có: setup (tên chiến lược), lý do vào, kế hoạch (entry/SL/TP/R), cảm xúc/trạng thái (1-5), lỗi. Review hằng tuần có mẫu cố định: R-multiple phân phối, lệnh tốt/xấu theo QUY TRÌNH (không theo kết quả), 1-2 hành động cải thiện. Post-mortem cho mỗi drawdown vượt ngưỡng và mỗi sự cố.
- **J3 Kiểm tra kỷ luật (tự động).** Quy tắc đo được: (1) tuân thủ kế hoạch: lệnh có SL ban đầu, SL không bị dời xa hơn, đúng kích thước theo risk/lệnh; (2) revenge trading: mở lệnh trong N phút sau lệnh lỗ, tăng size sau lỗ, vượt số lệnh/ngày; (3) overtrading: số lệnh/ngày vượt trung vị + 2 độ lệch; (4) giao dịch trong cửa sổ tin bị cấm; (5) vi phạm hạn mức lỗ ngày. Xuất "điểm kỷ luật" theo tuần. Đây thường có giá trị cao hơn tối ưu tín hiệu với nhà đầu tư cá nhân.
- **J4 Pre-trade checklist.** Bắt buộc điền trước khi bật chiến lược/lệnh tay lớn: lý do, kích thước theo risk, tin sắp tới, tương quan với vị thế hiện có, cổng pháp lý. Lưu `pretrade_checks`; khi có execution thì không có checklist = không cho gửi.

## 5. Báo cáo định kỳ tự động
Service `reporter` (hoặc job chạy theo lịch trong `paper-trader`): truy vấn các view tổng hợp -> Jinja2 -> HTML tĩnh (Evidence/Quarto cho biểu đồ) -> PDF qua WeasyPrint -> lưu file + hash -> gửi Telegram/ntfy/email qua `alert-service` (Apprise). 
- **Ngày** (1 trang): equity, P&L, DD, vị thế mở, margin level, ES/NAV, lệnh bị chặn bởi risk, sự kiện tin ngày mai, cảnh báo hệ thống.
- **Tuần**: hiệu suất vs benchmark, attribution, TCA, điểm kỷ luật, drift so với backtest, khuyến nghị hành động (không phải khuyến nghị đầu tư), việc cần người duyệt.
- **Tháng**: rolling metrics với CI, stress test, rà soát cấu hình/thay đổi trong tháng, thuế/phí, đối soát số dư với sao kê broker.
- **Tuân thủ/kiểm toán**: log thay đổi cấu hình, kill-switch đã thử, sao lưu/restore test, truy cập, hash-chain verify OK/FAIL.
Quy ước: mọi con số lấy từ cùng một nguồn tính toán (không tính lại trong LLM); LLM chỉ viết đoạn tóm tắt từ số đã tính.

## 6. Audit trail & kiểm soát nội bộ
- **A1 Hash-chain.** `paper_events`, `paper_fills`, `paper_orders` đã append-only bằng trigger; thêm `row_hash = sha256(prev_hash || canonical_json(row))` theo từng account và job `verify_chain` hằng ngày; lưu hash neo (anchor) hằng ngày ra nơi khác (file ký + object store có Object Lock/MinIO WORM, hoặc email cho chính mình). Mục tiêu: phát hiện sửa/xoá sau này (tamper-evident), không phải chống kẻ có quyền DB superuser. pgaudit cho log truy cập DDL/DML.
- **A2 4-eyes + thay đổi chiến lược.** Với hệ thống một người, "4-eyes" = quy trình hai bước có độ trễ: sửa tham số rủi ro -> PR Git (diff cấu hình) -> chờ cooling-off (ví dụ 24h) -> người duyệt thứ hai hoặc chính bạn xác nhận sau cooling-off; nới giới hạn rủi ro luôn cần bước này, siết chặt thì áp dụng ngay. Không sửa tham số trong lúc đang lỗ ngày. SOPS đã có cho secret.
- **A3 Kill-switch nhiều tầng.** Tầng 1: EA trên terminal (đóng/chặn khi equity < ngưỡng, độc lập server); Tầng 2: server (risk engine + process riêng, heartbeat); Tầng 3: lệnh Telegram/điện thoại; Tầng 4: ngoài băng tần — đổi investor/đóng API key tại broker (runbook). Mỗi tầng phải TEST định kỳ và ghi `killswitch_tests`. Quy tắc: kill-switch không phụ thuộc cùng DB/cùng process với strategy.
- **A4 Versioning.** Mỗi run/paper account ghi `config_hash`, git commit, phiên bản dữ liệu vào `paper_events`; strategy yaml bất biến theo phiên bản (đổi = phiên bản mới).
- **Runbook sự cố**: mất kết nối broker, dữ liệu trễ/rỗng, lệnh trùng, lệch vị thế, broker nới spread, DB đầy, lộ key. Mỗi runbook: dấu hiệu, người ra quyết định, bước, kiểm tra sau, mẫu post-mortem. Diễn tập game-day mỗi quý.

## 7. Nghiên cứu -> paper -> live
- **L1 Strategy card** (1 trang/chiến lược, lưu trong repo): giả thuyết kinh tế, vũ trụ, dữ liệu, tham số, số lần thử (cho deflated Sharpe), kết quả out-of-sample có CI, chi phí giả định, rủi ro đã biết, điều kiện dừng. Trạng thái: IDEA -> BACKTESTED -> PAPER -> PILOT (vốn rất nhỏ) -> LIVE -> RETIRED.
- **Tiêu chí chuyển giai đoạn (đề xuất, hiệu chỉnh theo bạn):** BACKTESTED->PAPER: walk-forward OOS, deflated Sharpe/PSR đạt ngưỡng đã nêu trước, nhạy tham số ổn định, chi phí x2 vẫn không sụp. PAPER->PILOT: >= 8-12 tuần (PLAN nói tối thiểu 4; STRATEGY_OPTIONS đề xuất 8-12), TCA khớp mô hình trong dải, không vi phạm risk, drift trong dải, pháp lý G1-G3 xong. PILOT->LIVE: tối thiểu N tháng vốn nhỏ, tăng quy mô từng bậc. Tiêu chí rút lui định trước (ví dụ DD > 1,5x DD backtest P95).
- **L2 Giám sát suy giảm alpha.** So return live/paper chuẩn hoá bằng vol backtest: CUSUM/SPRT trên "excess vs expected", kiểm định KS/so sánh phân phối, và tách suy giảm tín hiệu (IC giảm) với suy giảm thực thi (slippage, chi phí). Hiệu chỉnh ngưỡng bằng mô phỏng để kiểm soát báo động giả, nhớ hiệu chỉnh đa kiểm định khi theo dõi nhiều chiến lược. (CUSUM có gốc kiểm soát chất lượng và đã được dùng để theo dõi manager; bằng chứng độc lập cho giao dịch hệ thống còn hạn chế.) Phát hành trạng thái xanh/vàng/đỏ.
- **L3 Champion/challenger.** `paper_accounts` đã hỗ trợ nhiều account/chiến lược: chạy song song cùng dữ liệu, so sánh trên cùng kỳ; quy tắc: challenger muốn thay champion phải thắng có ý nghĩa (CI không chứa 0 về chênh lệch) qua đủ thời gian; tránh "chọn người thắng" trên mẫu ngắn.
- **L4 Thư viện thí nghiệm.** MLflow tracking (backend sqlite/Postgres, artifact local) cho mọi lần quét tham số trong `research/`: tham số, hash dữ liệu, seed, metric, hình. Đếm số thử nghiệm tự động để tính deflated Sharpe đúng.

## 8. Đặc thù Việt Nam
- **Thuế**: Luật Thuế TNCN 2025 hiệu lực 1/7/2026 giữ thuế 0,1% trên giá chuyển nhượng mỗi lần bán chứng khoán (ví dụ 1.000 cp x 25.000đ = 25 triệu -> 25.000đ); phái sinh theo Thông tư 87/2026/TT-BTC cũng 0,1%/lần nhưng giá tính thuế theo công thức có tỷ lệ ký quỹ ban đầu (cần đọc nguyên văn trước khi cài). Nhiều CTCK khấu trừ tự động khi tiền bán về. Mô-đun V1 tính thuế ở mỗi lệnh bán mô phỏng và cộng dồn theo năm. (Nguồn tin pháp lý trên là báo chí/trang CTCK: đối chiếu văn bản gốc hoặc kế toán.)
- **Phí CTCK**: biểu phí khác nhau theo CTCK, nhiều nơi ưu đãi theo thời điểm; chưa xác minh được số cụ thể -> để cấu hình YAML theo CTCK người dùng chọn (phí giao dịch %, phí lưu ký, phí ứng trước, lãi margin). Phí sàn/lưu ký là phần nhỏ.
- **Thanh toán**: nguồn chính thống cho thấy chu kỳ T+2 (từ 8/2022); chưa thấy văn bản xác nhận T+1 trong 2026 -> cấu hình `settlement_days=2`, kiểm tra khi có thông báo UBCKNN/VSDC; mô phỏng không cho bán cổ phiếu chưa về tài khoản và không "T0" trừ khi CTCK cho. Kiểm tra lại trạng thái hệ thống KRX và các thay đổi khớp lệnh khi triển khai (chưa xác minh được).
- **Margin**: tỷ lệ ký quỹ ban đầu tối thiểu 50%, duy trì tối thiểu khoảng 30% (theo tin 2026; mỗi CTCK có danh mục mã margin và tỷ lệ cho vay riêng, ví dụ có mã 50%, mã 20%); lãi margin tham chiếu ~9-14%/năm tuỳ CTCK; dư nợ margin toàn thị trường đang ở mức kỷ lục (~435.000 tỷ đồng cuối quý II/2026) nên rủi ro bán giải chấp dây chuyền tăng. Mô-đun R4/V1: danh mục margin theo CTCK, tỷ lệ an toàn, giá giải chấp (force-sell), cảnh báo cách ngưỡng gọi ký quỹ, chi phí lãi theo ngày.
- **Giá trần/sàn**: biên độ HOSE +/-7%, HNX +/-10%, UPCoM +/-15% -> khớp lệnh mô phỏng phải tôn trọng; thanh khoản mỏng mã nhỏ -> giới hạn % khối lượng ngày (participation cap).
- **Báo cáo cho kế toán**: xuất sao kê giao dịch (ngày, mã, KL, giá, phí, thuế, lãi/lỗ đã thực hiện FIFO) theo năm, CSV + PDF; đối chiếu với sao kê CTCK.
- **Cảnh báo pháp lý (mục V2, ghi vào banner + báo cáo):** theo PLAN.md: (G1) NHNN chưa cấp phép sàn forex; Nghị định 340/2025 (hiệu lực 9/2/2026) phạt tới 250 triệu cho phái sinh ngoại hối không phép, chế tài với cá nhân chưa rõ; (G2) chỉ đạo UBCKNN 2023 về robot đặt lệnh chứng khoán. Hệ thống ở chế độ READ-ONLY/paper; đây là cảnh báo vận hành, không phải tư vấn pháp lý: hỏi luật sư/CTCK bằng văn bản trước khi dùng tiền thật.

## 9. Bộ module nên làm trước (10 mục)
1. **A4 + L1 Cấu hình bất biến + strategy card + stage gate** (S): nền cho mọi thứ khác, rẻ nhất, chặn được "tối ưu rồi cho chạy luôn".
2. **A1 Hash-chain/WORM cho `paper_*`** (S-M): sổ sách đáng tin trước khi tin số.
3. **P1 Bộ chỉ số hiệu suất + CI + benchmark** (S): nhìn thật số; QuantStats/empyrical làm thư viện.
4. **R1 + R2 VaR/ES + stress test** (M): trả lời "tệ nhất là bao nhiêu".
5. **R4 Margin/leverage monitor + R6 risk-budget** (S-M): thay vì chờ stop-out.
6. **P4 TCA slippage thực vs mô hình** (M): hiệu chỉnh toàn bộ chi phí giả định.
7. **B1 + B2 Báo cáo ngày/tuần tự động + Telegram/ntfy** (M): vận hành đều, đưa cảnh báo vào thói quen.
8. **J4 + A3 Pre-trade checklist + kill-switch nhiều tầng + runbook** (M): bắt buộc trước bất kỳ live nào.
9. **L2 Drift monitor live/paper vs backtest** (M): phát hiện alpha chết sớm.
10. **V1 + V2 Thuế/phí/T+2/margin VN + banner pháp lý** (M): làm đúng ngay từ đầu cho phương án cổ phiếu VN và tránh vi phạm.
Sau đó: R3 concentration/factor, J1-J3 journal + kỷ luật (nếu bạn giao dịch tay), P2 attribution, L3-L4, B3.

## 10. Cấu trúc màn hình & báo cáo mẫu (web-ui, tiếng Việt)
Màn hình (mỗi màn có banner "KHÔNG PHẢI KHUYẾN NGHỊ ĐẦU TƯ — chế độ mô phỏng/chỉ đọc"):
1. **Tổng quan bàn giao dịch**: equity, P&L ngày/tuần/tháng, DD hiện tại/HWM, ES/NAV, margin level, trạng thái kill-switch (4 tầng), chiến lược theo giai đoạn (PAPER/PILOT...), health hệ thống.
2. **Rủi ro**: tiêu thụ ngân sách rủi ro (thanh), VaR/ES theo 3 phương pháp, bảng exposure theo tiền tệ/nhóm, ma trận tương quan, kết quả stress theo kịch bản (bảng + waterfall), đồ thị underwater.
3. **Hiệu suất**: đường vốn vs benchmark, rolling Sharpe/vol/DD (kèm CI), attribution theo tài sản/chiến lược, phân phối lệnh (R-multiple), chi phí (phí/swap/slippage/thuế).
4. **Chiến lược (vòng đời)**: strategy card, trạng thái, checklist tiêu chí chuyển giai đoạn (đạt/chưa), drift xanh/vàng/đỏ, so champion/challenger, liên kết MLflow.
5. **Nhật ký**: danh sách lệnh + thẻ setup/cảm xúc, điểm kỷ luật tuần, cờ revenge/overtrading, form review tuần/post-mortem.
6. **Kiểm soát & audit**: log thay đổi cấu hình (diff, người duyệt, cooling-off), kết quả verify hash-chain, lịch test kill-switch, runbook, sự cố mở.
7. **Thuế/kế toán VN**: thuế đã tạm tính theo năm, phí/lãi margin, xuất sao kê CSV/PDF.

Mẫu báo cáo tuần (1-2 trang): (1) Tóm tắt 5 dòng; (2) Số chính: P&L, DD, Sharpe(CI), ES/NAV; (3) So benchmark; (4) Attribution top 3 đóng góp/kéo; (5) Rủi ro: exposure, stress đáng chú ý, margin; (6) Thực thi: TCA, lệnh bị chặn, từ chối; (7) Kỷ luật & sự kiện: điểm kỷ luật, cảnh báo; (8) Drift từng chiến lược; (9) Thay đổi cấu hình tuần qua + hash verify; (10) Việc cần quyết định tuần tới (kèm hạn); (11) Phụ lục pháp lý/tuân thủ. Báo cáo ngày: mục (2),(5), cảnh báo và lịch tin 24h.

## 11. Nguồn tham khảo (đã tra 2026-10-11) và điểm chưa xác minh
- Riskfolio-Lib (BSD-3; CVaR, drawdown risk, Reports): https://riskfolio-lib.readthedocs.io/
- QuantStats / pyfolio-reloaded / empyrical-reloaded: tình trạng bảo trì chỉ có số liệu từ trang theo dõi bên thứ ba (QuantStats 0.0.81, sức khoẻ 65/100 đầu 2026; pyfolio-reloaded 0.9.x; empyrical-reloaded 0.5.x) -> kiểm GitHub/PyPI trước khi ghim: https://depscope.dev/pkg/pypi/quantstats , https://pypi.org/project/empyrical-reloaded/
- TradeTally (self-host; nhập CSV/API; MT4/MT5 chưa thấy; giấy phép nguồn tin mâu thuẫn): https://github.com/GeneBO98/tradetally
- CUSUM theo dõi manager (Morgan Stanley IM, chưa kiểm chứng độc lập): https://www.morganstanley.com/im/en-gb/intermediary-investor/insights/articles/when-good-managers-stumble.html ; CUSUM theo dõi mô hình: https://arxiv.org/pdf/2309.15187
- Thuế 0,1%: https://thuvienphapluat.vn/ma-so-thue/phap-luat-thue/tu-172026-chuyen-nhuong-chung-khoan-nop-thue-tncn-bao-nhieu-phan-tram-218598.html ; phái sinh: https://luatvietnam.vn/tin-van-ban-moi/tu-01-7-2026-thue-tncn-voi-chuyen-nhuong-chung-khoan-phai-sinh-la-01-moi-lan-chuyen-nhuong-186-110281-article.html
- Margin/danh mục ký quỹ: https://thesaigontimes.vn/du-no-margin-lien-tuc-pha-ky-luc-phep-thu-voi-thi-truong-chung-khoan/ ; thông báo danh mục margin ví dụ: https://masvn.com/api/attachment/file/1774515018622-DanhmucGDKQcapnhatwebsite2026.03.26.pdf
Chưa xác minh (cần kiểm trước khi triển khai): biểu phí cụ thể từng CTCK; T+1 và trạng thái KRX 2026; nguyên văn Thông tư 87/2026/TT-BTC về giá tính thuế phái sinh; giấy phép và định dạng import MT4/MT5 của TradeTally; mức stop-out từng broker; các kỹ thuật (hash-chain, WORM, ES 97,5% của FRTB, Kupiec backtest, 4-eyes) là thực hành ngành từ hiểu biết chung, chưa tra lại nguồn 2026 trong đợt này.
