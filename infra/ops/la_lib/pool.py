"""Pool node llama.cpp từ xa (data/ai-pool/nodes.json). Nạp lại khi file đổi, loại node chết/hết hạn,
cân bằng theo slot rảnh (1 slot/node, flock giữa các tiến trình). Khoá Bearer đọc từ pool_key, không in/ghi."""
import fcntl, json, os, time, urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(os.environ.get("TS_ROOT", Path(__file__).resolve().parents[3]))
POOL_DIR = Path(os.environ.get("LA_POOL_DIR", ROOT / "data" / "ai-pool"))
LOCK_DIR = ROOT / "data" / "la"
DEAD_S = 60            # node lỗi -> tạm loại 60 s
_cache = {"mtime": None, "nodes": []}
_dead = {}             # name -> hết hạn loại


def key():
    try:
        return (POOL_DIR / "pool_key").read_text().strip()
    except Exception:
        return ""


def _alive_time(n):
    try:
        return datetime.strptime(n["expires_at"], "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc) > datetime.now(timezone.utc)
    except Exception:
        return True


def nodes():
    """Danh sách node dùng được (status up, chưa hết TTL, không trong danh sách chết), nhanh nhất trước."""
    f = POOL_DIR / "nodes.json"
    try:
        m = f.stat().st_mtime
        if m != _cache["mtime"]:
            d = json.loads(f.read_text())
            _cache.update(mtime=m, nodes=d if isinstance(d, list) else d.get("nodes", []))
    except Exception:
        return []
    now = time.time()
    ok = [n for n in _cache["nodes"] if n.get("status") == "up" and _alive_time(n) and _dead.get(n["name"], 0) < now]
    return sorted(ok, key=lambda n: -n.get("tok_s_gen", 0))


def mark_dead(n):
    _dead[n["name"]] = time.time() + DEAD_S


def url(n):
    return f"http://{n['ip']}:{n['port']}"


def headers():
    h = {"Content-Type": "application/json"}
    k = key()
    if k:
        h["Authorization"] = "Bearer " + k
    return h


class Lease:
    """Chiếm 1 node rảnh (flock không chặn). Chờ tới khi có node; trả None nếu pool rỗng."""
    def __init__(self, wait_s=1200):
        self.wait_s, self.node, self.f = wait_s, None, None

    def __enter__(self):
        LOCK_DIR.mkdir(parents=True, exist_ok=True)
        t0 = time.time()
        while time.time() - t0 < self.wait_s:
            ns = nodes()
            if not ns:
                return None
            for n in ns:
                f = open(LOCK_DIR / f".pool-{n['name']}.lock", "w")
                try:
                    fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    self.node, self.f = n, f
                    return self
                except OSError:
                    f.close()
            time.sleep(1)
        return None

    def __exit__(self, *a):
        if self.f:
            self.f.close()


def health(n, timeout=5):
    try:
        req = urllib.request.Request(url(n) + "/health", headers=headers())
        return urllib.request.urlopen(req, timeout=timeout).status == 200
    except Exception:
        return False
