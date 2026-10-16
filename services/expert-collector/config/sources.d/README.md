# sources.d — them nguon chuyen gia bang YAML

Thu muc nay duoc loader (`expert_collector/sources_loader.py`) doc TU DONG khi expert-collector khoi dong, va HOP NHAT voi danh muc dung san
(`opinion_catalog.py`, ~90 nguon da kiem chung 2026-10-12). Moi nhom/agent chi sua FILE CUA MINH:

| Nhom | File |
|---|---|
| NHTW / Fed khu vuc / BIS / IMF / OECD | `central_banks.yaml` |
| Nghien cuu sell-side cong khai + nha kinh te/blog doc lap | `research_macro.yaml` |
| YouTube / podcast / Bluesky / Mastodon | `social_media.yaml` |
| Nguoi trong cuoc, nghi si, 13D/13G, hang hoa-nang luong-vang-crypto | `insiders_commodities.yaml` |
| Viet Nam | `vietnam.yaml` |

Ghi chu kiem chung/ToS/ly do LOAI: viet vao `docs/sources/<nhom>.md` (KHONG sua `services/expert-collector/SOURCES.md`; coordinator gop sau).

## Dinh dang file
Goc la danh sach, hoac `{sources: [...]}`. Moi muc:

```yaml
- id: nyfed_speeches            # [a-z0-9_-]{2,64}, DUY NHAT, on dinh (expert_id = "op:<id>")
  name_display: "Fed New York - phat bieu"   # TEN CHUYEN GIA/TO CHUC dua y kien (hien thi nhu noi dung), KHONG phai ten website/nha cung cap
  type: rss                     # rss|atom|youtube|bluesky|json|form4|house_trades|senate_trades|sec13d|podcast|mastodon|html_list
  url: https://example.org/feed.xml   # https:// bat buoc; bluesky: handle (vd justinwolfers.bsky.social) hoac URL getAuthorFeed
  lang: en                      # en|vi|...
  group: cb_speech              # cb_speech|cb_research|intl_org|bank_research|think_tank|indep_macro|indep_markets|crypto|commodity|insider|vn_analysis|social|...
  institution_type: central_bank   # central_bank|institution|individual|media
  prior_score: 0.85             # 0-1 (diem uy tin khoi tao; quy tac o dau opinion_catalog.py). < 0.40 -> khong theo doi
  topics: [lai_suat]            # lam_phat|viec_lam|tang_truong|lai_suat|trai_phieu|ngoai_hoi|nang_luong|vang_kim_loai|co_phieu|tien_so|ngan_hang|bat_dong_san|thuong_mai|tai_khoa|ai
  symbols_hint: [EURUSD, XAUUSD]   # ma gan san (VN: "VN:VNINDEX", US: "US:SPX")
  enabled: true                 # mac dinh true; false = ghi nhan nhung KHONG chay
  poll_minutes: 60              # 5..1440, chu ky keo toi thieu
  keywords_only: false          # true = chi nhan bai co tu khoa tai chinh (nguon da chu de)
  mode: mkt                     # cb (hawkish/dovish) | mkt (bullish/bearish); mac dinh cb neu group la cb_speech
  summary_max: 300              # cat tom tat (chi luu tieu de + link + tom tat ngan)
  author_as_expert: false       # true: tac gia tung bai la ten chuyen gia hien thi
  notes: "thien lech/ToS/ghi chu"   # thien lech, xung dot loi ich -> luu thanh bias
  override: false               # true + trung id muc dung san = GHI DE enabled/prior_score/poll_minutes/notes/topics/symbols_hint
```

Quy tac loader: muc loi bi BO QUA (log `sources.d: bo qua ...`, khong sap), dedupe theo `id` va `url` (muc dung san thang), gioi han toc do theo host (>= 2 s/host, SEC 0,2 s; ton trong robots.txt; cache + ETag).
`type: youtube` o thoi diem 2026-10-12 bi robots.txt cua YouTube chan `/feeds/` (loader van nhan nhung nguon se bi RobotsDenied -> dung dat `enabled: true` neu khong co cach hop le khac).
Provider moi (house_trades...): dat module `providers_<ten>.py` canh `sources/` (xem `sources/opinion_feeds.py::register_kind`); phan loader da nhan `type` do.

## Kiem tra (KHONG chay tren laptop)
1. Dong bo len VPS: `D:\Work\trading-system\deploy.sh ""` (chi sync, khong build).
2. Validate schema + dem nguon:
```bash
cd /d/Work/Work-do/devops/claude-memory/tools && export SSH_JUMP=<BASTION_IP>
node ssh-run.js <VPS_IP> "docker run --rm -v /root/trading-system/services/expert-collector:/w -e PYTHONPATH=/w/src tradingsys-expert-collector python -m expert_collector.sources_loader /w/config/sources.d"
```
In `files=.. yaml_ok=.. invalid=..`, so nguon theo nhom, va `LOI: <file>[<idx>]: ly do` cho muc sai (exit 1 neu co loi).
3. Truoc khi dua nguon vao YAML, ban PHAI da kiem tra that tu VPS: HTTP 200, robots.txt cho phep UA `trading-system/0.1 (contact: <OWNER_EMAIL>)`, feedparser doc ra muc, bai moi < 60 ngay. Khong vuot dang nhap/CAPTCHA/anti-bot, khong dang ky tai khoan/khoa.
