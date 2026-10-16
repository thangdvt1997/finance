"""Nap lich su gia CO PHIEU VN tu VNDirect finfo (cong khai, khong chinh thuc) cho nghien cuu backtest.
Khac vn_daily (chi ~150 ma 'focus' = thanh phan VN100/HNX30 HIEN TAI, tu 2018): o day lay TOAN BO ma dang niem yet HOSE + TOAN BO ma da huy niem yem
(status:delisted) tu 2013-01 de co universe theo thoi diem va giam survivorship bias. Tu gioi han >=0.9s/request, UA khai bao, cache theo ma (resume duoc).
Chay tren VPS (container python:3.12-slim). Ket qua: $RDATA/raw/<CODE>.json.gz, $RDATA/vn_meta.parquet, $RDATA/vn_index_raw.parquet.
"""
import gzip, json, os, pathlib, sys, time, urllib.parse, urllib.request
import pandas as pd

DATA = pathlib.Path(os.environ.get("RDATA", "/root/research/vn/data")); RAW = DATA / "raw"; RAW.mkdir(parents=True, exist_ok=True)
BASE = "https://api-finfo.vndirect.com.vn/v4"
UA = "trading-system-research/0.1 (personal research, read-only)"
GAP = float(os.environ.get("VN_GAP", "0.9")); START = os.environ.get("VN_START", "2012-12-01")
KEEP = ["code", "date", "floor", "type", "basicPrice", "ceilingPrice", "floorPrice", "open", "high", "low", "close", "average",
        "adOpen", "adHigh", "adLow", "adClose", "adAverage", "nmVolume", "nmValue", "ptVolume", "ptValue", "pctChange"]
_last = [0.0]; N_REQ = [0]


def get(path, q, size=3000, page=1, sort="date"):
    for attempt in range(5):
        w = _last[0] + GAP - time.monotonic()
        if w > 0: time.sleep(w)
        _last[0] = time.monotonic(); N_REQ[0] += 1
        url = f"{BASE}/{path}?" + urllib.parse.urlencode({"q": q, "size": size, "page": page, "sort": sort})
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"}), timeout=40) as r:
                return json.loads(r.read())
        except Exception as e:  # noqa
            print("retry", path, q[:50], attempt, repr(e)[:80], flush=True); time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"fail {path} {q}")


def fetch_all(path, q, sort="date"):
    out = []; page = 1
    while True:
        j = get(path, q, page=page, sort=sort); d = j.get("data") or []; out += d
        if not d or len(out) >= int(j.get("totalElements") or 0) or page >= 20: break
        page += 1
    return out


def main():
    meta = fetch_all("stocks", "type:STOCK,ETF~status:listed,delisted", sort="code")
    m = pd.DataFrame(meta)[["code", "type", "floor", "status", "listedDate", "delistedDate", "companyName"]]
    m.to_parquet(DATA / "vn_meta.parquet"); print("meta", len(m), m.status.value_counts().to_dict(), flush=True)
    want = m[(m.status == "delisted") | (m.floor == "HOSE")].code.tolist()
    # chi so (tu 2017-08 la toan bo lich su nguon co)
    ix = []
    for code in ["VNINDEX", "VN30", "VN100", "VNALL", "VNMID", "VNSML", "HNXINDEX", "HNX30"]:
        for r in fetch_all("vnmarket_prices", f"code:{code}~date:gte:2000-01-01"):
            ix.append({k: r.get(k) for k in ["code", "date", "open", "high", "low", "close", "nmValue", "advances", "declines"]})
    pd.DataFrame(ix).to_parquet(DATA / "vn_index_raw.parquet"); print("index rows", len(ix), flush=True)
    t0 = time.time()
    for i, code in enumerate(want):
        f = RAW / f"{code}.json.gz"
        if f.exists(): continue
        rows = fetch_all("stock_prices", f"code:{code}~date:gte:{START}")
        rows = [{k: r.get(k) for k in KEEP} for r in rows]
        with gzip.open(f, "wt") as fh: json.dump(rows, fh)
        if i % 25 == 0: print(f"{i}/{len(want)} {code} rows={len(rows)} req={N_REQ[0]} t={time.time()-t0:.0f}s", flush=True)
    print("DONE", len(list(RAW.glob('*.json.gz'))), flush=True)


if __name__ == "__main__":
    main()
