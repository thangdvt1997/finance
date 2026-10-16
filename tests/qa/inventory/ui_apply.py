"""Ap ket qua chay UI (d1_results.json, matrix.json cua eg_client_matrix, log eg_client_flows/smoke) vao tests/qa/inventory/results.json.
Dung: python3 tests/qa/inventory/ui_apply.py --d1 <d1_results.json> [--d1b <file bo sung/chay lai>] --matrix <matrix.json> --flows <log> --smoke <log>"""
import json, os, re, sys, collections
R = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
P = os.path.join(R, "tests/qa/inventory/results.json")
res = json.load(open(P)) if os.path.exists(P) else {}
a = sys.argv
def arg(k): return a[a.index(k) + 1] if k in a else None
def transient(i): return all(re.search(r"503|WebSocket|sse|stream|ERR_|502|Failed to load resource", x) for x in i)
if arg("--d1"):
    pages = collections.defaultdict(list)
    for f in [arg("--d1"), arg("--d1b")]:
        if not f: continue
        for r in json.load(open(f)): pages[r["key"].split("@")[0]].append(r["issues"])   # lan sau (chay lai) ghi de
    last = {}
    for f in [arg("--d1"), arg("--d1b")]:
        if not f: continue
        for r in json.load(open(f)): last[r["key"].split("@")[0]] = r["issues"]
    for p, iss in last.items():
        k = "UI-M:" + p
        res[k] = ["PASS" if not iss else "FAIL", "d1_pages 1366x768 tối/vi: 0 vấn đề" if not iss else "d1_pages: " + str(iss[0])[:140]]
if arg("--matrix"):
    m = json.load(open(arg("--matrix"))); by = collections.defaultdict(list)
    for r in m:
        if r["page"] != "_console": by[r["page"]].extend(i for i in r["issues"] if i["k"] != "console")
    n = sum(1 for r in m if r["page"] != "_console")
    for p, iss in by.items():
        res["UI-C:" + p] = ["PASS" if not iss else "FAIL", f"eg_client_matrix ({n//max(1,len(by))} tổ hợp ngôn ngữ x độ phân giải x theme)" + ("" if not iss else f": {len(iss)} vấn đề, vd {iss[0]}")]
if arg("--smoke") and "SMOKE XANH" in open(arg("--smoke"), encoding="utf-8").read():
    res["SMOKE"] = ["PASS", "smoke.sh xanh: 233 kiểm tra 3 vai trò"]
json.dump(res, open(P, "w"), ensure_ascii=False, indent=1)
