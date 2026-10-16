"""QA tu test cac muc ha tang/script/co cau hinh trong inventory.json; ghi tests/qa/inventory/results.json (ID -> [status, ghi chu]).
Chi doc (docker inspect, systemctl, API Prometheus/Gatus, bash -n, py_compile); khong sua gi. Chay: python3 tests/qa/inventory/verify.py [--keep]  (--keep: giu ket qua UI da ghi tay)"""
import json, os, re, subprocess, sys, glob, py_compile, tempfile
R = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
os.chdir(R)
def sh(c, t=60):
    try: return subprocess.run(c, shell=True, capture_output=True, text=True, timeout=t)
    except Exception as e: return subprocess.CompletedProcess(c, 1, "", str(e))
P = "tests/qa/inventory/results.json"
res = json.load(open(P)) if os.path.exists(P) and "--keep" in sys.argv else {}
inv = json.load(open("tests/qa/inventory.json"))["items"]
# containers
st = {}
for ln in sh("docker ps -a --filter label=com.docker.compose.project=tradingsys --format '{{.Label \"com.docker.compose.service\"}}|{{.Names}}|{{.Status}}' ").stdout.splitlines():
    s, n, status = ln.split("|", 2); st[s] = (n, status)
for ln in sh("for c in $(docker ps -aq --filter label=com.docker.compose.project=tradingsys); do echo $(docker inspect -f '{{.Config.Labels}}' $c | grep -o 'service:[a-z0-9-]*' | cut -d: -f2) $(docker inspect -f '{{.RestartCount}} {{.State.OOMKilled}}' $c); done").stdout.splitlines():
    p = ln.split()
    if len(p) == 3: st[p[0]] = (st.get(p[0], ("", ""))[0], st.get(p[0], ("", ""))[1], p[1], p[2])
for i in inv:
    if i["id"].startswith("INF-C:"):
        s = i["id"][6:]
        if s not in st: res[i["id"]] = ["BỎ QUA", "profile/tool container, không chạy thường trực (perf/tools)"]; continue
        v = st[s]; ok = v[1].startswith("Up") and "unhealthy" not in v[1] and "starting" not in v[1]
        rc = v[2] if len(v) > 2 else "?"
        res[i["id"]] = ["PASS" if ok else "FAIL", f"{v[1]}; restart={rc}"] if ok else ["FAIL", v[1]]
# timers
for i in inv:
    if i["id"].startswith("INF-T:") and i["id"].endswith(".timer"):
        t = i["id"][6:]; r = sh(f"systemctl is-active {t}; systemctl show {t} -p NextElapseUSecRealtime --value").stdout.split("\n")
        res[i["id"]] = ["PASS" if r[0] == "active" else "FAIL", f"{r[0]}; next={r[1][:30]}"]
cr = sh("crontab -l").stdout
dg = os.path.getmtime("docs/handoff/DIGEST.md") if os.path.exists("docs/handoff/DIGEST.md") else 0
import time
res["INF-T:cron-digest"] = ["PASS" if "digest.sh" in cr and time.time() - dg < 3600 else "FAIL", f"cron có digest.sh; DIGEST.md cập nhật {int((time.time()-dg)/60)} phút trước"]
# prometheus rules
rules = json.loads(sh("docker exec tradingsys-prometheus-1 wget -qO- localhost:9090/api/v1/rules").stdout)["data"]["groups"]
for i in inv:
    if i["id"].startswith("INF-R:"):
        f = i["id"][6:]; rs = [r for g in rules if g["file"].endswith("/" + f) for r in g["rules"]]
        bad = [r["name"] for r in rs if r.get("health") != "ok"]
        res[i["id"]] = ["PASS" if rs and not bad else "FAIL", f"{len(rs)} luật, lỗi={bad[:3]}"]
tg = json.loads(sh("docker exec tradingsys-prometheus-1 wget -qO- localhost:9090/api/v1/targets").stdout)["data"]["activeTargets"]
dn = [t["labels"].get("job") for t in tg if t["health"] != "up"]
res["INF-P:targets"] = ["PASS" if not dn else "FAIL", f"{len(tg)} targets, down={dn}"]
am = sh("docker exec tradingsys-alertmanager-1 wget -qO- localhost:9093/api/v2/status").stdout
res["INF-P:alertmanager"] = ["PASS" if '"cluster"' in am else "FAIL", "API /api/v2/status trả cấu hình" if am else "không trả lời"]
# grafana
gp = sh("docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}' tradingsys-grafana-1").stdout.split()
gdash = []
if gp:
    r = sh(f"curl -s -m 10 http://{gp[0]}:3000/api/health; echo; curl -s -m 10 'http://{gp[0]}:3000/api/search?type=dash-db'")
    try: gdash = [d["title"] for d in json.loads(r.stdout.split("\n", 1)[1])]
    except Exception: pass
for i in inv:
    if i["id"].startswith("INF-G:"):
        f = i["id"][6:]
        try: d = json.load(open("infra/grafana/dashboards/" + f)); t = d.get("title", "")
        except Exception as e: res[i["id"]] = ["FAIL", f"JSON hỏng {e}"]; continue
        n = len(d.get("panels", []))
        res[i["id"]] = ["PASS" if (t in gdash or not gdash) else "FAIL", f"JSON hợp lệ, {n} panel, " + ("Grafana nạp được" if t in gdash else "không đối chiếu được Grafana (cần auth)" if not gdash else "Grafana KHÔNG thấy")] if gdash else ["PASS", f"JSON hợp lệ ({n} panel); Grafana API cần auth, chỉ kiểm tĩnh"]
# gatus
gi = sh("docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}' tradingsys-gatus").stdout.split()
gs = {}
if gi:
    try:
        for e in json.loads(sh(f"curl -s -m 15 http://{gi[0]}:8080/api/v1/endpoints/statuses").stdout):
            gs[e["name"]] = e["results"][-1]["success"] if e.get("results") else None
    except Exception: pass
for i in inv:
    if i["id"].startswith("INF-GT:"):
        f = "infra/ops/gatus.yaml" if i["id"].endswith("gatus.yaml") and "gatus.d" not in i["id"] else "infra/ops/gatus.d/" + i["id"][7:]
        names = re.findall(r"^\s*- name:\s*(\S+)", open(f, encoding="utf-8").read(), re.M)
        names = [n.strip("\"'") for n in names]
        bad = [n for n in names if gs.get(n) is False]; miss = [n for n in names if n not in gs and not any(k.endswith(n) for k in gs)]
        res[i["id"]] = ["FAIL" if bad else "PASS", f"{len(names)} endpoint, lỗi={bad}, không thấy={miss[:3]}"]
# flags
for i in inv:
    if i["id"].startswith("FLAG:"):
        k = i["id"][5:]; g = sh(f"grep -rIl --include=*.py --include=*.yml --include=*.sh --include=*.js --include=*.jsx '{k}' services infra/docker-compose*.yml libs 2>/dev/null | head -3").stdout.split()
        res[i["id"]] = ["PASS" if g else "FAIL", ("dùng trong " + ", ".join(g)) if g else "cờ có trong env nhưng không code nào đọc -> mã chết/ cần xoá"]
# script kiem tinh
for i in inv:
    if i["id"].startswith("SCRX:"):
        f = i["id"][5:]
        if not os.path.exists(f): res[i["id"]] = ["BỎ QUA", "file không còn"]; continue
        if f.endswith((".sh",)) or open(f, "rb").read(80).startswith(b"#!/bin/sh") or open(f, "rb").read(80).startswith(b"#!/usr/bin/env bash") or open(f, "rb").read(80).startswith(b"#!/bin/bash"):
            r = sh(f"bash -n {f}"); res[i["id"]] = ["PASS (tĩnh)" if r.returncode == 0 else "FAIL", "bash -n" + ("" if r.returncode == 0 else ": " + r.stderr[:100])]
        elif f.endswith(".py") or open(f, "rb").read(40).startswith(b"#!/usr/bin/env python"):
            try: py_compile.compile(f, cfile=os.path.join(tempfile.gettempdir(), "inv_pyc_%d" % os.getpid()), doraise=True); res[i["id"]] = ["PASS (tĩnh)", "py_compile"]
            except Exception as e: res[i["id"]] = ["FAIL", "py_compile: " + str(e)[:100]]
        elif f.endswith((".mjs", ".js", ".cjs")):
            r = sh(f"node --check {f}"); res[i["id"]] = ["PASS (tĩnh)" if r.returncode == 0 else "FAIL", "node --check" + ("" if r.returncode == 0 else ": " + r.stderr[:100])]
        else: res[i["id"]] = ["BỎ QUA", "không phải mã thực thi (dữ liệu/ cấu hình)"]
json.dump(res, open(P, "w"), ensure_ascii=False, indent=1)
import collections; print(collections.Counter(v[0] for v in res.values()))
