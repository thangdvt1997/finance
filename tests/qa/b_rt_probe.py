"""QA nhom B: SSE /v1/rt/sse nhan tick, ngat + ket noi lai (retry), WS auth. Chay trong container api-gateway: docker exec -i tradingsys-api-gateway-1 python - < tests/qa/b_rt_probe.py"""
import os,time,socket,json,urllib.request
tok=[v for k,v in os.environ.items() if 'API_TOKEN' in k][0].split(',')[0]
def sse(topics,secs=8):
    r=urllib.request.Request('http://127.0.0.1:8000/v1/rt/sse?topics='+topics,headers={'x-api-key':tok})
    t0=time.time();fr=[]
    resp=urllib.request.urlopen(r,timeout=10);resp.fp.raw._sock.settimeout(3) if hasattr(resp.fp,'raw') else None
    try:
        while time.time()-t0<secs:
            l=resp.readline()
            if not l: break
            if l.startswith(b'data:'): fr.append(l[5:].strip()[:100])
            if l.startswith(b'retry:'): fr.append(l.strip())
    except Exception as e: fr.append(('exc',str(e)[:60]))
    resp.close();return fr
for rnd in (1,2):   # ket noi, dong, ket noi lai
    f=sse('q:EURUSD,q:XAUUSD');print('round',rnd,'frames',len(f));[print('  ',x) for x in f[:4]]
print(urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8000/v1/rt/stats',headers={'x-api-key':tok})).read())
