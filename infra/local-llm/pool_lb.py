#!/usr/bin/env python3
"""ai-pool-lb: cân bằng tải OpenAI-compatible tới pool node llama.cpp (nodes.json) + dự phòng local-llm.
- Nạp lại nodes.json khi mtime đổi; loại node status!=up/hết TTL/health lỗi; 1 slot/node (hàng đợi, chọn node rảnh nhanh nhất).
- Authorization: Bearer lấy từ pool_key (không in/log). Prompt quá dài (> ~3000 token, ctx node 4096) hoặc pool rỗng/lỗi -> local-llm.
- /health, /metrics (Prometheus). Chỉ stdlib."""
import http.client, json, os, threading, time, urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

POOL = os.environ.get("POOL_DIR", "/pool")
FALLBACK = os.environ.get("FALLBACK_URL", "http://local-llm:8080")
MAX_TOK = int(os.environ.get("POOL_MAX_PROMPT_TOK", "3000"))
QUEUE_S = float(os.environ.get("POOL_QUEUE_S", "90"))
DEAD_S = 60
lock = threading.Condition()
state = {"mtime": None, "nodes": {}}      # name -> dict(node, busy, dead_until, ok)
M = {"req": 0, "err": 0, "fallback": 0, "ptok": 0, "ctok": 0, "per": {}}


def key():
    try:
        return open(f"{POOL}/pool_key").read().strip()
    except Exception:
        return ""


def valid(n):
    try:
        exp = datetime.strptime(n["expires_at"], "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc)
        return n.get("status") == "up" and exp > datetime.now(timezone.utc)
    except Exception:
        return n.get("status") == "up"


def reload():
    try:
        m = os.stat(f"{POOL}/nodes.json").st_mtime
        if m == state["mtime"]:
            return
        d = json.load(open(f"{POOL}/nodes.json"))
        d = d if isinstance(d, list) else d.get("nodes", [])
    except Exception:
        return
    with lock:
        old = state["nodes"]
        state["nodes"] = {n["name"]: {"n": n, "busy": old.get(n["name"], {}).get("busy", 0),
                                      "dead": old.get(n["name"], {}).get("dead", 0), "ok": old.get(n["name"], {}).get("ok", True)}
                          for n in d}
        state["mtime"] = m
        lock.notify_all()


def bg():
    while True:
        reload()
        for name, s in list(state["nodes"].items()):
            n = s["n"]
            try:
                r = urllib.request.Request(f"http://{n['ip']}:{n['port']}/health", headers={"Authorization": "Bearer " + key()})
                ok = urllib.request.urlopen(r, timeout=5).status == 200
            except Exception:
                ok = False
            with lock:
                s["ok"] = ok
                lock.notify_all()
        time.sleep(15)


def usable(s):
    return s["ok"] and valid(s["n"]) and s["dead"] < time.time()


def acquire():
    end = time.time() + QUEUE_S
    with lock:
        while True:
            cand = [s for s in state["nodes"].values() if usable(s)]
            if not cand:
                return None
            free = sorted((s for s in cand if s["busy"] == 0), key=lambda s: -s["n"].get("tok_s_gen", 0))
            if free:
                free[0]["busy"] = 1
                return free[0]
            left = end - time.time()
            if left <= 0:
                return None
            lock.wait(min(left, 2))


def release(s):
    with lock:
        s["busy"] = 0
        lock.notify_all()


def est_tokens(body):
    try:
        j = json.loads(body)
        txt = json.dumps(j.get("messages") or j.get("prompt") or "", ensure_ascii=False)
        return len(txt) // 3 + int(j.get("max_tokens") or 0)
    except Exception:
        return 0


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _send(self, code, body, ct="application/json"):
        self.send_response(code); self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            n = sum(1 for s in state["nodes"].values() if usable(s))
            return self._send(200 if n else 503, json.dumps({"status": "ok" if n else "no-nodes", "nodes_up": n}).encode())
        if self.path == "/metrics":
            L = [f"ai_pool_requests_total {M['req']}", f"ai_pool_errors_total {M['err']}", f"ai_pool_fallback_total {M['fallback']}",
                 f"ai_pool_prompt_tokens_total {M['ptok']}", f"ai_pool_completion_tokens_total {M['ctok']}",
                 f"ai_pool_nodes_up {sum(1 for s in state['nodes'].values() if usable(s))}",
                 f"ai_pool_nodes_busy {sum(s['busy'] for s in state['nodes'].values())}"]
            for k, s in state["nodes"].items():
                L.append(f'ai_pool_node_up{{node="{k}"}} {int(usable(s))}')
                L.append(f'ai_pool_node_requests_total{{node="{k}"}} {M["per"].get(k, 0)}')
            return self._send(200, ("\n".join(L) + "\n").encode(), "text/plain")
        return self._proxy("GET", b"")

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        self._proxy("POST", self.rfile.read(n))

    def _fwd(self, host, port, method, body, hdrs):
        c = http.client.HTTPConnection(host, port, timeout=900)
        c.request(method, self.path, body, hdrs)
        r = c.getresponse()
        data = r.read()
        return r.status, data

    def _proxy(self, method, body):
        M["req"] += 1
        hdrs = {"Content-Type": self.headers.get("Content-Type", "application/json")}
        res = None
        use_pool = self.path.startswith("/v1/") and method == "POST" and est_tokens(body) <= MAX_TOK
        if use_pool:
            for _ in range(3):
                s = acquire()
                if not s:
                    break
                n = s["n"]
                try:
                    st, data = self._fwd(n["ip"], n["port"], method, body, dict(hdrs, Authorization="Bearer " + key()))
                    if st < 500:
                        res = (st, data); M["per"][n["name"]] = M["per"].get(n["name"], 0) + 1
                        try:
                            u = json.loads(data).get("usage", {}); M["ptok"] += u.get("prompt_tokens", 0); M["ctok"] += u.get("completion_tokens", 0)
                        except Exception:
                            pass
                        break
                    s["dead"] = time.time() + DEAD_S
                except Exception:
                    s["dead"] = time.time() + DEAD_S
                finally:
                    release(s)
        if res is None:
            M["fallback"] += 1
            host, port = FALLBACK.split("//")[1].split(":")
            try:
                res = self._fwd(host, int(port), method, body, hdrs)
            except Exception as e:
                M["err"] += 1
                return self._send(502, json.dumps({"error": str(e)[:200]}).encode())
        self._send(*res)


class S(ThreadingHTTPServer):
    daemon_threads = True


if __name__ == "__main__":
    reload()
    threading.Thread(target=bg, daemon=True).start()
    S(("0.0.0.0", 8080), H).serve_forever()
