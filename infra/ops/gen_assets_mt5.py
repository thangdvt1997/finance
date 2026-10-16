#!/usr/bin/env python3
"""Sinh danh muc symbol MT5 (forex/kim loai/chi so) tu symbols.csv -> assets_mt5.yaml + feed_symbols.txt. Idempotent (ghi de nguyen file).

Dung:  python3 infra/ops/gen_assets_mt5.py [--csv /root/mtlab/out/symbols.csv]
Ra:    libs/common/src/tscommon/assets_mt5.yaml  (assets.py nap TRUOC assets.yaml -> muc viet tay trong assets.yaml thang)
       infra/mt-bridge/feed_symbols.txt           (FEED_CANON_SYMBOLS=@/config/feed_symbols.txt)
Chuan hoa: duong dan 'Indexes\\US500' -> ten 'US500' (symbol chuan = cot name, hoa); chi lay path bat dau Forex|Metals|Indexes.
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CUR = {"USD": ("Đô la Mỹ", "US Dollar"), "EUR": ("Euro", "Euro"), "GBP": ("Bảng Anh", "British Pound"), "JPY": ("Yên Nhật", "Japanese Yen"),
       "CHF": ("Franc Thuỵ Sĩ", "Swiss Franc"), "AUD": ("Đô la Úc", "Australian Dollar"), "CAD": ("Đô la Canada", "Canadian Dollar"),
       "NZD": ("Đô la New Zealand", "New Zealand Dollar"), "CNH": ("Nhân dân tệ (offshore)", "Chinese Yuan (offshore)"), "RMB": ("Nhân dân tệ", "Chinese Yuan"),
       "HKD": ("Đô la Hồng Kông", "Hong Kong Dollar"), "SGD": ("Đô la Singapore", "Singapore Dollar"), "SEK": ("Curon Thuỵ Điển", "Swedish Krona"),
       "NOK": ("Curon Na Uy", "Norwegian Krone"), "DKK": ("Curon Đan Mạch", "Danish Krone"), "PLN": ("Zloty Ba Lan", "Polish Zloty"),
       "CZK": ("Curon Séc", "Czech Koruna"), "HUF": ("Forint Hungary", "Hungarian Forint"), "TRY": ("Lira Thổ Nhĩ Kỳ", "Turkish Lira"),
       "ZAR": ("Rand Nam Phi", "South African Rand"), "MXN": ("Peso Mexico", "Mexican Peso"), "THB": ("Baht Thái", "Thai Baht"),
       "ILS": ("Shekel Israel", "Israeli Shekel"), "RUB": ("Rúp Nga", "Russian Ruble"), "RUR": ("Rúp Nga (cũ)", "Russian Ruble (old)"),
       "ARS": ("Peso Argentina", "Argentine Peso"), "BRL": ("Real Brazil", "Brazilian Real"), "CLP": ("Peso Chile", "Chilean Peso"),
       "COP": ("Peso Colombia", "Colombian Peso"), "GEL": ("Lari Georgia", "Georgian Lari"), "KRW": ("Won Hàn Quốc", "South Korean Won"),
       "INR": ("Rupee Ấn Độ", "Indian Rupee"), "NGN": ("Naira Nigeria", "Nigerian Naira"), "IDR": ("Rupiah Indonesia", "Indonesian Rupiah"),
       "XAU": ("Vàng", "Gold"), "XAG": ("Bạc", "Silver"), "XPT": ("Bạch kim", "Platinum"), "XPD": ("Palladium", "Palladium")}
G8 = {"USD", "EUR", "GBP", "JPY", "CHF", "AUD", "CAD", "NZD"}
MAJORS = {"EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD"}
IDX = {  # symbol -> (nhom, ten vi, quote)
    "US500": ("Mỹ", "S&P 500", "USD"), "US500M": ("Mỹ", "S&P 500 mini", "USD"), "US30": ("Mỹ", "Dow Jones 30", "USD"), "US30M": ("Mỹ", "Dow Jones 30 mini", "USD"),
    "USTEC": ("Mỹ", "Nasdaq 100", "USD"), "USTECH100M": ("Mỹ", "Nasdaq 100 mini", "USD"), "US2000": ("Mỹ", "Russell 2000", "USD"), "CA60": ("Châu Mỹ", "Canada 60", "CAD"),
    "DE40": ("Châu Âu", "DAX 40", "EUR"), "MIDDE50": ("Châu Âu", "Đức Mid 50", "EUR"), "TECHDE30": ("Châu Âu", "Đức Tech 30", "EUR"), "UK100": ("Châu Âu", "FTSE 100", "GBP"),
    "FRA40": ("Châu Âu", "CAC 40", "EUR"), "ESP35": ("Châu Âu", "IBEX 35", "EUR"), "EUSTX50": ("Châu Âu", "Euro Stoxx 50", "EUR"), "IT40": ("Châu Âu", "Ý 40", "EUR"),
    "NETH25": ("Châu Âu", "Hà Lan 25", "EUR"), "NOR25": ("Châu Âu", "Na Uy 25", "NOK"), "SE30": ("Châu Âu", "Thuỵ Điển 30", "SEK"), "SWI20": ("Châu Âu", "Thuỵ Sĩ 20", "CHF"),
    "JPN225": ("Châu Á - Thái Bình Dương", "Nikkei 225", "JPY"), "HK50": ("Châu Á - Thái Bình Dương", "Hang Seng 50", "HKD"), "CHINA50": ("Châu Á - Thái Bình Dương", "FTSE China A50", "USD"),
    "CHINAH": ("Châu Á - Thái Bình Dương", "Trung Quốc H-shares", "HKD"), "AUS200": ("Châu Á - Thái Bình Dương", "ASX 200", "AUD"), "SA40": ("Khác", "Nam Phi 40", "ZAR")}
_SYM = re.compile(r"^[A-Z0-9]{3,12}$")


def _fx(s: str) -> dict:
    b, q = s[:3], s[3:]
    nb, nq = CUR.get(b, (b, b)), CUR.get(q, (q, q))
    grp = "Majors" if s in MAJORS else ("Minors" if b in G8 and q in G8 else "Exotics")
    d = {"s": s, "name": f"{nb[0]} / {nq[0]}", "name_en": f"{nb[1]} / {nq[1]}", "group": grp}
    if q in ("JPY", "KRW", "HUF", "CLP", "COP", "IDR") or s.endswith("JPY"):
        d["precision"] = 3 if s.endswith("JPY") or q == "HUF" else 2
    return d


def build(rows: list[dict]) -> dict:
    out: dict[str, list[dict]] = {"forex": [], "metal": [], "index": []}
    for r in rows:
        name, path = r["name"].strip().upper(), r["path"].strip().replace("\\\\", "\\")
        kind = path.split("\\", 1)[0]
        if not _SYM.match(name) or kind not in ("Forex", "Metals", "Indexes"):
            continue
        if kind == "Forex":
            out["forex"].append(_fx(name))
        elif kind == "Metals":
            b, q = name[:3], name[3:]
            nb, nq = CUR.get(b, (b, b)), CUR.get(q, (q, q))
            d = {"s": name, "name": f"{nb[0]} / {nq[0]} (giao ngay)", "name_en": f"{nb[1]} / {nq[1]} (spot)", "group": "Kim loại quý", "session": "fx_24x5"}
            if b in ("XAG",):
                d["precision"] = 3
            if q != "USD":
                d["quote"] = q
            out["metal"].append(d)
        else:
            g, vi, q = IDX.get(name, ("Khác", r.get("desc", name), "USD"))
            d = {"s": name, "name": f"{vi} (CFD)", "name_en": f"{r.get('desc') or name} (CFD)", "group": g, "session": "fx_24x5"}
            if q != "USD":
                d["quote"] = q
            out["index"].append(d)
    return out


def dump_yaml(data: dict) -> str:
    def q(v):
        return '"' + str(v).replace('"', "'") + '"' if isinstance(v, str) else str(v)
    lines = ["# SINH TU DONG boi infra/ops/gen_assets_mt5.py tu symbols.csv - KHONG sua tay (muc viet tay dat trong assets.yaml, duoc uu tien).", "version: 1", "symbols:"]
    for cls, items in data.items():
        lines.append(f"  {cls}:")
        for it in items:
            lines.append("    - {" + ", ".join(f"{k}: {q(v)}" for k, v in it.items()) + "}")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="/root/mtlab/out/symbols.csv")
    ap.add_argument("--out-dir", default=str(ROOT))
    a = ap.parse_args(argv)
    with open(a.csv, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f, delimiter=";"))
    data = build(rows)
    base = Path(a.out_dir)
    (base / "libs/common/src/tscommon/assets_mt5.yaml").write_text(dump_yaml(data), encoding="utf-8")
    syms = sorted({it["s"] for items in data.values() for it in items})
    (base / "infra/mt-bridge/feed_symbols.txt").write_text("# SINH TU DONG (gen_assets_mt5.py): symbol duoc phat chuoi canon M1..D1. Moi dong 1 ma; # = ghi chu.\n" + "\n".join(syms) + "\n", encoding="utf-8")
    print({k: len(v) for k, v in data.items()}, "feed:", len(syms))
    return 0


if __name__ == "__main__":
    sys.exit(main())
