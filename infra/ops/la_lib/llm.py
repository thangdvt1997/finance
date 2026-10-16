"""Client LLM local (OpenAI-compatible, stdlib). Giới hạn song song <=2 (flock giữa các tiến trình), ghi token."""
import fcntl, json, os, re, subprocess, time, urllib.request, urllib.error
from pathlib import Path
try:
    from . import pool
except ImportError:
    import pool

ROOT = Path(os.environ.get("TS_ROOT", Path(__file__).resolve().parents[3]))
DATA = ROOT / "data" / "la"
MAX_PAR = int(os.environ.get("LA_PARALLEL", "2"))   # <=2: không tranh CPU với đường giá
TIMEOUT = int(os.environ.get("LA_TIMEOUT", "900"))


def _docker_ip(name):
    try:
        out = subprocess.run(["docker", "inspect", name, "--format",
                              "{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}"],
                             capture_output=True, text=True, timeout=10).stdout.split()
        return out
    except Exception:
        return None


def _ok(url):
    try:
        return urllib.request.urlopen(url + "/health", timeout=5).status == 200
    except Exception:
        return False


def resolve():
    """(url, model). Ưu tiên LA_LLM_URL; rồi local-llm (alias/ IP container); rồi briefing-llm tạm thời."""
    model = os.environ.get("LA_MODEL", "code")
    if os.environ.get("LA_LLM_URL"):
        return os.environ["LA_LLM_URL"].rstrip("/"), model
    cands = ["http://local-llm:8080"]
    for c in ("tradingsys-local-llm", "local-llm"):
        cands += [f"http://{ip}:8080" for ip in _docker_ip(c)]
    for u in cands:
        if _ok(u):
            return u, model
    for ip in _docker_ip("tradingsys-briefing-llm"):   # tạm trong lúc L1 chưa xong
        if _ok(f"http://{ip}:8080"):
            return f"http://{ip}:8080", os.environ.get("LA_MODEL", "briefing")
    raise SystemExit("Không có LLM local sẵn sàng (đặt LA_LLM_URL / LA_MODEL).")


class _Slot:
    def __enter__(self):
        DATA.mkdir(parents=True, exist_ok=True)
        while True:
            for i in range(MAX_PAR):
                f = open(DATA / f".slot{i}.lock", "w")
                try:
                    fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    self.f = f
                    return self
                except OSError:
                    f.close()
            time.sleep(1)

    def __exit__(self, *a):
        self.f.close()


def log_tokens(kind, ptok, ctok, model, secs):
    DATA.mkdir(parents=True, exist_ok=True)
    rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "day": time.strftime("%Y-%m-%d"), "kind": kind, "task": kind,
           "model": model, "prompt_tokens": ptok, "completion_tokens": ctok, "secs": round(secs, 1)}
    with open(DATA / "tokens.jsonl", "a") as f:
        f.write(json.dumps(rec) + "\n")


def strip_think(t):
    t = re.sub(r"<think>.*?</think>", "", t, flags=re.S)
    return t.split("</think>")[-1].strip()


def _post(base, model, msgs, max_tokens, temperature, headers):
    body = json.dumps({"model": model, "messages": msgs, "max_tokens": max_tokens,
                       "temperature": temperature, "stream": False,
                       "chat_template_kwargs": {"enable_thinking": False}}).encode()
    req = urllib.request.Request(base + "/v1/chat/completions", body, headers)
    return json.load(urllib.request.urlopen(req, timeout=TIMEOUT))


def chat(messages, kind="misc", max_tokens=1024, temperature=0.1):
    msgs = [dict(m) for m in messages]
    if msgs and msgs[-1]["role"] == "user" and "/no_think" not in msgs[-1]["content"]:
        msgs[-1]["content"] += "\n/no_think"
    t0 = time.time()
    d = model = None
    if os.environ.get("LA_USE_POOL", "1") != "0" and not os.environ.get("LA_LLM_URL"):
        for _ in range(3):                      # thử tối đa 3 node, node lỗi bị loại tạm
            with pool.Lease() as ls:
                if not ls:
                    break
                n = ls.node
                try:
                    model = "pool:" + n["name"]
                    # node ctx nhỏ (4096): giữ max_tokens vừa phải
                    d = _post(pool.url(n), n.get("model", "default"), msgs, min(max_tokens, 1024), temperature, pool.headers())
                    break
                except urllib.error.HTTPError as e:
                    d = None                    # 400 (vượt ctx 4096)... không phải node chết -> rơi về local
                    if e.code >= 500:
                        pool.mark_dead(n)
                    else:
                        break
                except Exception:
                    pool.mark_dead(n)
                    d = None
    if d is None:                               # pool rỗng/lỗi -> local-llm (giới hạn <=2 song song)
        url, model = resolve()
        with _Slot():
            try:
                d = _post(url, model, msgs, max_tokens, temperature, {"Content-Type": "application/json"})
            except urllib.error.URLError as e:
                raise SystemExit(f"LLM lỗi: {e}")
    u = d.get("usage", {})
    log_tokens(kind, u.get("prompt_tokens", 0), u.get("completion_tokens", 0), model, time.time() - t0)
    return strip_think(d["choices"][0]["message"].get("content") or "")


def extract_json(t):
    t = re.sub(r"^```(?:json)?|```$", "", t.strip(), flags=re.M).strip()
    i = t.find("{")
    if i < 0:
        return None
    dec = json.JSONDecoder()
    try:
        return dec.raw_decode(t[i:])[0]
    except Exception:
        return None


def extract_code(t):
    m = re.search(r"```(?:python|py|sh|bash|yaml|markdown|md)?\n(.*?)```", t, re.S)
    return (m.group(1) if m else t).strip("\n") + "\n"
