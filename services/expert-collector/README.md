# expert-collector

Theo doi lenh/tin hieu/y kien chuyen gia uy tin tu nguon CONG KHAI va HOP PHAP. **Chi la du lieu tham khao, KHONG phai khuyen nghi dau tu.** Khong thuc thi lenh. Xem `SOURCES.md` cho bang nguon/ToS.

## Luong
`ExpertSource.list_experts()` -> tinh `reputation_score` (nguong cau hinh; loai martingale/grid, chuyen gia xoa lich su) -> chi chuyen gia dat nguong moi duoc theo doi -> `fetch_signals`/`fetch_positions` -> phat hien mo/dong/dao chieu -> publish `expert.signals`, `expert.positions`, alert `alerts.out` (co `dedupe_key`) -> canh bao dong thuan khi >= N chuyen gia uy tin cung chieu tren 1 symbol trong cua so thoi gian.

Lan quan sat DAU TIEN cua mot chuyen gia la "baseline": phat signal (raw.baseline=true) nhung KHONG alert.

## Plugin
`sources/base.py::ExpertSource`. Bat/tat bang `EC_SOURCES` (csv). Nguon rui ro (mql5, myfxbook) bi chan neu thieu xac nhan (`EC_MQL5_ACCEPT_TOS`, credentials). Them nguon moi: ke thua `ExpertSource`, dang ky trong `registry.py`, parser la ham thuan + fixture test.

## Trang thai (Redis, tien to `ec:`)
`ec:experts` (hash: ho so + diem + ly do loai), `ec:rep:{id}` (snapshot uy tin theo ngay), `ec:pos:{id}`, `ec:stances:{id}`, `ec:seen:*` (dedupe). Khong doc DB cua service khac.

## API / van hanh
`GET /healthz`, `GET /metrics`, `GET /experts[?tracked=true]`, `GET /experts/{id}`. Port `PORT` (mac dinh 8010).
Chay: `python -m expert_collector`. Test: `python -m pytest` (khong can mang/Docker; fakeredis + fixture).

## Dinh dang `static_json`
Xem docstring `sources/static_json.py` (experts[] voi reputation, positions, signals, closed_trades).

## Luu y hop dong
Bang `experts` (reputation jsonb) chua co stream de storage-writer ghi; hien metadata chi o Redis + `raw.reputation_score` trong signal. De xuat them stream `expert.profiles` (type `expert_profile`).

## Mac dinh co du lieu that
`EC_RSS_FEEDS` khong dat -> dung `default_feeds.py` (ActionForex Weekly Outlook, mode `technical_outlook`, ~8 tin hieu/tuan). `EC_RSS_FEEDS='[]'` de tat. Chi tiet kiem chung/ToS: `SOURCES.md`.

## Y kien chuyen gia (opinion_feeds, 2026-10-12)
`EC_SOURCES` mac dinh them `opinion_feeds`: danh muc dung san (`opinion_catalog.py`) + `config/sources.d/*.yaml` (loader `sources_loader.py`, schema/cach test: `config/sources.d/README.md`). Moi bai -> `news.items` (source `expert:op:<id>`, `expert{...}` gom xu huong hawkish/dovish/bullish/bearish, chu de, uy tin, nhan "y kien tham khao") + `expert.profiles`; storage-writer ghi `expert_opinions` khi `STORAGE_EXPERT_OPINIONS=true` (migration 017); API gateway `GET /v1/expert-opinions`; service nay `GET /opinions`. Provider: rss/atom/podcast, bluesky (API cong khai), form4 (`providers_insiders`, SEC daily-index), html_list (`providers_htmllist`, 4 CTCK VN). Env: `EC_OPINION_DISABLE=id1,id2`, `EC_OPINION_MIN_CRED=40`, `EC_SOURCES_DIR`. Bang nguon/ToS/diem: `SOURCES.md`.
