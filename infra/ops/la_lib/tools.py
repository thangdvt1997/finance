"""Công cụ allow-list cho agent: chỉ trong worktree; không đụng secret; test/lint qua lệnh cố định."""
import os, re, subprocess
from pathlib import Path

DENY = re.compile(r"(^|/)(\.env[^/]*|.*secret.*|.*\.key|.*\.pem|\.git(/|$)|data(/|$)|backups(/|$))", re.I)
MAXOUT = 6000


class Tools:
    def __init__(self, wt: Path, root: Path):
        self.wt, self.root = Path(wt).resolve(), Path(root)
        self.written = set()

    def _p(self, rel):
        p = (self.wt / rel).resolve()
        if self.wt not in p.parents and p != self.wt:
            raise ValueError("ngoài repo")
        r = str(p.relative_to(self.wt))
        if DENY.search(r):
            raise ValueError("đường dẫn bị chặn")
        return p

    def read_file(self, path, start=1, end=200):
        lines = self._p(path).read_text(errors="replace").splitlines()
        s, e = int(start), int(end)
        return "\n".join(f"{i+s}: {l}" for i, l in enumerate(lines[s-1:e]))[:MAXOUT]

    def write_file(self, path, content):
        p = self._p(path)
        if p.suffix not in (".py", ".md", ".yml", ".yaml", ".sh", ".json", ".txt", ".toml", ".js", ".jsx"):
            raise ValueError("đuôi file không cho phép")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        self.written.add(str(p.relative_to(self.wt)))
        return f"đã ghi {path} ({len(content)} ký tự)"

    def grep(self, pattern, path="."):
        r = subprocess.run(["grep", "-rnI", "-m", "20", "--exclude-dir=node_modules", "--exclude-dir=.git",
                            "--exclude-dir=data", "-E", pattern, str(self._p(path))],
                           capture_output=True, text=True, timeout=60, cwd=self.wt)
        return r.stdout.replace(str(self.wt) + "/", "")[:MAXOUT] or "(không có kết quả)"

    def list_dir(self, path="."):
        return "\n".join(sorted(x.name + ("/" if x.is_dir() else "") for x in self._p(path).iterdir()))[:MAXOUT]

    def git_diff(self):
        subprocess.run(["git", "add", "-N", "--"] + sorted(self.written), cwd=self.wt, capture_output=True) if self.written else None
        return subprocess.run(["git", "diff", "HEAD"], capture_output=True, text=True, cwd=self.wt).stdout[:MAXOUT]

    def run_tests(self, service):
        if not re.fullmatch(r"[a-z0-9-]+|common", service):
            raise ValueError("tên service lạ")
        return run_tests(self.wt, service)

    def run_lint(self, path="."):
        return lint(self.wt, [str(self._p(path).relative_to(self.wt))])

    def call(self, name, args):
        if name not in ("read_file", "write_file", "grep", "list_dir", "git_diff", "run_tests", "run_lint"):
            return f"ERR: công cụ '{name}' không có trong allow-list"
        try:
            return str(getattr(self, name)(**args))
        except Exception as e:
            return f"ERR: {e}"


def run_tests(wt, service, timeout=1200):
    """pytest trong container tạm python:3.12-slim (run_tests.sh), mã lấy từ worktree. Trả về (rc/-1, tail)."""
    env = dict(os.environ, TS_ROOT=str(wt))
    r = subprocess.run(["sh", str(Path(__file__).resolve().parents[1] / "run_tests.sh"), service],
                       capture_output=True, text=True, timeout=timeout, env=env)
    return f"rc={r.returncode}\n" + (r.stdout + r.stderr)[-3000:]


def lint(wt, paths):
    """py_compile + ruff (container tạm). rc=0 nếu sạch."""
    py = [p for p in paths if p == "." or p.endswith(".py") or Path(wt, p).is_dir()]
    cmd = ("pip install -q ruff >/dev/null 2>&1; cd /w && ruff check --no-cache --select E9,F --output-format concise "
           + " ".join(py or ["."]) + " 2>&1 | tail -40")
    r = subprocess.run(["docker", "run", "--rm", "-v", f"{wt}:/w:ro", "python:3.12-slim", "sh", "-c", cmd],
                       capture_output=True, text=True, timeout=600)
    out = (r.stdout + r.stderr).strip()
    clean = "All checks passed" in out
    return f"rc={0 if clean else 1}\n{out[-3000:]}"
