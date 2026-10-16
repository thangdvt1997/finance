"""Tai du lieu cong khai: CFTC COT (TFF + Disaggregated, futures only) va gia ngay Yahoo. Tai lap: python fetch_data.py"""
import io, sys, time, zipfile, pathlib, json
import requests
D = pathlib.Path(__file__).parent / "data"; D.mkdir(exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 research-script contact:<OWNER_EMAIL>"}
def get(url, dest):
    p = D / dest
    if p.exists() and p.stat().st_size > 1000: return p
    r = requests.get(url, headers=UA, timeout=120); r.raise_for_status()
    p.write_bytes(r.content); time.sleep(1); return p
B = "https://www.cftc.gov/files/dea/history/"
files = [("fin_fut_txt_2006_2016.zip",)] + [(f"fut_fin_txt_{y}.zip",) for y in range(2017, 2027)]
files += [("fut_disagg_txt_hist_2006_2016.zip",)] + [(f"fut_disagg_txt_{y}.zip",) for y in range(2017, 2027)]
for (f,) in files: print(f, get(B + f, f).stat().st_size)
import datetime as dt
syms = {"EURUSD":"EURUSD=X","GBPUSD":"GBPUSD=X","USDJPY":"JPY=X","AUDUSD":"AUDUSD=X","USDCAD":"CAD=X","USDCHF":"CHF=X","XAU":"GC=F"}
p1 = int(dt.datetime(2006,1,1).timestamp()); p2 = int(time.time())
for k,v in syms.items():
    out = D / f"px_{k}.json"
    if out.exists(): continue
    r = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{v}", params={"period1":p1,"period2":p2,"interval":"1d"}, headers=UA, timeout=60)
    r.raise_for_status(); out.write_text(r.text); print(k, len(r.text)); time.sleep(1)
