import json,urllib.request,calendar,datetime as d
def ep(s): return calendar.timegm(d.datetime.fromisoformat(s).timetuple())
u="https://query1.finance.yahoo.com/v8/finance/chart/GC=F?interval=15m&period1=%d&period2=%d"%(ep("2026-09-20"),ep("2026-10-08"))
r=json.load(urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"Mozilla/5.0"}),timeout=30))["chart"]["result"][0]
q=r["indicators"]["quote"][0]; rows=[]
for i,t in enumerate(r["timestamp"]):
    if None in (q["open"][i],q["high"][i],q["low"][i],q["close"][i]): continue
    rows.append({"t":t,"o":q["open"][i],"h":q["high"][i],"l":q["low"][i],"c":q["close"][i]})
json.dump(rows,open("/data/gc_m15.json","w")); print(len(rows),rows[0],rows[-1])
