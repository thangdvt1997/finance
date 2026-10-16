# paper-trader — giao dịch MÔ PHỎNG (forward test)

**KHÔNG tiền thật. KHÔNG kết nối broker/MT. KHÔNG có đường nào tới thực thi thật.** Mục đích: kiểm chứng phương pháp giao dịch theo thời gian thực
(vốn ảo, dữ liệu thật) trước khi đụng cổng pháp lý G1-G3 (PLAN.md). Test `tests/test_no_real_execution.py` quét AST/compose để bảo đảm: không import
SDK broker/MT/mt-bridge, không gọi `order_send`/`place_order`, không HTTP ghi, chỉ ghi bảng `paper_*`, compose không phụ thuộc mt-bridge.

## Kiến trúc
```
bars (ts_ro) ─► MarketView (CHỈ nến đã đóng) ─► Engine.step(bar T)
   1 khớp lệnh chờ ở GIÁ MỞ CỬA bar T (lệnh quyết định ở bar trước)   [execution.py]
   2 swap/funding, định giá theo close, đỉnh/lỗ ngày/tuần             [portfolio.py]
   3 kill-switch (tự khoá + tất toán)                                 [risk.py]
   4 tới kỳ rebalance: Strategy.targets() ─► RiskEngine.size/gate/filter ─► lệnh mô phỏng
journal (ts_paper): paper_accounts/orders/fills/positions/equity(hypertable)/events ─► bus paper.events + alerts.out
API (FastAPI :8000) /paper/... ─► api-gateway /v1/paper/... (GET proxy) ─► web-ui trang "Mô phỏng"
```
- **Strategy (plugin)** chỉ trả `Targets` (tỷ trọng, hoặc `conviction` ∈[-1,1] để risk engine đổi sang tỷ trọng). Không ra lệnh, chỉ thấy bar đã đóng.
- **Risk engine** (tất định): whitelist, short được phép?, trần tỷ trọng/symbol, đòn bẩy, vol targeting / ATR sizing, lỗ ngày (tạm dừng tới hết ngày), lỗ tuần
  (tạm dừng tới hết tuần), drawdown (KHOÁ CỨNG, reset tay), lệnh/phút, chặn tăng vị thế trong cửa sổ tin (`/v1/risk-windows` của api-gateway; lỗi → `news_windows` tĩnh).
- **Khớp lệnh** bảo thủ: open bar kế ± (nửa spread + slippage cố định + frac×biên độ bar), phí theo bps, thuế bán (VN), swap bps/năm theo ngày giữ, làm tròn lot.
  `client_order_id = <account>:<đóng cửa bar quyết định>:<symbol>` → ghi idempotent; events có `event_key` duy nhất; journal bất biến (trigger DB).
- Trạng thái engine lưu trong `paper_accounts.state` → restart không trùng lệnh/fill.
- **Hiệu suất**: OSS `empyrical-reloaded` (CAGR, vol, Sharpe, Sortino, Calmar, MaxDD, alpha/beta). Lý do không dùng NautilusTrader/LEAN/vectorbt làm engine:
  quá nặng cho nhu cầu rebalance D1/tuần/tháng và khó kiểm soát tính bất biến + chống look-ahead; chỉ tham khảo kiến trúc OMS/mô phỏng khớp. Engine tự viết ~400 dòng, test bằng tay-tính.

## Vận hành
```
infra/db/create_paper_role.sh                      # migration 003_paper.sql + role ts_paper (POSTGRES_PAPER_PASSWORD vào .env)
./deploy.sh "up -d --build paper-trader"            # compose tools
```
Cấu hình: `paper.example.yaml` (tài khoản, universe, chi phí, rủi ro). Tài khoản mới bắt đầu forward từ bar đã đóng gần nhất (`start_at` = replay có nhãn REPLAY).
Quản trị (cần `PAPER_ADMIN_TOKEN`, gọi trực tiếp paper-trader, KHÔNG qua gateway): `POST /paper/accounts/{id}/kill-switch/reset|halt`.
Metrics: `paper_equity`, `paper_drawdown`, `paper_account_status`, `paper_fills_total`...

## Thêm phương pháp của bạn
1. Tạo `strategies/my_method.py` (mount `:ro` vào `/cfg/strategies`, hoặc package với entry-point nhóm `papertrader.strategies`):
```python
from paper_trader.strategy import Strategy, StrategyContext, register
from paper_trader.models import Targets

@register("my_method")
class MyMethod(Strategy):
    @property
    def required_history(self): return 100            # thiếu -> trả status='warming_up'
    def targets(self, ctx: StrategyContext) -> Targets:
        c = ctx.history["EURUSD"]["c"]                 # DataFrame o,h,l,c,v — chỉ bar đã đóng
        return Targets(weights={"EURUSD": 1.0 if c.iloc[-1] > c.mean() else 0.0}, kind="conviction")  # hoặc kind="weight"
```
2. Thêm khối tài khoản vào `paper.example.yaml` (`strategy: my_method`, `params`, `universe`, `rebalance`, `risk`, `benchmark: bh_fx`), restart.
3. Quy trình khuyến nghị: backtest trung thực → paper ≥ 8-12 tuần so với benchmark/backtest → mới xét bước sau.

## Giới hạn (trung thực)
- Lịch sử D1 (2026-10-11) đã backfill qua collector (FX từ 1999 `frankfurter`, ETF/vàng/VN từ `yahoo_daily`, ưu tiên nguồn: `docs/DATA_SOURCE_PRIORITY.md`) → đủ lịch sử cho `slow_trend_multiasset` (cần ~254 phiên). Mô tả chiến lược + giới hạn của plugin: mục "Chiến lược `slow_trend_multiasset` (v2)" dưới đây. Tài khoản `smoke_fx_replay` chỉ kiểm tra đường ống, KHÔNG có ý nghĩa thống kê.

## Chiến lược `slow_trend_multiasset` (v2, 2026-10-12) — khớp backtest
Nguồn: `research/multiasset/ma_engine.py`, `docs/research/MULTI_ASSET_BACKTEST.md`, `research/strategies/slow_trend_multiasset.yaml`. Cài lại vì bản đầu (chỉ momentum 12-1 + MA200, vol-target nghịch đảo vol của risk engine)
không khớp backtest (khớp dấu 24/35, kẹt đòn bẩy 3x, net bán trái phiếu −1,28) => forward test vô nghĩa. Bản cũ còn ở plugin `slow_trend_simple` (legacy, dùng cho smoke test).
- **Tín hiệu mỗi tài sản** = trung bình 4 bộ (tham số cố định theo văn liệu, không tối ưu): TSMOM 12-1; TSMOM 1/3/12 tháng; dấu (I − SMA200); Donchian 200/100 (có trạng thái). `long_short` clip [−1,1] (PRIMARY); `allow_short: false` = `long_flat`.
- **Rủi ro**: 6 lớp (eq, bond, fx, metal, energy, agri) ngang ngân sách, chia đều trong lớp; `raw = signal·budget·10%/σ` (σ EWMA span 60, sàn 1%); vol-target danh mục 10% bằng `L = min(lmax, 10%/√(w'Σw))`, Σ EWMA halflife 60 + shrink 20%. Plugin trả `kind=weight`; risk engine ở `passthrough` chỉ còn cổng an toàn (max_weight/max_leverage/kill-switch).
- **Rebalance** tháng (engine, bar đầu tiên của tháng mới), khớp ở open bar kế (lag ≥ 1 phiên). Cấu hình: `strategies/slow_trend_multiasset.yaml` (+ `params` theo tài khoản).
- **Khác backtest CÓ CHỦ ĐÍCH**: trần gộp 2,0x (backtest 8x, TB ~2,3x), |w| ≤ 0,5 (backtest 3,0), mỗi lớp |w| ≤ 0,6, tổng bán trái phiếu ≤ 0,25 (backtest không giới hạn: cùng ngày 2026-10-09 backtest có net trái phiếu −1,45 vì xu hướng lãi suất tăng — plugin KHÔNG sai ở điểm này, ta chủ động chặn cho mô phỏng khả thi). Hệ quả: vol ex-ante thấp hơn 10% khi ensemble bất đồng (L chạm lmax) hoặc trần cắn; **dấu** vị thế không đổi vì trần chỉ co tỷ lệ.
- **Dữ liệu**: ETF/FX là GIÁ THÔ còn backtest dùng chuỗi excess (vượt tiền mặt, chỉ số nội tệ). Xấp xỉ: cổ phiếu cộng (cổ tức − `cash_rate`), hàng hoá trừ `cash_rate`, trái phiếu coupon≈tiền mặt (net 0), FX chỉ spot (KHÔNG có carry lãi suất — thiếu `rates3m`), `cash_rate` là hằng số 4% (chưa đọc FRED). ETF châu Âu/Á tính bằng USD nên chịu thêm tỷ giá (EWG/FEZ/EWA lệch dấu so DAX/SX5E/ASX nội tệ). VNM/VN:* không điều chỉnh cổ tức/thưởng. Lịch sử tải mỗi chu kỳ `history_bars: 2000` để Donchian hội tụ về trạng thái của backtest (đường dài từ 1990).
- **Kiểm tra**: `tests/test_backtest_consistency.py` (so trọng số plugin với bản sao nguyên văn mã backtest `tests/ref_backtest.py` trên dữ liệu tổng hợp 30 tài sản, sai số < 1e-6; thêm so trực tiếp với `research/` khi import được). `tools/dump_targets.py` xuất mục tiêu hiện tại để đối chiếu với backtest cùng ngày (2026-10-09: 32/35 symbol cùng dấu = 91%, gộp 1,31x, net −0,02, vol ex-ante 5,6%).
- **Tài khoản**: `slow_trend_global_v2`, `slow_trend_fx_v2`, `slow_trend_vn_v2` (+ `slow_trend_global_replay_v2`). Bản cũ `slow_trend_global`, `slow_trend_fx`, `slow_trend_vn`, `slow_trend_global_replay` đặt `deprecated: true` => đóng băng (journal bất biến được giữ, không còn bước mô phỏng), `meaningful: false`; so sánh chỉ dùng v2.
- **Vẫn là giới hạn**: tham số cố định nhưng backtest 1990-2026 có Sharpe 0,55 (CI95 0,21–0,87), kỳ vọng forward 0,3–0,5; giai đoạn 2010-2019 gần như không sinh lời. Chi phí paper là giả định; thanh khoản/thuế/margin chưa mô phỏng.
- Giá bar không có bid/ask → spread/slippage là giả định; dữ liệu FX có thể là giá tham chiếu. Chưa mô phỏng: T+2 và biên độ ±7% cổ phiếu VN, margin call, swap ×3 thứ Tư, cổ tức/chia tách, thanh khoản/độ sâu sổ lệnh.
- Khớp ở open bar kế (D1) — chưa dùng quote tick mới nhất. `analytics` chỉ truyền cho bước mới nhất, không point-in-time.
- Sharpe/CAGR chỉ đáng tin khi ≥ 60 ngày; kết quả mô phỏng không đảm bảo tương lai, không phải khuyến nghị đầu tư.

## Chất lượng & quản trị (2026-10-12) — hiệu suất CI, TCA, suy giảm, strategy card, hash-chain
Mã: `perfx.py` (hiệu suất + CI), `tca.py`, `drift.py`, `card.py` + `cards/*.yaml`, `chain.py` + `govern.py` (journal bất biến), `service.py` (gom báo cáo + Monitor). Migration: `infra/db/migrations/004_paper_governance.sql` (`paper_chain`, `paper_config_versions`; chạy bằng `infra/db/create_paper_role.sh`). Chưa áp migration → paper-trader vẫn chạy, chỉ tắt hash-chain/phiên bản cấu hình.
- **Hiệu suất có CI** `GET /paper/accounts/{id}/performance`: CAGR/vol/Sharpe/Sortino/Calmar/MaxDD/% ngày lãi kèm CI95 (stationary bootstrap, hạt giống cố định, cần ≥ 20 ngày), rolling Sharpe/DD 30 và 90 ngày (dải CI giải tích Lo 2002), so benchmark (`bh_6040`, `bh_fx` + benchmark khai báo): alpha/beta/tương quan/IR/up-down capture, đóng góp theo lớp tài sản (đối chiếu sổ: `unreconciled` ≈ 0), đòn bẩy theo thời gian. Công thức khớp `empyrical` (test đối chiếu).
- **TCA** `.../tca`: chi phí thực (mô phỏng, có phần biên độ bar) vs giả định (nửa spread + slippage cố định + phí), theo lớp/symbol/chiều, chi phí luỹ kế, vòng quay. Trung thực: giá khớp là mô hình, chưa phải fill thật; cùng công thức dùng cho fill demo/live sau này.
- **Giám sát suy giảm** `.../drift` (chỉ tài khoản có kỳ vọng backtest cùng tham số: `slow_trend_global_v2`): CUSUM một phía chuẩn hoá theo vol live (ngưỡng đỏ ≈ ARL0 5 năm, Siegmund), kiểm định trung bình + tỷ lệ ngày lãi, tách SUY GIẢM TÍN HIỆU (lợi suất gộp) vs THỰC THI (chi phí/giả định > 1,5x vàng, > 2x đỏ). Đỏ → `alerts.out` + sự kiện `drift_alert`; vàng chỉ hiển thị. Hạn chế: với Sharpe ~0,5 trên dữ liệu ngày, CUSUM cần hàng năm để kết luận.
- **Strategy card** `.../card`: thẻ YAML (`cards/slow_trend_multiasset.yaml`: giả thuyết, tham số cố định, backtest + CI, cổng backtest KỂ CẢ mục không đạt, tiêu chí paper → xét duyệt: ≥12 tuần, ≥60 ngày, ≥30 fill, ≥3 kỳ rebalance, Sharpe điểm ≥0, |MaxDD| ≤15%, chi phí ≤1,5x giả định, drift không đỏ, chain nguyên vẹn, không khoá cứng, cấu hình không đổi). Giai đoạn tính TỰ ĐỘNG (`paper_early`/`paper_hold`/`review_ready`/`suspended`); KHÔNG có bước tự động lên tiền thật. `locked_params_hash` trong thẻ khoá hash tham số theo tài khoản.
- **Hash-chain** `GET /paper/verify`, `.../accounts/{id}/verify`: mỗi bản ghi (lệnh, trạng thái lệnh, fill, sự kiện, equity) có `row_hash = sha256(prev_hash|seq|kind|ref|content_hash)` trong `paper_chain` (ghi cùng transaction với bản ghi nguồn, append-only bằng trigger). Phát hiện sửa/xoá/chèn/đổi trạng thái; neo `seq:hash` ra Redis để phát hiện viết lại cả chuỗi. Monitor kiểm mỗi giờ; đứt → alert `crit` + metric `paper_chain_ok=0`. Journal cũ trước migration được neo (genesis) lúc khởi động — chỉ bảo vệ từ mốc đó. Không chống được superuser DB tính lại chuỗi VÀ xoá neo.
- **Cấu hình bất biến**: hash cấu hình hiệu lực (tham số, universe, rủi ro, giả định chi phí) lưu ở `paper_config_versions`; đổi → phiên bản mới + sự kiện `config_version` (+ alert) và đồng hồ giai đoạn bắt đầu lại. `GET .../config-versions`, `GET /paper/governance` (tổng quan cho UI). Metrics: `paper_chain_ok`, `paper_drift_status`, `paper_config_version`.
