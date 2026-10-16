# PATTERN_DATA - bo du lieu lich su cho bo nhan dien kich ban nen

Ngay: 2026-10-14. Gia 0 dong: chi nguon cong khai/mien phi. Ma nguon: `services/pattern-research/pattern_research/` (fetch.py, build.py, export_db_d1.py, loader.py).
Du lieu: VPS <VPS_IP> `/root/trading-system/data/research/patterns/` (Parquet, KHONG dung bang `bars` production). Tong ~360 MB.

## Nguon
| Ma | Nguon | Ghi chu |
|---|---|---|
| BTCUSD, ETHUSD | Binance public data (data.binance.vision, spot **BTCUSDT/ETHUSDT** M1) | 2020-10-01 -> 2026-10-13, UTC, volume that. Quote USDT, khong phai USD. |
| EURUSD, GBPUSD, USDJPY | Yahoo chart API (FX spot) | H1 ~2023-12-28 -> nay; M15/M5 chi ~80 ngay. Volume = 0 (FX khong co volume). |
| XAUUSD | Yahoo `GC=F` (futures vang, **proxy**, chua dieu chinh roll) | H1 tu 2024-05-22; M15/M5 ~70 ngay |
| US500 | Yahoo `ES=F` (futures S&P, **proxy**) | H1 tu 2024-05-22; M15/M5 ~70 ngay |
| US500_SPY, XAUUSD_GC | Bang `bars` san co (yahoo_daily): SPY ETF 1993+, GC=F 2000+ | chi D1, dung kiem tra mau hinh D1 dai han |
| (that bai) Dukascopy M1 | datafeed.dukascopy.com | tu VPS bi 503/timeout (tuong tu market-collector); chi lay duoc ~6 ngay. Da dung fetcher; chay lai `python -m pattern_research.fetch duka` + `merge` + `build` khi duoc mo la tu nang cap len M1 >=3 nam (cache raw/duka, tiep tuc duoc). |

## Bang ma x khung (so nen, tu - den)
| Ma | M1 | M5 | M15 | H1 | H4 | D1 | Khoang |
|---|---|---|---|---|---|---|---|
| BTCUSD | 3.17M | 634k | 211k | 52.9k | 13.2k | 2204 | 2020-10 -> 2026-10 |
| ETHUSD | 3.17M | 634k | 211k | 52.9k | 13.2k | 2204 | 2020-10 -> 2026-10 |
| EURUSD | - | 16.9k* | 5.6k* | 17.2k | 4355 | 730 | H1+: 2023-12 -> 2026-10 |
| GBPUSD | - | 16.9k* | 5.6k* | 17.2k | 4355 | 730 | nt |
| USDJPY | - | 16.9k* | 5.6k* | 17.1k | 4354 | 730 | nt |
| XAUUSD | - | 13.5k* | 4.5k* | 13.7k | 3605 | 616 | H1+: 2024-05 -> 2026-10 |
| US500 | - | 13.5k* | 4.5k* | 13.7k | 3604 | 617 | nt |
| US500_SPY | - | - | - | - | - | 8483 | 1993 -> 2026 |
| XAUUSD_GC | - | - | - | - | - | 6114 | 2000 -> 2026 |
(* = chi ~70-80 ngay gan nhat, toan bo nam trong tap TEST - khong dung de train.) Chi tiet day du: `manifest.json` (ma, khung, tu-den, so nen, %nen thieu, so nen tung split, sha).

## Resample / phien
- M5/M15/H1/(H4,D1 crypto): moc UTC. Crypto D1/H4: UTC.
- FX/vang/US500 H4 & D1: **dong ngay 17:00 New York** (21h/22h UTC theo DST) - 5 nen D1/tuan, nen gan nhan = mo cua (CN 17:00 NY cho nen "thu Hai"). Nen sau 17:00 NY thu Sau (Yahoo con 1 nen H1) gop vao nen thu Sau.
- Cot: `ts_open` (UTC), o,h,l,c,v, `n_m1` (so phut M1 thuc co; che do Yahoo la xap xi = so nen H1*60 hoac 5/15), `split`.

## Kiem tra chat luong (`qc.json`)
- Crypto M1: 3.17M nen/ma, **thieu 0.045% phut** (10 khoang trong, 8 khoang <1 ngay), 0 trung, 0 OHLC loi, 0 NaN, 0.007% nen phang/volume 0, vai bien dong >5%/phut (BTC 2, ETH 12) do cac su kien that (khong xoa).
- Yahoo FX/vang/US500: 0 trung, 0 OHLC loi; D1 nen thieu (<50% gio) 0.55-0.82% (FX), ~3% (XAU/US500 - nghi gio/ngay le); H4 0.4-1.1%. Khoang trong >3h ngoai cuoi tuan: XAU 23, EUR 7, GBP 6, JPY 5, US500 23. Volume FX = 0 (100%); vang/US500 volume = futures (3.6% nen = 0).
- Gioi han: nen o `n_m1 < 0.5*phut` co the loc bang `load(..., min_fill=0.5)`.

## Chia train / val / test (theo thoi gian, khong xao tron)
`splits.json` - ranh gioi CHUNG cho moi ma/khung, cua so 2023-10-01 -> 2026-10-14, 60/20/20 + **embargo 5 ngay** giua cac doan:
train < 2025-07-27 | val 2025-08-01 -> 2026-03-06 | test >= 2026-03-11. Ma co lich su dai (crypto, SPY, GC) co them nhieu train truoc 2023.
**TEST KHOA**: `load(..., split="test")` bat buoc `allow_test=True` va ghi `test_access.log`; chi mo 1 lan o buoc bao cao cuoi. Warmup chi khong bao gio lan sang test.

## Loader
```python
from pattern_research.loader import load, manifest, split_bounds, symbols
df = load("XAUUSD", "H1", split="train")                 # index UTC, cot o,h,l,c,v,n_m1,split,in_split
df = load("EURUSD", "H4", split="val", warmup=200, min_fill=0.5)
```
Chay trong container: `-v .../patterns:/out -v services/pattern-research:/app:ro -e PYTHONPATH=/app:/out/.pylib -e PATTERN_DATA=/out`.

## MT5 native (tai khoan demo MetaQuotes-Demo, nguon noi bo `mt5_demo`) - 2026-10-14
Nen **native cua terminal MT5** (CopyRates, 21 khung M1..MN1), xuat bang script doc-chi `mt-agent/MQL5/Scripts/MTAgentExport.mq5`, nhap bang `pattern_research/import_mt5.py`.
Du lieu: `/root/trading-system/data/research/patterns/mt5/` (CHI tren VPS, khong git, khong copy ve laptop): `raw/<SYM>_<TF>.bin` (MqlRates 60 byte, gio server), `bars/<SYM>_<TF>.parquet`, `manifest.json`, `qc_mt5.json`, `compare_native_vs_m1.json`, `tz_check.json`, `splits.json` (ban sao ranh gioi chung).
Load: `PATTERN_DATA=/root/trading-system/data/research/patterns/mt5` (loader.py co 21 khung). Trang thai tung ma: `docs/handoff/MT5_status.md`.

<!-- MT5_TABLE_BEGIN -->
Nhap lai tz `eu` (EET) 2026-10-14T14:12 UTC. Moi ma du **21/21 khung** (M1..M6, M10, M12, M15, M20, M30, H1..H4, H6, H8, H12, D1, W1, MN1); bang duoi la cac khung chinh (so nen), chi tiet tung khung trong `manifest.json`.

| Ma | M1 tu (UTC) | den (UTC) | M1 | M5 | M15 | M30 | H1 | H4 | D1 | W1 | MN1 | dung tu (QC) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| EURUSD | 1971-01-03T22:00 | 2026-10-14T11:56 | 10,073,971 | 2,066,655 | 695,756 | 351,784 | 179,639 | 50,424 | 14,383 | 2,909 | 669 | 2001-01-01 |
| XAUUSD | 2004-06-11T04:18 | 2026-10-14T11:48 | 7,070,576 | 1,499,741 | 513,023 | 258,317 | 129,918 | 34,228 | 5,741 | 1,166 | 268 | 2009-01-01 (M1-M30); H1+ tu 2007 |
| GBPUSD | 1993-05-11T21:00 | 2026-10-14T12:36 | 9,923,441 | 2,053,686 | 689,183 | 345,822 | 173,866 | 44,728 | 8,691 | 1,744 | 401 | 2001-01-01 |
| USDJPY | 1971-01-03T22:00 | 2026-10-14T13:03 | 10,031,564 | 2,065,410 | 695,233 | 351,546 | 179,551 | 50,418 | 14,386 | 2,908 | 669 | 2001-01-01 |
| US500 | 2012-08-05T21:00 | 2026-10-14T13:54 | 3,201,290 | 666,014 | 228,215 | 118,733 | 63,468 | 17,206 | 3,631 | 733 | 169 | toan bo |
| US30 | 2012-08-05T21:00 | 2026-10-14T13:57 | 3,284,684 | 666,007 | 227,736 | 118,506 | 63,440 | 17,204 | 3,632 | 733 | 169 | toan bo |
| USTEC | 2022-07-06T09:39 | 2026-10-14T14:01 | 1,446,418 | 289,500 | 96,573 | 48,328 | 24,194 | 6,358 | 1,067 | 216 | 50 | toan bo |

Tong 147 file parquet (7 ma x 21 khung).
<!-- MT5_TABLE_END -->

- **Gio**: server MetaQuotes-Demo = **EET (Europe/Athens, GMT+2 dong / GMT+3 he, DST chau Au)**. `ts_open` da doi ra UTC theo quy tac `eu` (importer mac dinh `MT5_TZ_RULE=eu`, ghi trong `tz_check.json` khoa `applied`). Kiem chung: buoc nhay tick-volume luc mo cua co phieu My tren US500 M1 roi dung 13:30 UTC (EDT) ca trong tuan lech DST My/Au (10/3, 17/3/2026, 28/10/2025) va 14:30 UTC (EST, 4/11/2025, 14/1/2026). `detect_rule` tren FX chon 'us' la ao giac (FX mo tuan o gio server co dinh); chi so cho 'eu' 100%. Ban nhap truoc 2026-10-14 14:10 (quy tac 'us') da bi thay.
- **QC dung tu**: EURUSD/GBPUSD/USDJPY truoc 1999 chi ~1 nen/ngay o moi khung (tong hop) -> dung tu 2001; XAUUSD 2004-2006 thua -> M1-M30 tu 2009, H1+ tu 2007; FX 2007-2008 ty le nen M1 phang cao. Chi tiet: `docs/handoff/MT5_status.md`.
- **Native vs resample M1** (`compare_native_vs_m1.json`): so OHLC nen native voi nen dung lai tu M1 cung server. `mismatch_pct_full_bars` = lech tren nen du phut.
- `n_m1` = so phut M1 that trong nen (tu M1 native); ngoai pham vi M1 gia dinh day du.
- Volume = tick volume (khong phai khoi luong that); cot `spread` (diem) cua server demo.
- Han che: gia la gia **feed demo MetaQuotes** (khong phai broker cua nguoi dung; spread/gio nghi co the khac); lich su som (truoc ~2010) thua, nhieu khoang trong M1.

- **Live (2026-10-14)**: nen song trong DB (`bars`) cho 7 ma nay lay tu CUNG feed demo nay qua EA -> mt-bridge, `source='canon:mt5:100000001'` (M1 tre ~1-2 phut; M5..D1 moc **UTC**, khac parquet MT5 o tren theo gio server EET cho H4/D1 -> khi so live voi backtest MT5 tren H4/D1 phai resample cung moc). Xem `docs/KIEN_TRUC.md` muc Feed canon, `docs/handoff/FEED_status.md`.

### Chinh sach luu tru / don raw (MT5)
1. `raw/*.bin` chi giu den khi parquet tuong ung duoc kiem (qc_mt5.json khong loi, `dup_ts`=0, so dong parquet == so nen trong `status.csv` tru nen OHLC loi bi loc).
2. Sau do nen: `zstd -T6 -15 --rm raw/*.bin && zstd -t raw/*.zst` (giu `.bin.zst` de tai tao khong can terminal). **Da nen 2026-10-14 cho ca 7 ma** (raw 7.3G -> 1.6G, 147 file `.bin.zst`, `zstd -t` OK). Nhap lai: `zstd -d raw/<SYM>_*.bin.zst` -> `runimp.sh <SYM>` -> nen lai. Hoac xoa neu thieu cho; tai xuat tu terminal bat cu luc nao (job-mt5.cfg).
3. `bars/*.parquet` + json la ban chuan. **Khong nam trong backup tu dong** (timer backup chi gom Postgres + cau hinh) va khong vao git: neu mat thi tai tao bang cach xuat lai tu terminal (~10 phut/ma) + `runimp.sh`. Giu `.bin.zst` giup tai tao khong can terminal.
4. Them ma/khung: doi `SymbolList` trong `/root/mtlab/out/MTAgentExport.set` + tao lai `job-mt5.cfg` + restart `mtlab-mt5` (xem `mt-agent/LAB.md`).

## Han che trung thuc
1. **FX/vang/US500 khong co M1, M5/M15 chi 70-80 ngay** (Dukascopy bi chan tu VPS) -> train mau hinh FX chi o H1/H4/D1 (~2-2.8 nam; D1 chi ~730 nen: mau lon thua). M5/M15 FX nam het trong test -> chi dung kiem tra chong lech khung.
2. Vang/US500 la **futures proxy** (roll, gia lech ~0.3-1% so voi spot/CFD; US500=ES=F co gio nghi 1h/ngay). Khong phai gia CFD cua broker.
3. Crypto = spot USDT; weekend/hoat dong 24/7 khac FX - khong tron thong ke khi so sanh phien.
4. Khong co spread/tick: backtest phai tu gia dinh phi/truot gia.
5. Tap TEST FX H1+ chi ~7 thang: du it setup; ket luan thong ke nen dung them crypto/D1 dai han (SPY, GC).

## Feed toan bo cap va backfill (2026-10-14)
Danh muc MT5 mo rong: 126 forex + 10 kim loai + 26 chi so (nguon `/root/mtlab/out/symbols.csv`). Backfill native moi khung chi nam o `data/research/patterns/mt5/` (khong dua vao git), gio server EET -> UTC. Feed realtime moi (EA market-feed) chi cap quote/M1 realtime vao DB; kiem chat luong theo `tests/e2e/test_feed_all.py` (phu symbol, lech gio nguyen, tre MT5->bus). Khi nap lich su, doi chieu so nen/ngay voi lich phien o docs/OBSERVABILITY.md §7 de khong tinh ngay nghi la thieu.

### Kết quả backfill A4 (hoàn tất 2026-10-15 ~02:55 UTC)
- 155 mã đã export native đủ 21 khung (M1..MN1); 152 import thành công, 7 mã canon cũ có từ trước (tổng 162). Bảng mã × khung: [PATTERN_DATA_mt5_coverage.md](PATTERN_DATA_mt5_coverage.md).
- Không import được: **NZDMXN, USDARS, USDGEL** — broker không có lịch sử M1 (0 nến, chỉ M2+), importer M1 báo IndexError khi rỗng; USDNGN (36k nến M1) và USDCLP (32k) có M1 ngắn.
- 29 mã im lặng trên feed realtime (không phải mất dữ liệu): chỉ số châu Âu ngoài giờ (UK100, NOR25, SA40, SE30, MIDDE50, TECHDE30, USTECH100M) và FX exotic thanh khoản thấp (AUDHUF/THB/ZAR, CAD*DKK/MXN/PLN/SEK, CHFMXN/TRY, EURILS/RUB, cặp chéo NOK/SEK/DKK, USDARS/GEL/RUB/RUR…) — broker không phát tick trong thời gian dài; lịch sử vẫn có theo khung tương ứng nếu bảng cho thấy số nến > 0.
- Cách chạy: `data/mtlab-hist/driver_q.sh` (hàng đợi chung `queue.txt`, flock `queue.lock`, import qua `imp.lock`), container `mtlab-mt5-hist..hist7` (terminal mới cần `out<N>/job-mt5.cfg`). Đã dừng cả 7 container sau khi xong (volume giữ).
