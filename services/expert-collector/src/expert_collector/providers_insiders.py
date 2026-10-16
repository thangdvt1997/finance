"""Provider Form 4 (SEC EDGAR): giao dich cua NGUOI TRONG CUOC (insider) -> expert.signals 'insider_buy' / 'insider_sell'.

Nguon du lieu (cong khai, mien phi, khong dang nhap): ho so Form 4 cua SEC.
  1) Feed Atom 'latest filings' (cgi-bin/browse-edgar?action=getcurrent&type=4&output=atom): robots.txt cua SEC co `Disallow: /cgi-bin`
     (urllib.robotparser bo sot vi dong trong giua file) -> MAC DINH TAT (use_atom=False); neu bat va bi RobotsDenied thi ha cap sang (2).
  2) Daily index `Archives/edgar/daily-index/<nam>/QTR<q>/form.<YYYYMMDD>.idx` (robots cho phep /Archives) -> danh sach Form 4 trong ngay,
     moi dong tro toi `edgar/data/<cik>/<accession>.txt` (goi nop day du, co chua <ownershipDocument> XML).
Quy tac SEC fair-access: <= 10 request/giay, User-Agent bat buoc co email lien he (cau hinh PoliteClient host_intervals {'www.sec.gov': 0.2}).

Loc 'co hoi' (tin hieu dung duoc, khong phai khuyen nghi):
  * Chi giu giao dich thi truong mo: ma P (mua) va S (ban) o bang non-derivative; bo A (thuong/cap), M (thuc hien quyen), F (nop thue),
    G (tang), D, J, C, X... va moi giao dich o bang derivative.
  * Bo giao dich theo ke hoach 10b5-1 (co aff10b5One=1 hoac chu thich neu 10b5-1) va mua qua DRIP/ESPP/ke hoach tich luy.
  * Mua: gop theo (nguoi, ma, ngay), gia tri >= min_buy_usd (mac dinh 100.000 USD). Ban: chi giu >= min_sell_usd (mac dinh 1.000.000 USD)
    vi ban thuong la da dang hoa/thue, tin hieu yeu hon nhieu so voi mua.
  * Vai tro: CEO/CFO/Chairman/President > Officer/Director khac > 10% owner. 'cluster' = >= 3 nguoi khac nhau mua cung ma.
Moi SignalInfo.raw chua: kind (insider_buy|insider_sell), value_usd, shares, price, roles, title, owner, issuer, accession, strength.
"""
from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from .httpclient import PoliteClient, RobotsDenied
from .models import ExpertInfo, SignalInfo
from .sources.base import ExpertSource

SEC_ATOM_FORM4 = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=4&owner=include&count=100&output=atom"
SEC_ARCHIVES = "https://www.sec.gov/Archives/"
DAILY_INDEX = SEC_ARCHIVES + "edgar/daily-index/{y}/QTR{q}/form.{ymd}.idx"

_PLAN_RX = re.compile(r"10b5[-‐-― ]?1|trading plan|pre-?arranged", re.I)
_AUTO_BUY_RX = re.compile(r"dividend reinvest|\bDRIP\b|employee stock purchase|\bESPP\b|automatic(?:ally)? (?:invest|purchas)|"
                          r"periodic (?:investment|purchase)|401\(?k\)?|deferred compensation|director fees? (?:paid|elected)", re.I)
_TAX_SELL_RX = re.compile(r"tax withholding|satisfy .{0,40}tax|withheld", re.I)


@dataclass
class InsiderTx:
    accession: str
    issuer: str
    ticker: str
    owner: str
    owner_cik: str
    roles: list[str]
    title: str
    code: str  # ma giao dich SEC: P/S/A/M/F/G...
    shares: float
    price: float | None
    value_usd: float
    tx_date: date | None
    acq_disp: str  # A|D
    plan_10b5: bool
    auto_buy: bool
    direct: bool
    post_shares: float | None
    derivative: bool = False
    note: str = ""


# ---------------- phan tich chi muc / feed ----------------
def parse_daily_index(text: str, form: str = "4") -> list[dict[str, str]]:
    """form.idx cot co dinh; tach bang regex: <form> <cong ty> <CIK> <YYYYMMDD> <duong-dan.txt>."""
    out: list[dict[str, str]] = []
    rx = re.compile(r"^(?P<form>\S+)\s+(?P<company>.+?)\s+(?P<cik>\d{1,10})\s+(?P<date>\d{8})\s+(?P<path>edgar/\S+\.txt)\s*$")
    for line in text.splitlines():
        m = rx.match(line)
        if m and m.group("form") == form:
            out.append({k: m.group(k) for k in ("company", "cik", "date", "path")})
    return out


def parse_atom_filings(text: str) -> list[dict[str, str]]:
    """Atom 'latest filings': moi ho so xuat hien 2 lan (Reporting + Issuer) cung accession -> gop. Tra ve path `edgar/data/<cik>/<acc>.txt`."""
    out: dict[str, dict[str, str]] = {}
    for ent in re.findall(r"<entry>(.*?)</entry>", text, re.S):
        acc = re.search(r"accession-number=([0-9-]+)", ent)
        href = re.search(r'<link[^>]*href="([^"]+)"', ent)
        title = re.search(r"<title>(.*?)</title>", ent, re.S)
        term = re.search(r'term="([^"]+)"', ent)
        if not acc or not href or (term and term.group(1) != "4"):
            continue
        cik = re.search(r"/edgar/data/(\d+)/", href.group(1))
        if not cik:
            continue
        a = acc.group(1)
        out.setdefault(a, {"company": (title.group(1) if title else "").strip(), "cik": cik.group(1), "date": "",
                           "path": f"edgar/data/{cik.group(1)}/{a}.txt"})
    return list(out.values())


# ---------------- phan tich Form 4 ----------------
def extract_ownership_xml(doc: str) -> str | None:
    m = re.search(r"<ownershipDocument>.*?</ownershipDocument>", doc, re.S)
    return m.group(0) if m else None


def _t(el: ET.Element | None, path: str) -> str:
    if el is None:
        return ""
    n = el.find(path)
    return (n.text or "").strip() if n is not None and n.text else ""


def _f(s: str) -> float | None:
    try:
        return float(s.replace(",", ""))
    except (ValueError, AttributeError):
        return None


def _bool(s: str) -> bool:
    return s.strip().lower() in {"1", "true", "y", "yes"}


def _d(s: str) -> date | None:
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def parse_form4(xml_text: str, accession: str = "") -> list[InsiderTx]:
    """Phan tich <ownershipDocument> thanh danh sach giao dich non-derivative co ma giao dich (khong gom holding)."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    if _t(root, "documentType") not in {"4", "4/A"}:
        return []
    issuer, ticker = _t(root, "issuer/issuerName"), _t(root, "issuer/issuerTradingSymbol").upper()
    foot = {fn.get("id"): " ".join((fn.text or "").split()) for fn in root.iter("footnote")}
    plan_flag = _bool(_t(root, "aff10b5One"))
    owner_el = root.find("reportingOwner")
    owner, ocik = _t(owner_el, "reportingOwnerId/rptOwnerName"), _t(owner_el, "reportingOwnerId/rptOwnerCik")
    rel = owner_el.find("reportingOwnerRelationship") if owner_el is not None else None
    title = _t(rel, "officerTitle")
    roles: list[str] = []
    if rel is not None:
        if _bool(_t(rel, "isDirector")):
            roles.append("director")
        if _bool(_t(rel, "isOfficer")):
            roles.append("officer")
        if _bool(_t(rel, "isTenPercentOwner")):
            roles.append("10pct_owner")
        if _bool(_t(rel, "isOther")):
            roles.append("other")
    out: list[InsiderTx] = []
    for tx in root.findall("nonDerivativeTable/nonDerivativeTransaction"):
        ids = [x.get("id") for x in tx.iter("footnoteId")]
        notes = " ".join(foot.get(i, "") for i in ids)
        shares = _f(_t(tx, "transactionAmounts/transactionShares/value")) or 0.0
        price = _f(_t(tx, "transactionAmounts/transactionPricePerShare/value"))
        out.append(InsiderTx(
            accession=accession, issuer=issuer, ticker=ticker, owner=owner, owner_cik=ocik, roles=roles, title=title,
            code=_t(tx, "transactionCoding/transactionCode").upper(), shares=shares, price=price,
            value_usd=round(shares * price, 2) if price else 0.0, tx_date=_d(_t(tx, "transactionDate/value")),
            acq_disp=_t(tx, "transactionAmounts/transactionAcquiredDisposedCode/value").upper(),
            plan_10b5=plan_flag or bool(_PLAN_RX.search(notes)), auto_buy=bool(_AUTO_BUY_RX.search(notes)),
            direct=_t(tx, "ownershipNature/directOrIndirectOwnership/value").upper() != "I",
            post_shares=_f(_t(tx, "postTransactionAmounts/sharesOwnedFollowingTransaction/value")), note=notes[:300]))
    return out


# ---------------- loc 'co hoi' ----------------
def role_weight(roles: list[str], title: str) -> float:
    t = title.lower()
    if re.search(r"chief executive|\bceo\b|chief financial|\bcfo\b|chair|president|founder", t):
        return 1.0
    if "officer" in roles:
        return 0.85
    if "director" in roles:
        return 0.75
    if "10pct_owner" in roles:
        return 0.6
    return 0.4


def aggregate(txs: list[InsiderTx]) -> list[InsiderTx]:
    """Gop cac dong cung (nguoi, ma, ngay, ma giao dich, huong) thanh 1 giao dich (gia = VWAP)."""
    groups: dict[tuple, list[InsiderTx]] = defaultdict(list)
    for x in txs:
        groups[(x.owner_cik or x.owner, x.ticker, x.tx_date, x.code, x.acq_disp)].append(x)
    out = []
    for g in groups.values():
        sh = sum(x.shares for x in g)
        val = sum(x.value_usd for x in g)
        first = g[0]
        out.append(InsiderTx(**{**first.__dict__, "shares": sh, "value_usd": round(val, 2),
                                "price": round(val / sh, 4) if sh else first.price,
                                "plan_10b5": any(x.plan_10b5 for x in g), "auto_buy": any(x.auto_buy for x in g)}))
    return out


def is_opportunity(x: InsiderTx, min_buy_usd: float = 100_000, min_sell_usd: float = 1_000_000) -> str | None:
    """Tra ve 'insider_buy' | 'insider_sell' neu giao dich dang chu y, nguoc lai None."""
    if x.derivative or not x.ticker or x.plan_10b5 or not x.price or x.price <= 0:
        return None
    if x.code == "P" and x.acq_disp == "A" and not x.auto_buy and x.value_usd >= min_buy_usd:
        return "insider_buy"
    if x.code == "S" and x.acq_disp == "D" and x.value_usd >= min_sell_usd and not _TAX_SELL_RX.search(x.note):
        return "insider_sell"
    return None


def strength(x: InsiderTx, cluster: int = 1) -> float:
    """0..1: log gia tri (100k USD ~0.3, 1M ~0.6, 10M ~0.9) * trong so vai tro, +0.1 moi nguoi cum them (toi da +0.2)."""
    base = min(1.0, max(0.0, (math.log10(max(x.value_usd, 1.0)) - 4.0) / 3.5 + 0.1))
    return round(min(1.0, base * role_weight(x.roles, x.title) + min(0.2, 0.1 * max(0, cluster - 1))), 3)


def build_signals(txs: list[InsiderTx], min_buy_usd: float = 100_000, min_sell_usd: float = 1_000_000,
                  cluster_min: int = 3) -> list[SignalInfo]:
    agg = aggregate(txs)
    picked = [(k, x) for x in agg if (k := is_opportunity(x, min_buy_usd, min_sell_usd))]
    buyers: dict[str, set[str]] = defaultdict(set)
    for k, x in picked:
        if k == "insider_buy":
            buyers[x.ticker].add(x.owner_cik or x.owner)
    sigs: list[SignalInfo] = []
    for kind, x in picked:
        n = len(buyers[x.ticker]) if kind == "insider_buy" else 1
        when = datetime(x.tx_date.year, x.tx_date.month, x.tx_date.day, tzinfo=timezone.utc) if x.tx_date else None
        sigs.append(SignalInfo(
            symbol=f"US:{x.ticker}", side="buy" if kind == "insider_buy" else "sell", entry=x.price, opened_at=when,
            url=f"https://www.sec.gov/Archives/{x.accession}" if x.accession else "",
            raw={"kind": kind, "value_usd": x.value_usd, "shares": x.shares, "price": x.price, "roles": x.roles, "title": x.title,
                 "owner": x.owner, "issuer": x.issuer, "accession": x.accession, "direct": x.direct, "post_shares": x.post_shares,
                 "cluster": n if (kind == "insider_buy" and n >= cluster_min) else 0,
                 "strength": strength(x, n if kind == "insider_buy" else 1),
                 "note": "Giao dich thi truong mo (P/S), khong theo ke hoach 10b5-1. Chi la du lieu cong khai, khong phai khuyen nghi."}))
    return sigs


# ---------------- nguon (ExpertSource) ----------------
def _accession_from_path(path: str) -> str:
    return path.rsplit("/", 1)[-1].removesuffix(".txt")


def _recent_business_days(today: date, n: int) -> list[date]:
    d, out = today, []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= timedelta(days=1)
    return out


class InsiderForm4Source(ExpertSource):
    """Doc Form 4 gan day cua SEC va phat tin hieu insider_buy/insider_sell da loc."""
    name = "insiders"
    tos_risk = "low"
    warning = "Du lieu cong khai SEC EDGAR; tin hieu tham khao, khong phai khuyen nghi dau tu."

    def __init__(self, client: PoliteClient, lookback_days: int = 2, max_filings: int = 400, min_buy_usd: float = 100_000,
                 min_sell_usd: float = 1_000_000, today: date | None = None, use_atom: bool = False):
        self.client, self.lookback_days, self.max_filings = client, lookback_days, max_filings
        self.min_buy_usd, self.min_sell_usd, self.today, self.use_atom = min_buy_usd, min_sell_usd, today, use_atom

    async def list_experts(self) -> list[ExpertInfo]:
        return [ExpertInfo(expert_id="sec_form4_insiders", source=self.name, display_name="Nguoi trong cuoc (Form 4)",
                           url="https://www.sec.gov/edgar/search/", reputation={"kind": "insider", "prior_score": 0.6})]

    async def _filings(self) -> list[dict[str, str]]:
        if self.use_atom:
            try:
                return parse_atom_filings(await self.client.get_text(SEC_ATOM_FORM4))
            except RobotsDenied:
                pass  # robots SEC cam /cgi-bin -> ha cap xuong daily-index
        out: list[dict[str, str]] = []
        for d in _recent_business_days(self.today or datetime.now(timezone.utc).date(), self.lookback_days + 1):
            url = DAILY_INDEX.format(y=d.year, q=(d.month - 1) // 3 + 1, ymd=d.strftime("%Y%m%d"))
            try:
                out += parse_daily_index(await self.client.get_text(url))
            except Exception:  # 404 (ngay chua co/le) -> bo qua
                continue
        return out

    async def fetch_signals(self, expert: ExpertInfo) -> list[SignalInfo]:
        txs: list[InsiderTx] = []
        for f in (await self._filings())[: self.max_filings]:
            try:
                doc = await self.client.get_text(SEC_ARCHIVES + f["path"], cache=False)
            except Exception:
                continue
            xml = extract_ownership_xml(doc)
            if xml:
                txs += parse_form4(xml, _accession_from_path(f["path"]))
        return build_signals(txs, self.min_buy_usd, self.min_sell_usd)
