"""Ham thuan: xu huong (hawkish/dovish hoac bullish/bearish), chu de, ma lien quan va bo loc lien quan tai chinh cho Y KIEN chuyen gia.
Chi la quy tac tu khoa minh bach (khong LLM). Ket qua la NHAN THAM KHAO, khong phai khuyen nghi mua/ban."""
from __future__ import annotations

import re
import unicodedata


def fold(s: str) -> str:
    s = (s or "").replace("đ", "d").replace("Đ", "D")
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


# --- tu vung (EN + VN khong dau). Moi cum la regex tren van ban da fold ---
_HAWK = [r"rate hikes?", r"raise (?:interest )?rates?", r"tighten(?:ing)?", r"restrictive", r"higher for longer", r"upside risks? to inflation",
         r"inflation (?:remains?|is|stays?) (?:elevated|high|too high|persistent|sticky)", r"persistent inflation", r"sticky inflation",
         r"not yet appropriate to (?:cut|lower|ease)", r"further (?:rate )?increases?", r"overheating", r"inflationary pressures?",
         r"hawkish", r"balance sheet runoff", r"quantitative tightening", r"strong labou?r market",
         r"tang lai suat", r"that chat", r"lam phat (?:cao|tang)", r"ap luc lam phat"]
_DOVE = [r"rate cuts?", r"cut(?:ting)? (?:interest )?rates?", r"lower(?:ing)? (?:interest )?rates?", r"eas(?:e|ing) (?:monetary )?policy", r"accommodative",
         r"downside risks? to (?:employment|growth|the labou?r market)", r"labou?r market (?:is )?(?:softening|weakening|cooling|weak)", r"disinflation",
         r"inflation (?:has |is )?(?:eased|easing|cooling|falling|coming down|declin\w+)", r"dovish", r"quantitative easing", r"weak(?:er|ening)? (?:growth|demand)",
         r"giam lai suat", r"noi long", r"ho tro tang truong"]
_BULL = [r"bullish", r"rall(?:y|ies|ied)", r"upside", r"recovery", r"rebound", r"outperform", r"strong(?:er)? growth", r"soft landing", r"resilien\w+",
         r"all[- ]time high", r"record high", r"upgrade[sd]?", r"buy(?:ing)? opportunit\w+", r"undervalued", r"accumulat\w+",
         r"tich cuc", r"kha quan", r"hoi phuc", r"but pha", r"di len", r"tang diem", r"co hoi", r"mua rong", r"len gia"]
_BEAR = [r"bearish", r"sell[- ]?off", r"plunge[sd]?", r"slump(?:s|ed)?", r"recession", r"downside", r"downturn", r"crash", r"bubble", r"overvalued", r"downgrade[sd]?",
         r"contraction", r"default risk", r"stagflation", r"collapse", r"warning", r"risks? (?:of|to) (?:a )?(?:slowdown|recession)", r"weak(?:er|ening)? (?:outlook|economy)",
         r"tieu cuc", r"suy yeu", r"giam diem", r"ban thao", r"ban rong", r"rui ro", r"dieu chinh giam", r"suy thoai", r"lao doc", r"mat gia"]
_RX = {k: [re.compile(r"(?<![a-z0-9])" + p + r"(?![a-z0-9])") for p in v] for k, v in
       {"hawk": _HAWK, "dove": _DOVE, "bull": _BULL, "bear": _BEAR}.items()}


def _hits(text: str, key: str) -> int:
    return sum(1 for rx in _RX[key] if rx.search(text))


def classify_stance(title: str, summary: str = "", mode: str = "mkt", min_margin: int = 2) -> tuple[str, float]:
    """mode='cb' -> hawkish/dovish/neutral; mode='mkt' -> bullish/bearish/neutral. Tieu de nang trong so 2.
    Tra (nhan, diem [-1,1]); diem > 0 = hawkish/bullish. Can chenh lech >= min_margin moi dat nhan, con lai neutral."""
    t, s = fold(title), fold(summary)[:1500]
    pos_k, neg_k = ("hawk", "dove") if mode == "cb" else ("bull", "bear")
    pos = 2 * _hits(t, pos_k) + _hits(s, pos_k)
    neg = 2 * _hits(t, neg_k) + _hits(s, neg_k)
    tot = pos + neg
    if tot == 0 or abs(pos - neg) < min_margin:
        return "neutral", 0.0
    score = round((pos - neg) / (tot + 2), 2)
    if pos > neg:
        return ("hawkish" if mode == "cb" else "bullish"), score
    return ("dovish" if mode == "cb" else "bearish"), score


_TOPICS = {
    "lam_phat": [r"inflation", r"cpi", r"pce", r"prices?", r"lam phat", r"disinflation"],
    "viec_lam": [r"labou?r", r"employment", r"unemployment", r"payrolls?", r"jobs?", r"wages?", r"viec lam", r"that nghiep"],
    "tang_truong": [r"gdp", r"growth", r"recession", r"output", r"tang truong", r"suy thoai"],
    "lai_suat": [r"interest rates?", r"policy rates?", r"rate (?:hike|cut)s?", r"monetary policy", r"fomc", r"federal funds", r"lai suat", r"chinh sach tien te"],
    "trai_phieu": [r"treasur(?:y|ies)", r"bonds?", r"yields?", r"duration", r"trai phieu"],
    "ngoai_hoi": [r"fx", r"currenc(?:y|ies)", r"dollar", r"euro", r"yen", r"sterling", r"exchange rates?", r"ty gia"],
    "nang_luong": [r"oil", r"crude", r"opec", r"natural gas", r"gasoline", r"energy", r"lng", r"dau tho", r"xang dau"],
    "vang_kim_loai": [r"gold", r"silver", r"copper", r"precious metals?", r"bullion", r"vang"],
    "co_phieu": [r"equit(?:y|ies)", r"stocks?", r"s&p 500", r"nasdaq", r"earnings", r"valuations?", r"co phieu", r"chung khoan", r"vn-?index"],
    "tien_so": [r"bitcoin", r"crypto\w*", r"ethereum", r"stablecoins?", r"btc", r"eth"],
    "ngan_hang": [r"banks?", r"banking", r"credit", r"financial stability", r"ngan hang", r"tin dung"],
    "bat_dong_san": [r"housing", r"mortgage", r"real estate", r"home prices?", r"bat dong san"],
    "thuong_mai": [r"tariffs?", r"trade war", r"trade policy", r"sanctions?", r"thuong mai", r"thue quan"],
    "tai_khoa": [r"fiscal", r"deficit", r"public debt", r"budget", r"no cong"],
    "ai": [r"ai", r"artificial intelligence", r"data cent(?:er|re)s?"],
}
_TOPIC_RX = {k: re.compile(r"(?<![a-z0-9])(?:" + "|".join(v) + r")(?![a-z0-9])") for k, v in _TOPICS.items()}


def detect_topics(title: str, summary: str = "", default: tuple[str, ...] | list[str] = (), limit: int = 4) -> list[str]:
    t, s = fold(title), fold(summary)[:1500]
    scored = []
    for k, rx in _TOPIC_RX.items():
        n = 3 * len(rx.findall(t)) + len(rx.findall(s))
        if n:
            scored.append((n, k))
    scored.sort(reverse=True)
    out = list(dict.fromkeys([*default, *[k for _, k in scored]]))
    return out[:limit]


_REL = re.compile(r"(?<![a-z0-9])(?:fed|fomc|inflation|cpi|pce|rates?|yields?|treasur\w+|gdp|jobs?|payrolls?|unemployment|recession|tariffs?|dollar|euro|yen|"
                  r"gold|oil|stocks?|equit\w+|s&p|nasdaq|markets?|bonds?|credit|bitcoin|crypto\w*|ecb|boj|boe|economy|economic|economists?|growth|labou?r|wages?|"
                  r"housing|deficit|debt|earnings|monetary|fiscal|currenc\w+|banks?|banking|trade|commodit\w+|volatility|liquidity|"
                  r"lai suat|chung khoan|vn-?index|ty gia|lam phat|co phieu|ngan hang|trai phieu|vang|dau tho|kinh te|tang truong|vi mo)(?![a-z0-9])")


def is_finance_relevant(text: str, min_hits: int = 1) -> bool:
    return len(_REL.findall(fold(text))) >= min_hits


_SYM_RULES: list[tuple[list[str], list[str]]] = [
    ([r"eur/?usd", r"eurusd", r"ecb", r"lagarde", r"euro area", r"eurozone"], ["EURUSD"]),
    ([r"gbp/?usd", r"gbpusd", r"sterling", r"bank of england", r"boe"], ["GBPUSD"]),
    ([r"usd/?jpy", r"usdjpy", r"yen", r"bank of japan", r"boj"], ["USDJPY"]),
    ([r"aud/?usd", r"audusd", r"reserve bank of australia", r"rba"], ["AUDUSD"]),
    ([r"usd/?cad", r"usdcad", r"bank of canada", r"loonie"], ["USDCAD"]),
    ([r"usd/?chf", r"usdchf", r"swiss franc", r"snb"], ["USDCHF"]),
    ([r"gold", r"xau", r"bullion", r"vang"], ["XAUUSD"]),
    ([r"silver", r"xagusd"], ["XAGUSD"]),
    ([r"crude", r"wti", r"brent", r"opec", r"oil", r"dau tho"], ["USOIL"]),
    ([r"bitcoin", r"btc"], ["BTCUSD"]),
    ([r"ethereum", r"eth"], ["ETHUSD"]),
    ([r"s&p ?500", r"wall street", r"nasdaq", r"dow jones"], ["US:SPX"]),
    ([r"vn-?index", r"vnindex", r"hose", r"hnx", r"chung khoan"], ["VN:VNINDEX"]),
    ([r"federal reserve", r"fomc", r"fed", r"powell", r"treasury yields?", r"nonfarm", r"payrolls"], ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"]),
]
_SYM_RX = [(re.compile(r"(?<![a-z0-9])(?:" + "|".join(p) + r")(?![a-z0-9])"), s) for p, s in _SYM_RULES]


def tag_symbols(text: str, default: list[str] | tuple[str, ...] = (), limit: int = 6) -> list[str]:
    f = fold(text)
    out = list(dict.fromkeys(default))
    for rx, syms in _SYM_RX:
        if rx.search(f):
            for s in syms:
                if s not in out:
                    out.append(s)
    return out[:limit]
