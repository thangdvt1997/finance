"""AI-001..: do LLM cuc bo (do tre token dau, token/s, timeout->LLMError, fallback). Chay: docker exec -i tradingsys-ai-trading python - < file"""
import time, json, urllib.request, sys
sys.path.insert(0, "/app/src") if False else None
def call(url, model, msgs, mt=60, to=150):
    body = {"model": model, "messages": msgs, "max_tokens": mt, "stream": True, "temperature": 0.3, "chat_template_kwargs": {"enable_thinking": False}}
    r = urllib.request.Request(url + "/v1/chat/completions", json.dumps(body).encode(), {"Content-Type": "application/json"})
    t = time.time(); ft = None; n = 0
    for l in urllib.request.urlopen(r, timeout=to):
        l = l.decode().strip()
        if l.startswith("data:") and "[DONE]" not in l:
            d = json.loads(l[5:]); c = (d["choices"][0].get("delta") or {}).get("content")
            if c:
                n += 1
                if ft is None: ft = time.time() - t
    tt = time.time() - t
    return {"first_s": round(ft or -1, 2), "chunks": n, "total_s": round(tt, 2), "tok_s": round(n / max(tt - (ft or 0), .01), 2)}
import os
for u, m in ((os.environ.get("PROBE_URL", "http://briefing-llm:8080"), os.environ.get("PROBE_MODEL", "classroom")),):
    try: print(u, call(u, m, [{"role": "user", "content": "Nói xin chào bằng tiếng Việt trong 1 câu."}]))
    except Exception as e: print(u, "ERR", type(e).__name__, e)
