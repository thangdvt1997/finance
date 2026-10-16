#!/usr/bin/env python3
"""Benchmark la: chạy 20 task cơ học bằng LLM local (tuần tự, ≤2 song song bằng khoá), báo tỉ lệ/thời gian/token."""
import json, os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from la_lib import llm
from tasks import TASKS

only = set(sys.argv[1:])
res, tot_p, tot_c = [], 0, 0
for tid, kind, prompt, chk in TASKS:
    if only and tid not in only:
        continue
    t0 = time.time()
    n0 = sum(1 for _ in open(llm.DATA / "tokens.jsonl")) if (llm.DATA / "tokens.jsonl").exists() else 0
    try:
        out = llm.chat([{"role": "system", "content": "Trả lời tiếng Việt; đúng định dạng yêu cầu, không giải thích thêm."},
                        {"role": "user", "content": prompt}], kind="bench-" + kind, max_tokens=700)
        ok = bool(chk(out))
    except SystemExit as e:
        out, ok = f"ERR {e}", False
    except Exception as e:
        out, ok = f"EXC {e}", False
    tf = llm.DATA / "tokens.jsonl"
    lines = [json.loads(l) for l in tf.read_text().splitlines()[n0:]] if tf.exists() else []
    p = sum(l["prompt_tokens"] for l in lines); c = sum(l["completion_tokens"] for l in lines)
    tot_p += p; tot_c += c
    if out.startswith(("ERR", "EXC")):
        print("   ", out[:200], flush=True)
    r = {"id": tid, "kind": kind, "ok": ok, "secs": round(time.time() - t0, 1), "ptok": p, "ctok": c, "out": out[:400]}
    res.append(r)
    print(f"{tid:8}{kind:14}{'OK' if ok else 'FAIL':5}{r['secs']:7}s  {p}+{c} tok", flush=True)
n = len(res); k = sum(r["ok"] for r in res)
by = {}
for r in res:
    by.setdefault(r["kind"], []).append(r["ok"])
print(f"\nTỔNG {k}/{n} = {k*100//max(n,1)}%  thời gian {sum(r['secs'] for r in res):.0f}s  token {tot_p}+{tot_c}")
for kd, v in by.items():
    print(f"  {kd:14}{sum(v)}/{len(v)}")
out = llm.DATA / "bench_last.json"
out.write_text(json.dumps({"model": llm.resolve()[1], "url_kind": "local", "results": res}, ensure_ascii=False, indent=1))
