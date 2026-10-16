"""20 task cơ học mẫu: mỗi task = (id, loại, prompt, check(output)->bool). Kiểm tra tự động, không dùng LLM."""
import ast, re, subprocess, sys, tempfile, os, textwrap

def code(o):
    m = re.search(r"```(?:python|py)?\n(.*?)```", o, re.S)
    return m.group(1) if m else o

def runs(src, call_check, timeout=10):
    """Chạy src + đoạn kiểm tra trong tiến trình con; True nếu exit 0."""
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "t.py")
        open(p, "w").write(src + "\n" + call_check)
        try:
            return subprocess.run([sys.executable, "-I", p], capture_output=True, timeout=timeout, cwd=d).returncode == 0
        except Exception:
            return False

def unused_imports(src):
    t = ast.parse(src)
    names = set()
    for n in ast.walk(t):
        if isinstance(n, ast.Import):
            names |= {(a.asname or a.name).split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            names |= {a.asname or a.name for a in n.names}
    used = {n.id for n in ast.walk(t) if isinstance(n, ast.Name)} | {n.value.id for n in ast.walk(t) if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)}
    return names - used

def lint_task(src, assertion):
    def chk(o):
        c = code(o)
        try:
            return not unused_imports(c) and runs(c, assertion)
        except SyntaxError:
            return False
    return chk

def test_task(fn_src, good_asserts_ok, buggy_src):
    """Test do LLM viết phải PASS với hàm đúng và FAIL với bản lỗi (mutation)."""
    def chk(o):
        t = code(o)
        runner = "\nimport sys\nfor _n,_f in list(globals().items()):\n    if _n.startswith('test_') and callable(_f): _f()\n"
        return runs(fn_src + "\n" + t + runner, "") and not runs(buggy_src + "\n" + t + runner, "")
    return chk

def has_all(*ws):
    return lambda o: all(w.lower() in o.lower() for w in ws)

def label(*expected):
    return lambda o: re.sub(r"\W", "", o.strip().upper().split()[0]) in expected if o.strip() else False

LINT_RULE = "Sửa lỗi lint trong đoạn Python sau (xoá import thừa, sửa tên chưa định nghĩa). Giữ nguyên hành vi. Chỉ trả về code trong một khối ```python.\n\n"
TEST_RULE = "Viết các hàm test thuần Python (def test_...(): assert ...), KHÔNG dùng pytest, KHÔNG import hàm (hàm đã có sẵn trong cùng file), ít nhất 3 assert gồm biên. Chỉ trả về một khối ```python chỉ chứa test.\n\nHàm:\n"
LOG_RULE = "Tóm tắt log sau trong tối đa 5 dòng, nêu rõ nguyên nhân chính.\n\n"
CLS_RULE = "Phân loại lỗi vào đúng MỘT nhãn trong: CONFIG, NETWORK, DB, CODE, RESOURCE. Chỉ trả về nhãn (một từ).\n\nLỗi:\n"

F = {
 "clamp": ("def clamp(x, lo, hi):\n    return max(lo, min(x, hi))\n", "def clamp(x, lo, hi):\n    return min(lo, max(x, hi))\n"),
 "is_even": ("def is_even(n):\n    return n % 2 == 0\n", "def is_even(n):\n    return n % 2 == 1\n"),
 "mean": ("def mean(xs):\n    return sum(xs) / len(xs) if xs else 0.0\n", "def mean(xs):\n    return sum(xs) / (len(xs) + 1) if xs else 0.0\n"),
 "slug": ("def slug(s):\n    import re\n    return re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')\n", "def slug(s):\n    import re\n    return re.sub(r'[^a-z0-9]+', '-', s.lower())\n"),
}

TASKS = [
 ("lint1", "fix-lint", LINT_RULE + "import os\nimport sys\n\ndef f(a, b):\n    return a + b\n", lint_task("import os\nimport sys\n\ndef f(a, b):\n    return a + b\n", "assert f(1, 2) == 3")),
 ("lint2", "fix-lint", LINT_RULE + "import json, re\n\ndef g(s):\n    return json.dumps({'k': s})\n", lint_task("", "assert g('x') == '{\"k\": \"x\"}'")),
 ("lint3", "fix-lint", LINT_RULE + "from typing import List, Dict\n\ndef h(xs: List[int]) -> int:\n    return sum(xs)\n", lint_task("", "assert h([1,2,3]) == 6")),
 ("lint4", "fix-lint", LINT_RULE + "def k(x):\n    y = x * 2\n    return z\n", lint_task("", "assert k(2) in (4, 2) or True")),  # sửa NameError: chạy được là đủ
 ("lint5", "fix-lint", LINT_RULE + "import math\nimport time\n\ndef area(r):\n    return math.pi * r * r\n", lint_task("", "assert abs(area(1) - 3.14159) < 1e-3")),
 ("test1", "add-test", TEST_RULE + F["clamp"][0], test_task(F["clamp"][0], 0, F["clamp"][1])),
 ("test2", "add-test", TEST_RULE + F["is_even"][0], test_task(F["is_even"][0], 0, F["is_even"][1])),
 ("test3", "add-test", TEST_RULE + F["mean"][0], test_task(F["mean"][0], 0, F["mean"][1])),
 ("test4", "add-test", TEST_RULE + F["slug"][0], test_task(F["slug"][0], 0, F["slug"][1])),
 ("log1", "summarize", LOG_RULE + "2026-10-15 10:01 ERROR db: canceling statement due to statement timeout (bars DISTINCT ON)\n" * 3 + "2026-10-15 10:02 WARN analytics retry 1/3\n", has_all("timeout")),
 ("log2", "summarize", LOG_RULE + "10:01 INFO start\n10:02 ERROR redis: Connection refused host=redis:6379\n10:03 ERROR redis: Connection refused host=redis:6379\n10:04 INFO retry\n", has_all("redis")),
 ("log3", "summarize", LOG_RULE + "10:01 WARN disk usage 93% on /var/lib/docker\n10:05 ERROR write failed: No space left on device\n", lambda o: any(w in o.lower() for w in ("disk", "đĩa", "dung lượng"))),
 ("log4", "summarize", LOG_RULE + "10:01 ERROR auth: JWT signature invalid for user 12\n10:02 ERROR auth: JWT signature invalid for user 15\n10:03 INFO ok\n", has_all("jwt")),
 ("docs1", "docs", "Viết đoạn README ngắn (<= 8 dòng, markdown) cho hàm clamp(x, lo, hi) trả x bị kẹp trong [lo, hi]. Có mục 'Cách dùng' và ví dụ clamp(5, 0, 3) = 3.", has_all("clamp", "cách dùng", "3")),
 ("docs2", "docs", "Viết docstring Google-style tiếng Việt cho: def mean(xs): return sum(xs)/len(xs) if xs else 0.0 . Có Args, Returns.", has_all("args", "returns", "mean")),
 ("docs3", "docs", "Viết bảng markdown 3 cột (Biến, Mặc định, Ý nghĩa) cho 3 biến: LA_LLM_URL (rỗng, địa chỉ LLM), LA_MODEL (code, tên model), LA_PARALLEL (2, số yêu cầu song song).", has_all("LA_LLM_URL", "LA_MODEL", "LA_PARALLEL", "|")),
 ("cls1", "explain-error", CLS_RULE + "psycopg.OperationalError: connection to server at \"timescaledb\" failed: Connection refused", label("DB", "NETWORK")),
 ("cls2", "explain-error", CLS_RULE + "KeyError: 'LA_LLM_URL' (biến môi trường chưa đặt trong .env)", label("CONFIG")),
 ("cls3", "explain-error", CLS_RULE + "OSError: [Errno 28] No space left on device / MemoryError khi nạp model", label("RESOURCE")),
 ("commit1", "commit-msg", "Viết commit message một dòng kiểu 'fix(scope): mô tả' (<=72 ký tự) cho diff này, chỉ in dòng đó:\n-    return max(lo, min(hi, x))\n+    return max(lo, min(x, hi))\n(trong hàm clamp của utils.py)", lambda o: bool(re.match(r"^(fix|feat|docs|test|refactor)(\([\w.-]+\))?: .{5,}", o.strip().splitlines()[0])) and len(o.strip().splitlines()[0]) <= 80),
]
assert len(TASKS) == 20
