# Nguon du lieu chuyen gia: truy cap hop le, ToS, do tin cay

CAP NHAT 2026-10-12: them plugin `opinion_feeds` (y kien chuyen gia/to chuc: RSS/Atom, Bluesky, Form 4) + co che `config/sources.d/*.yaml` (xem `config/sources.d/README.md`). Danh muc dung san: `src/expert_collector/opinion_catalog.py`; moi nhom nguon do 1 agent nghien cuu rieng (ghi chu goc: `docs/sources/*.md`).

## Nguyen tac (bat buoc)
- Kiem chung THAT tu VPS <VPS_IP> voi User-Agent `trading-system/0.1 (contact: ...)`: HTTP 200 + robots.txt cho phep (PoliteClient mac dinh; YouTube `/feeds/` bi robots CHAN -> khong dung) + feedparser/JSON doc ra muc that + bai moi.
- Khong dang nhap vuot quyen, khong vuot CAPTCHA/chong bot (403/Cloudflare = DUNG, khong lach), khong tu dang ky tai khoan/khoa. Rate limit >= 2 s/host (SEC 0,2 s; Bluesky 0,5 s), chu ky poll theo tung nguon, ETag/If-Modified-Since, cache, dedupe theo URL (Redis `ec:seen:op:*`).
- Chi luu **tieu de + link + tom tat <= 300 ky tu** (khong sao chep toan van); tin phat qua `news.items` voi nhan "y kien tham khao" (`expert.label`), kem `disclaimer`. KHONG phat `expert.signals`, KHONG sinh khuyen nghi mua/ban, KHONG alert. (Rieng giao dich noi bo Form 4 la du lieu phap ly: `stance` bullish/bearish chi mo ta chieu giao dich.)
- Bang chung (docs/research/INFO_SIGNALS_STUDY.md): tin hieu chuyen gia cong khai it gia tri du bao -> dung lam NGU CANH. Diem uy tin = uy tin to chuc/chuyen mon/do on dinh ky thuat cua nguon, KHONG phai thanh tich du bao.
- UI khong hien thi ten website/nha cung cap: ten hien thi la ten CHUYEN GIA/TO CHUC (`name_display`); URL bai goc chi la khoa lien ket (xem docs/UI_NO_SOURCES.md, muc "Con lo").
- Tat tung nguon: `enabled: false` trong YAML (`override: true` + trung id de tat nguon dung san) hoac env `EC_OPINION_DISABLE=id1,id2`; nguong theo doi `EC_OPINION_MIN_CRED` (mac dinh 40).

## Xu huong (stance)
Quy tac tu khoa minh bach, khong LLM (`stance.py`): NHTW -> hawkish/dovish/neutral; con lai -> bullish/bearish/neutral (EN + VN khong dau; tieu de nang trong so 2, can chenh >= 2 moi gan nhan, con lai neutral). Chu de (`lam_phat`, `lai_suat`, ...) + ma lien quan (EURUSD, XAUUSD, `VN:VNINDEX`, `US:<ticker>`...) bang tu khoa. `nlp` tiep tuc lam giau sentiment/symbols qua `news.enriched` (tin di qua cung duong `news.items`).

## Dau ra / luu tru
`news.items` (source=`expert:op:<id>`, payload `expert{expert_id,name,group,stance,topics,credibility,label,disclaimer}`) -> `news_items` + bang `expert_opinions` (migration 017, `STORAGE_EXPERT_OPINIONS=true`); `expert.profiles` -> `experts` (reputation.kind=opinion, credibility, group, bias); API `GET /v1/expert-opinions?group=&stance=&symbol=&expert_id=`, `GET /v1/experts`; expert-collector `/opinions`, `/experts`. Metric: `ec_opinion_sources{state}`, `ec_opinion_sources_by_group{group}`, `ec_opinions_published_total`.

## Quy tac diem uy tin khoi tao (prior_score x 100)
90-95 to chuc nha nuoc/lien chinh phu cong bo chinh thuc; 80-88 nghien cuu nhan vien NHTW khu vuc/to chuc nghien cuu uy tin; 65-79 ngan hang/cong ty nghien cuu thuong mai, hoc gia viet blog; 50-64 nha dau tu/blogger co tieng nhung thien lech ro/tan suat don le/tong hop; 40-49 truyen thong dai chung/tai khoan MXH chua xac minh (ket hop loc tu khoa); tru 5-15 diem neu thien lech y thuc he ro, quang ba san pham, hoac nguon cu. Duoi 40 -> khong theo doi.


## Bang nguon day du (danh muc hop nhat dung san + sources.d; 'Thu' = ket qua chay that tren VPS 2026-10-12: so bai trong 30 ngay)

<!-- sinh tu loader: {'builtin': 91, 'yaml': 234, 'dup_id': 35, 'dup_url': 46, 'overridden': 9, 'enabled': 256, 'disabled': 69, 'invalid': 0, 'files': 6} -->
| Nhom | id | Chuyen gia / to chuc (hien thi) | Loai | Diem | Poll (phut) | Thu 2026-10-12 | Thien lech / ghi chu |
|---|---|---|---|---|---|---|---|
| Ngan hang/sell-side | ing_think | ING Think (nghien cuu kinh te/FX/hang hoa) | rss | 75 | 30 | OK 10 bai | Nghien cuu sell-side cua ngan hang co ban giao dich FX/lai suat -> co the thien lech theo vi the; nhung phan t |
| Ngan hang/sell-side | vn_phs_daily | Phú Hưng (PHS) - bản tin thị trường hằng ngày | html_list | 65 | 240 | chua chay | html_list: a[href^="/trung-tam-phan-tich/ban-tin-ngay-"]; id cuối slug (/4788) + ngày trong slug dd-mm-yyyy; t |
| Ngan hang/sell-side | vn_shs_daily | SHS - bản tin thị trường ngày/tuần | html_list | 65 | 240 | chua chay | html_list: a[href^="/nhan-dinh-thi-truong/"]; text = "dd/mm/yyyy" + tiêu đề (dính liền). Redirect 1 lần sang U |
| Ngan hang/sell-side | vn_vcsc_research | Vietcap - Trung tâm phân tích (bản tin, ngành, vĩ mô, chiến lược) | html_list | 78 | 180 | chua chay | html_list: selector a[href^="/trung-tam-phan-tich/"] (bỏ ?page= và link chuyên mục). Text chứa tiêu đề + chuyê |
| Ngan hang/sell-side | vn_vdsc_daily | Rồng Việt (VDSC) - bản tin sáng hằng ngày | html_list | 72 | 240 | chua chay | html_list: a[href^="/data/api/app/file-storage/"] (PDF CÔNG KHAI, không qua /dang-nhap). Text: "09 tháng 10 -  |
| Nghien cuu NHTW/Fed khu vuc | atl_macroblog | Fed Atlanta - macroblog | rss | 86 | 120 | OK 2 bai | Blog nhan vien Fed Atlanta (tac gia GDPNow) |
| Nghien cuu NHTW/Fed khu vuc | atlantafed_gdpnow | Federal Reserve Bank of Atlanta - GDPNow | rss | 88 | 60 | OK 7 bai | Nowcast GDP My (vd 'Q3 3.6%'); tieu de chua so lieu - dung cho tin hieu macro. |
| Nghien cuu NHTW/Fed khu vuc | boc_deliberations | Ngan hang Canada - Tom tat thao luan HDQT | rss | 92 | 120 | OK 1 bai | Bien ban tom tat thao luan chinh sach (nguon goc) |
| Nghien cuu NHTW/Fed khu vuc | boc_publications | Bank of Canada - Publications | rss | 87 | 180 | OK 4 bai | Tong hop an pham. |
| Nghien cuu NHTW/Fed khu vuc | boc_research | Bank of Canada - Staff research | rss | 82 | 360 | OK 10 bai | Working papers + analytical notes. |
| Nghien cuu NHTW/Fed khu vuc | boc_san | Ngan hang Canada - Staff Analytical Papers | rss | 86 | 120 | OK 10 bai | Nghien cuu nhan vien BoC |
| Nghien cuu NHTW/Fed khu vuc | boc_staff_notes | Bank of Canada - Staff analytical notes | rss | 82 | 360 | OK 0 bai | Ghi chu phan tich. |
| Nghien cuu NHTW/Fed khu vuc | boc_wp | Ngan hang Canada - Staff Working Papers | rss | 85 | 120 | OK 6 bai | Bai nghien cuu nhan vien BoC |
| Nghien cuu NHTW/Fed khu vuc | boe_bankunderground | Bank Underground (nhan vien BoE) | rss | 85 | 120 | OK 5 bai | Blog nhan vien BoE; ghi ro khong phai quan diem BoE |
| Nghien cuu NHTW/Fed khu vuc | boe_publications | Ngan hang Anh (BoE) - An pham | rss | 90 | 60 | OK 15 bai | An pham/nghien cuu BoE |
| Nghien cuu NHTW/Fed khu vuc | boe_statistics | Bank of England - Statistics releases | rss | 80 | 240 | OK 6 bai | Thong ke dinh ky (tin hieu thap). |
| Nghien cuu NHTW/Fed khu vuc | dallas_updates | Fed Dallas - Economic Updates | rss | 86 | 60 | OK 6 bai | Cap nhat kinh te Fed Dallas (nang luong, Texas, WEI) |
| Nghien cuu NHTW/Fed khu vuc | dallasfed_headlines | Federal Reserve Bank of Dallas - Headlines | rss | 82 | 120 | OK 15 bai | Tong hop moi cua Dallas Fed (100 muc); manh ve nang luong/dau. |
| Nghien cuu NHTW/Fed khu vuc | dallasfed_releases | Federal Reserve Bank of Dallas - News releases (Texas surveys) | rss | 82 | 180 | OK 1 bai | Khao sat san xuat/dich vu Texas, Energy Survey. |
| Nghien cuu NHTW/Fed khu vuc | ecb_blog | ECB - Blog | rss | 90 | 60 | OK 5 bai | Blog nhan vien/lanh dao ECB; khong co tom tat trong feed |
| Nghien cuu NHTW/Fed khu vuc | ecb_pub | ECB - An pham nghien cuu | rss | 88 | 60 | OK 15 bai | Tong hop an pham (bao gom working papers) cua ECB |
| Nghien cuu NHTW/Fed khu vuc | ecb_rbu | ECB - Research Bulletin | rss | 88 | 120 | OK 2 bai | Ban tin nghien cuu ECB |
| Nghien cuu NHTW/Fed khu vuc | ecb_supervision_press | ECB Banking Supervision - Press & interviews | rss | 82 | 240 | OK 13 bai | Khong co summary. |
| Nghien cuu NHTW/Fed khu vuc | ecb_working_papers | European Central Bank - Working papers | rss | 80 | 360 | OK 15 bai | Working paper hoc thuat. |
| Nghien cuu NHTW/Fed khu vuc | fed_feds_notes | Fed Board - FEDS Notes | rss | 90 | 60 | OK 14 bai | Ghi chu nghien cuu nhan vien Hoi dong Fed |
| Nghien cuu NHTW/Fed khu vuc | fed_feds_papers | Fed Board - FEDS Working Papers | rss | 88 | 120 | OK 6 bai | Bai nghien cuu nhan vien Fed (hoc thuat, nhieu ky thuat) |
| Nghien cuu NHTW/Fed khu vuc | fed_ifdp | Fed Board - International Finance Discussion Papers | rss | 86 | 120 | OK 1 bai | Bai nghien cuu tai chinh quoc te cua Fed |
| Nghien cuu NHTW/Fed khu vuc | nyfed_liberty | Fed New York - Liberty Street Economics | rss | 88 | 60 | OK 11 bai | Nghien cuu nhan vien Fed NY; khong phai quan diem chinh thuc |
| Nghien cuu NHTW/Fed khu vuc | rba_bulletin | Reserve Bank of Australia - Bulletin | rss | 85 | 360 | OK 0 bai | Bai bulletin. |
| Nghien cuu NHTW/Fed khu vuc | rba_rdp | Reserve Bank of Australia - Research Discussion Papers | rss | 80 | 360 | OK 1 bai | Nghien cuu RBA. |
| Nghien cuu NHTW/Fed khu vuc | rbi_bulletin | Reserve Bank of India - Monthly Bulletin | rss | 80 | 360 | OK 10 bai | Bang so lieu bulletin. |
| Nghien cuu NHTW/Fed khu vuc | rbi_publications | Reserve Bank of India - Publications & working papers | rss | 82 | 360 | OK 10 bai | Ten feed 'ANNUAL REPORT' nhung chua WPS/an pham. |
| Nghien cuu NHTW/Fed khu vuc | sffed_blog | Fed San Francisco - Blog nghien cuu | rss | 86 | 120 | OK 1 bai | Nghien cuu nhan vien Fed SF |
| Nghien cuu NHTW/Fed khu vuc | sffed_main | Federal Reserve Bank of San Francisco | rss | 85 | 180 | OK 1 bai | Economic Letters + tin SF Fed (10 muc). Feed theo chuyen muc: 404. |
| Nghien cuu NHTW/Fed khu vuc | stl_openvault | Fed St. Louis - Open Vault | rss | 84 | 120 | OK 3 bai | Blog nhan vien Fed St. Louis (bank/credit) |
| Nghien cuu NHTW/Fed khu vuc | stl_ote | Fed St. Louis - On the Economy | rss | 86 | 60 | OK 10 bai | Blog nhan vien Fed St. Louis |
| Nghien cuu NHTW/Fed khu vuc | stl_review | Fed St. Louis - Review | rss | 88 | 120 | OK 1 bai | Tap chi nghien cuu Fed St. Louis |
| Phat bieu NHTW | bis_cbspeeches | Phat bieu cac thong doc NHTW (tong hop BIS) | rss | 92 | 30 | OK 15 bai | Tong hop phat bieu NHTW toan cau (tieu de khong luon neu ten dien gia) |
| Phat bieu NHTW | bis_mgmt_speeches | BIS - Management speeches (General Manager) | rss | 90 | 180 | OK 4 bai | Phat bieu lanh dao BIS. |
| Phat bieu NHTW | boc_mpr | Bank of Canada - Monetary Policy Report | rss | 93 | 360 | OK 0 bai | MPR hang quy; moi nhat 2026-07. |
| Phat bieu NHTW | boc_press | Bank of Canada - Press releases | rss | 93 | 30 | OK 0 bai | Quyet dinh lai suat. |
| Phat bieu NHTW | boc_speeches | Ngan hang Canada (BoC) - phat bieu | rss | 93 | 60 | OK 8 bai | Phat bieu chinh thuc BoC |
| Phat bieu NHTW | boe_news | Bank of England - News | rss | 93 | 30 | OK 15 bai | Tin chinh thuc BoE (50 muc). |
| Phat bieu NHTW | boe_speeches | Ngan hang Anh (BoE) - phat bieu | rss | 93 | 30 | OK 10 bai | Phat bieu chinh thuc MPC/BoE |
| Phat bieu NHTW | boj_whatsnew | Bank of Japan - What's new | rss | 93 | 60 | OK 15 bai | 48 muc; khong co summary (chi tieu de+link, dang RSS 1.0). |
| Phat bieu NHTW | dallas_speeches | Fed Dallas - phat bieu | rss | 90 | 60 | OK 2 bai | Phat bieu chu tich Fed Dallas (thanh vien bo phieu FOMC theo luan phien) |
| Phat bieu NHTW | ecb_press | European Central Bank - Press releases & monetary policy | rss | 95 | 30 | OK 15 bai | Feed khong co truong summary (chi tieu de+link); can lay noi dung tu trang neu can. |
| Phat bieu NHTW | fed_barr | Michael Barr (Fed) | rss | 93 | 30 | OK 2 bai | Phat bieu chinh thuc cua quan chuc NHTW; khong phai du bao thi truong |
| Phat bieu NHTW | fed_bowman | Michelle Bowman (Fed) | rss | 93 | 30 | OK 5 bai | Phat bieu chinh thuc cua quan chuc NHTW; khong phai du bao thi truong |
| Phat bieu NHTW | fed_cook | Lisa Cook (Fed) | rss | 93 | 30 | OK 2 bai | Phat bieu chinh thuc cua quan chuc NHTW; khong phai du bao thi truong |
| Phat bieu NHTW | fed_jefferson | Philip Jefferson (Fed) | rss | 93 | 30 | OK 2 bai | Phat bieu chinh thuc cua quan chuc NHTW; khong phai du bao thi truong |
| Phat bieu NHTW | fed_miran | Stephen Miran (Fed) | rss | 88 | 30 | OK 0 bai | Phat bieu chinh thuc cua quan chuc NHTW; khong phai du bao thi truong |
| Phat bieu NHTW | fed_powell | Jerome Powell (Fed) | rss | 93 | 30 | OK 0 bai | Phat bieu chinh thuc cua quan chuc NHTW; khong phai du bao thi truong |
| Phat bieu NHTW | fed_press_all | Federal Reserve Board - Press releases | rss | 93 | 30 | OK 15 bai | Thong cao chinh thuc cua Fed Board (tat ca). |
| Phat bieu NHTW | fed_press_bcreg | Federal Reserve Board - Banking & consumer regulation | rss | 85 | 120 | OK 4 bai | Quy dinh ngan hang, stress test. |
| Phat bieu NHTW | fed_press_monetary | Federal Reserve Board - Monetary policy (FOMC) | rss | 97 | 15 | OK 3 bai | FOMC statement/minutes/ky hop; nguon so cap quan trong nhat cho USD. |
| Phat bieu NHTW | fed_speeches | Federal Reserve Board - Speeches (all governors) | rss | 92 | 20 | OK 14 bai | Phat bieu cua thanh vien Board; tom tat ngan trong feed. |
| Phat bieu NHTW | fed_speeches_testimony | Fed - phat bieu va chung ngon | rss | 85 | 120 | OK 14 bai | 15 muc, moi nhat 3 ngay. |
| Phat bieu NHTW | fed_testimony | Federal Reserve Board - Congressional testimony | rss | 95 | 60 | OK 0 bai | Semiannual Monetary Policy Report, trinh bay Quoc hoi. |
| Phat bieu NHTW | fed_waller | Christopher Waller (Fed) | rss | 93 | 30 | OK 3 bai | Phat bieu chinh thuc cua quan chuc NHTW; khong phai du bao thi truong |
| Phat bieu NHTW | fed_warsh | Kevin Warsh (Fed) | rss | 93 | 30 | OK 0 bai | Phat bieu chinh thuc cua quan chuc NHTW; khong phai du bao thi truong |
| Phat bieu NHTW | hkma_speeches | Cuc Tien te Hong Kong (HKMA) - phat bieu | rss | 90 | 60 | OK 5 bai | Phat bieu chinh thuc HKMA |
| Phat bieu NHTW | rba_media | Reserve Bank of Australia - Media releases | rss | 93 | 60 | OK 1 bai | Quyet dinh lai suat; feed ~1 muc moi nhat. |
| Phat bieu NHTW | rba_smp | Reserve Bank of Australia - Statements on Monetary Policy | rss | 93 | 360 | OK 0 bai | SMP hang quy; moi nhat 2026-08. |
| Phat bieu NHTW | rba_speeches | Ngan hang Du tru Uc (RBA) - phat bieu | rss | 93 | 60 | OK 1 bai | Phat bieu chinh thuc RBA |
| Phat bieu NHTW | rbi_press | Reserve Bank of India - Press releases | rss | 90 | 120 | OK 10 bai | 10 muc; gom MPC/chinh sach. |
| Phat bieu NHTW | rbi_speeches | Reserve Bank of India - Speeches | rss | 88 | 180 | OK 10 bai | 10 muc; feed ~190 KB, khong co ngay publish chuan. robots.txt tra 'Unauthorised' nhung feed cong khai 200. |
| Phat bieu NHTW | rbnz_news | Reserve Bank of New Zealand - News releases | rss | 92 | 60 | OK 12 bai | 50 muc. URL cu /rss tra 403; dung /feeds/news (200). robots.txt tra trang loi -> khong co quy tac cam ro rang. |
| Phat bieu NHTW | riksbank_press | Sveriges Riksbank - Press releases | rss | 88 | 120 | OK 4 bai | 10 muc. |
| Phat bieu NHTW | riksbank_speeches | Sveriges Riksbank - Speeches | rss | 88 | 120 | OK 4 bai | 10 muc. |
| Phat bieu NHTW | snb_speeches | Ngan hang Quoc gia Thuy Si (SNB) - phat bieu | rss | 93 | 60 | OK 2 bai | Phat bieu chinh thuc SNB; tieu de ngan, khong co tom tat |
| Hang hoa/nang luong | cftc_cot_futures | CFTC - Cam ket cua Nha giao dich (COT, hang tuan) | json | 80 | 1440 | TAT | Du lieu vi the quy dau co/thuong mai (CSV 420 KB, HTTP 200, robots cho phep), cong bo thu Sau. Day la DU LIEU, |
| Hang hoa/nang luong | cftc_enforcement | CFTC - thi hanh | rss | 65 | 480 | TAT | 403 tu VPS (chan bot) - khong lach |
| Hang hoa/nang luong | cftc_press_releases | CFTC - thong cao | rss | 70 | 240 | TAT | 403 tu VPS (chan bot) - khong lach |
| Hang hoa/nang luong | cftc_statements | CFTC - tuyen bo | rss | 65 | 480 | TAT | 403 tu VPS (chan bot) - khong lach |
| Hang hoa/nang luong | eia_gasoline_diesel_prices | EIA - gia xang dau ban le hang tuan | rss | 80 | 360 | OK 1 bai | 1 muc/tuan (cap nhat thu Hai), moi nhat 5 ngay. |
| Hang hoa/nang luong | eia_heating_oil_propane | EIA - gia dau suoi va propane theo mua | rss | 75 | 720 | OK 1 bai | 1 muc/tuan trong mua dong; moi nhat 4 ngay. |
| Hang hoa/nang luong | eia_natgas_storage | EIA - ton kho khi tu nhien hang tuan (WNGSR) | json | 85 | 360 | TAT | JSON 7 KB HTTP 200 (robots.txt cua ir.eia.gov tra 403 -> theo ToS EIA du lieu cong cong, nhung chua co provide |
| Hang hoa/nang luong | eia_press | EIA - Thong cao/du bao | rss | 90 | 120 | OK 1 bai | Du bao nang luong chinh thuc (STEO...) |
| Hang hoa/nang luong | eia_today | EIA - Today in Energy | rss | 90 | 60 | OK 10 bai | Co quan nang luong My; phan tich nang luong hang ngay |
| Hang hoa/nang luong | farmdoc_daily | Dai hoc Illinois - farmdoc daily (kinh te nong nghiep) | rss | 65 | 480 | OK 10 bai | Hoc thuat, hoc gia xu ly WASDE, gia ngu coc; 10 muc, moi nhat 2 ngay. USDA (WASDE/Crop Progress) KHONG truy ca |
| Hang hoa/nang luong | silver_institute | Vien Bac (Silver Institute) | rss | 55 | 720 | OK 0 bai | Hiep hoi nganh bac -> thien lech tich cuc. 10 muc, moi nhat 40 ngay (it bai). |
| Hang hoa/nang luong | us_doe_news | Bo Nang luong My (DOE) | rss | 55 | 360 | OK 0 bai | Tin chinh sach (du tru dau chien luoc SPR, xuat khau LNG); nhieu tin khong lien quan thi truong -> keywords_on |
| Hang hoa/nang luong | wgc_gold_research | Hoi dong Vang The gioi (World Gold Council) - nghien cuu & tin | rss | 65 | 360 | OK 4 bai | To chuc nganh vang (do cac cong ty khai thac vang tai tro) -> THIEN LECH TICH CUC; dung lam boi canh cung/cau, |
| Crypto | a16z_crypto | a16z crypto - nghien cuu & quan diem | rss | 50 | 720 | OK 4 bai | Quy dau tu vi the lon trong crypto -> XUNG DOT LOI ICH ro (thoi phong); 30 muc, moi nhat 12 ngay. |
| Crypto | bankless | Tin & nghien cuu crypto (truyen thong chuyen nganh) | rss | 48 | 60 | OK 15 bai | Truyen thong crypto, nhieu noi dung co tai tro/qua tang; thien bullish crypto |
| Crypto | bitcoin_optech | Bitcoin Optech - ban tin ky thuat Bitcoin | rss | 50 | 1440 | OK 8 bai | Ban tin hang tuan cua nha phat trien Bitcoin (10 muc, moi nhat 3 ngay); ky thuat, khong co nhan dinh gia. |
| Crypto | chainalysis_blog | Chainalysis - phan tich chuoi khoi va an ninh | rss | 65 | 480 | OK 9 bai | 10 muc, moi nhat 3 ngay; du lieu tin cay nhung la hang ban san pham tuan thu. |
| Crypto | coindesk | Tin tuc va nghien cuu crypto (truyen thong chuyen nganh) | rss | 55 | 60 | OK 15 bai | Truyen thong crypto lon; tin la chinh, khong phai y kien chuyen gia; tom tat rong |
| Crypto | coinmetrics | Coin Metrics (nghien cuu on-chain) | rss | 72 | 240 | OK 4 bai | Nha cung cap du lieu on-chain; bao cao du lieu; ra thuong mai du lieu |
| Crypto | ethereum_foundation_blog | Ethereum Foundation - blog giao thuc | rss | 50 | 720 | OK 3 bai | Thong bao ky thuat/nang cap (feed 642 muc, moi nhat 7 ngay); khong phai nhan dinh gia, chi la boi canh nang ca |
| Crypto | glassnode_research | Glassnode - nghien cuu on-chain | rss | 75 | 360 | TAT | KHONG DUNG: curl cho 200 nhung httpx/urllib (UA hop le) nhan 403 (Cloudflare chan bot theo TLS) -> khong vuot  |
| Crypto | sec_admin_proceedings | SEC - thu tuc hanh chinh | rss | 55 | 480 | OK 1 bai | 25 muc, moi nhat 2 ngay. |
| Crypto | sec_litigation_releases | SEC - ban cao trang khoi to dan su | rss | 60 | 360 | OK 1 bai | 25 muc, moi nhat 2 ngay; thong tin vu kien, khong phai nhan dinh thi truong. |
| Crypto | sec_press_releases | Uy ban Chung khoan My (SEC) - thong cao bao chi | rss | 70 | 120 | OK 4 bai | 25 muc, moi nhat 2 ngay. UA bat buoc co email lien he; toc do <= 10 req/s. |
| Crypto | sec_speeches_statements | SEC - phat bieu va tuyen bo cua Uy vien | rss | 70 | 240 | OK 2 bai | 25 muc, moi nhat 2 ngay (gom ca nhom cong tac crypto). |
| Crypto | sec_statements | SEC - tuyen bo cua Ban Chu tich va cac Vu | rss | 65 | 240 | OK 0 bai | 25 muc, moi nhat 2 ngay (trung lap mot phan voi speeches-statements). |
| Nha kinh te doc lap | apricitas | Joey Politano | rss | 72 | 120 | OK 1 bai | Nha kinh te du lieu; ban tin Substack; cap nhat 1-2 bai/tuan |
| Nha kinh te doc lap | delong | Brad DeLong | rss | 62 | 60 | OK 2 bai | Giao su Berkeley; viet nhieu; bai tong hop/link |
| Nha kinh te doc lap | econbrowser | Menzie Chinn & James Hamilton | rss | 78 | 120 | OK 10 bai | Hai giao su kinh te tai Wisconsin/UCSD; thien huong tu do vua phai, hoc thuat |
| Nha kinh te doc lap | employamerica | Employ America (phan tich vi mo/lao dong) | rss | 76 | 60 | OK 13 bai | Think tank nho; thien huong ung ho viec lam toi da; phan tich so lieu sat (preview CPI/NFP) |
| Nha kinh te doc lap | krugman | Paul Krugman | rss | 68 | 60 | OK 4 bai | Nobel kinh te; thien huong chinh tri ro; ban tin Substack, ban dau mien phi |
| Nha kinh te doc lap | marginalrev | Tyler Cowen & Alex Tabarrok | rss | 72 | 60 | OK 1 bai | Giao su GMU; nhieu bai link/nhan xet ngan; da chu de nen loc tu khoa |
| Nha kinh te doc lap | noahpinion | Noah Smith | rss | 65 | 60 | OK 0 bai | Nha viet/nha kinh te; quan diem ca nhan manh; nhieu chu de chinh tri |
| Nha kinh te doc lap | projectsyndicate | Cot y kien nha kinh te/cuu quan chuc quoc te | rss | 70 | 60 | OK 9 bai | Cot y kien cua nhieu tac gia (moi bai co tac gia rieng); quan diem ca nhan, thien lech tuy tac gia |
| Nha kinh te doc lap | tooze | Adam Tooze | rss | 70 | 60 | OK 10 bai | Su gia kinh te Columbia; ban tin dai, de y chinh tri-kinh te |
| Nha phan tich thi truong doc lap | alphaarchitect | Alpha Architect (nghien cuu dinh luong) | rss | 62 | 240 | OK 2 bai | Cong ty quan ly quy; nghien cuu hoc thuat dinh luong nhung gan voi san pham quy |
| Nha phan tich thi truong doc lap | awealthofcs | Ben Carlson | rss | 64 | 120 | OK 6 bai | Giam doc nghien cuu RWM; giao duc dau tu dai han |
| Nha phan tich thi truong doc lap | berkshire_letters | Berkshire Hathaway - thu gui co dong (Warren Buffett) | html_list | 85 | 1440 | TAT | Trang liet ke thu thuong nien (PDF hang nam, vd /letters/2025ltr.pdf, HTTP 200). Khong co RSS; moi nam 1 thu - |
| Nha phan tich thi truong doc lap | bridgewater_insights | Bridgewater Associates - nghien cuu & nhan dinh | rss | 70 | 720 | OK 1 bai | Quy phong ho lon nhat the gioi; it bai (3 muc, moi nhat 17 ngay). Lap truong vi mo dai han, co lien quan loi i |
| Nha phan tich thi truong doc lap | capitalspectator | James Picerno | rss | 62 | 120 | OK 9 bai | Nha phan tich da tai san; blog ca nhan |
| Nha phan tich thi truong doc lap | damodaran | Aswath Damodaran | rss | 85 | 240 | OK 1 bai | Giao su dinh gia NYU; phuong phap minh bach, tan suat thap |
| Nha phan tich thi truong doc lap | lynalden | Lyn Alden | rss | 66 | 240 | OK 0 bai | Nha chien luoc vi mo/Bitcoin; thien huong thich tai san cung/BTC; it bai |
| Nha phan tich thi truong doc lap | marctomarket | Marc Chandler - chien luoc gia FX | rss | 72 | 60 | OK 15 bai | Chien luoc gia FX lau nam (tung o ngan hang); phan tich tuan/ngay cong khai; xu huong USD, khong tiet lo vi th |
| Nha phan tich thi truong doc lap | mebfaber | Meb Faber | rss | 60 | 240 | OK 2 bai | Quan ly quy; thien huong chien luoc cua quy cua ong ta |
| Nha phan tich thi truong doc lap | mish | Mike 'Mish' Shedlock | rss | 48 | 60 | OK 1 bai | Thien lech Austrian/vang, rat nhieu bai chinh tri; dung bo loc tu khoa; do tin cay thap hon |
| Nha phan tich thi truong doc lap | oaktree_memos | Howard Marks (Oaktree) - ghi nho dau tu | html_list | 85 | 1440 | TAT | Trang 200 nhung la SPA nang (970KB), khong co RSS/feed (memo-rss 404). Can html_list parser rieng -> enabled=f |
| Nha phan tich thi truong doc lap | ofdollars | Nick Maggiulli | rss | 66 | 240 | OK 2 bai | Truong du lieu Ritholtz Wealth; phan tich du lieu tai chinh ca nhan |
| Nha phan tich thi truong doc lap | ritholtz | Barry Ritholtz | rss | 66 | 60 | OK 5 bai | Quan ly tai san/binh luan; nhieu bai tong hop doc; co the thien lech san pham RWM |
| Nha phan tich thi truong doc lap | thirdpoint_letters | Third Point - thu gui nha dau tu | html_list | 65 | 1440 | TAT | Trang 200, khong co feed. Pershing Square (403, bot-block) KHONG dung. enabled=false cho toi khi co html_list  |
| Nha phan tich thi truong doc lap | vn_vinacapital_insights | VinaCapital - nhận định thị trường (EN) | rss | 70 | 720 | TAT | Feed sống (HTTP 200, 10 mục) nhưng bài mới nhất 2026-06-22 (>60 ngày) -> TẮT; bật lại nếu có bài mới. Quỹ có x |
| Nha phan tich thi truong doc lap | wolfstreet | Wolf Richter | rss | 58 | 60 | OK 7 bai | Blog doc lap; xu huong thien bearish/nghi ngo he thong; co quang cao/kham gia |
| Giao dich noi bo | house_ptr_members | Nghi si Ha vien My (bao cao giao dich PTR) | house_trades | 45 | 360 | TAT | NGUON CONG BO CHINH THUC cua Van phong Thu ky Ha vien: index XML 2026 (418 PTR, truong FilingType=P, DocID) -> |
| Giao dich noi bo | sec_form4_insiders | Nguoi trong cuoc (Form 4 - giam doc, lanh dao, co dong >10%) | form4 | 60 | 60 | OK 14 bai | Provider providers_insiders.py: doc daily-index (robots cho phep /Archives; Atom cgi-bin bi Disallow) -> goi . |
| To chuc quoc te | bea_releases | US Bureau of Economic Analysis - Releases | rss | 90 | 60 | OK 3 bai | GDP/PCE/can can thuong mai (48 muc). |
| To chuc quoc te | bis_papers | BIS - BIS Papers | rss | 88 | 360 | OK 2 bai | 25 muc. |
| To chuc quoc te | bis_press | BIS - Media releases | rss | 88 | 180 | OK 4 bai | Thong cao BIS, Basel Committee. |
| To chuc quoc te | bis_pubs | BIS - An pham nghien cuu | rss | 90 | 120 | OK 12 bai | BIS/FSI an pham, ban tin, bao cao |
| To chuc quoc te | bis_wp | BIS - Working Papers | rss | 90 | 120 | OK 4 bai | To chuc lien NHTW; bai nghien cuu hoc thuat |
| To chuc quoc te | cbo_publications | US Congressional Budget Office - Publications | rss | 88 | 240 | OK 15 bai | 30 muc; robots.txt tra thu thach JS (anti-bot) nen KHONG lach: chi lay feed cong khai, poll thua; tat neu bi c |
| To chuc quoc te | census_indicators | US Census Bureau - Economic Indicators | rss | 88 | 60 | OK 12 bai | 18 chi bao kinh te. |
| To chuc quoc te | oecd_ecoscope | OECD - ECOSCOPE (blog kinh te) | rss | 85 | 120 | OK 8 bai | Blog nha kinh te OECD; khong phai du bao chinh thuc |
| research_macro | aei | American Enterprise Institute (AEI) | rss | 60 | 360 | OK 15 bai | Think tank bao thu My; phan lon chinh sach, can loc topic kinh te; co thien kien; Thien kien chinh tri (bao th |
| research_macro | alhambra | Jeffrey Snider (Alhambra Investments) | rss | 55 | 240 | OK 5 bai | Phan tich thanh khoan/Eurodollar; quan diem heterodox; Quan ly tai san - xung dot loi ich; quan diem heterodox |
| research_macro | bond_vigilantes | Bond Vigilantes (Royal London AM) | rss | 60 | 360 | TAT | Blog trai phieu cua quan ly quy; feed hop le nhung RONG 0 muc; Feed rong -> tat |
| research_macro | calculated_risk | Bill McBride (Calculated Risk) | atom | 80 | 180 | TAT | Blog nha o/viec lam My uy tin; NHUNG feed tra du lieu cu (moi nhat 2026-01-12); Feed STALE (3 bien the deu 202 |
| research_macro | collaborative_fund | Collaborative Fund (Morgan Housel et al.) | rss | 40 | 720 | TAT | Tieu luan dau tu hanh vi; khong phai tin hieu; Quy VC - xung dot; mac dinh tat |
| research_macro | econofact | EconoFact (Tufts Fletcher School) | rss | 78 | 360 | OK 3 bai | Nha kinh te hoc thuat giai thich chinh sach/du lieu, mien phi |
| research_macro | forexcrunch | Tin tong hop forex (trang thuong mai) | rss | 50 | 60 | OK 10 bai | Tin/phan tich FX tong hop, bai ngan; Trang thuong mai quang cao; tin tong hop |
| research_macro | fxempire_news | FXEmpire (tin) | rss | 40 | 60 | TAT | Tin FX; muc moi nhat 2026-08-04 (stale); Stale -> tat |
| research_macro | hussman | John Hussman (Hussman Funds) | rss | 45 | 720 | TAT | Binh luan dinh gia co phieu cua nha quan ly quy; thien kien bear keo dai; Xung dot loi ich + bear bias; mac di |
| research_macro | investing_economy | Tin kinh te tong hop | rss | 40 | 60 | TAT | Tin kinh te tong hop (feed khong co tom tat); ToS Investing han che scrape -> chi RSS cong khai tieu de+link;  |
| research_macro | investing_indicators | Tin chi so kinh te tong hop | rss | 40 | 60 | TAT | Tin chi bao kinh te (khong summary); Nhu tren; mac dinh tat |
| research_macro | macro_musings | David Beckworth (Macro Musings podcast) | rss | 60 | 720 | TAT | Podcast kinh te tien te, khach la nha kinh te/quan chuc Fed; chi mo ta tap; Podcast; chi tieu de+mo ta; mac di |
| research_macro | mankiw | N. Gregory Mankiw (Greg Mankiw Blog) | atom | 68 | 720 | OK 0 bai | Giao su Harvard; tan suat thap, tom tat ngan |
| research_macro | naked_capitalism | Naked Capitalism (Yves Smith et al.) | rss | 45 | 240 | TAT | Tong hop link/binh luan tai chinh; quan diem chinh tri ro; Thien kien chinh tri; mac dinh tat, chi ngu canh |
| research_macro | nber | NBER Working Papers | rss | 70 | 720 | OK 15 bai | Working paper hoc thuat moi; do tre lon, khong tin hieu giao dich; Khong co ngay trong feed; chi lam ngu canh  |
| research_macro | overshoot_klein | Matthew C. Klein (The Overshoot) | rss | 80 | 240 | OK 4 bai | Vi mo toan cau/can can thanh toan; nha bao-kinh te chat luong; Mot so bai paywall |
| research_macro | piie_update | Peterson Institute for International Economics (PIIE) | rss | 82 | 180 | OK 10 bai | Think tank hang dau ve thuong mai/tien te quoc te; hoc thuat doc lap; Feed gom ca su kien sap toi (ngay tuong  |
| research_macro | rbc_econ | RBC Economics (RBC Thought Leadership) | rss | 70 | 180 | OK 4 bai | Bao cao kinh te Canada/My cua ngan hang lon, tom tat day du; Feed gom ca bai thought leadership phi kinh te; l |
| research_macro | realclearmarkets | RealClearMarkets (tong hop) | rss | 45 | 240 | TAT | Tong hop op-ed/link thi truong; khong phai tac gia goc; Aggregator/thien kien; mac dinh tat |
| research_macro | resolution_foundation | Resolution Foundation | rss | 65 | 360 | OK 8 bai | Nghien cuu thu nhap/kinh te Anh (ngu canh GBP) |
| research_macro | sahm_claudia | Claudia Sahm (Stay-At-Home Macro) | rss | 82 | 240 | OK 2 bai | Tac gia Sahm Rule, cuu nhan vien Fed; thi truong lao dong/Fed; Tan suat thap (vai bai/thang) |
| research_macro | slow_boring | Matthew Yglesias (Slow Boring) | rss | 45 | 360 | TAT | Chinh sach cong/kinh te chinh tri; lien quan thap den gia; Mac dinh tat; phan paywall |
| research_macro | standard_chartered | Standard Chartered (feed tin chung) | rss | 30 | 720 | TAT | Feed tin ngan hang chung, khong phai bao cao research; Khong phai nghien cuu -> tat |
| research_macro | tax_foundation | Tax Foundation | rss | 45 | 720 | TAT | Chinh sach thue My; lien quan thap; Mac dinh tat; feed khong co ngay chuan |
| research_macro | visual_capitalist | Visual Capitalist | rss | 35 | 720 | TAT | Infographic; khong co tin hieu giao dich; Mac dinh tat |
| research_macro | yardeni | Ed Yardeni (Yardeni Research QuickTakes) | rss | 72 | 120 | OK 15 bai | Chien luoc gia co phieu/vi mo ky cu, nhieu bieu do; ban chat advisory; Tu van tra phi; ban QuickTakes mien phi |
| Mang xa hoi (Bluesky) | bsky_adamtooze | Adam Tooze (Columbia) | bsky | 58 | 30 | OK 0 bai | Su gia kinh te; tai khoan chua xac minh (khop tieu su) |
| Mang xa hoi (Bluesky) | bsky_arindube | Arin Dube (UMass Amherst) | bsky | 52 | 30 | OK 5 bai | Giao su kinh te lao dong; tai khoan chua xac minh (khop tieu su) |
| Mang xa hoi (Bluesky) | bsky_betseystevenson | Betsey Stevenson (Univ. Michigan) | bsky | 58 | 30 | OK 0 bai | Kinh te hoc lao dong; cuu CEA; tai khoan chua xac minh (khop tieu su) |
| Mang xa hoi (Bluesky) | bsky_biancoresearch06 | Jim Bianco (Bianco Research) | bsky | 58 | 30 | OK 0 bai | Nha chien luoc vi mo/lai suat doc lap; tai khoan chua xac minh (khop tieu su) |
| Mang xa hoi (Bluesky) | bsky_byheatherlong | Heather Long (Washington Post) | bsky | 52 | 30 | OK 0 bai | Nha bao kinh te; tai khoan chua xac minh (khop tieu su) |
| Mang xa hoi (Bluesky) | bsky_conorsen | Conor Sen (Bloomberg Opinion) | bsky | 56 | 30 | OK 8 bai | Binh luan nha o/thi truong; tai khoan da xac minh |
| Mang xa hoi (Bluesky) | bsky_deanbaker13 | Dean Baker (CEPR) | bsky | 55 | 30 | OK 1 bai | Nha kinh te thien tien bo; viet nhieu; tai khoan chua xac minh (khop tieu su) |
| Mang xa hoi (Bluesky) | bsky_elerianm | Mohamed El-Erian (Wharton/Allianz) | bsky | 62 | 30 | OK 15 bai | Co van Allianz, binh luan vi mo thi truong; tai khoan da xac minh |
| Mang xa hoi (Bluesky) | bsky_ernietedeschi | Ernie Tedeschi (kinh te truong Stripe) | bsky | 58 | 30 | OK 0 bai | Cuu giam doc kinh te Nha Trang; binh luan vi mo My; tai khoan chua xac minh (khop tieu su) |
| Mang xa hoi (Bluesky) | bsky_jasonfurman | Jason Furman (Harvard) | bsky | 62 | 30 | OK 2 bai | Giao su Harvard, cuu chu tich CEA; tai khoan chua xac minh (khop tieu su) |
| Mang xa hoi (Bluesky) | bsky_josephpolitano | Joey Politano | bsky | 58 | 30 | OK 8 bai | Nha kinh te du lieu; tai khoan chua xac minh (khop tieu su) |
| Mang xa hoi (Bluesky) | bsky_justinwolfers | Justin Wolfers (Univ. Michigan) | bsky | 62 | 30 | OK 15 bai | Giao su kinh te, binh luan chinh sach; tai khoan da xac minh |
| Mang xa hoi (Bluesky) | bsky_katie0martin_ft_com | Katie Martin (Financial Times) | bsky | 55 | 30 | OK 2 bai | Nha bao thi truong tai chinh FT; tai khoan da xac minh |
| Mang xa hoi (Bluesky) | bsky_larrysummers | Larry Summers (Harvard) | bsky | 62 | 30 | OK 0 bai | Cuu Bo truong Tai chinh My; hay phat bieu ve lam phat/Fed; tai khoan chua xac minh (khop tieu su) |
| Mang xa hoi (Bluesky) | bsky_markzandi | Mark Zandi (Moody's Analytics) | bsky | 58 | 30 | OK 1 bai | Kinh te truong Moody's Analytics; thien huong du bao kinh te My; tai khoan chua xac minh (khop tieu su) |
| Mang xa hoi (Bluesky) | bsky_mchinn | Menzie Chinn (Univ. Wisconsin) | bsky | 60 | 30 | OK 5 bai | Giao su kinh te quoc te (dong tac gia Econbrowser); tai khoan chua xac minh (khop tieu su) |
| Mang xa hoi (Bluesky) | bsky_mtkonczal | Mike Konczal (Economic Security Project) | bsky | 52 | 30 | OK 4 bai | Chinh sach kinh te thien tien bo; tai khoan chua xac minh (khop tieu su) |
| Mang xa hoi (Bluesky) | bsky_nicktimiraos | Nick Timiraos (WSJ) | bsky | 56 | 30 | OK 3 bai | Phong vien trung tam ve Fed (dua tin ro rang tu nguon Fed); tai khoan chua xac minh (khop tieu su) |
| Mang xa hoi (Bluesky) | bsky_robin-j-brooks | Robin Brooks (Brookings) | bsky | 56 | 30 | OK 15 bai | Cuu kinh te truong IIF; binh luan FX/dia chinh tri; tai khoan chua xac minh (khop tieu su) |
| Mang xa hoi (Bluesky) | bsky_skandaamarnath | Skanda Amarnath (Employ America) | bsky | 60 | 30 | OK 0 bai | Giam doc dieu hanh Employ America; vi mo/lao dong; tai khoan chua xac minh (khop tieu su) |
| Mang xa hoi (Bluesky) | bsky_tracyalloway | Tracy Alloway (Bloomberg, Odd Lots) | bsky | 58 | 30 | OK 0 bai | Nha bao tai chinh; tai khoan da xac minh |
| Mang xa hoi (Bluesky) | bsky_weisenthal | Joe Weisenthal (Bloomberg, Odd Lots) | bsky | 58 | 30 | OK 0 bai | Nha bao tai chinh; tai khoan da xac minh |
| social_media | bsky_barry_ritholtz | Barry Ritholtz | bluesky | 50 | 180 | OK 3 bai | nha quan ly tai san/binh luan thi truong; verified 2026-09-18 |
| social_media | bsky_ben_casselman | Ben Casselman | bluesky | 65 | 120 | OK 10 bai | phong vien kinh te NYT, bao cao so lieu; verified 2026-10-05 |
| social_media | bsky_bloomberg_opinion | Bloomberg Opinion | bluesky | 60 | 60 | OK 15 bai | muc y kien, khong phai tin su that; verified 2026-10-11 |
| social_media | bsky_bls | U.S. Bureau of Labor Statistics | bluesky | 90 | 30 | OK 15 bai | co quan thong ke chinh thuc, thong bao NFP/CPI; verified 2026-10-09 |
| social_media | bsky_brad_delong | Brad DeLong | bluesky | 40 | 360 | TAT | su hoc kinh te, dang nhieu; verified 2026-10-09; tat vi nhieu |
| social_media | bsky_brookings | Brookings Institution | bluesky | 65 | 120 | OK 15 bai | vien nghien cuu chinh sach, domain xac thuc; verified 2026-10-08 |
| social_media | bsky_claudia_sahm | Claudia Sahm | bluesky | 72 | 60 | OK 14 bai | cuu kinh te gia Fed, tac gia Sahm Rule, thi truong lao dong; verified 2026-10-09 |
| social_media | bsky_cnbc | CNBC | bluesky | 60 | 15 | OK 15 bai | tin thi truong nhanh, nhieu tin nong/nhieu nhieu; verified 2026-10-12 |
| social_media | bsky_ecb | European Central Bank | bluesky | 90 | 30 | OK 15 bai | tai khoan chinh thuc NHTW chau Au, thong bao chinh sach; verified 2026-10-08 |
| social_media | bsky_ecb_president | Christine Lagarde (ECB President) | bluesky | 90 | 30 | OK 15 bai | chu tich ECB, tai khoan xac thuc theo domain ecb.europa.eu; verified 2026-10-09; xac thuc domain |
| social_media | bsky_economist | The Economist | bluesky | 65 | 30 | OK 15 bai | tap chi kinh te uy tin, thien phan tich dai; verified 2026-10-12 |
| social_media | bsky_ed_conway | Ed Conway | bluesky | 60 | 180 | OK 10 bai | bien tap kinh te Sky News, tac gia Material World; verified 2026-10-08 |
| social_media | bsky_federal_reserve | Federal Reserve | bluesky | 92 | 30 | OK 15 bai | tai khoan chinh thuc Fed (domain federalreserve.gov); verified 2026-10-09 |
| social_media | bsky_ft | Financial Times | bluesky | 72 | 15 | OK 15 bai | bao tai chinh hang dau; verified 2026-10-12 |
| social_media | bsky_jared_bernstein | Jared Bernstein | bluesky | 55 | 180 | OK 3 bai | cuu chu tich CEA, goc nhin chinh sach; verified 2026-10-04 |
| social_media | bsky_kansas_city_fed | Federal Reserve Bank of Kansas City | bluesky | 80 | 60 | OK 15 bai | Fed khu vuc, Jackson Hole/nghien cuu; verified 2026-10-09 |
| social_media | bsky_mark_blyth | Mark Blyth | bluesky | 40 | 360 | TAT | giao su Brown, kinh te chinh tri; verified 2026-09-17 |
| social_media | bsky_marketwatch | MarketWatch | bluesky | 50 | 30 | OK 15 bai | tin thi truong pho thong; verified 2026-10-09 |
| social_media | bsky_matt_levine | Matt Levine | bluesky | 50 | 240 | OK 15 bai | binh luan cau truc thi truong; hay ban link; verified 2026-10-08 |
| social_media | bsky_matt_yglesias | Matthew Yglesias | bluesky | 30 | 360 | TAT | binh luan chinh tri-kinh te, rat nhieu noi dung ngoai de tai; verified 2026-10-10; tat vi nhieu |
| social_media | bsky_michael_pettis | Michael Pettis | bluesky | 65 | 120 | OK 15 bai | giao su Peking, chuyen gia kinh te Trung Quoc/can can thuong mai; verified 2026-10-11 |
| social_media | bsky_nikkei_asia | Nikkei Asia | bluesky | 65 | 30 | OK 15 bai | tin kinh te chau A, JPY/CNY/ASEAN; verified 2026-10-12 |
| social_media | bsky_noah_smith | Noah Smith | bluesky | 50 | 120 | OK 15 bai | nha binh luan kinh te (Noahpinion), co chinh kien; verified 2026-10-12 |
| social_media | bsky_piie | Peterson Institute for International Economics | bluesky | 70 | 120 | OK 15 bai | vien nghien cuu thuong mai/tien te quoc te; verified 2026-10-06 |
| social_media | bsky_reuters | Reuters | bluesky | 75 | 15 | OK 15 bai | hang tin lon, tieu de + link nhanh; chi lay tieu de; verified 20/20 post 2026-10-12 |
| social_media | bsky_stlouis_fed | Federal Reserve Bank of St. Louis | bluesky | 80 | 60 | OK 15 bai | Fed khu vuc, du lieu FRED/nghien cuu; verified 2026-10-09 |
| social_media | bsky_wsj | The Wall Street Journal | bluesky | 70 | 15 | OK 15 bai | bao tai chinh hang dau; tieu de + link; verified 2026-10-12 |
| social_media | bsky_yanis_varoufakis | Yanis Varoufakis | bluesky | 30 | 360 | TAT | chinh kien manh, nhieu chinh tri; verified 2026-10-11 |
| social_media | pod_animal_spirits | Animal Spirits | podcast | 40 | 720 | OK 0 bai | binh luan thi truong/dau tu ca nhan (Compound), khong phai nghien cuu; RSS verified OK 2026-10-05 |
| social_media | pod_bloomberg_big_take | The Big Take | podcast | 58 | 240 | OK 15 bai | dieu tra chu de lon, pham vi rong khong chi thi truong; RSS verified OK 2026-10-09 |
| social_media | pod_bloomberg_businessweek | Bloomberg Businessweek | podcast | 60 | 240 | OK 15 bai | tin doanh nghiep/kinh te thuong mai, it truc tiep ve gia; RSS verified OK 2026-10-09 |
| social_media | pod_bloomberg_daybreak | Bloomberg Daybreak US | podcast | 62 | 120 | OK 15 bai | tom tat sang truoc phien My, ngan, ra deu dan; RSS verified OK 2026-10-09 |
| social_media | pod_bloomberg_surveillance | Bloomberg Surveillance | podcast | 70 | 120 | OK 15 bai | ban tin thi truong hang ngay, khach la chien luoc gia/NHTW; ep 2026-10-09; RSS verified OK; ~4740 ep, chi lay  |
| social_media | pod_boe_money_matters | Money Matters (Bank of England) | podcast | 75 | 720 | OK 2 bai | NHTW chinh thuc, tinh giao duc, ep thua; RSS verified OK 2026-09-25 |
| social_media | pod_capitalisnt | Capitalisn't | podcast | 45 | 720 | OK 3 bai | hoc gia Chicago Booth, goc nhin chinh sach/canh tranh; RSS verified OK 2026-10-08 |
| social_media | pod_chat_with_traders | Chat With Traders | podcast | 30 | 1440 | TAT | chia se trader ca nhan, tinh giai thoai nhieu hon tin hieu; RSS OK nhung ep gan nhat 2026-09-16; tat mac dinh |
| social_media | pod_conversations_with_tyler | Conversations with Tyler | podcast | 50 | 720 | OK 3 bai | phong van chuyen gia hang dau (Tyler Cowen), rong, khong chuyen thi truong; RSS verified OK 2026-09-30 |
| social_media | pod_economist_money_talks | Money Talks (The Economist) | podcast | 65 | 360 | OK 0 bai | The Economist, phan tich thi truong/chinh sach tuan; RSS verified OK 2026-10-01; feed chi 11 ep |
| social_media | pod_econtalk | EconTalk | podcast | 55 | 720 | OK 4 bai | phong van hoc gia/kinh te gia hoc thuat (Russ Roberts); RSS verified OK 2026-10-05 |
| social_media | pod_forward_guidance | Forward Guidance | podcast | 55 | 360 | OK 0 bai | macro + crypto, khach da dang, chat luong khong deu; RSS verified OK 2026-09-25 |
| social_media | pod_freakonomics | Freakonomics Radio | podcast | 35 | 720 | OK 5 bai | kinh te hoc pho thong, it lien quan thi truong; RSS verified OK 2026-10-09 |
| social_media | pod_goldman_exchanges | Exchanges at Goldman Sachs | podcast | 70 | 360 | OK 0 bai | nghien cuu chinh thuc cua GS (chu yeu chien luoc gia noi bo); RSS verified OK 2026-09-29 |
| social_media | pod_grant_williams | The Grant Williams Podcast | podcast | 45 | 720 | OK 2 bai | macro goc nhin trai chieu, khach da dang; co thien kien bi quan; RSS verified OK 2026-09-21 |
| social_media | pod_hidden_forces | Hidden Forces | podcast | 40 | 720 | OK 5 bai | phong van dai ve he thong/chinh tri kinh te; RSS verified OK 2026-10-05 |
| social_media | pod_imf | IMF Podcasts | podcast | 80 | 720 | OK 1 bai | to chuc quoc te chinh thuc (IMF), phat hanh thua nhung chuan muc; RSS verified OK 2026-09-16 |
| social_media | pod_irf | The IRF Podcast | podcast | 45 | 720 | OK 2 bai | macro/ket hop FX-rates voi nhieu khach; RSS verified OK 2026-10-09 |
| social_media | pod_jpm_making_sense | Making Sense (J.P. Morgan) | podcast | 65 | 360 | OK 4 bai | Market Matters/Making Sense cua JPM Asset Management; RSS verified OK 2026-10-02; goc la quang ba cua to chuc |
| social_media | pod_kitco | Kitco News | podcast | 55 | 240 | OK 0 bai | tin va phong van vang/kim loai quy chuyen sau; RSS verified OK 2026-10-07 |
| social_media | pod_macro_musings | Macro Musings (David Beckworth) | podcast | 65 | 360 | OK 4 bai | chinh sach tien te/Fed voi chuyen gia va cuu quan chuc; Mercatus; RSS verified OK 2026-10-05 |
| social_media | pod_macrovoices | MacroVoices | podcast | 65 | 360 | OK 5 bai | phong van tuan gioi quy macro/hang hoa/nang luong, ky luat tot; RSS verified OK 2026-10-08 |
| social_media | pod_marketplace | Marketplace | podcast | 58 | 240 | OK 15 bai | ban tin kinh te hang ngay cua dai cong; RSS verified OK; feed chi 50 ep |
| social_media | pod_merryn_talks_money | Merryn Talks Money | podcast | 55 | 360 | OK 13 bai | dau tu gia tri/dai han voi khach nha quan ly quy; RSS verified OK 2026-10-07 |
| social_media | pod_money_stuff | Money Stuff (Matt Levine) | podcast | 60 | 360 | OK 4 bai | binh luan cau truc thi truong/phap ly tai chinh; kho dung truc tiep cho tin hieu gia; RSS verified OK 2026-10- |
| social_media | pod_morgan_stanley_otm | Thoughts on the Market (Morgan Stanley) | podcast | 70 | 180 | OK 0 bai | chien luoc gia MS (Wilson, Zentner...), ep ngan, deu dan; RSS verified OK 2026-10-08 |
| social_media | pod_odd_lots | Odd Lots | podcast | 72 | 180 | OK 15 bai | Bloomberg, phong van nha kinh te/trader ky luat; ep moi 2026-10-08; RSS verified OK |
| social_media | pod_planet_money | Planet Money | podcast | 55 | 360 | OK 8 bai | giai thich kinh te dai chung, chat luong bien tap cao, tre ve thoi diem; RSS verified OK 2026-10-07 |
| social_media | pod_real_vision | Real Vision | podcast | 55 | 360 | OK 0 bai | phong van quan ly quy/macro; mot so ep mang tinh quang ba; RSS verified OK 2026-09-21 |
| social_media | pod_sprott_radio | Sprott Radio | podcast | 40 | 720 | OK 0 bai | nha quan ly quy kim loai quy/khai khoang; co loi ich ban hang; RSS verified OK 2026-09-14 |
| social_media | pod_the_indicator | The Indicator | podcast | 58 | 240 | OK 15 bai | ngan, bam sat so lieu kinh te moi; RSS verified OK 2026-10-08 |
| social_media | pod_top_traders_unplugged | Top Traders Unplugged | podcast | 50 | 720 | OK 8 bai | phong van quan ly quy/CTA, xu huong va quan tri rui ro; RSS verified OK 2026-10-07 |
| social_media | pod_wealthion | Wealthion | podcast | 35 | 720 | OK 0 bai | phong van macro/vang, khach chat luong khong deu, nhieu tu van ban dich vu; RSS verified OK 2026-10-07 |
| social_media | pod_world_bank_wh | What Have We Learned (World Bank Group) | podcast | 65 | 720 | OK 1 bai | to chuc quoc te, ban tin phat trien dai han; RSS verified OK 2026-09-21 |
| social_media | reddit_economics | Cong dong thao luan Economics | reddit | 20 | 120 | TAT | cong dong kiem duyet nhung noi dung do nguoi dung, nhieu y kien/chinh tri; chi dung lam tin hieu mo ta chu de; |
| social_media | reddit_securityanalysis | Cong dong Security Analysis | reddit | 25 | 240 | TAT | kiem duyet cao, thao luan gia tri; chat luong thap/khong on dinh; feed khong kiem duoc do 429 luc test; tat ma |
| social_media | yt_boe | Bank of England | youtube | 90 | 60 | TAT | kenh chinh thuc BoE; channel_id verified; feed 404 |
| social_media | yt_bridgewater | Bridgewater Associates | youtube | 60 | 480 | TAT | quy macro lon nhat; noi dung it va thien lich su; channel_id verified; feed 404 |
| social_media | yt_bundesbank | Deutsche Bundesbank | youtube | 80 | 120 | TAT | kenh chinh thuc Bundesbank; channel_id verified; feed 404 |
| social_media | yt_cfa_institute | CFA Institute | youtube | 50 | 480 | TAT | to chuc nghe nghiep, noi dung giao duc; channel_id verified; feed 404 |
| social_media | yt_cnbc | CNBC | youtube | 55 | 60 | TAT | kenh chinh CNBC; channel_id verified; feed 404 |
| social_media | yt_cnbc_television | CNBC Television | youtube | 60 | 60 | TAT | truyen hinh tai chinh, phong van truc tiep; channel_id verified; feed 404 |
| social_media | yt_damodaran | Aswath Damodaran | youtube | 75 | 720 | TAT | giao su dinh gia NYU Stern, bai giang dinh gia; channel_id verified; feed 404 |
| social_media | yt_ecb | European Central Bank | youtube | 90 | 60 | TAT | kenh chinh thuc ECB (hop bao chi, phat bieu); channel_id verified; feed 404 |
| social_media | yt_economist | The Economist | youtube | 65 | 240 | TAT | tap chi kinh te; channel_id verified; feed 404 |
| social_media | yt_federal_reserve | Federal Reserve | youtube | 92 | 60 | TAT | kenh chinh thuc Fed (hop bao chi, phat bieu); channel_id verified tu trang kenh; feed 404 2026-10-12 |
| social_media | yt_forward_guidance | Forward Guidance | youtube | 50 | 240 | TAT | macro + crypto; channel_id verified; feed 404 |
| social_media | yt_ft | Financial Times | youtube | 70 | 120 | TAT | bao tai chinh hang dau; channel_id verified; feed 404 |
| social_media | yt_george_gammon | George Gammon | youtube | 30 | 720 | TAT | goc nhin bi quan, thien kien chu quan; channel_id verified; feed 404 |
| social_media | yt_hnx | So Giao dich Chung khoan Ha Noi (HNX) | youtube | 70 | 240 | TAT | san niem yet chinh thuc; channel_id tu trang kenh; feed 404; xac nhan |
| social_media | yt_hose | So Giao dich Chung khoan TP.HCM (HOSE) | youtube | 70 | 240 | TAT | san niem yet chinh thuc; channel_id tu trang kenh; feed 404; xac nhan |
| social_media | yt_imf | IMF | youtube | 80 | 120 | TAT | kenh tin tuc chinh thuc IMF; channel_id verified; feed 404 |
| social_media | yt_kbsv | KB Securities Vietnam | youtube | 55 | 240 | TAT | CTCK KBSV; channel_id tu trang kenh; feed 404; xac nhan |
| social_media | yt_kis_vn | KIS Vietnam | youtube | 55 | 240 | TAT | CTCK KIS Viet Nam; channel_id tu trang kenh; feed 404; xac nhan |
| social_media | yt_kitco | Kitco News | youtube | 55 | 120 | TAT | tin va phong van vang; channel_id verified; feed 404 |
| social_media | yt_macro_compass | The Macro Compass | youtube | 55 | 240 | TAT | Alfonso Peccatiello, macro/thanh khoan, co thu phi; channel_id verified; feed 404 |
| social_media | yt_oecd | OECD | youtube | 70 | 240 | TAT | kenh chinh thuc OECD; channel_id verified; feed 404 |
| social_media | yt_patrick_boyle | Patrick Boyle | youtube | 60 | 480 | TAT | cuu quan ly quy, binh luan tai chinh co can nhac; channel_id verified; feed 404 |
| social_media | yt_peterson_institute | Peterson Institute for International Economics | youtube | 65 | 240 | TAT | vien nghien cuu, hoi thao; channel_id verified; feed 404 |
| social_media | yt_plain_bagel | The Plain Bagel | youtube | 50 | 720 | TAT | giai thich tai chinh, khong phai tin hieu; channel_id verified; feed 404 |
| social_media | yt_rba | Reserve Bank of Australia | youtube | 80 | 120 | TAT | kenh chinh thuc RBA; channel_id verified; feed 404 |
| social_media | yt_real_vision | Real Vision | youtube | 55 | 120 | TAT | phong van macro/dau tu, chat luong khong deu; channel_id verified; feed 404 |
| social_media | yt_reuters | Reuters | youtube | 70 | 60 | TAT | hang tin lon; channel_id verified; feed 404; chi tieu de+link |
| social_media | yt_snb | Swiss National Bank | youtube | 80 | 120 | TAT | kenh chinh thuc SNB; channel_id verified; feed 404 |
| social_media | yt_stlouis_fed | Federal Reserve Bank of St. Louis | youtube | 75 | 240 | TAT | Fed khu vuc, giao duc/nghien cuu; channel_id verified; feed 404 |
| social_media | yt_vietcap | Chung khoan Vietcap | youtube | 60 | 240 | TAT | CTCK Vietcap (VCI), nghien cuu uy tin; channel_id tu trang kenh; feed 404; xac nhan |
| social_media | yt_vndirect | VNDIRECT | youtube | 55 | 240 | TAT | CTCK, bao cao/nhan dinh; co loi ich moi gioi; channel_id tu trang kenh; feed 404 |
| social_media | yt_vneconomy | Kenh video kinh te VN | youtube | 60 | 120 | TAT | bao kinh te Viet Nam; channel_id tu trang kenh; feed 404 |
| social_media | yt_vtv24 | VTV24 | youtube | 60 | 60 | TAT | kenh tin tuc cua dai truyen hinh quoc gia; channel_id tu trang kenh; feed 404; xac nhan danh tinh |
| social_media | yt_vtv_finance | VTV Tai chinh | youtube | 60 | 120 | TAT | kenh tai chinh VTV; channel_id tu trang kenh; feed 404; xac nhan |
| social_media | yt_wealthion | Wealthion | youtube | 35 | 480 | TAT | chat luong khach khong deu; channel_id verified; feed 404 |
| social_media | yt_world_bank | World Bank Group | youtube | 70 | 240 | TAT | kenh chinh thuc World Bank; channel_id verified; feed 404 |
| social_media | yt_wsj | The Wall Street Journal | youtube | 65 | 120 | TAT | bao tai chinh; channel_id verified; feed 404 |
| Think tank | bruegel | Bruegel (think tank kinh te chau Au) | rss | 80 | 120 | OK 0 bai | Think tank chau Au; nghiep vu chinh sach; cap nhat thua |
| Think tank | voxeu | CEPR - VoxEU (cot nha kinh te hoc) | rss | 82 | 60 | OK 15 bai | Cot cua hoc gia; quan diem tung tac gia, dang bai cong khai |
| Viet Nam | vn_cf_banking | Tài chính - ngân hàng (chính sách NHNN, lãi suất) | rss | 55 | 60 | OK 15 bai | 50 mục, mới 10-12; nhiều tin NHNN. |
| Viet Nam | vn_cf_intl_finance | Tài chính quốc tế | rss | 48 | 90 | OK 15 bai | 50 mục, mới 10-12. |
| Viet Nam | vn_cf_macro | Kinh tế vĩ mô & đầu tư | rss | 52 | 60 | OK 15 bai | 50 mục, mới 10-12. |
| Viet Nam | vn_cf_stock_market | Chuyên gia chứng khoán - tin & nhận định thị trường | rss | 50 | 30 | OK 15 bai | 50 mục, mới 10-12. Nhiều tin nhanh; trích chuyên gia khi có. |
| Viet Nam | vn_ct_energy | Năng lượng (cơ quan ngôn luận Bộ Công Thương) | rss | 58 | 180 | OK 15 bai | 25 mục, feed build 10-09. |
| Viet Nam | vn_ct_finance | Tài chính (cơ quan ngôn luận Bộ Công Thương) | rss | 58 | 120 | OK 15 bai | 25 mục, feed build 10-09. |
| Viet Nam | vn_dt_business | Kinh doanh (báo Dân trí) | rss | 48 | 60 | OK 13 bai | 100 mục, mới 10-12. |
| Viet Nam | vn_gov_economy | Chính phủ Việt Nam - chuyên mục Kinh tế | rss | 75 | 60 | OK 15 bai | 50 mục, mới 10-12. Cùng định dạng ngày M/D/Y. |
| Viet Nam | vn_gov_policy | Chính phủ Việt Nam - Chính sách mới | rss | 75 | 90 | OK 15 bai | 50 mục. Thông cáo / chính sách. Cùng định dạng ngày. |
| Viet Nam | vn_gov_stock | Chính phủ Việt Nam - chuyên mục Chứng khoán | rss | 75 | 60 | OK 15 bai | Báo Chính phủ. 50 mục. pubDate "10/8/2026 5:21:00 PM" dạng M/D/Y 12h (loader tự parse). |
| Viet Nam | vn_nd_economy | Kinh tế (báo cơ quan Đảng) | rss | 62 | 90 | OK 15 bai | 50 mục, mới 10-12. |
| Viet Nam | vn_nd_stock | Tài chính - chứng khoán (báo cơ quan Đảng) | rss | 62 | 90 | OK 15 bai | 50 mục, mới 10-12. |
| Viet Nam | vn_ndh_finance | Tài chính - chứng khoán - doanh nghiệp (tạp chí) | rss | 50 | 180 | OK 10 bai | 10 mục/feed, mới 10-02 (tần suất thấp). WordPress. |
| Viet Nam | vn_nso_news | Cục Thống kê (Bộ Tài chính) - thông cáo số liệu | rss | 85 | 120 | OK 10 bai | WordPress, 10 mục, mới 10-12. Số liệu GDP/CPI/XNK chính thức. |
| Viet Nam | vn_nso_stats_news | Cục Thống kê (Bộ Tài chính) - tin tức thống kê | rss | 85 | 180 | OK 4 bai | 10 mục, mới 10-12. Trùng một phần feed chính. |
| Viet Nam | vn_tn_banking | Ngân hàng (báo Thanh Niên) | rss | 50 | 90 | OK 15 bai | 50 mục, mới 10-12; hay đưa giá vàng. Entity HTML trong tiêu đề. |
| Viet Nam | vn_tn_stock | Chứng khoán (báo Thanh Niên) | rss | 50 | 90 | OK 15 bai | 50 mục, mới 10-10. Tiêu đề có entity HTML (&aacute;) -> unescape. |
| Viet Nam | vn_tp_economy | Kinh tế (báo Tiền Phong) | rss | 48 | 90 | OK 15 bai | 50 mục, mới 10-12. |
| Viet Nam | vn_tp_stock | Tài chính - ngân hàng - chứng khoán (báo Tiền Phong) | rss | 48 | 90 | OK 15 bai | 50 mục, mới 10-12. |
| Viet Nam | vn_tt_business | Kinh doanh (báo Tuổi Trẻ) | rss | 52 | 60 | OK 10 bai | 50 mục. pubDate dạng "10/12/2026 9:20:00 AM" (feedparser KHÔNG parse -> loader tự parse M/D/Y). |
| Viet Nam | vn_ve_banking | Ngân hàng - tiền tệ (tạp chí kinh tế) | rss | 58 | 120 | OK 15 bai | 50 mục, mới 10-08. |
| Viet Nam | vn_ve_finance | Tài chính - tiền tệ (tạp chí kinh tế) | rss | 60 | 60 | OK 15 bai | 50 mục, mới 10-12. |
| Viet Nam | vn_ve_world | Kinh tế thế giới (tạp chí kinh tế) | rss | 55 | 90 | OK 15 bai | 50 mục, mới 10-12. |
| Viet Nam | vn_vir_business | Vietnam Investment Review - kinh doanh (EN) | rss | 55 | 90 | OK 15 bai | 25 mục, mới 10-12; tiếng Anh. |
| Viet Nam | vn_vne_business | Kinh doanh - chứng khoán, vĩ mô (báo online) | rss | 55 | 60 | OK 15 bai | 60 mục, mới 10-12. Chuyên mục chung -> keywords_only. |
| Viet Nam | vn_vnn_business | Kinh doanh (báo VietnamNet) | rss | 48 | 60 | OK 9 bai | 1000 mục (rất lớn) -> chỉ lấy 50 mới nhất. Chuyên mục chung -> keywords_only. |
| Viet Nam | vn_vnp_economy | Kinh tế (thông tấn xã Việt Nam) | rss | 68 | 60 | OK 15 bai | 50 mục. Server trả gzip dù không xin (không khai báo Content-Encoding) -> giải nén nếu bytes bắt đầu 1f8b. |
| Viet Nam | vn_vnp_stock | Chứng khoán (thông tấn xã Việt Nam) | rss | 68 | 90 | OK 15 bai | 50 mục. Cùng lưu ý gzip. Nguồn tin nhà nước. |
| Viet Nam | vn_vov_economy | Kinh tế (đài tiếng nói quốc gia) | rss | 60 | 90 | OK 15 bai | 30 mục, mới 10-12. |
| Viet Nam | vn_vs_bond | Thị trường trái phiếu Việt Nam | rss | 60 | 120 | OK 15 bai | Đấu thầu TPCP / trái phiếu DN (20 mục, mới 10-12). |
| Viet Nam | vn_vs_fuel | Giá dầu & nhiên liệu | rss | 55 | 120 | OK 15 bai | Dầu Brent / xăng dầu (20 mục, mới 10-12). |
| Viet Nam | vn_vs_gold | Thị trường vàng & kim loại quý trong nước | rss | 55 | 120 | OK 15 bai | Giá vàng SJC / thế giới (20 mục, mới 10-10). |
| Viet Nam | vn_vs_hot_stocks | Cổ phiếu nóng trong tuần - góc nhìn kỹ thuật VN | rss | 52 | 120 | OK 15 bai | Danh mục cổ phiếu đáng chú ý (20 mục, mới 10-12). |
| Viet Nam | vn_vs_intl_finance | Tài chính quốc tế (USD, Fed, thị trường toàn cầu) | rss | 55 | 90 | OK 15 bai | USD/Fed/ngoại hối (20 mục, mới 10-10). |
| Viet Nam | vn_vs_macro | Kinh tế vĩ mô Việt Nam | rss | 58 | 90 | OK 15 bai | Tin/nhận định vĩ mô (20 mục, mới 10-12). |
| Viet Nam | vn_vs_world_stocks | Chứng khoán thế giới (tổng kết phiên) | rss | 52 | 120 | OK 15 bai | Tin chứng khoán Mỹ/châu Á (20 mục, mới 10-11). |
| Viet Nam | vn_vtv_economy | Kinh tế (đài truyền hình quốc gia) | rss | 60 | 60 | OK 9 bai | 500 mục (lớn), pubDate TZ "+07" (feedparser không parse). Chỉ lấy 50 mới nhất. |
| Viet Nam | vneco_ck | Nhan dinh chung khoan (bao kinh te) | rss | 55 | 30 | OK 15 bai | Bao kinh te; tin + nhan dinh tron lan; dung bo loc tu khoa |
| Viet Nam | vs_nhandinh | Nhan dinh thi truong chung khoan hang ngay | rss | 60 | 30 | OK 15 bai | Nhan dinh hang ngay (phan lon do bien tap vien/CTCK); co the thien lech lac quan |
| Viet Nam | vs_ptcb | Phan tich co ban doanh nghiep | rss | 60 | 60 | OK 2 bai | Phan tich co ban doanh nghiep (nhieu bai tu CTCK); xung dot loi ich sell-side |
| Viet Nam | vs_ptkt | Phan tich ky thuat co phieu/chi so | rss | 58 | 30 | OK 15 bai | Phan tich ky thuat co phieu/chi so; tac gia/CTCK da dang |
| Viet Nam | vs_ykien | Y kien chuyen gia chung khoan (tong hop) | rss | 62 | 30 | OK 15 bai | Muc tong hop y kien cua chuyen gia/CTCK dang tren bao |

## Nguon da thu va KHONG dung (tong hop 2026-10-12; chi tiet: `docs/sources/*.md`)
| Nguon | Ket qua | Ly do (khong lach) |
|---|---|---|
| YouTube (kenh Fed/ECB/IMF/Real Vision/... 37 kenh) | feed `/feeds/videos.xml` co the 200 nhung robots.txt YouTube CHAN `/feeds/` voi UA cua he thong | Ton trong robots -> `enabled: false` (PoliteClient se RobotsDenied) |
| TradingView ideas | RSS 200 | ToS cam thu thap tu dong va dung phi hien thi |
| MQL5 Signals, Myfxbook, OANDA/IG/FXCM sentiment, eToro, ZuluTrade, cTrader Copy, Darwinex | 403 / can tai khoan-khoa / khong API cong khai / HTML khong co feed | Can dang nhap hoac ToS khong cho phep; khong tu dang ky tai khoan. (`mql5`, `myfxbook` cu van TAT mac dinh) |
| IMF, OECD (chinh), World Bank blogs, Treasury, Kansas/Cleveland/Richmond/Philly/Minneapolis Fed, Norges Bank, Bundesbank (theo chuyen muc) | 403 / 404 / HTML / timeout | Chan bot hoac khong co feed cong khai |
| Goldman, JPM, Morgan Stanley, Wells Fargo, UBS, BNP, Commerzbank, Nordea, Danske, SEB, Rabobank (403), ABN AMRO, BlackRock BII, Vanguard, PIMCO, Allianz... | 403/404/HTML (JS) | Khong co RSS cong khai dung duoc. Chi ING + RBC Economics co feed |
| Glassnode (403), Messari (404), Kitco (404), OPEC (403), Investing.com (ToS), DailyFX (403), FT Alphaville (tra phi), Zero Hedge (do tin cay thap) | | Chan bot / ToS / do tin cay |
| CFTC press/enforcement/statements RSS | 403 tu VPS | Chan bot -> TAT (`zz_overrides.yaml`) |
| SEC Atom "latest filings" (`/cgi-bin/browse-edgar`) | 200 | robots.txt SEC co `Disallow: /cgi-bin` (nhom sau dong trong bi `urllib.robotparser` bo sot -> da SUA PoliteClient bo dong trong khi parse). Form 4 lay qua `Archives/edgar/daily-index` (robots cho phep) |
| Senate eFD (efdsearch.senate.gov) | phai bam dong y dieu khoan/session | Khong tu dong hoa vuot buoc dong y |
| House PTR (disclosures-clerk.house.gov, 418 PTR/PDF) | 200, can doc PDF | Nguon chinh thuc hop le nhung can provider PDF; `house_ptr_members` TAT cho toi khi lam |
| 13D/13G, Berkshire/Oaktree/Third Point letters | HTML/SPA, tan suat thap | `sec13d`, `html_list` chua co provider/profile -> TAT |
| Podcast chinh tri/giai tri, Reddit (429, chat luong thap) | | Tat mac dinh |
| SSI/VNDirect/MBS/VPBankS/HSC/Yuanta/BVSC/KBSV/Mirae/FPTS/VCBS/HOSE/SBV/MOF/UBCKNN | 403/WAF/Cloudflare/dang nhap/SPA/JS | Khong lach WAF/dang nhap. Chi dung duoc: Vietcap, VDSC, PHS, SHS (trang danh sach HTML, provider `html_list`) + bao tai chinh |
| X/Twitter, Mastodon (khong co tai khoan kinh te hoat dong co RSS) | | X can khoa/ToS |

## Rui ro ToS con lai
- RSS bao thuong mai/blog: chi luu tieu de + link + tom tat <= 300 ky tu, dung ca nhan/phi thuong mai; neu mo rong cong khai/thuong mai can xin phep tung nguon.
- Bluesky: API cong khai khong xac thuc, robots `public.api.bsky.app` cho phep; chi bai CUA tai khoan, bo repost/tra loi; tai khoan khong co dau xac minh duoc ghi "khop tieu su".
- Chat luong: bai "y kien" chua duoc doi chieu ket qua; track-record (service rieng) moi la noi do hieu qua; `stance` dua tren tu khoa nen phan lon la neutral.
- Fair Economy/ForexFactory (news-collector) van la nguon ca nhan/noi bo (xem README news-collector).

---
## LICH SU kiem chung 2026-10-11 (bang cu, giu nguyen)

KIEM CHUNG THUC TE 2026-10-11 (curl/Python tu VPS <VPS_IP> voi User-Agent co email lien he; robots.txt kiem bang urllib.robotparser). Nguyen tac: khong dang nhap vuot quyen, khong vuot CAPTCHA/chong bot (gap 403/Cloudflare = DUNG, khong lach), ton trong robots.txt (PoliteClient mac dinh), rate limit + cache. Moi du lieu CHI de tham khao, KHONG phai khuyen nghi dau tu.

## Bang ket qua da thu (2026-10-11)

| Nguon | Da thu | Ket qua | ToS / rui ro | Trang thai |
|---|---|---|---|---|
| **ActionForex "XXX/YYY Weekly Outlook"** `https://www.actionforex.com/feed/` | 200, 20 muc, robots cho phep | **DU LIEU THAT**: 8 ban tin/tuan (EURUSD, USDJPY, GBPUSD, USDCHF, AUDUSD, USDCAD, EURGBP, EURCHF) co cau "bias ... further rise/decline ... as long as N support/resistance holds" -> parser `technical_outlook` ra side + muc vo hieu hoa (sl) | RSS cong khai; trang dieu khoan khong doc duoc tu dong -> chi dung ca nhan, giu link + ten nguon, khong phan phoi lai. Rui ro THAP-TB | **BAT MAC DINH** (`default_feeds.py`, expert_id `rss:actionforex_weekly`; diem uy tin = uy tin to chuc phat hanh, khong phai thanh tich giao dich) |
| FXStreet analysis `https://www.fxstreet.com/rss/analysis` | 200, 30 muc | Bai "Weekly Forecast" nhung tieu de/tom tat khong co khuyen nghi ro (vi du "bearish route" o than bai) -> parser KHONG sinh tin hieu (da test, tranh tin hieu rac) | RSS cong khai, robots cho phep; ToS chua doc | Dung lam TIN (news-collector `fxstreet_news`), khong dung lam tin hieu chuyen gia |
| BabyPips `babypips.com/feed.rss` | 200 | Bai giao duc/recap, khong co khuyen nghi | - | Khong dung cho expert |
| investingLive/ForexLive `forexlive.com/feed` | 200, 25 muc | Tin thi truong, khong co lenh/khuyen nghi | Doi ten sang investinglive.com | Chi lam tin (news-collector) |
| Investing.com RSS | 200, 10 muc | Tin chung; ToS (8 KB) co han che khai thac du lieu | TB-CAO | KHONG dung |
| DailyFX | 403 (Access Denied) tu VPS, timeout tu may dev | Bi chan chong bot | - | KHONG (khong lach) |
| **Vietstock** nhan dinh/y kien chuyen gia/PTKT/PTCB (`vietstock.vn/145|1636|585|582/...rss`) | 200, 20 muc/feed | Bai phan tich tieng Viet that nhung KHONG co khuyen nghi MUA/BAN o tieu de (ket qua parser = 0 tin hieu; truoc khi siet parser ra rac `VN:GIA`) | RSS cong khai, robots cho phep | Chuyen sang TIN (news-collector `vietstock_*`); khong lam tin hieu |
| CafeF / VnExpress / VnEconomy / Tuoi Tre RSS | 200 | Tin tai chinh, khong phai khuyen nghi CTCK | RSS cong khai | Chi lam tin (news-collector) |
| **SSI Research** (`ssi.com.vn/khach-hang-ca-nhan/bao-cao-phan-tich`) | 403 (WAF) | Khong co RSS; bao cao la PDF sau trang bi chan | - | KHONG (khong lach WAF) |
| VNDirect (`vndirect.com.vn/category/phan-tich-bao-cao/`) | 403 | Nhu tren | - | KHONG |
| MBS (`mbs.com.vn`) | 403 | Nhu tren | - | KHONG |
| HSC, Rong Viet (VDSC), VCBS | 200 (HTML) | Khong tim thay RSS cong khai; bao cao = PDF/HTML khong co cau truc khuyen nghi on dinh | Khong co cho phep thu thap | KHONG. Muon theo doi tay -> `static_json` (nhap khuyen nghi tu bao cao cong khai) |
| **TradingView ideas** `https://www.tradingview.com/feed/` | 200, 30 muc, robots (UA thuong) khong cam /feed/ | CO RSS cong khai (y tuong cua trader, kem ten tac gia) NHUNG ToS (muc 3) cam "automated data collection... scripts, APIs, screen scraping, robots" va dung du lieu phi hien thi / algorithmic decision-making; tac gia so huu noi dung | CAO | **KHONG DUNG** theo dung nguyen tac "ToS cam thi khong" |
| CFTC COT | Socrata 200 (VPS); 403 tu may dev | 12/12 ma hop dong co du lieu tuan 2026-10-06 | Du lieu cong CFTC | Do `news-collector` phu trach (`expert_id=CFTC:<ma>`), KHONG lam o day |
| SEC 13F | data.sec.gov 200 | Parser chay voi infotable that cua Berkshire | Thap (can UA co email) | Do `news-collector` phu trach (mac dinh TAT) |
| **Myfxbook community outlook** | trang `myfxbook.com/community/outlook` 403 (Cloudflare), robots 403; endpoint `api/get-community-outlook.json` tra `{"error":true,"message":"Required fields missing."}` khi khong session | Khong co truy cap an danh hop le; API chinh thuc can dang nhap (session) bang tai khoan cua ban (free ~100 req/ngay, dung API = dong y Terms) | TRUNG BINH | KHONG bat mac dinh. `myfxbook` chi chay khi co `MYFXBOOK_EMAIL/PASSWORD` (tai khoan cua ban); chua co parser community-outlook vi khong co phan hoi that de lam fixture (khong tao tai khoan thay nguoi dung) |
| OANDA order/position book | `api-fxtrade.oanda.com/v3/instruments/EUR_USD/orderBook` 401 | Can token API (tai khoan OANDA, ke ca practice) | - | KHONG (can khoa cua ban); de Phase sau |
| IG client sentiment | trang `ig.com/en/trading-strategies/client-sentiment` 404; API can tai khoan | - | - | KHONG |
| FXCM sentiment | 403 | - | - | KHONG |
| MQL5 Signals | 200 HTML, robots cho phep, khong co RSS/API cho Signals | Selector HTML la gia dinh; Dieu khoan Signals rieng, khong cho phep ro rang thu thap tu dong | CAO | TAT mac dinh; can `EC_SOURCES` + `EC_MQL5_ACCEPT_TOS=true` + URL tu liet ke |
| FX Blue, cTrader Copy, eToro PI | Khong co API cong khai on dinh khong khoa | - | CAO | KHONG cai dat |
| Darwinex (DARWIN) | Info API can khoa | - | TB | Chua cai dat |
| `static_json` (tep tu bien soan) | - | Hop le (du lieu cua ban) | Thap | BAT (cho theo doi tay chuyen gia/CTCK VN) |

## Cau hinh mac dinh (khong can nguoi dung cau hinh)
- `EC_SOURCES` mac dinh `rss_ideas,static_json`; `EC_RSS_FEEDS` KHONG dat -> dung `src/expert_collector/default_feeds.py` (1 feed: ActionForex Weekly Outlook, mode `technical_outlook`). Dat `EC_RSS_FEEDS='[]'` de tat, hoac JSON rieng de thay the. Moi feed co the them `"mode": "ideas"|"technical_outlook"`.
- Ky vong du lieu that sau khi deploy: ~8 `expert.signals`/tuan (thu Bay/Chu nhat, ban tin cap nhat cuoi tuan); lan quan sat dau = baseline (khong alert). `sl` = muc vo hieu hoa neu van ban co ("as long as N ... holds").
- Luu y trung thuc: diem uy tin cua feed chi phan anh to chuc phat hanh ({"kind":"publisher"}), KHONG co thanh tich giao dich da kiem chung -> consumer khong nen dung de dat lenh; consensus can >= 3 chuyen gia (hien moi co 1 feed) nen se chua phat canh bao dong thuan.

## Rui ro chung
- Parser HTML (MQL5) dua tren cau truc gia dinh -> de hong khi site doi; luon fail an toan (tra rong).
- Parser `ideas` chi nhan tieu de co tu khoa ro rang; `technical_outlook` phu thuoc cau chu cua ActionForex (neu doi cach viet -> 0 tin hieu, khong sinh rac).
- Mot nguon loi/chan khong lam sap nguon khac (counter `ec_source_errors_total`).
- Chong "xoa lich su": snapshot uy tin hang ngay; so thang/so lenh giam bat thuong -> `history_wiped` 90 ngay.
- Heuristic martingale/grid can lich su lenh/vi the mo; khong thay the tham dinh.
