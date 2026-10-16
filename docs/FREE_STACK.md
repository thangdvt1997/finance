# FREE_STACK: gói dữ liệu 0 đồng

Nguyên tắc: mọi nguồn dưới đây miễn phí. Provider **tự bật khi có key trong `/root/trading-system/infra/.env`**; thiếu key thì tắt gọn (log 1 dòng, không lỗi, không spam) và trang **Hệ thống** hiển thị trạng thái **"Cần key"**. Không bao giờ đưa key vào repo. Hệ thống không tự đăng ký tài khoản hộ bạn.

## Bảng nguồn

| Nguồn | Dùng cho | Đăng ký ở đâu | Biến môi trường | Giới hạn miễn phí | Bật tự động |
|---|---|---|---|---|---|
| Dukascopy | FX/vàng M1 (chuẩn đối chiếu) | không cần | không | 2 req/s | luôn bật |
| Frankfurter (ECB) | FX D1, đối chiếu | không cần | không | 30 req/phút | luôn bật |
| **FRED** (`fredgraph.csv`) | vĩ mô D1: `FRED:DGS10`, `DGS2`, `DFF`, `T10YIE`, `DTWEXBGS` | không cần | không (đổi chuỗi: `FRED_SYMBOLS`) | 20 req/phút, poll 6h | luôn bật |
| **OANDA practice v20** | nến M1 FX + vàng (giá BID), đối chiếu | https://www.oanda.com (mở tài khoản practice, My Hub → Manage API Access) | `OANDA_PRACTICE_TOKEN` | tự giới hạn 60 req/phút | khi có token |
| **TrueFX** | quote FX real-time, đối chiếu | https://www.truefx.com (Register, miễn phí) | `TRUEFX_USER`, `TRUEFX_PASS` | 1 req/30s cho cả nhóm cặp | khi có cả hai |
| **Alpaca Free** | nến H1+D1 cổ phiếu/ETF Mỹ (IEX) | https://app.alpaca.markets/signup (Paper) | `ALPACA_KEY`, `ALPACA_SECRET` | 200 req/phút, tối đa 30 mã (`ALPACA_MAX_SYMBOLS`) | khi có cả hai |
| **Tiingo Starter** | nến EOD D1 cổ phiếu/ETF Mỹ | https://www.tiingo.com (Account → API token) | `TIINGO_TOKEN` | 50 req/giờ, 1000/ngày, 500 mã/tháng (tự giới hạn 40/giờ, 25 mã) | khi có token |
| **Yahoo `yahoo_daily`** (RỦI RO ToS) | nến D1 thô ETF Mỹ/cổ phiếu VN/vàng: lịch sử từ 1990 + cập nhật hằng ngày 22:30 UTC | không cần | `PROVIDERS=...,yahoo_daily` + `ALLOW_RISKY_PROVIDERS=true`, `YAHOO_DAILY_AT_UTC` | 10 req/phút, chỉ cá nhân | mặc định TẮT; ưu tiên nguồn: `docs/DATA_SOURCE_PRIORITY.md` |
| **Crypto `crypto_ccxt`** (ccxt, chỉ dữ liệu công khai) | nến M1/M5/M15/H1/H4/D1 + quote ~15s của 29 cặp `CRYPTO:<BASE>USDT` (BTC, ETH, SOL, XRP...) 24/7 | không cần | `CRYPTO_EXCHANGES` (mặc định `okx,kucoin,gate,bitfinex`), `CRYPTO_QUOTE_INTERVAL`, `CRYPTO_BACKFILL_<TF>`, `CRYPTO_CCXT_SYMBOLS` | rate limit chuẩn từng sàn qua ccxt `enableRateLimit`; từ VPS: Binance 451, Bybit 403 (bị chặn) — OKX/KuCoin/Gate/Bitfinex/Bitstamp/Kraken/Coinbase/HTX/MEXC/Bitget/Binance.US dùng được | luôn bật (`PROVIDERS=...,crypto_ccxt`) |
| Twelve Data | FX/cổ phiếu (đã có) | https://twelvedata.com/register | `TWELVEDATA_API_KEY` | 8 req/phút, 800/ngày | khi có key |
| **Marketaux Free** | tin + thực thể + sentiment | https://www.marketaux.com/register | `MARKETAUX_TOKEN` | 100 req/ngày, 3 bài/req (tự giới hạn 70/ngày, xoay vòng 4 truy vấn, 1 req/20 phút) | khi có token |
| FRED API key | thêm `actual` cho lịch kinh tế (news-collector) | https://fred.stlouisfed.org/docs/api/api_key.html | `FRED_API_KEY` | 120 req/phút | khi có key |
| FMP | lịch kinh tế (tuỳ chọn) | https://site.financialmodelingprep.com/register | `FMP_API_KEY` + `NC_SRC_CAL_FMP=true` | 250 req/ngày; chưa xác minh calendar có trong gói free | mặc định TẮT |

Quyết định: **FRED releases/calendar không thêm** vì `releases/dates` chỉ có ngày (không có giờ) và trùng BLS/Fair Economy, sẽ làm sai cửa sổ rủi ro tin. FRED được dùng làm chuỗi vĩ mô (provider `fred`) và `actual` (khi có key).

## Hướng dẫn từng bước
1. Đăng ký ở URL trong bảng (tự làm trên trình duyệt; mỗi nguồn vài phút).
2. SSH vào VPS, sửa `/root/trading-system/infra/.env` (không commit), ví dụ:
   ```
   OANDA_PRACTICE_TOKEN=...
   TRUEFX_USER=...
   TRUEFX_PASS=...
   ALPACA_KEY=...
   ALPACA_SECRET=...
   TIINGO_TOKEN=...
   MARKETAUX_TOKEN=...
   ```
   Lưu ý TrueFX dùng HTTP không mã hoá: hãy dùng mật khẩu riêng chỉ cho TrueFX.
3. Áp dụng (chỉ 2 service): `cd /root/trading-system/infra && docker compose -p tradingsys --env-file .env up -d market-collector news-collector`.
4. Kiểm tra bật thành công:
   - Web UI → **Hệ thống** → panel "Nguồn dữ liệu miễn phí": nguồn chuyển từ "Cần key" sang "Đang chạy".
   - `docker compose -p tradingsys exec market-collector python -c "import urllib.request;print(urllib.request.urlopen('http://localhost:8000/providers').read().decode())"` (và `/reconcile?run=true`); news-collector: `/providers`.
   - Metric `mc_provider_state{provider=...}`: 1 = chạy, 0,5 = cần key.

## Đối chiếu nguồn giá
Mỗi 15 phút (`RECONCILE_INTERVAL`), với EURUSD/GBPUSD/USDJPY/XAUUSD (`RECONCILE_PAIRS`): lấy giờ đã đóng gần nhất (trừ 1 giờ chờ Dukascopy xuất file), so giá đóng cửa M1 trên các phút chung của Dukascopy với OANDA và TrueFX; Frankfurter so với phút 14:15 CET của Dukascopy (mỗi ngày ECB một lần).
- Lệch trung vị > `RECONCILE_THRESHOLD_BPS` (8 bps = 0,08%) hoặc lệch tối đa > 4 lần ngưỡng → alert `alerts.out` (dedupe 6 giờ/cặp/nguồn), `mc_recon_mismatch_total`; Frankfurter dùng `RECONCILE_FRANKFURTER_BPS` (25).
- Cuối tuần/chưa có nguồn thứ hai: trạng thái "Chưa có dữ liệu", không alert.
- Hiển thị: trang Hệ thống → "Chất lượng dữ liệu: đối chiếu nguồn giá". API: `GET /v1/data-sources`.
- Metric: `mc_recon_diff_bps{pair,source,stat}`, `mc_recon_status`, `mc_recon_last_run_timestamp`.

## Giới hạn và rủi ro
- Giấy phép: tất cả chỉ dùng cá nhân/nội bộ, không phân phối lại; free tier có thể đổi bất cứ lúc nào.
- TrueFX và Marketaux chưa kiểm chứng với tài khoản thật (fixture theo tài liệu); OANDA/Alpaca/Tiingo cũng mới kiểm bằng fixture. Lần đầu có key, xem log và `/providers`.
- Alpaca Free chỉ IEX (một phần khối lượng thị trường Mỹ); Tiingo EOD cập nhật sau phiên.
- Bộ đếm hạn mức Marketaux nằm trong RAM: khởi động lại container nhiều lần/ngày có thể vượt 100 (hệ thống đặt trần 70 để dư chỗ).
