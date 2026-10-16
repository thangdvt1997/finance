# Nguon chuyen gia: Ngan hang trung uong & dinh che cong (macro)

Kiem chung THAT 2026-10-12 tu VPS <VPS_IP> (container tam python:3.12-slim + feedparser, UA `Mozilla/5.0 (compatible; MarketMonitor/1.0)`, timeout 25 s). Cot "muc" = so muc feedparser doc duoc (tieu de + link; co summary tru khi ghi "khong summary"). "Moi nhat" = ngay bai moi nhat trong feed. Cau hinh: `services/expert-collector/config/sources.d/central_banks.yaml` (63 feed DUNG). Uy tin (prior_score) = uy tin to chuc phat hanh, khong phai thanh tich du bao. Chi mang tinh tham khao, khong phai khuyen nghi dau tu.

## A. Feed DUNG (63)

| To chuc / nguon | Feed (id trong YAML) | HTTP/dinh dang | Muc | Moi nhat | robots/ToS | Dung |
|---|---|---|---|---|---|---|
| Fed Board | `federalreserve.gov/feeds/` press_all, press_monetary, press_bcreg, speeches, testimony, feds_notes, feds, ifdp | 200 text/xml (RSS) | 15-20 moi feed | 2026-07..10-09 | robots.txt tra trang HTML (khong co quy tac cam); feed RSS cong bo chinh thuc | DUNG (8) |
| Fed Board theo nguoi | s_t_powell, s_t_warsh (Chu tich), s_t_waller, s_t_cook, s_t_barr, s_t_jefferson, m_w_Bowman, s_t_miran | 200 text/xml | 1-15 | warsh 08-28; waller 10-08; miran 2026-03 (thua) | nhu tren | DUNG (8) |
| NY Fed Liberty Street | `libertystreeteconomics.newyorkfed.org/feed/` | 200 RSS, 2,9 MB | 100 | 10-09 | robots cho phep | DUNG (poll 120 phut vi nang) |
| SF Fed | `frbsf.org/feed/` | 200 RSS | 10 | 10-07 | cho phep | DUNG |
| Atlanta Fed | `/rss/macroblog`, `/rss/gdpnow` (GDPNow) | 200 RSS | 15 | 09-29 / 10-08 | cho phep | DUNG (2) |
| Dallas Fed | `/rss/dallasfed.xml`, releases, speeches, updates (WEI) | 200 RSS | 100 moi feed | 09-21..10-08 | cho phep | DUNG (4) |
| ECB | `ecb.europa.eu/rss/` press, blog, pub, wppub; ECB Banking Supervision press | 200 application/rss+xml | 15 | 10-07..08 | cho phep | DUNG (5); press/blog/supervision khong summary |
| Bank of England | `/rss/` news, speeches, publications, statistics | 200 text/xml | 50 | 10-05..09 | cho phep | DUNG (4) |
| Bank of Japan | `boj.or.jp/en/rss/whatsnew.xml` | 200 application/xml (RSS 1.0) | 48 | 10-09 | robots.txt tra 404 (khong co quy tac) | DUNG; khong summary |
| RBA | rss-cb-speeches, media-releases, bulletin, rdp, smp | 200 text/xml | 1-2 moi feed (chi giu muc moi nhat) | 08-11..10-01 | cho phep | DUNG (5) |
| RBNZ | `rbnz.govt.nz/feeds/news` | 200 text/xml | 50 | 10-07 | robots.txt tra trang loi (khong co quy tac) | DUNG (URL `/rss` cu = 403) |
| Bank of Canada | speeches, press-releases, publications, mpr, research, staff-analytical-notes, summary-of-deliberations (`/content_type/<x>/feed/`) | 200 RSS | 10 | 07-15..10 | cho phep | DUNG (7) |
| SNB | `snb.ch/public/en/rss/speeches` | 200 RSS | 10 | 10-01 | cho phep | DUNG |
| Riksbank | `/en-gb/rss/press-releases/`, `/en-gb/rss/speeches/` | 200 text/xml | 10 | 10-08 | cho phep | DUNG (2) |
| BIS | doclist/cbspeeches (phat bieu NHTW toan cau), bispapers, bis_fsi_publs, all_pressrels, mgmtspeeches | 200 application/rss+xml | 10-50 | 10-05..08 | cho phep | DUNG (5) |
| RBI (An Do) | rbi.org.in speeches, pressreleases, Publication, Bulletin (`*_rss.xml`) | 200 text/xml, to (100-400 KB) | 10 | khong co ngay chuan | robots.txt tra 'Unauthorised' nhung feed cong khai 200 | DUNG (4); poll thua |
| CBO | `cbo.gov/publications/all/rss.xml` | 200 RSS | 30 | 10-09 | robots.txt bi thu thach JS anti-bot; feed van 200 -> chi lay feed, KHONG lach | DUNG co dieu kien (poll 240 phut; tat neu bi chan) |
| OECD Ecoscope blog | `oecdecoscope.blog/feed/` | 200 RSS | 10 | 10-09 | cho phep | DUNG |
| BEA | `bea.gov/rss/rss.xml` | 200 RSS | 48 | 10-06 | cho phep | DUNG |
| Census | `census.gov/economic-indicators/indicator.xml` | 200 XML | 18 | 10-08 | cho phep | DUNG |

## B. Da thu va LOAI (khong dung)

| Nguon | URL thu | Ket qua | Ly do |
|---|---|---|---|
| St. Louis Fed (FRED blog, On the Economy, Review, Page One) | `fredblog.stlouisfed.org/feed/`, `stlouisfed.org/rss/page-resources/...` (URL dung theo trang /rss) | timeout >25 s tu VPS (lap lai 2 dot) | khong truy cap duoc tu VPS; thu lai sau |
| Kansas City Fed | `/rss`, `/rss/publications...` | timeout | nhu tren |
| Cleveland, Richmond, Minneapolis, Philadelphia Fed | `/rss`, `/rss/news`... | 404 hoac trang HTML | khong tim thay feed cong khai (nowcast Cleveland: khong co RSS) |
| NY Fed (speeches/press/research) | `newyorkfed.org/rss/feeds/*` | 200 nhung HTML 65-100 KB | khong phai RSS; chi Liberty Street dung |
| Boston Fed | `/feeds/rss_news|research|speeches.xml` | 200 RSS, 50 muc, khong tieu de/summary | moi nhat 2025-12 / 2020 / 2024 -> cu, bo |
| Chicago Fed | `/forms/rss/NewsReleases|Speeches|insights|DataReleases...` | 200 RSS to (0,2-1,4 MB) | moi nhat 2023-2024 -> cu, bo |
| SF Fed economic-letter / theo chuyen muc | `/research-and-insights/.../feed/` | 404 | chi dung feed chung |
| Atlanta speeches / wage tracker / policyhub | `/rss/speeches` ... | 404 | khong ton tai |
| BoE `bank-overground` | 200 | moi nhat 2025-10 -> cu; `events` = lich su kien toi 2027 (nhieu) | bo |
| BoC feed chung `/feed/` | 200 | tron lan su kien tuong lai (2027) | trung lap voi feed chuyen muc |
| ECB `statpress` | 200 | trung press; `fxref-*` = ty gia tham chieu (du lieu, khong phai y kien) | bo |
| Fed DDP (g17, h15, h41, h6, z1, datadownload...) | 200 | thong bao ky thuat data, khong phai y kien | bo (lam bang du lieu rieng) |
| IMF (blog, WEO, rss-list) | `imf.org/...` | 403 | bi chan anti-bot; khong lach |
| OECD chinh (`oecd.org/.../rss`) | 403 | nhu tren | chi dung Ecoscope blog |
| World Bank blogs / news | `blogs.worldbank.org/...rss*` | 404 / DNS fail | khong co feed cong khai tim duoc |
| US Treasury (press, TIC) | `home.treasury.gov/...` | 404 | khong tim duoc feed; TIC la CSV, do collector du lieu |
| ESM, EC economy-finance | 404 | khong co feed |
| PBoC (EN) | `pbc.gov.cn/en/...` | HTML, khong feed | khong co RSS |
| SBV (NHNN Viet Nam) | `sbv.gov.vn/.../rss` | HTML 420 KB, khong feed | khong co RSS cong khai (chuyen cho nhom Viet Nam) |
| Norges Bank | `/en/rss-feeds/` | 200 HTML trang huong dan, URL feed goi y 404 | chua tim ra URL feed dung; co the thu lai |
| SNB press/research | 404 | chi speeches dung |
| Eurostat statistics-update | 200, 2385 muc | du lieu cap nhat, khong phai y kien | bo |
| FT | 301 | bao tra phi | khong |

## Luu y
- Tat ca la RSS cong khai do chinh to chuc cong bo; khong dang nhap, khong lach CAPTCHA/anti-bot (IMF/OECD/CBO-robots dung lai o dau bi chan).
- Nhieu feed (ECB, BoJ) khong co truong summary: collector luu tieu de + link.
- RBA/Riksbank/SNB chi giu 1-10 muc -> poll thua la du.
- Mot so feed co the cau hinh `mode: cb` (hawkish/dovish) cho cb_speech, `mode: mkt` cho cb_research/intl_org (chua chay validator loader vi loader do agent khac tao).
