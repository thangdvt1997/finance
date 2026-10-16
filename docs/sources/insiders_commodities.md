# Nguon nhom: nguoi trong cuoc / nghi si, hang hoa-nang luong-vang, crypto research

Kiem chung THAT tu VPS <VPS_IP> ngay 2026-10-12 (UA `MarketMonitor/1.0` hoac `trading-system/0.1 (contact: <OWNER_EMAIL>)`; feedparser trong container tam `src-ic-val`; httpx de thu chong bot).
Cau hinh: `services/expert-collector/config/sources.d/insiders_commodities.yaml` (46 muc hop le, 0 loi; 36 bat, 10 tat).
Provider moi: `services/expert-collector/src/expert_collector/providers_insiders.py` (Form 4) + `tests/test_providers_insiders.py` (9 test dat trong container `src-ic-test`).

## A. Nguoi trong cuoc / nghi si / quy / thu cong khai

| Nguon | URL thu | Ket qua (2026-10-12 tu VPS) | robots/ToS | Quyet dinh |
|---|---|---|---|---|
| SEC Form 4 (insider) - Atom latest filings | `sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=4&output=atom` | 200 atom, 40 muc (moi filing 2 dong Reporting+Issuer) | robots: `Disallow: /cgi-bin` (urllib.robotparser bo sot vi dong trong giua file) | KHONG dung lam duong chinh (tuan thu robots); provider co co `use_atom` |
| SEC Form 4 - daily-index | `sec.gov/Archives/edgar/daily-index/2026/QTR4/form.20261009.idx` | 200, 626 KB, 564 dong Form 4; moi dong -> `edgar/data/<cik>/<acc>.txt` (200, 4-46 KB, chua `<ownershipDocument>` XML) | `/Archives` duoc phep; fair-access <=10 req/s, UA co email | **DUNG** (`sec_form4_insiders`, enabled) |
| SEC Form 3 / Form 5 | Atom `type=3` 200 40 muc; `type=5` 200 nhung 0 muc | Form 3 = nam giu ban dau (khong co giao dich), Form 5 = bao cao nam | nhu tren | Khong tao tin hieu (khong co "mua/ban") |
| SEC 13D/13G (moi: `SCHEDULE 13D`, `SCHEDULE 13G`) | Atom `type=SCHEDULE%2013D` 200 40 muc; `SC 13D` cu = 0 muc | Doc duoc qua daily-index | nhu tren | Ghi nhan, chua co provider -> enabled=false |
| SEC 13F-HR (quy) | Atom `type=13F-HR` 200 40 muc; daily-index | Tre toi 45 ngay | nhu tren | Ghi nhan, enabled=false (boi canh, khong thoi gian thuc) |
| SEC insider datasets (bulk) | `sec.gov/files/structureddata/data/insider-transactions-data-sets/2026q1_form345.zip` | link co trong trang `data-research/sec-markets-data/insider-transactions-data-sets` (zip form345 theo quy, TSV da chuan hoa) | du lieu cong khai SEC | Dung de backfill lich su sau nay (chua can) |
| Ha vien My - PTR (chinh thuc) | `disclosures-clerk.house.gov/public_disc/financial-pdfs/2026FD.xml` | 200 XML 474 KB, 418 PTR (`FilingType=P`, `DocID`); PDF `.../ptr-pdfs/2026/<DocID>.pdf` 200 80 KB, pypdf doc duoc van ban (ma, S/P, ngay, khoang gia tri) | khong co robots.txt (404); du lieu cong khai | **DUNG, can provider PDF** (`house_ptr_members`, enabled=false). Chi co khoang so tien + tre toi 45 ngay -> tin hieu yeu |
| Thuong nghi vien (Senate eFD) | `efdsearch.senate.gov/search/home/` | 200 nhung buoc "chap nhan dieu khoan" (prohibition su dung thuong mai) moi vao duoc du lieu; khong co API chinh thuc | click-through consent = khong vuot | **KHONG DUNG**; cac dich vu trung gian thuong mai cung KHONG dung |
| Bridgewater | `bridgewater.com/research-and-insights.rss` | 200 rss, 3 muc, moi nhat 17 ngay | khong han che | **DUNG** (`bridgewater_insights`) |
| Alpha Architect (nghien cuu dinh luong) | `alphaarchitect.com/feed/` | 200, 5 muc, 3 ngay | robots cho phep | **DUNG** (keywords_only) |
| Berkshire Hathaway (thu Buffett) | `berkshirehathaway.com/letters/letters.html`, `/letters/2025ltr.pdf` | 200 HTML / 200 PDF 91 KB; khong co RSS | robots 404 | Hop le nhung 1 thu/nam -> enabled=false (html_list) |
| Oaktree - memo Howard Marks | `oaktreecapital.com/insights/howard-marks-memos` | 200 SPA 970 KB, khong co feed (`memo-rss` 404) | robots cho phep trang | enabled=false cho toi khi co html_list parser |
| Third Point | `thirdpointlimited.com/investor-letters` | 200 HTML, khong feed | robots cho phep | enabled=false |
| Pershing Square | `pershingsquareholdings.com`, `assets.pershingsquareholdings.com` | 403 (chan bot) | - | **KHONG DUNG** (khong vuot chan) |

## B. Hang hoa / nang luong / vang

| Nguon | URL thu | Ket qua | robots/ToS | Quyet dinh |
|---|---|---|---|---|
| EIA - Today in Energy | `eia.gov/rss/todayinenergy.xml` | 200, 15 muc, 4 ngay | khong chan | **DUNG** |
| EIA - gia xang/dau diesel | `eia.gov/petroleum/gasdiesel/includes/gas_diesel_rss.xml` | 200, 1 muc/tuan, 5 ngay | khong chan | **DUNG** |
| EIA - dau suoi/propane | `.../heatingoilpropane/includes/hopu_rss.xml` | 200, 1 muc, 4 ngay | | **DUNG** |
| EIA - thong cao (co STEO) | `eia.gov/rss/press_rss.xml` | 200, 12 muc, 5 ngay | | **DUNG** |
| EIA - This Week in Petroleum | `.../petroleum/weekly/includes/week_in_petroleum_rss.xml` | 200 nhung muc moi nhat 10/2025, pubDate hong | | KHONG DUNG (cu/hong) |
| EIA - testimony / presentations | `eia.gov/rss/testimony.xml`, `presentations.xml` | 200, 1 muc, 1790 / 221 ngay | | KHONG DUNG (qua cu) |
| EIA - STEO, ton kho dau | `eia.gov/outlooks/steo/`, `/petroleum/...` | trang HTML, khong co RSS (steo.xml, petroleum.xml 404) | | Khong co feed; dung thong cao (press_rss) |
| EIA - ton kho khi (WNGSR) | `ir.eia.gov/ngs/wngsr.json` | 200 JSON 7 KB | robots.txt 403 (theo ToS EIA du lieu cong cong) | enabled=false (can provider JSON) |
| IEA | `iea.org/rss`, `/news/rss`, `/feed` | 404; trang `iea.org/news` 200 HTML | - | KHONG co feed -> khong dung |
| OPEC | `opec.org/rss.xml`, `/press-releases.html` | 403 | chan bot | KHONG DUNG |
| World Gold Council | `gold.org/rss.xml` | 200, 10 muc, 5 ngay (cac URL `/feed`, `/goldhub/research/rss` 404) | robots cho phep | **DUNG** (thien lech nganh vang) |
| LBMA | `lbma.org.uk/feed`, `/rss`, `/rss.xml` | 404; `/articles`, `/alchemist` 200 HTML | - | Khong co feed -> khong dung |
| Silver Institute | `silverinstitute.org/feed/` | 200, 10 muc, 40 ngay | cho phep | **DUNG** |
| USDA (WASDE, Crop Progress, ERS, AMS) | `usda.gov/rss/*`, `ams.usda.gov`, `esmis.nal.usda.gov` | 403 / ket noi bi dong; `nass.usda.gov` loi ket noi | chan bot | KHONG DUNG (khong vuot). FAS `apps.fas.usda.gov/psdonline/circulars/production.pdf` 200 (PDF thang) ghi nhan de sau |
| FAO | `fao.org/*/rss*` | 404; trang FFPI 200 HTML | - | Khong co feed -> khong dung |
| CME Group insights | `cmegroup.com/*` | khong ket noi / 404 | chan bot | KHONG DUNG |
| Baker Hughes rig count | `rigcount.bakerhughes.com/*` | 403 | chan bot | KHONG DUNG |
| CFTC thong cao / thi hanh / phat bieu | `cftc.gov/RSS/RSSGP/rssgp.xml`, `RSSENF/rssenf.xml`, `RSSST/rssst.xml` | 200, moi feed 10 muc, 2 / 11 / 6 ngay (duong `/rss.xml` cu 404) | robots cho phep | **DUNG** (keywords_only) |
| CFTC COT (vi the) | `cftc.gov/dea/newcot/deafut.txt` | 200 CSV 420 KB | robots cho phep | enabled=false (can provider du lieu) |
| Bo Nang luong My (DOE) | `energy.gov/rss` | 200, 10 muc, 1 ngay | cho phep | **DUNG** (keywords_only) |
| farmdoc daily (U. Illinois) | `farmdocdaily.illinois.edu/feed` | 200, 10 muc, 2 ngay | cho phep | **DUNG** |
| Oxford Inst. for Energy Studies | `oxfordenergy.org/feed` | 200 nhung 0 muc | - | KHONG DUNG |

## C. Crypto research cong khai

| Nguon | URL thu | Ket qua | robots/ToS | Quyet dinh |
|---|---|---|---|---|
| Glassnode | `insights.glassnode.com/rss/` -> 301 `research.glassnode.com/rss/` | curl 200 (15 muc) nhung httpx/urllib voi UA hop le = **403 (Cloudflare chan bot)** | khong vuot chan | **KHONG DUNG** (enabled=false) |
| Coin Metrics - State of the Network | `coinmetrics.substack.com/feed` | 200, 20 muc, 5 ngay | cho phep | **DUNG** |
| Messari | `messari.substack.com/feed` (moi nhat 2504 ngay = bo); `messari.io/*` 404/429 | - | - | KHONG DUNG |
| Galaxy Research | `galaxy.com/insights/*/rss`, `/feed` | 404 (khong co feed) | - | KHONG DUNG |
| CoinDesk | `coindesk.com/arc/outboundfeeds/rss/` | 200, 25 muc, 0 ngay | cho phep; bao chi chu khong phai research | **DUNG** (prior 0.45, muc thap) |
| The Block | `theblock.co/rss.xml` | 200, 20 muc | bao chi, nhieu bai tra phi/PR | Khong dung (trung chuc nang CoinDesk) |
| Chainalysis | `chainalysis.com/blog/feed/` | 200, 10 muc, 3 ngay | cho phep | **DUNG** |
| a16z crypto | `a16zcrypto.com/feed/` | 200, 30 muc, 12 ngay | cho phep | **DUNG** (xung dot loi ich) |
| Ethereum Foundation blog | `blog.ethereum.org/feed.xml` | 200, 642 muc, 7 ngay | cho phep | **DUNG** |
| Bitcoin Optech | `bitcoinops.org/feed.xml` | 200, 10 muc, 3 ngay | robots 404 | **DUNG** |
| Paradigm, Kaiko, Delphi, Coinbase blog, Fidelity Digital Assets | `*/feed*` | 404 hoac 403 | - | KHONG DUNG |
| SEC (thong cao, phat bieu, tuyen bo, kien tung, hanh chinh) | `sec.gov/news/pressreleases.rss`, `/news/speeches-statements.rss`, `/news/statements.rss`, `/enforcement-litigation/litigation-releases/rss`, `.../administrative-proceedings/rss` | 200, moi feed 25 muc, 2 ngay (`/rss/litigation/litreleases.xml` cu 404) | UA co email, <=10 req/s | **DUNG** (keywords_only) |
| BIS (FSI, BIS Papers, working papers, phat bieu NHTW) | `bis.org/doclist/bis_fsi_publs.rss`, `bispapers.rss`, `wppubls.rss`, `cbspeeches.rss` | 200, 20/25/25/50 muc, 4-6 ngay | cho phep | **DUNG** |
| Fed (FEDS Notes, FEDS papers, press, speeches, monetary) | `federalreserve.gov/feeds/{feds_notes,feds,press_all,speeches_and_testimony,press_monetary}.xml` | 200, 15-20 muc, 2-9 ngay | robots 404 | **DUNG** |
| BoE / ECB | `bankofengland.co.uk/rss/publications`, `ecb.europa.eu/rss/press.html` | 200, 50 / 15 muc, 2 / 3 ngay | cho phep | **DUNG** |
| IMF blog/news | `imf.org/en/News/RSS` | 429 (gioi han toc do) | - | Bo qua, thu lai nhom khac |

## Provider Form 4 (tom tat thiet ke)
- Luong: daily-index (3 ngay lam viec gan nhat) -> loc dong `4` -> tai `.txt` -> bat `<ownershipDocument>` -> `parse_form4` (ElementTree) -> `aggregate` (VWAP theo nguoi/ma/ngay) -> `is_opportunity` -> `SignalInfo` (`symbol=US:<TICKER>`, `side`, `entry=gia`, `raw.kind` = `insider_buy|insider_sell`, `raw.value_usd`, `roles`, `title`, `owner`, `strength`, `cluster`).
- Loc: chi ma P (mua) / S (ban) o bang non-derivative; bo A/M/F/G/D/J...; bo 10b5-1 (co `aff10b5One`=1 hoac chu thich); bo mua qua DRIP/ESPP/401k; mua >= 100.000 USD, ban >= 1.000.000 USD va khong phai nop thue.
- Do manh: log gia tri x trong so vai tro (CEO/CFO/Chu tich 1.0, officer 0.85, director 0.75, 10% owner 0.6), cong +0.1/nguoi nua khi >=2 nguoi cung mua (cluster >= 3 nguoi duoc danh dau).
- Fixture that (rut gon) tu EDGAR 2026-10-09: `real_form4_sah_buy.xml` (mua 819.046 USD, co dong >10%), `real_form4_ahrt_drip.xml` (mua DRIP, bi loai), `real_form4_ptct_10b5_sell.xml` (ban 10b5-1, bi loai), `real_form4_stld_grant.xml` (cap DSU, bi loai), `real_form4_daily_index.idx`, `real_form4_atom.xml`.
- Ghi chu ky thuat: `PoliteClient` dung `urllib.robotparser`, ket thuc nhom khi gap dong trong nen KHONG thay `Disallow: /cgi-bin` cua SEC; vi vay Atom bi TAT mac dinh. Dat `host_intervals={"www.sec.gov": 0.2}` cho SEC. Chi la du lieu cong khai, khong phai khuyen nghi.
