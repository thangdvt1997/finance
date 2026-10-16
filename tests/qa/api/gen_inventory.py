"""Kiem ke route: chay TRONG container api-gateway (co INTERNAL_TOKEN + mang backend), in JSON ra STDOUT (khong in secret).
   docker exec -i tradingsys-api-gateway-1 python - < tests/qa/api/gen_inventory.py > /tmp/inv_raw.json"""
import json, os, urllib.request

SVCS = {  # ten service -> host:port trong mang compose
    "api-gateway": "127.0.0.1:8000", "auth": "auth:8000", "ai-trading": "ai-trading:8000", "data-keeper": "data-keeper:8000",
    "briefing": "briefing:8000", "analytics": "analytics:8000", "journal": "journal:8000", "reporter": "reporter:8000",
    "risk-monitor": "risk-monitor:8000", "track-record": "track-record:8000", "vn-market": "vn-market:8000",
    "paper-trader": "paper-trader:8000", "alert-rules": "alert-rules:8000", "pattern-scan": "pattern-scan:8000",
    "pattern-engine": "pattern-engine:8000", "pattern-render": "pattern-render:8000", "nlp": "nlp:8000",
    "mt-bridge": "mt-bridge:8000", "alert-service": "alert-service:8000", "market-collector": "market-collector:8000",
    "news-collector": "news-collector:8000", "expert-collector": "expert-collector:8000", "storage-writer": "storage-writer:8000",
    "briefing-llm": "briefing-llm:8000",
}
tok = os.environ.get("INTERNAL_TOKEN", "")
key = os.environ.get("API_TOKENS", "").split(",")[0]
out = {}
for s, hp in SVCS.items():
    try:
        r = urllib.request.Request(f"http://{hp}/openapi.json", headers={"X-Internal-Token": tok, "X-API-Key": key})
        out[s] = json.loads(urllib.request.urlopen(r, timeout=8).read())
    except Exception as e:  # noqa
        out[s] = {"error": f"{type(e).__name__}: {str(e)[:80]}"}
print(json.dumps(out))
