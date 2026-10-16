# Thứ tự ưu tiên nguồn nến D1 (lịch sử + hằng ngày)

Ngày: 2026-10-11. Áp dụng cho bảng `bars` (khóa `(symbol, tf, ts_open, source)`): nhiều nguồn có thể cùng tồn tại cho một `(symbol, tf, ts_open)`.

## Quyết định (đơn giản, an toàn, không đổi truy vấn)
Mọi đường đọc (paper-trader, analytics, api-gateway `/v1/bars`...) dùng `SELECT DISTINCT ON (ts_open) ... ORDER BY ts_open DESC, source` → khi trùng `ts_open` **nguồn có tên đứng đầu theo bảng chữ cái thắng**. Ta *dựa vào quy tắc đó* thay vì sửa truy vấn (không động vào code của service khác), và đặt tên `source` để thứ tự tự nhiên là thứ tự ưu tiên mong muốn:

| Loại | Thứ tự ưu tiên (cao → thấp) | Ghi chú |
|---|---|---|
| FX/vàng/chỉ số feed (EURUSD, GBPUSD, USDJPY, XAUUSD, US500, US30, USTEC) — mọi khung | `canon:mt5:100000001` > (nguồn bên dưới) | Từ 2026-10-14: chuỗi feed EA (mt-bridge `feed.py`, M1 trễ ~1–2 phút, M5..D1 mốc UTC) đứng đầu theo chữ cái; chỉ có ở khoảng thời gian EA online → ngoài khoảng đó tự rơi về dòng dưới. Rollback: `FEED_CANON_ENABLED=false` + xoá `source LIKE 'canon:%'`. Xem KIEN_TRUC.md §2.1. |
| FX (EURUSD, GBPUSD, USDJPY…) | `dukascopy` > `frankfurter` | `frankfurter` (ECB, ~14:15 CET, o=h=l=c, v=0) là **lịch sử từ 1999**; Dukascopy (giá BID, nến UTC) chỉ có vài ngày gần nhất nên che phần trùng. Điểm nối: lệch tối đa vài chục bps trong 1 ngày (khác giờ lấy giá) — chấp nhận cho trend chậm. |
| Vàng `XAUUSD` | `dukascopy` > `yahoo_daily` | lịch sử = futures liên tục `GC=F` (chưa điều chỉnh roll, premium ~0,3–1% so với spot; nhảy khi roll). Proxy, không phải spot. |
| ETF Mỹ `US:*` | `alpaca` > `tiingo` > `yahoo_daily` | hai nguồn đầu chỉ bật khi có key (mặc định tắt). Cả ba là giá thô (chưa điều chỉnh cổ tức). |
| Cổ phiếu VN `VN:*` | **chỉ `yahoo_daily`** (vnstock D1 TẮT: `VNSTOCK_SYMBOLS=` rỗng) | Đã kiểm tra: `vnstock` không key chỉ trả ~100 nến/lần và là giá **đã điều chỉnh** (lệch tới 7% so với Yahoo giá thô ở 2025) → trộn hai nguồn tạo nhảy giả 3–7% trong cửa sổ momentum. Vì vậy đã xoá 600 hàng D1 `vnstock` (sao lưu CSV trong container timescaledb `/tmp/vnstock_d1_backup.csv`, tạm) và dùng Yahoo `FPT.VN/VCB.VN/VNM.VN` (VND thật, khớp vnstock ở 5 phiên gần nhất). Bật lại vnstock chỉ khi có `VNSTOCK_API_KEY` và đã kiểm tra lịch sử điều chỉnh. Rủi ro còn lại: Yahoo không điều chỉnh cổ phiếu thưởng (VCB 2025-03-03 −33% là nhảy giả) → dấu momentum VN có thể sai ~12 tháng sau mỗi sự kiện thưởng. |

`source` của **cả lịch sử lẫn cập nhật hằng ngày** của Yahoo là cùng `yahoo_daily` → không có mốc nối giữa backfill và daily (cùng khóa, upsert idempotent). Tên đặt cố ý: ký tự đầu `y` ≥ mọi nguồn chính thống khác.
Nếu sau này thêm nguồn tên đứng sau `yahoo_daily` (ví dụ `zzz`) thì phải đặt lại tên — quy tắc là *thứ tự chữ cái của `source`*.

## Cách nạp (đường chính thống)
`market-collector` provider → `quality.check_bars` (loại OHLC sai/giá ≤ 0, cảnh báo gap/nhảy > 10%) → `md.bars` (Redis Streams) → `storage-writer` (`validate_bar` + upsert `ON CONFLICT`). Script điều khiển: `infra/ops/backfill_hist.py` (gọi `POST /backfill` theo cửa sổ ≤ 10 năm, tuần tự):
```
cd /root/trading-system/infra
docker compose -p tradingsys --env-file .env exec -T market-collector python - yahoo_daily:1990-01-01:XAUUSD,US:SPY,... < ops/backfill_hist.py
docker compose -p tradingsys --env-file .env exec -T market-collector python - frankfurter:1999-01-04:EURUSD,GBPUSD,... < ops/backfill_hist.py
```
Yêu cầu `.env`: `PROVIDERS=...,yahoo_daily`, `ALLOW_RISKY_PROVIDERS=true`, `BACKFILL_TOKEN`, `FRANKFURTER_SYMBOLS`. Dữ liệu Parquet nghiên cứu (`/root/research/data`) **không** nạp trực tiếp: nó là chuỗi *excess return* tổng hợp (cổ tức giả định, proxy trái phiếu từ lợi suất FRED) chứ không phải giá giao dịch; hệ thống mô phỏng cần giá của đúng công cụ sẽ giao dịch (ETF/FX).

## Provider `yahoo_daily` (RỦI RO ToS)
- API chart v8 không chính thức của Yahoo; điều khoản chỉ cho mục đích **cá nhân/phi thương mại**; không phân phối lại. Có thể bị đổi/chặn bất cứ lúc nào.
- **Cờ tắt**: bỏ `yahoo_daily` khỏi `PROVIDERS` hoặc `ALLOW_RISKY_PROVIDERS=false` rồi `up -d market-collector` (dữ liệu đã nạp vẫn còn).
- Lịch: poll 1 lần/ngày lúc `YAHOO_DAILY_AT_UTC` (mặc định 22:30 UTC, sau đóng cửa NYSE cả khi DST), 10 req/phút, backoff mũ + Retry-After, User-Agent riêng (`Mozilla/5.0 (compatible; trading-system-market-collector/0.1; personal-use)`). Nến của ngày UTC hiện tại bị bỏ (chưa đóng) → không ghi nến dở dang.
- Đối chiếu chất lượng: `check_bars` (OHLC, gap ≥ 10 nến, nhảy > 10% → `alerts.out`), metric `mc_bars_rejected_total{provider="yahoo_daily"}`; so sánh chéo ETF (ví dụ SPY) với Alpaca/Tiingo khi có key (nguồn thay thế hợp pháp hơn: `ALPACA_KEY/SECRET`, `TIINGO_TOKEN`, thêm `alpaca`/`tiingo` vào `PROVIDERS` — chúng tự thắng Yahoo theo bảng trên).

## Giới hạn dữ liệu đã biết
- Giá thô, không điều chỉnh cổ tức → ETF trái phiếu/cổ phiếu thấp hơn lợi suất tổng 1–4%/năm (ảnh hưởng nhỏ tới dấu momentum 12-1 nhưng lệch so với backtest dùng chuỗi excess).
- Ngày nghỉ khác nhau theo thị trường: mỗi symbol có lịch riêng, chiến lược chỉ dùng chuỗi của chính nó.
- ETF ra đời muộn (CPER 2011, CORN 2010, WEAT/SOYB/CANE 2011, BNO 2010, VNM 2009): lịch sử ngắn hơn backtest (backtest nối spot/futures trước đó).

## Crypto (`crypto_ccxt`, 2026-10-12)
`source` = `crypto_ccxt` cho mọi sàn (khóa upsert không tách theo sàn). Thứ tự ưu tiên sàn theo từng symbol: `CRYPTO_EXCHANGES` (okx > kucoin > gate > bitfinex; TON chỉ có trên Bitfinex/Kraken nên tự rơi xuống sàn sau). Mọi tf là nến GỐC của sàn (không resample từ M1), chỉ nến ĐÃ ĐÓNG; D1 cắt 00:00 UTC. Không có nguồn thứ hai cùng tên `source` nên không cần thứ tự ưu tiên; nếu thêm nguồn crypto khác, đặt tên `source` đứng SAU `crypto_ccxt` theo bảng chữ cái (quy tắc `DISTINCT ON ... ORDER BY source`).

## Feed MT5 toàn bộ cặp (2026-10-14)
Quote realtime của 126 forex + 10 kim loại + 26 chỉ số đến từ EA market-feed (source `mt5:...-feed`), ưu tiên cao nhất cho quote realtime của các mã này; 7 mã canon (nến M1) giữ nguyên chuỗi ưu tiên hiện hành (canon > EA thô > dukascopy làm dự phòng, xem mục trên). Khi feed mất trong giờ mở cửa (cảnh báo `Feed*`), UI rơi về nguồn dự phòng/nến trễ đã có; dữ liệu cuối tuần/lễ không bị coi là mất. Lịch phiên dùng cho cảnh báo: docs/OBSERVABILITY.md §7.
