# market-collector

Thu thap gia/nen va phat len Redis Streams `md.bars` / `md.quotes` (envelope `tscommon.Event`, theo `docs/CONTRACTS.md`).
Loi canh bao chat luong/provider loi phat len `alerts.out`.

## Kien truc
- `providers/` – plugin `Provider` (`fetch_bars(symbol, tf, start, end)`, tuy chon `latest_quote`). Registry `build_providers` bat/tat qua env `PROVIDERS`.
- `collector.py` – backfill (chia chunk theo ngay, resume qua `STATE_FILE`) + poll dinh ky (asyncio, interval theo provider).
  Provider tra M1 -> tu resample sang `OUTPUT_TFS` (M5/M15/H1/H4/D1, bucket theo UTC). Cua so luon cat ve 00:00 UTC de bucket khong bi thieu nen.
- `quality.py` – nen trung / OHLC mau thuan / gia <= 0 (bi loai), gap, nhay gia > 10% (chi canh bao) -> `alerts.out` (dedupe_key on dinh).
  Provider tra rong lien tuc `EMPTY_ALERT_AFTER` lan khi thi truong dang mo -> alert (1 lan, khong spam).
- `ratelimit.py` (sliding window), `retry.py` (exponential backoff + Retry-After), moi HTTP request deu qua rate limit + User-Agent rieng.
- Moc thoi gian luon UTC; symbol chuan hoa `EURUSD`, `XAUUSD`, `VN:VNM`.

## Nguon du lieu, ToS, rate limit
| Provider | Du lieu | Key | Mac dinh | Rate limit | Ghi chu / ToS |
|---|---|---|---|---|---|
| `dukascopy` | tick .bi5 theo gio -> M1 (gia BID) cho FX + vang/bac | khong | BAT | 2 req/s, 2 song song (env `DUKASCOPY_RATE_PER_SEC`/`DUKASCOPY_CONCURRENCY`), backoff + jitter + Retry-After, cache dia | Datafeed cong khai, khong co dieu khoan API chinh thuc; dung cho muc dich ca nhan, giu cache de khong tai lai. Volume = tong volume tick (don vi nha cung cap). |
| `frankfurter` | ty gia tham chieu ECB, D1 (o=h=l=c, v=0) | khong | BAT | 30 req/phut | Mien phi, khong key; chi ngay lam viec, khong co vang. Dung lam du phong/doi chieu. |
| `vnstock` | co phieu VN (`VN:VNM`), D1 (them H1/M-tf tuy nguon) | `VNSTOCK_API_KEY` tuy chon | BAT neu da cai (khong cai -> tu tat, log 1 dong) | 20 req/phut (60 neu co key) | **License vnstock 4.x (license-2026.09)**: mien phi cho ca nhan/hoc tap/nghien cuu, KHONG phai OSI; phan phoi lai hoac san pham ban quyen truy cap du lieu cho ben thu ba can thoa thuan rieng. **Gia da chuan hoa ve VND that (nguon tra nghin dong, nhan 1000)**; volume = so co phieu. Intraday: gio VN -> UTC; D1: ts_open = 00:00 UTC cua ngay. Xem muc "Bat vnstock". |
| `twelvedata` | M1..D1 FX/co phieu | `TWELVEDATA_API_KEY` bat buoc | TAT neu thieu key | 8 req/phut (free: 800/ngay) | Free tier gioi han, kiem tra ToS ve redistribute. Key khong bao gio ghi vao log/loi. |
| `oanda` | nen M1 (gia BID) FX+vang tu tai khoan practice v20; resample len M5..D1 | `OANDA_PRACTICE_TOKEN` | TU BAT khi co token | 60 req/phut (tu gioi han) | Nguon thu hai de DOI CHIEU Dukascopy. Token qua header, khong vao log. |
| `truefx` | quote FX real-time (khong nen), bo dem phut cho doi chieu | `TRUEFX_USER`+`TRUEFX_PASS` | TU BAT khi co du ca hai | 1 req/30s cho ca nhom cap | HTTP khong TLS (thiet ke cua TrueFX) -> dung tai khoan rieng. Chua kiem chung voi tai khoan that. |
| `alpaca` | nen H1+D1 co phieu/ETF My (`US:AAPL`), feed IEX | `ALPACA_KEY`+`ALPACA_SECRET` | TU BAT khi co du ca hai | 150 req/phut, toi da `ALPACA_MAX_SYMBOLS`=30 ma | Goi Free chi IEX (khong phai toan thi truong). |
| `tiingo` | nen EOD D1 co phieu/ETF My (gia tho) | `TIINGO_TOKEN` | TU BAT khi co token | 40 req/gio (Starter: 50/gio, 1000/ngay), toi da `TIINGO_MAX_SYMBOLS`=25 | Chi dung noi bo. |
| `fred` | chuoi vi mo D1 `FRED:DGS10`... qua `fredgraph.csv` | khong | BAT | 20 req/phut, poll 6h | Khong can key; chuoi mac dinh la du lieu cong khai. Doi chuoi: `FRED_SYMBOLS`. |
| `yahoo_daily` | nen D1 tho (chua dieu chinh co tuc) ETF My `US:*`, co phieu VN `VN:*` (`FPT.VN`, VND), vang `XAUUSD` (<- GC=F): **lich su tu 1990 + cap nhat hang ngay** | khong | **TAT** (can `PROVIDERS` co `yahoo_daily` **va** `ALLOW_RISKY_PROVIDERS=true`) | 10 req/phut, 1 poll/ngay luc `YAHOO_DAILY_AT_UTC`=22:30 | **Rui ro ToS** (API chart v8 khong chinh thuc; chi ca nhan, khong phan phoi lai). Co tat: bo khoi `PROVIDERS`/`ALLOW_RISKY_PROVIDERS=false`. Bo nen ngay UTC hien tai (chua dong). Quy tac uu tien nguon + backfill: `docs/DATA_SOURCE_PRIORITY.md`, `infra/ops/backfill_hist.py`. |
| `stooq` | CSV D1 | khong | **TAT** | 10 req/phut | Rui ro ToS. Can `PROVIDERS` co `stooq` **va** `ALLOW_RISKY_PROVIDERS=true`. Chi la khung, chua kiem chung. |
| `yahoo` | yfinance D1 | khong | **TAT** | 10 req/phut | Rui ro ToS (API khong chinh thuc, ca nhan). Nhu tren; can `pip install .[yahoo]`. Chi la khung. |

## Nguon mien phi + doi chieu (goi 0 dong)
Xem `docs/FREE_STACK.md` (dang ky key o dau, bien env, cach kiem tra). `GET /providers` = trang thai tung nguon (`active|needs_key|disabled`),
`GET /reconcile[?run=true]` = doi chieu Dukascopy vs OANDA/TrueFX (M1 cung phut, lech trung vi bps) vs Frankfurter (ECB 14:15 CET), moi `RECONCILE_INTERVAL`=900s.
Lech trung vi > `RECONCILE_THRESHOLD_BPS` (8) hoac lech toi da > 4x -> alert `alerts.out` (dedupe 6h/cap/nguon). Metric: `mc_recon_diff_bps`, `mc_recon_mismatch_total`, `mc_recon_status`, `mc_provider_state`.

## Crypto (`crypto_ccxt`)
ccxt (async, chỉ REST công khai, không key). Symbol `CRYPTO:<BASE>USDT`. Sàn theo thứ tự `CRYPTO_EXCHANGES` (mặc định `okx,kucoin,gate,bitfinex`; từ VPS <VPS_IP> Binance trả 451, Bybit 403). Nến gốc M1..D1 (chỉ nến đã đóng, `resample_m1=False`), lịch sử khi khởi động: D1 6 năm, H4 540 ngày, H1 180 ngày, M15 30 ngày, M5 14 ngày, M1 3 ngày (đổi bằng `CRYPTO_BACKFILL_<TF>=<ngày>`; resume theo `state.json`). Poll: M1 60s, M5 2', M15 5', H1 10', H4 20', D1 30' (mỗi poll lấy lại đúng nến đóng cuối để có tín hiệu "sàn còn sống"). Quote: vòng riêng mỗi `CRYPTO_QUOTE_INTERVAL` (15s) — 1 `fetch_tickers`/sàn, chỉ phát khi giá đổi. 24/7: `trades_weekends=True`; gap detector H1 theo dõi giờ đã thấy, ngày thiếu giờ được tải lại, giờ sàn thật sự không có nến được nhớ (`_known_empty`). Hook mới trong `Provider`: `chunk_for`, `backfill_start`, `poll_tfs`, `poll_start`, `latest_quotes`/`quote_stream_interval`, `resample_m1`, `trades_weekends`.

## Bat vnstock (tuy chon)
`pip install vnstock` tren PyPI khong con cho Python 3.12 (chi co `vnstock3` 3.2.1 cu). Ban hien hanh (4.x) cai tu index cua tac gia (theo README github thinh-vu/vnstock):
```
pip install -U --extra-index-url https://vnstocks.com/api/simple vnstock vnai
```
Docker: `WITH_VNSTOCK=1 docker compose -f infra/docker-compose.yml build market-collector` (build-arg `WITH_VNSTOCK`, mac dinh 0).
Khong cai -> provider vnstock tu tat (log canh bao), service van chay. API duoc dung: `Market().equity("VNM").ohlcv(start, end, interval)`; `VNSTOCK_API_KEY` (tuy chon, khoa Community) nang han muc. Telemetry cua thu vien duoc tat (`VNSTOCK_TELEMETRY=off`).

## Lap day khoang trong (gap) + tu phuc hoi
- Chunk backfill thieu gio (503/429) khong con chan cac ngay sau: phat phan da co, ghi **ngay thieu** vao gap registry va di tiep.
- **Gap detector** (moi `GAP_SCAN_INTERVAL`=900s, cua so `GAP_SCAN_DAYS`): Dukascopy doi chieu cache dia (file chi ghi khi tai thanh cong) -> ngay thieu; `fill_gaps` tai lai nguyen ngay (toi da `GAP_FILL_PER_CYCLE`=3/vong, ngay moi nhat truoc, cooldown tang dan `BACKFILL_RETRY_BASE..MAX`). Ton qua `GAP_ALERT_AFTER` (6h) -> 1 alert tong hop/provider.
- Task provider duoc **giam sat**: loi bat ngo (vd Redis bi recreate) chi log + metric `mc_loop_errors_total`, vong lap tiep tuc / task tu khoi dong lai (truoc day exception lam task chet am tham -> state dung yen, healthz van OK). `GET /status` co `tasks_alive`, `last_cycle`, `gaps`.
- Metric moi: `mc_gap_days`, `mc_gap_filled_total`, `mc_bars_rejected_total{provider,reason}`, `mc_provider_loop_alive`.
- Validate nen truoc khi phat: gia huu han > 0, low <= min(o,c), high >= max(o,c), volume huu han >= 0; nen sai bi loai + metric + 1 alert tong hop/lo (publisher chan lan cuoi).

## Do ben khi nguon loi (Dukascopy 503/404)
- 404 = gio khong co du lieu (cuoi tuan/ngay le: 25/12, 1/1) -> rong binh thuong, khong alert; 503/429/mang = loi tam thoi -> backoff mu + jitter, ton trong `Retry-After`, throttle thich ung (tang khi gap 503, giam khi thanh cong).
- Gio da tai xong duoc cache dia -> lan thu lai chi tai gio con thieu; chunk thieu gio => `PartialData`, backfill giu moc resume (`STATE_FILE`) tai chunk loi va **tu thu lai** (cooldown `BACKFILL_RETRY_BASE`..`BACKFILL_RETRY_MAX`).
- Loi tam thoi chi alert sau `ERROR_ALERT_AFTER` (mac dinh 5) lan lien tiep; log httpx per-request da tat (WARNING).

## Cau hinh
Xem `.env.example`. Chinh: `PROVIDERS`, `<PROVIDER>_SYMBOLS`, `OUTPUT_TFS`, `BACKFILL_DAYS`, `BACKFILL_ON_START`, `POLL_INTERVAL_<PROVIDER>`, `CACHE_DIR`, `STATE_FILE`, `REDIS_URL`, `BACKFILL_TOKEN`.
Backfill 1 lan khi khoi dong (tu `BACKFILL_DAYS` ngay truoc, resume tu moc cuoi trong `STATE_FILE`), sau do cap nhat dinh ky.
Luu `/data` bang volume de giu cache + state.

## HTTP
- `GET /healthz`, `GET /metrics` (Prometheus: `mc_bars_published_total`, `mc_fetch_errors_total`, `mc_fetch_empty_total`, `mc_quality_issues_total`, ...), `GET /status`.
- `POST /backfill` (header `X-Backfill-Token: $BACKFILL_TOKEN`; tat neu token rong), tra 202 + `job_id`:
  ```
  curl -X POST :8010/backfill -H "X-Backfill-Token: ..." -H "content-type: application/json" \
    -d '{"provider":"dukascopy","symbol":"EURUSD","start":"2024-01-01T00:00:00Z","end":"2024-02-01T00:00:00Z"}'
  ```

## Chay
```
pip install -e libs/common -e "services/market-collector[test]"
python -m pytest services/market-collector      # khong can mang/Docker (fixture gia + fakeredis)
python -m market_collector                         # can Redis
docker build -f services/market-collector/Dockerfile -t market-collector .   # tu goc repo
```
Stream `md.bars` idempotent theo khoa tu nhien `(symbol, tf, ts_open, source)` – phat lai/backfill chong len nhau an toan.
