"""Danh muc CHUYEN GIA/TO CHUC uy tin co nguon cong khai hop le (RSS/Atom/API cong khai khong khoa).
KIEM CHUNG THUC TE 2026-10-12 tu VPS <VPS_IP> (HTTP 200 + robots.txt cho phep + feedparser doc duoc muc that). Chi tiet/ly do loai: SOURCES.md.

Moi muc = 1 "chuyen gia" (ten hien thi la TEN CHUYEN GIA/TO CHUC dua y kien -> hien thi nhu noi dung; KHONG ghi ten website/nha cung cap du lieu).
Truong:
  id        expert_id = "op:<id>" (on dinh, dung de tat/bat: env EC_OPINION_DISABLE=id1,id2)
  name      ten hien thi tieng Viet/Anh cua chuyen gia/to chuc
  group     nhom (cb_speech | cb_research | intl_org | bank_research | indep_macro | indep_markets | crypto | commodity | insider | vn_analysis | social)
  org_type  institution | central_bank | individual | media
  kind      rss | bsky | form4
  url       feed (rss) | handle (bsky) | atom (form4)
  lang      en | vi
  cred      DIEM UY TIN KHOI TAO 0-100 (quy tac ben duoi), chi la uy tin cua nguon ve mat to chuc/chuyen mon/do tin cay ky thuat,
            KHONG phai thanh tich du bao da kiem chung (INFO_SIGNALS_STUDY: y kien cong khai it gia tri du bao -> chi lam NGU CANH)
  bias      thien lech/xung dot loi ich can biet
  mode      cb (hawkish/dovish) | mkt (bullish/bearish)
  kw        True = chi nhan bai co tu khoa tai chinh/vi mo (nguon nhieu chu de ngoai le)
  symbols/topics  gan san; bo sung boi stance.tag_symbols/detect_topics
  every     chu ky toi thieu giua 2 lan keo (giay)

QUY TAC DIEM cred (khoi tao, minh bach):
  90-95  to chuc nha nuoc/lien chinh phu cong bo chinh thuc (NHTW, BIS) - nguon goc, khong qua trung gian
  80-88  nghien cuu nhan vien cua NHTW khu vuc / to chuc nghien cuu uy tin (Fed khu vuc, ECB, BoE, OECD, CEPR)
  65-79  ngan hang/cong ty nghien cuu thuong mai (ING) co so thich thuong mai; hoc gia/nha kinh te noi tieng viet blog ca nhan
  50-64  nha dau tu/blogger co tieng nhung thien lech y thuc he ro / tan suat don le / noi dung tong hop
  40-49  nguon dai chung/truyen thong/tai khoan MXH chua xac minh (chi bio khop); ghep voi bo loc tu khoa
  Tru 5-15 diem neu: thien lech chinh tri/y thuc he ro, quang ba san pham, hoac nguon cu/it cap nhat. Duoi 40 -> KHONG theo doi.
"""
from __future__ import annotations

USD_PAIRS = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"]


def _fed(fid: str, name: str, cred: int = 93, bias: str = "Phat bieu chinh thuc cua quan chuc NHTW; khong phai du bao thi truong") -> dict:
    return dict(id=f"fed_{fid}", name=name, group="cb_speech", org_type="central_bank", kind="rss",
                url=f"https://www.federalreserve.gov/feeds/{fid_file(fid)}.xml", lang="en", cred=cred, mode="cb", bias=bias,
                symbols=USD_PAIRS, topics=["lai_suat"], every=1800)


_FED_FILES = {"powell": "s_t_powell", "waller": "s_t_waller", "cook": "s_t_cook", "jefferson": "s_t_jefferson", "barr": "s_t_barr",
              "bowman": "m_w_Bowman", "warsh": "s_t_warsh", "miran": "s_t_miran"}


def fid_file(fid: str) -> str:
    return _FED_FILES[fid]


def _rss(id, name, group, org_type, url, cred, bias, lang="en", mode="mkt", kw=False, symbols=(), topics=(), every=3600, summary_max=300, author=False):
    return dict(id=id, name=name, group=group, org_type=org_type, kind="rss", url=url, lang=lang, cred=cred, bias=bias, mode=mode, kw=kw,
                symbols=list(symbols), topics=list(topics), every=every, summary_max=summary_max, author=author)


def _bsky(handle, name, cred, bias, verified=False):
    return dict(id="bsky_" + handle.replace(".bsky.social", "").replace(".", "_"), name=name, group="social", org_type="individual", kind="bsky",
                url=handle, lang="en", cred=cred, bias=bias + ("; tai khoan da xac minh" if verified else "; tai khoan chua xac minh (khop tieu su)"),
                mode="mkt", kw=True, symbols=[], topics=[], every=1800, summary_max=300, author=False)


CB = "cb_speech"
CBR = "cb_research"
CATALOG: list[dict] = [
    # ---- (b) Phat bieu quan chuc NHTW: tung thanh vien Hoi dong Thong doc Fed (hawkish/dovish theo tung nguoi) ----
    _fed("powell", "Jerome Powell (Fed)"),
    _fed("waller", "Christopher Waller (Fed)"),
    _fed("cook", "Lisa Cook (Fed)"),
    _fed("jefferson", "Philip Jefferson (Fed)"),
    _fed("barr", "Michael Barr (Fed)"),
    _fed("bowman", "Michelle Bowman (Fed)"),
    _fed("warsh", "Kevin Warsh (Fed)"),
    _fed("miran", "Stephen Miran (Fed)", cred=88),
    _rss("bis_cbspeeches", "Phat bieu cac thong doc NHTW (tong hop BIS)", CB, "central_bank", "https://www.bis.org/doclist/cbspeeches.rss", 92,
         "Tong hop phat bieu NHTW toan cau (tieu de khong luon neu ten dien gia)", mode="cb", every=1800, summary_max=300),
    _rss("boe_speeches", "Ngan hang Anh (BoE) - phat bieu", CB, "central_bank", "https://www.bankofengland.co.uk/rss/speeches", 93,
         "Phat bieu chinh thuc MPC/BoE", mode="cb", symbols=["GBPUSD"], topics=["lai_suat"], every=1800),
    _rss("boc_speeches", "Ngan hang Canada (BoC) - phat bieu", CB, "central_bank", "https://www.bankofcanada.ca/content_type/speeches/feed/", 93,
         "Phat bieu chinh thuc BoC", mode="cb", symbols=["USDCAD"], topics=["lai_suat"], every=3600),
    _rss("snb_speeches", "Ngan hang Quoc gia Thuy Si (SNB) - phat bieu", CB, "central_bank", "https://www.snb.ch/public/rss/en/speeches", 93,
         "Phat bieu chinh thuc SNB; tieu de ngan, khong co tom tat", mode="cb", symbols=["USDCHF"], topics=["lai_suat"], every=3600),
    _rss("rba_speeches", "Ngan hang Du tru Uc (RBA) - phat bieu", CB, "central_bank", "https://www.rba.gov.au/rss/rss-cb-speeches.xml", 93,
         "Phat bieu chinh thuc RBA", mode="cb", symbols=["AUDUSD"], topics=["lai_suat"], every=3600),
    _rss("hkma_speeches", "Cuc Tien te Hong Kong (HKMA) - phat bieu", CB, "central_bank", "https://www.hkma.gov.hk/eng/other-information/rss/rss_speeches.xml", 90,
         "Phat bieu chinh thuc HKMA", mode="cb", every=3600),
    _rss("dallas_speeches", "Fed Dallas - phat bieu", CB, "central_bank", "https://www.dallasfed.org/rss/speeches.xml", 90,
         "Phat bieu chu tich Fed Dallas (thanh vien bo phieu FOMC theo luan phien)", mode="cb", symbols=USD_PAIRS, topics=["lai_suat"], every=3600),
    # ---- (a) Nghien cuu/chien luoc cua NHTW & to chuc cong ----
    _rss("nyfed_liberty", "Fed New York - Liberty Street Economics", CBR, "central_bank", "https://libertystreeteconomics.newyorkfed.org/feed/", 88,
         "Nghien cuu nhan vien Fed NY; khong phai quan diem chinh thuc", symbols=USD_PAIRS, every=3600),
    _rss("stl_ote", "Fed St. Louis - On the Economy", CBR, "central_bank", "https://www.stlouisfed.org/rss/page-resources/publications/blog-entries", 86,
         "Blog nhan vien Fed St. Louis", symbols=USD_PAIRS, every=3600),
    _rss("stl_openvault", "Fed St. Louis - Open Vault", CBR, "central_bank", "https://www.stlouisfed.org/rss/page-resources/publications/open-vault-blog", 84,
         "Blog nhan vien Fed St. Louis (bank/credit)", every=7200),
    _rss("stl_review", "Fed St. Louis - Review", CBR, "central_bank", "https://www.stlouisfed.org/rss/page-resources/publications/review", 88,
         "Tap chi nghien cuu Fed St. Louis", every=7200),
    _rss("sffed_blog", "Fed San Francisco - Blog nghien cuu", CBR, "central_bank", "https://www.frbsf.org/research-and-insights/blog/feed/", 86,
         "Nghien cuu nhan vien Fed SF", symbols=USD_PAIRS, every=7200),
    _rss("atl_macroblog", "Fed Atlanta - macroblog", CBR, "central_bank", "https://www.atlantafed.org/rss/macroblog", 86,
         "Blog nhan vien Fed Atlanta (tac gia GDPNow)", symbols=USD_PAIRS, every=7200),
    _rss("dallas_updates", "Fed Dallas - Economic Updates", CBR, "central_bank", "https://www.dallasfed.org/rss/updates.xml", 86,
         "Cap nhat kinh te Fed Dallas (nang luong, Texas, WEI)", every=3600),
    _rss("fed_feds_notes", "Fed Board - FEDS Notes", CBR, "central_bank", "https://www.federalreserve.gov/feeds/feds_notes.xml", 90,
         "Ghi chu nghien cuu nhan vien Hoi dong Fed", symbols=USD_PAIRS, every=3600),
    _rss("fed_feds_papers", "Fed Board - FEDS Working Papers", CBR, "central_bank", "https://www.federalreserve.gov/feeds/feds.xml", 88,
         "Bai nghien cuu nhan vien Fed (hoc thuat, nhieu ky thuat)", every=7200, summary_max=300),
    _rss("fed_ifdp", "Fed Board - International Finance Discussion Papers", CBR, "central_bank", "https://www.federalreserve.gov/feeds/ifdp.xml", 86,
         "Bai nghien cuu tai chinh quoc te cua Fed", every=7200),
    _rss("ecb_blog", "ECB - Blog", CBR, "central_bank", "https://www.ecb.europa.eu/rss/blog.html", 90,
         "Blog nhan vien/lanh dao ECB; khong co tom tat trong feed", symbols=["EURUSD"], every=3600),
    _rss("ecb_pub", "ECB - An pham nghien cuu", CBR, "central_bank", "https://www.ecb.europa.eu/rss/pub.html", 88,
         "Tong hop an pham (bao gom working papers) cua ECB", symbols=["EURUSD"], every=3600),
    _rss("ecb_rbu", "ECB - Research Bulletin", CBR, "central_bank", "https://www.ecb.europa.eu/rss/rbu.html", 88,
         "Ban tin nghien cuu ECB", symbols=["EURUSD"], every=7200),
    _rss("boe_publications", "Ngan hang Anh (BoE) - An pham", CBR, "central_bank", "https://www.bankofengland.co.uk/rss/publications", 90,
         "An pham/nghien cuu BoE", symbols=["GBPUSD"], every=3600),
    _rss("boe_bankunderground", "Bank Underground (nhan vien BoE)", CBR, "central_bank", "https://bankunderground.co.uk/feed/", 85,
         "Blog nhan vien BoE; ghi ro khong phai quan diem BoE", symbols=["GBPUSD"], every=7200),
    _rss("boc_san", "Ngan hang Canada - Staff Analytical Papers", CBR, "central_bank", "https://www.bankofcanada.ca/content_type/staff-analytical-paper/feed/", 86,
         "Nghien cuu nhan vien BoC", symbols=["USDCAD"], every=7200),
    _rss("boc_wp", "Ngan hang Canada - Staff Working Papers", CBR, "central_bank", "https://www.bankofcanada.ca/content_type/working-papers/feed/", 85,
         "Bai nghien cuu nhan vien BoC", symbols=["USDCAD"], every=7200),
    _rss("boc_deliberations", "Ngan hang Canada - Tom tat thao luan HDQT", CBR, "central_bank", "https://www.bankofcanada.ca/content_type/summary-of-deliberations/feed/", 92,
         "Bien ban tom tat thao luan chinh sach (nguon goc)", mode="cb", symbols=["USDCAD"], topics=["lai_suat"], every=7200),
    _rss("bis_wp", "BIS - Working Papers", "intl_org", "institution", "https://www.bis.org/doclist/wppubls.rss", 90,
         "To chuc lien NHTW; bai nghien cuu hoc thuat", every=7200),
    _rss("bis_pubs", "BIS - An pham nghien cuu", "intl_org", "institution", "https://www.bis.org/doclist/bis_fsi_publs.rss", 90,
         "BIS/FSI an pham, ban tin, bao cao", every=7200),
    _rss("oecd_ecoscope", "OECD - ECOSCOPE (blog kinh te)", "intl_org", "institution", "https://oecdecoscope.blog/feed/", 85,
         "Blog nha kinh te OECD; khong phai du bao chinh thuc", every=7200),
    _rss("voxeu", "CEPR - VoxEU (cot nha kinh te hoc)", "think_tank", "institution", "https://cepr.org/rss/vox-content", 82,
         "Cot cua hoc gia; quan diem tung tac gia, dang bai cong khai", every=3600),
    _rss("bruegel", "Bruegel (think tank kinh te chau Au)", "think_tank", "institution", "https://www.bruegel.org/rss.xml", 80,
         "Think tank chau Au; nghiep vu chinh sach; cap nhat thua", symbols=["EURUSD"], every=7200),
    _rss("projectsyndicate", "Cot y kien nha kinh te/cuu quan chuc quoc te", "indep_macro", "media", "https://www.project-syndicate.org/rss", 70,
         "Cot y kien cua nhieu tac gia (moi bai co tac gia rieng); quan diem ca nhan, thien lech tuy tac gia", kw=True, every=3600, author=True),
    # ---- nang luong (EIA) ----
    _rss("eia_today", "EIA - Today in Energy", "commodity", "institution", "https://www.eia.gov/rss/todayinenergy.xml", 90,
         "Co quan nang luong My; phan tich nang luong hang ngay", symbols=["USOIL"], topics=["nang_luong"], every=3600),
    _rss("eia_press", "EIA - Thong cao/du bao", "commodity", "institution", "https://www.eia.gov/rss/press_rss.xml", 90,
         "Du bao nang luong chinh thuc (STEO...)", symbols=["USOIL"], topics=["nang_luong"], every=7200),
    # ---- ngan hang/to chuc nghien cuu thuong mai ----
    _rss("ing_think", "ING Think (nghien cuu kinh te/FX/hang hoa)", "bank_research", "institution", "https://think.ing.com/rss/", 75,
         "Nghien cuu sell-side cua ngan hang co ban giao dich FX/lai suat -> co the thien lech theo vi the; nhung phan tich cong khai chat luong cao", every=1800),
    # ---- (c) Nha kinh te/nha phan tich doc lap ----
    _rss("econbrowser", "Menzie Chinn & James Hamilton", "indep_macro", "individual", "https://econbrowser.com/feed", 78,
         "Hai giao su kinh te tai Wisconsin/UCSD; thien huong tu do vua phai, hoc thuat", every=7200),
    _rss("marginalrev", "Tyler Cowen & Alex Tabarrok", "indep_macro", "individual", "https://marginalrevolution.com/feed", 72,
         "Giao su GMU; nhieu bai link/nhan xet ngan; da chu de nen loc tu khoa", kw=True, every=3600),
    _rss("noahpinion", "Noah Smith", "indep_macro", "individual", "https://www.noahpinion.blog/feed", 65,
         "Nha viet/nha kinh te; quan diem ca nhan manh; nhieu chu de chinh tri", kw=True, every=3600),
    _rss("krugman", "Paul Krugman", "indep_macro", "individual", "https://paulkrugman.substack.com/feed", 68,
         "Nobel kinh te; thien huong chinh tri ro; ban tin Substack, ban dau mien phi", kw=True, every=3600),
    _rss("delong", "Brad DeLong", "indep_macro", "individual", "https://braddelong.substack.com/feed", 62,
         "Giao su Berkeley; viet nhieu; bai tong hop/link", kw=True, every=3600),
    _rss("employamerica", "Employ America (phan tich vi mo/lao dong)", "indep_macro", "institution", "https://www.employamerica.org/feed/", 76,
         "Think tank nho; thien huong ung ho viec lam toi da; phan tich so lieu sat (preview CPI/NFP)", every=3600),
    _rss("apricitas", "Joey Politano", "indep_macro", "individual", "https://www.apricitas.io/feed", 72,
         "Nha kinh te du lieu; ban tin Substack; cap nhat 1-2 bai/tuan", every=7200),
    _rss("tooze", "Adam Tooze", "indep_macro", "individual", "https://adamtooze.substack.com/feed", 70,
         "Su gia kinh te Columbia; ban tin dai, de y chinh tri-kinh te", kw=True, every=3600),
    _rss("marctomarket", "Marc Chandler - chien luoc gia FX", "indep_markets", "individual", "https://www.marctomarket.com/feeds/posts/default", 72,
         "Chien luoc gia FX lau nam (tung o ngan hang); phan tich tuan/ngay cong khai; xu huong USD, khong tiet lo vi the", symbols=USD_PAIRS, every=3600, summary_max=300),
    _rss("wolfstreet", "Wolf Richter", "indep_markets", "individual", "https://wolfstreet.com/feed/", 58,
         "Blog doc lap; xu huong thien bearish/nghi ngo he thong; co quang cao/kham gia", kw=True, every=3600),
    _rss("damodaran", "Aswath Damodaran", "indep_markets", "individual", "https://aswathdamodaran.blogspot.com/feeds/posts/default", 85,
         "Giao su dinh gia NYU; phuong phap minh bach, tan suat thap", every=14400, summary_max=300),
    _rss("capitalspectator", "James Picerno", "indep_markets", "individual", "https://capitalspectator.com/feed/", 62,
         "Nha phan tich da tai san; blog ca nhan", kw=True, every=7200),
    _rss("lynalden", "Lyn Alden", "indep_markets", "individual", "https://www.lynalden.com/feed/", 66,
         "Nha chien luoc vi mo/Bitcoin; thien huong thich tai san cung/BTC; it bai", every=14400),
    _rss("ritholtz", "Barry Ritholtz", "indep_markets", "individual", "https://ritholtz.com/feed/", 66,
         "Quan ly tai san/binh luan; nhieu bai tong hop doc; co the thien lech san pham RWM", kw=True, every=3600),
    _rss("awealthofcs", "Ben Carlson", "indep_markets", "individual", "https://awealthofcommonsense.com/feed/", 64,
         "Giam doc nghien cuu RWM; giao duc dau tu dai han", kw=True, every=7200),
    _rss("ofdollars", "Nick Maggiulli", "indep_markets", "individual", "https://ofdollarsanddata.com/feed/", 66,
         "Truong du lieu Ritholtz Wealth; phan tich du lieu tai chinh ca nhan", kw=True, every=14400),
    _rss("mebfaber", "Meb Faber", "indep_markets", "individual", "https://mebfaber.com/feed/", 60,
         "Quan ly quy; thien huong chien luoc cua quy cua ong ta", kw=True, every=14400),
    _rss("alphaarchitect", "Alpha Architect (nghien cuu dinh luong)", "indep_markets", "institution", "https://alphaarchitect.com/feed/", 62,
         "Cong ty quan ly quy; nghien cuu hoc thuat dinh luong nhung gan voi san pham quy", kw=True, every=14400),
    _rss("mish", "Mike 'Mish' Shedlock", "indep_markets", "individual", "https://mishtalk.com/feed", 48,
         "Thien lech Austrian/vang, rat nhieu bai chinh tri; dung bo loc tu khoa; do tin cay thap hon", kw=True, every=3600),
    # ---- crypto ----
    _rss("coinmetrics", "Coin Metrics (nghien cuu on-chain)", "crypto", "institution", "https://coinmetrics.substack.com/feed", 72,
         "Nha cung cap du lieu on-chain; bao cao du lieu; ra thuong mai du lieu", symbols=["BTCUSD", "ETHUSD"], topics=["tien_so"], every=14400),
    _rss("bankless", "Tin & nghien cuu crypto (truyen thong chuyen nganh)", "crypto", "media", "https://www.bankless.com/rss/feed", 48,
         "Truyen thong crypto, nhieu noi dung co tai tro/qua tang; thien bullish crypto", kw=True, symbols=["BTCUSD", "ETHUSD"], topics=["tien_so"], every=3600),
    _rss("coindesk", "Tin crypto (truyen thong chuyen nganh lon)", "crypto", "media", "https://www.coindesk.com/arc/outboundfeeds/rss/", 55,
         "Truyen thong crypto lon; tin la chinh, khong phai y kien chuyen gia; tom tat rong", symbols=["BTCUSD"], topics=["tien_so"], every=3600),
    # ---- (g) Viet Nam: muc nhan dinh/y kien chuyen gia cua bao tai chinh (chi tieu de + link + tom tat ngan) ----
    _rss("vs_ykien", "Y kien chuyen gia chung khoan (tong hop)", "vn_analysis", "media", "https://vietstock.vn/145/chung-khoan/y-kien-chuyen-gia.rss", 62,
         "Muc tong hop y kien cua chuyen gia/CTCK dang tren bao", lang="vi", symbols=["VN:VNINDEX"], every=1800),
    _rss("vs_nhandinh", "Nhan dinh thi truong chung khoan hang ngay", "vn_analysis", "media", "https://vietstock.vn/1636/nhan-dinh-phan-tich/nhan-dinh-thi-truong.rss", 60,
         "Nhan dinh hang ngay (phan lon do bien tap vien/CTCK); co the thien lech lac quan", lang="vi", symbols=["VN:VNINDEX"], every=1800),
    _rss("vs_ptkt", "Phan tich ky thuat co phieu/chi so", "vn_analysis", "media", "https://vietstock.vn/585/nhan-dinh-phan-tich/phan-tich-ky-thuat.rss", 58,
         "Phan tich ky thuat co phieu/chi so; tac gia/CTCK da dang", lang="vi", symbols=["VN:VNINDEX"], every=1800),
    _rss("vs_ptcb", "Phan tich co ban doanh nghiep", "vn_analysis", "media", "https://vietstock.vn/582/nhan-dinh-phan-tich/phan-tich-co-ban.rss", 60,
         "Phan tich co ban doanh nghiep (nhieu bai tu CTCK); xung dot loi ich sell-side", lang="vi", symbols=["VN:VNINDEX"], every=3600),
    _rss("vneco_ck", "Nhan dinh chung khoan (bao kinh te)", "vn_analysis", "media", "https://vneconomy.vn/chung-khoan.rss", 55,
         "Bao kinh te; tin + nhan dinh tron lan; dung bo loc tu khoa", lang="vi", kw=True, symbols=["VN:VNINDEX"], every=1800),
    # ---- (e) Bluesky: tai khoan chuyen gia cong khai (API doc khong xac thuc) ----
    _bsky("justinwolfers.bsky.social", "Justin Wolfers (Univ. Michigan)", 62, "Giao su kinh te, binh luan chinh sach", True),
    _bsky("elerianm.bsky.social", "Mohamed El-Erian (Wharton/Allianz)", 62, "Co van Allianz, binh luan vi mo thi truong", True),
    _bsky("tracyalloway.bsky.social", "Tracy Alloway (Bloomberg, Odd Lots)", 58, "Nha bao tai chinh", True),
    _bsky("weisenthal.bsky.social", "Joe Weisenthal (Bloomberg, Odd Lots)", 58, "Nha bao tai chinh", True),
    _bsky("conorsen.bsky.social", "Conor Sen (Bloomberg Opinion)", 56, "Binh luan nha o/thi truong", True),
    _bsky("mchinn.bsky.social", "Menzie Chinn (Univ. Wisconsin)", 60, "Giao su kinh te quoc te (dong tac gia Econbrowser)"),
    _bsky("josephpolitano.bsky.social", "Joey Politano", 58, "Nha kinh te du lieu"),
    _bsky("skandaamarnath.bsky.social", "Skanda Amarnath (Employ America)", 60, "Giam doc dieu hanh Employ America; vi mo/lao dong"),
    _bsky("ernietedeschi.bsky.social", "Ernie Tedeschi (kinh te truong Stripe)", 58, "Cuu giam doc kinh te Nha Trang; binh luan vi mo My"),
    _bsky("jasonfurman.bsky.social", "Jason Furman (Harvard)", 62, "Giao su Harvard, cuu chu tich CEA"),
    _bsky("betseystevenson.bsky.social", "Betsey Stevenson (Univ. Michigan)", 58, "Kinh te hoc lao dong; cuu CEA"),
    _bsky("adamtooze.bsky.social", "Adam Tooze (Columbia)", 58, "Su gia kinh te"),
    _bsky("deanbaker13.bsky.social", "Dean Baker (CEPR)", 55, "Nha kinh te thien tien bo; viet nhieu"),
    _bsky("byheatherlong.bsky.social", "Heather Long (Washington Post)", 52, "Nha bao kinh te"),
    _bsky("nicktimiraos.bsky.social", "Nick Timiraos (WSJ)", 56, "Phong vien trung tam ve Fed (dua tin ro rang tu nguon Fed)"),
    _bsky("larrysummers.bsky.social", "Larry Summers (Harvard)", 62, "Cuu Bo truong Tai chinh My; hay phat bieu ve lam phat/Fed"),
    _bsky("markzandi.bsky.social", "Mark Zandi (Moody's Analytics)", 58, "Kinh te truong Moody's Analytics; thien huong du bao kinh te My"),
    _bsky("biancoresearch06.bsky.social", "Jim Bianco (Bianco Research)", 58, "Nha chien luoc vi mo/lai suat doc lap"),
    _bsky("robin-j-brooks.bsky.social", "Robin Brooks (Brookings)", 56, "Cuu kinh te truong IIF; binh luan FX/dia chinh tri"),
    _bsky("mtkonczal.bsky.social", "Mike Konczal (Economic Security Project)", 52, "Chinh sach kinh te thien tien bo"),
    _bsky("arindube.bsky.social", "Arin Dube (UMass Amherst)", 52, "Giao su kinh te lao dong"),
    _bsky("katie0martin.ft.com", "Katie Martin (Financial Times)", 55, "Nha bao thi truong tai chinh FT", True),
]
