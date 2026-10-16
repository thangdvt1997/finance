# Nguon chuyen gia: research_macro (ngan hang / think tank / blog vi mo doc lap)

Thu that ngay 2026-10-12 tu VPS <VPS_IP> (container tam `src-rm-*`, feedparser, UA `Mozilla/5.0 (compatible; MarketMonitor/1.0)`). Cau hinh: `services/expert-collector/config/sources.d/research_macro.yaml`.

## Bang nguon

| id | To chuc / chuyen gia | URL | HTTP | So muc | Moi nhat | robots | Dung? | Ly do / luu y |
|---|---|---|---|---|---|---|---|---|
| ing_think | ING Think (ING Economics & FX Strategy) | https://think.ing.com/rss | 200 | 10 | 2026-10-09 | ok | CO | Sell-side (ING co vi the thi truong FX) - xung dot loi ich nhe |
| rbc_econ | RBC Economics (RBC Thought Leadership) | https://thoughtleadership.rbc.com/feed/ | 200 | 99 | 2026-10-02 | ok | CO | Feed gom ca bai thought leadership phi kinh te; loc topic. Sell-side |
| piie_update | Peterson Institute for International Economics (PIIE) | https://www.piie.com/rss/update.xml | 200 | 10 | 2026-11-17 (event) | ok | CO | Feed gom ca su kien sap toi (ngay tuong lai) - bo qua published > now |
| bruegel | Bruegel (think tank kinh te Chau Au) | https://www.bruegel.org/rss.xml | 200 | 10 | 2026-08-19 | ok | CO | Tan suat dang thap (vai bai/thang) |
| vox_cepr | VoxEU / CEPR | https://cepr.org/rss/vox-content | 200 | 50 | 2026-10-11 | norobots | CO | Khong co robots.txt -> coi nhu cho phep; chi lay tieu de+tom tat |
| nber | NBER Working Papers | https://www.nber.org/rss/new.xml | 200 | 45 | - | ok | CO | Khong co ngay trong feed; chi lam ngu canh nghien cuu |
| marginal_revolution | Tyler Cowen & Alex Tabarrok (Marginal Revolution) | https://marginalrevolution.com/feed | 200 | 15 | 2026-10-11 | ok | CO | Quan diem ca nhan, khong phai dinh gia |
| noahpinion | Noah Smith (Noahpinion) | https://www.noahpinion.blog/feed | 200 | 20 | 2026-10-11 | ok | CO | Substack; phan paywall chi hien doan dau |
| econbrowser | Menzie Chinn & James Hamilton (Econbrowser) | https://econbrowser.com/feed | 200 | 10 | 2026-10-09 | ok | CO | Vai bai/tuan |
| mishtalk | Mike Mish Shedlock (MishTalk) | https://mishtalk.com/feed | 200 | 10 | 2026-10-11 | ok | CO | Co thien kien ro; dung kem nguon khac |
| marc_to_market | Marc Chandler (Marc to Market) | https://www.marctomarket.com/feeds/posts/default | 200 | 25 | 2026-10-10 | ok | CO | Tac gia lam advisory/sell-side nhung blog doc lap |
| project_syndicate | Project Syndicate (op-ed kinh te) | https://www.project-syndicate.org/rss | 200 | 20 | 2026-10-09 | ok | CO | Chi tieu de+tom tat; van ban day du co the can dang ky |
| naked_capitalism | Naked Capitalism (Yves Smith et al.) | https://www.nakedcapitalism.com/feed | 200 | 10 | 2026-10-11 | ok | KHONG (tat) | Thien kien chinh tri; mac dinh tat, chi ngu canh |
| wolf_street | Wolf Richter (Wolf Street) | https://wolfstreet.com/feed/ | 200 | 10 | 2026-10-11 | ok | CO | Quan diem bear, nhung dua tren so lieu |
| employ_america | Employ America | https://www.employamerica.org/feed/ | 200 | 15 | 2026-10-09 | ok | CO | Nghien cuu viec lam/Fed/vi mo My; nhieu nha kinh te cuu Fed |
| tooze_chartbook | Adam Tooze (Chartbook) | https://adamtooze.substack.com/feed | 200 | 20 | 2026-10-11 | ok | CO | Mot so bai paywall |
| overshoot_klein | Matthew C. Klein (The Overshoot) | https://theovershoot.co/feed | 200 | 20 | 2026-10-09 | ok | CO | Mot so bai paywall |
| sahm_claudia | Claudia Sahm (Stay-At-Home Macro) | https://stayathomemacro.substack.com/feed | 200 | 20 | 2026-09-21 | ok | CO | Tan suat thap (vai bai/thang) |
| yardeni | Ed Yardeni (Yardeni Research QuickTakes) | https://yardeniquicktakes.com/feed/ | 200 | 15 | 2026-10-12 | ok | CO | Tu van tra phi; ban QuickTakes mien phi. Xung dot loi ich co the |
| apricitas | Joseph Politano (Apricitas Economics) | https://www.apricitas.io/feed | 200 | 20 | 2026-09-27 | ok | CO | Phan tich du lieu vi mo My chi tiet, minh bach nguon |
| awealth | Ben Carlson (A Wealth of Common Sense) | https://awealthofcommonsense.com/feed/ | 200 | 10 | 2026-10-11 | ok | CO | Thuoc Ritholtz Wealth Mgmt - xung dot loi ich nhe |
| delong | J. Bradford DeLong (Grasping Reality) | https://braddelong.substack.com/feed | 200 | 20 | 2026-10-09 | ok | CO | Giao su Berkeley; kinh te hoc & lich su kinh te |
| slow_boring | Matthew Yglesias (Slow Boring) | https://www.slowboring.com/feed | 200 | 20 | 2026-10-11 | ok | KHONG (tat) | Mac dinh tat; phan paywall |
| krugman | Paul Krugman (Substack) | https://paulkrugman.substack.com/feed | 200 | 20 | 2026-10-11 | ok | CO | Mot so bai paywall; quan diem co thien huong |
| mankiw | N. Gregory Mankiw (Greg Mankiw Blog) | https://gregmankiw.blogspot.com/feeds/posts/default | 200 | 25 | 2026-09-08 | ok | CO | Giao su Harvard; tan suat thap, tom tat ngan |
| ofdollars | Nick Maggiulli (Of Dollars And Data) | https://ofdollarsanddata.com/feed/ | 200 | 10 | 2026-10-06 | ok | CO | Thuoc Ritholtz - xung dot nhe |
| alpha_architect | Alpha Architect (nghien cuu dinh luong) | https://alphaarchitect.com/feed/ | 200 | 5 | 2026-10-08 | ok | CO | Quan ly quy ETF -> xung dot loi ich |
| econofact | EconoFact (Tufts Fletcher School) | https://econofact.org/feed | 200 | 10 | 2026-10-09 | ok | CO | Nha kinh te hoc thuat giai thich chinh sach/du lieu, mien phi |
| aei | American Enterprise Institute (AEI) | https://www.aei.org/feed/ | 200 | 24 | 2026-10-09 | ok | CO | Thien kien chinh tri (bao thu); nen loc tag economics |
| resolution_foundation | Resolution Foundation | https://www.resolutionfoundation.org/feed/ | 200 | 10 | 2026-10-09 | ok | CO | Nghien cuu thu nhap/kinh te Anh (ngu canh GBP) |
| alhambra | Jeffrey Snider (Alhambra Investments) | https://alhambrapartners.com/feed/ | 200 | 10 | 2026-10-12 | ok | CO | Quan ly tai san - xung dot loi ich; quan diem heterodox |
| hussman | John Hussman (Hussman Funds) | https://hussmanfunds.com/feed/ | 200 | 10 | 2026-09-17 | ok | KHONG (tat) | Xung dot loi ich + bear bias; mac dinh tat |
| forexcrunch | ForexCrunch (Forex Crunch) | https://www.forexcrunch.com/feed/ | 200 | 10 | 2026-10-11 | ok | CO | Trang thuong mai quang cao; tin tong hop |
| investing_economy | Investing.com - Economy News (RSS) | https://www.investing.com/rss/news_14.rss | 200 | 10 | 2026-10-12 | ok | KHONG (tat) | ToS Investing han che scrape -> chi RSS cong khai tieu de+link; mac dinh tat |
| investing_indicators | Investing.com - Economic Indicators News (RSS) | https://www.investing.com/rss/news_95.rss | 200 | 10 | 2026-10-09 | ok | KHONG (tat) | Nhu tren; mac dinh tat |
| realclearmarkets | RealClearMarkets (tong hop) | https://www.realclearmarkets.com/index.xml | 200 | 118 | 2026-10-10 | ok | KHONG (tat) | Aggregator/thien kien; mac dinh tat |
| visual_capitalist | Visual Capitalist | https://www.visualcapitalist.com/feed/ | 200 | 10 | 2026-10-12 | ok | KHONG (tat) | Mac dinh tat |
| tax_foundation | Tax Foundation | https://taxfoundation.org/feed/ | 200 | 20 | - | ok | KHONG (tat) | Mac dinh tat; feed khong co ngay chuan |
| standard_chartered | Standard Chartered (feed tin chung) | https://www.sc.com/en/rss/ | 200 | 10 | - | ok | KHONG (tat) | Khong phai nghien cuu -> tat |
| macro_musings | David Beckworth (Macro Musings podcast) | https://macromusings.libsyn.com/rss | 200 | 399 | 2026-10-05 | norobots | KHONG (tat) | Podcast; chi tieu de+mo ta; mac dinh tat |
| collaborative_fund | Collaborative Fund (Morgan Housel et al.) | https://collabfund.com/feed | 200 | 16 | 2026-09-17 | norobots | KHONG (tat) | Quy VC - xung dot; mac dinh tat |
| ecb_blog | ECB Blog (ngan hang trung uong) | https://www.ecb.europa.eu/rss/blog.html | 200 | 15 | 2026-10-08 | ok | KHONG (tat) | Trung nhom NHTW; tat tranh trung |
| bis_publications | BIS & FSI publications | https://www.bis.org/doclist/bis_fsi_publs.rss | 200 | 20 | 2026-10-08 | ok | KHONG (tat) | Trung nhom NHTW; tat |
| ny_fed_liberty | NY Fed - Liberty Street Economics | https://libertystreeteconomics.newyorkfed.org/feed/ | 200 | 100 | 2026-10-09 | ok | KHONG (tat) | Trung nhom NHTW; tat |
| boe_bank_underground | Bank Underground (nhan vien BoE) | https://bankunderground.co.uk/feed/ | 200 | 10 | 2026-10-08 | ok | KHONG (tat) | Trung nhom NHTW; tat |
| calculated_risk | Bill McBride (Calculated Risk) | https://www.calculatedriskblog.com/feeds/posts/default | 200 | 25 | 2026-01-12 (stale) | ok | KHONG (tat) | Feed STALE (3 bien the deu 2026-01-12) - tat cho den khi sua |
| bond_vigilantes | Bond Vigilantes (Royal London AM) | https://www.bondvigilantes.com/feed | 200 | 0 | - | ok | KHONG (tat) | Feed rong -> tat |
| fxempire_news | FXEmpire (tin) | https://www.fxempire.com/api/v1/en/articles/rss/news | 200 | 20 | 2026-08-04 (stale) | ok | KHONG (tat) | Stale -> tat |

## Tong ket
- Feed song, hop le, co noi dung: 45/48 (tren ~190 URL ung vien da thu); 3 muc cuoi la feed hop le nhung stale/rong.
- Bat mac dinh: 30; phan con lai tat vi trung nhom NHTW, thien kien, hoac khong co tin hieu.

## Ngan hang / sell-side KHONG co RSS cong khai dung duoc
Da thu va that bai (404/403/tra HTML thay vi feed): Nordea, Danske, SEB, Swedbank, Handelsbanken, Rabobank (403 chan bot), ABN AMRO, Commerzbank, DekaBank, Natixis, Credit Agricole, BNP Paribas, ANZ, NAB, Westpac IQ, ASB (403), BNZ, TD, CIBC, BMO, Scotiabank, MUFG, Wells Fargo, Goldman Sachs, JPM, Morgan Stanley, Citi, BofA, UBS, Deutsche Bank Research, PIMCO, BlackRock BII, Vanguard, Fidelity (403), Schroders, AllianceBernstein, Invesco, Amundi, Allianz. Cung khong dung duoc: DailyFX (403), Oanda, FedGuy (403), Lyn Alden (403), Brookings (tra HTML), Tim Duy/Brad Setser/Apollo (khong tim duoc feed hop le). Khong co vuot chan bot theo quy tac. Chi ING va RBC co feed ngan hang dung duoc; co the bo sung sau neu co feed chinh thuc hoac trang listing HTML (can parser rieng + doi chieu ToS).

## Da co san / trung (khong them lai)
ActionForex, FXStreet analysis, InvestingLive/ForexLive, TradingView (da co trong default_feeds/SOURCES.md).

## Luu y xung dot loi ich
- Ngan hang & quan ly quy co vi the/san pham lien quan: chi la y kien tham khao, khong phai tin hieu doc lap; `prior_score` da tru diem.
- Blog ca nhan (Mish, Hussman, Alhambra, Yardeni...) co thien kien ro; can doi chieu nhieu nguon.
- Substack co phan paywall: chi lay tieu de + doan tom tat trong feed, khong keo toan van.
- ToS: chi doc feed cong khai do chu so huu cung cap; khong luu/phat lai toan van. robots.txt: tat ca `ok` hoac khong co robots.txt (vox_cepr, macro_musings, collaborative_fund).
- Nguon thuoc nhom NHTW (ECB/BIS/NY Fed/BoE Bank Underground) de tat de tranh trung voi nhom central_bank.
