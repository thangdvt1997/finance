"""Sinh requirements.lock (có hash) cho từng service từ pyproject.toml: gộp phụ thuộc runtime của libs/common + service (bỏ `tscommon`).
Chạy TRONG container python:3.12-slim (xem infra/ops/lock_deps.sh). Dockerfile cài: pip install --require-hashes -r services/<svc>/requirements.lock
rồi pip install --no-deps libs/common services/<svc>. Cập nhật lock: chạy lại script (Renovate/CI sẽ làm khi có remote)."""
import subprocess, sys, tomllib, pathlib

root = pathlib.Path(sys.argv[1]); out = pathlib.Path(sys.argv[2]); services = sys.argv[3:]
def deps(p):
    d = tomllib.loads((root / p / "pyproject.toml").read_text(encoding="utf8"))["project"]["dependencies"]
    return [x for x in d if not x.lower().startswith("tscommon")]
common = deps("libs/common")
for s in services:
    req = sorted(set(common + deps(f"services/{s}")))
    inp = out / f"{s}.in"; inp.write_text("\n".join(req) + "\n")
    dst = out / f"{s}.requirements.lock"
    subprocess.run(["uv", "pip", "compile", str(inp), "--generate-hashes", "--python-version", "3.12", "--no-header",
                    "--quiet", "-o", str(dst)], check=True)
    print(s, sum(1 for l in dst.read_text().splitlines() if l and not l.startswith((" ", "#"))), "packages")
