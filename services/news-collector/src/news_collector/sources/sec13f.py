"""SEC EDGAR 13F-HR cua cac quy cau hinh (config/funds_13f.yaml) -> expert.positions expert_id='SEC13F:<cik>'.

Yeu cau SEC: User-Agent co ten + email lien he, toi da 10 req/s (client dung 0.15s/req).
13F chi cho ten issuer + CUSIP (khong co ticker): anh xa CUSIP->ticker o config/cusip_map.yaml,
khong co thi symbol = 'CUSIP:<cusip>'. Chi lay vi the co phieu (SH), bo qua quyen chon (putCall).
"""
from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from datetime import datetime, timezone

from defusedxml import ElementTree as ET

from ..models import Emit, iso
from .base import Context, Source

log = logging.getLogger("news_collector.sec13f")
SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik10}.json"
ARCHIVE = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/"


def _strip_ns(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def latest_13f(submissions: dict) -> dict | None:
    """Tra ve {accession, report_date, filing_date} cua 13F-HR moi nhat (bo qua ban sua /A)."""
    rec = submissions.get("filings", {}).get("recent", {})
    for i, form in enumerate(rec.get("form", [])):
        if form == "13F-HR":
            return {"accession": rec["accessionNumber"][i], "report_date": rec["reportDate"][i],
                    "filing_date": rec["filingDate"][i]}
    return None


def find_infotable_name(index_json: dict) -> str | None:
    names = [i["name"] for i in index_json.get("directory", {}).get("item", []) if i["name"].lower().endswith(".xml")]
    cands = [n for n in names if n.lower() != "primary_doc.xml" and not n.lower().startswith("xsl")]
    pref = [n for n in cands if re.search(r"info|table|form13f", n, re.I)]
    return (pref or cands or [None])[0]


def parse_infotable(xml: bytes) -> list[dict]:
    """Gop theo CUSIP: tong value(USD), tong shares. Bo qua options."""
    root = ET.fromstring(xml)
    agg: dict[str, dict] = defaultdict(lambda: {"value": 0.0, "shares": 0.0, "name": None})
    for it in root.iter():
        if _strip_ns(it.tag) != "infoTable":
            continue
        f = {_strip_ns(c.tag): c for c in it.iter()}
        txt = lambda k: (f[k].text or "").strip() if k in f else ""
        if txt("putCall") or txt("sshPrnamtType") not in ("SH", ""):
            continue
        cusip = txt("cusip").upper()
        try:
            value, shares = float(txt("value")), float(txt("sshPrnamt"))
        except ValueError:
            continue
        a = agg[cusip]
        a["value"] += value
        a["shares"] += shares
        a["name"] = a["name"] or txt("nameOfIssuer")
    return [{"cusip": c, **v} for c, v in sorted(agg.items(), key=lambda kv: -kv[1]["value"])]


def build_positions(cik: str, fund: dict, filing: dict, holdings: list[dict], cusip_map: dict, top_n: int) -> list[Emit]:
    as_of = datetime.fromisoformat(filing["report_date"]).replace(tzinfo=timezone.utc)
    total = sum(h["value"] for h in holdings) or 1.0
    out = []
    for h in holdings[:top_n]:
        sym = cusip_map.get(h["cusip"]) or f"CUSIP:{h['cusip']}"
        payload = {"expert_id": f"SEC13F:{cik}", "source": "sec13f", "symbol": sym, "net_volume": h["shares"],
                   "avg_price": (h["value"] / h["shares"]) if h["shares"] else None, "as_of": iso(as_of),
                   "raw": {"fund": fund.get("name"), "issuer": h["name"], "cusip": h["cusip"], "value_usd": h["value"],
                           "weight": h["value"] / total, "accession": filing["accession"],
                           "filed": filing["filing_date"],
                           "note": "avg_price = value/shares tai cuoi quy (gia tham chieu, khong phai gia von)"}}
        out.append(Emit("expert_positions", "expert_position", payload, f"13f:{cik}:{sym}:{payload['as_of']}"))
    return out


class Sec13FSource(Source):
    name = "sec13f"

    def __init__(self, interval: float = 43200):
        self.interval = interval

    async def fetch(self, ctx: Context) -> list[Emit]:
        if "@" not in ctx.user_agent:
            log.warning("SEC13F bo qua: USER_AGENT phai chua email lien he (yeu cau cua SEC)")
            return []
        cfg = ctx.load_yaml("funds_13f.yaml")
        cusip_map = ctx.load_yaml("cusip_map.yaml").get("cusips", {})
        out: list[Emit] = []
        for fund in cfg.get("funds", []):
            cik = str(int(fund["cik"]))
            try:
                body, _ = await ctx.client.get(SUBMISSIONS.format(cik10=cik.zfill(10)))
                filing = latest_13f(json.loads(body))
                if not filing:
                    continue
                base = ARCHIVE.format(cik=cik, acc=filing["accession"].replace("-", ""))
                idx, _ = await ctx.client.get(base + "index.json")
                name = find_infotable_name(json.loads(idx))
                if not name:
                    log.warning("13F %s: khong tim thay infotable", cik)
                    continue
                xml, _ = await ctx.client.get(base + name)
                out += build_positions(cik, fund, filing, parse_infotable(xml), cusip_map, int(cfg.get("top_n", 50)))
            except Exception as ex:
                log.warning("13F %s loi: %s", cik, ex)
        return out
