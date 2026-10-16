"""QA nhom B: do API bars/health/rt trong container api-gateway (chi doc). Chay: docker exec -i tradingsys-api-gateway-1 python - < tests/qa/b_api_probe.py"""
import os,time,urllib.request
tok=[v for k,v in os.environ.items() if 'API_TOKEN' in k][0].split(',')[0]
def g(p):
    t=time.time();r=urllib.request.Request('http://127.0.0.1:8000'+p,headers={'x-api-key':tok})
    try:
        b=urllib.request.urlopen(r,timeout=30).read();return round(time.time()-t,3),len(b),b[:160]
    except Exception as e: return str(e)[:120]
for p in ['/v1/bars?symbol=EURUSD&tf=M1&limit=500','/v1/bars?symbol=EURUSD&tf=M30&limit=200','/v1/bars?symbol=EURUSD&tf=W1&limit=100','/v1/bars?symbol=EURUSD&tf=MN1&limit=50','/v1/bars?symbol=EURUSD&tf=D1&limit=300','/v1/bars?symbol=XAUUSD&tf=H4&limit=300','/v1/bars?symbol=EURUSD&tf=M1&limit=500','/v1/data/health','/v1/rt/stats']:
    print(p,g(p))
