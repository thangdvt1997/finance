"""Kiem ke function tong hop: tests/qa/inventory.json + docs/handoff/FUNCTION_INVENTORY.md.
Chay: python3 tests/qa/inventory/build.py   (doc-only; khong ghi de file cua phien khac)
Nguon: api_inventory.json (ts), FUNCTION_INVENTORY_research.md (research), quet code (UI/AI/infra), docker/systemd/prometheus (thuc te).
Ket qua test cua QA nam trong tests/qa/inventory/results.json (ID -> [status, ghi chu]); chay lai test roi cap nhat file do."""
import glob, json, os, re, subprocess, collections
R = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
os.chdir(R)
def sh(c):
    return subprocess.run(c, shell=True, capture_output=True, text=True).stdout
RES = json.load(open("tests/qa/inventory/results.json")) if os.path.exists("tests/qa/inventory/results.json") else {}
items = []
def add(id, cat, desc, how, status, owner, note=""):
    if id in RES: status, note = RES[id][0], RES[id][1]
    items.append(dict(id=id, cat=cat, desc=desc, test=how, status=status, owner=owner, note=note))

# ---- API (ts; feed cho duong gia) : trang thai doc tu api_inventory.json (do run_api.py cua ts ghi)
FEED = {"mt-bridge", "market-collector", "news-collector", "expert-collector", "storage-writer", "alert-service"}
api = json.load(open("tests/qa/api_inventory.json"))
for a in api:
    st = a.get("status", "CHƯA TEST")
    add("API:" + a["id"], "api", f'{a["method"]} {a["path"]} - {a.get("summary","")}', "tests/qa/api/run_api.py --only " + a["path"],
        st, "feed" if a["service"] in FEED else "ts", a.get("detail", "")[:120])

# ---- Script/tool: research tsv + trang thai tu FUNCTION_INVENTORY_research.md
rs = {}
for ln in open("docs/handoff/FUNCTION_INVENTORY_research.md", encoding="utf-8"):
    m = re.match(r"\| (S-\d+) \| ([^|]+?) \| ([^|]*?) \| ([^|]*?) \|", ln)
    if m: rs[m.group(1)] = (m.group(2).strip(), m.group(3).strip(), m.group(4).strip(" `"))
covered = set()
for ln in open("tests/qa/research/scripts/inventory.tsv", encoding="utf-8"):
    if ln.startswith("#") or "|" not in ln: continue
    p = ln.rstrip("\n").split("|")
    sid, g, lab, desc = p[0], p[1], p[2], "|".join(p[3:])
    for pat in g.split():
        covered.update(glob.glob(pat))
    st, lb, _ = rs.get(sid, ("CHƯA TEST", "", ""))
    note = "deprecated" if lb == "deprecated" else ""
    add("SCR:" + sid, "script", f"{g} - {desc}", f"bash tests/qa/research/scripts/run_scripts.sh --only {sid}", st, "research", note)
for gp in ["tests/qa/research/backtest", "tests/qa/research/perf"]:
    pass
# script/test chua co trong inventory research: QA kiem tinh (bash -n / py_compile)
extra_globs = ["infra/ops/*.sh", "infra/ops/*.py", "infra/ops/la/*", "infra/ops/la_lib/*.py", "infra/ops/la_bench/*", "services/*/scripts/*", "tests/qa/*.sh", "tests/qa/*.py",
               "tests/qa/*.mjs", "tests/qa/api/*.py", "tests/qa/auth/*", "tests/e2e/*.sh", "tests/*.sh", "mt-agent/lab-feed/scripts/*", "data/mtlab-hist/*.sh",
               "infra/host/*", "infra/perf/*", "infra/local-llm/*.sh", "infra/mt-bridge/*.sh"]
seen = set()
for g in extra_globs:
    for f in sorted(glob.glob(g)):
        if f in covered or f in seen or os.path.isdir(f) or "__pycache__" in f or f.endswith((".json", ".txt", ".out", ".log", ".manifest", ".yaml", ".md")): continue
        seen.add(f)
        owner = "qa" if f.startswith(("tests/qa/inventory", "tests/qa/a_", "tests/qa/d", "tests/qa/eg", "tests/qa/s_", "tests/qa/c_", "tests/qa/auth", "tests/qa/f_", "tests/qa/ij", "tests/qa/b_", "tests/qa/api")) or f in ("infra/ops/smoke.sh", "infra/ops/deploy_local.sh") else "research"
        if f.startswith("mt-agent") or f.startswith("data/mtlab"): owner = "feed"
        if f.startswith("tests/e2e"): owner = "ts"
        if f.startswith("infra/ops/la"): owner = "ux"
        add("SCRX:" + f, "script", f, "kiem tinh: bash -n / py_compile (+ ghi o results.json neu chay that)", "CHƯA TEST", owner)

# ---- UI trang master / client
pat = re.compile(r'path:\s*"([a-z0-9-]+)"(.*)')
mp = {}
for f in glob.glob("services/web-ui/app/src/pages/*.jsx") + ["services/web-ui/app/src/shell/legacyPages.js"]:
    for ln in open(f, encoding="utf-8"):
        m = pat.search(ln)
        if m:
            lab = re.search(r'label:\s*"([^"]+)"', ln); roles = re.search(r"roles:\s*(\[[^\]]*\]|M)", ln)
            mp[m.group(1)] = (lab.group(1) if lab else m.group(1), roles.group(1) if roles else "master")
mp.setdefault("thi-truong", ("Thị trường", "master"))
for p, (lab, roles) in sorted(mp.items()):
    add("UI-M:" + p, "ui-master", f"Trang master /{p} - {lab} (vai {roles})", f"tests/qa/d1_run.sh (d1_pages) / smoke.sh / d2_run.sh", "CHƯA TEST", "ux" if p in ("ai-trading", "lop-hoc-ai", "kich-ban") else "qa")
pre = open("services/client-ui/app/src/lib/preload.js", encoding="utf-8").read()
for p in sorted(set(re.findall(r'"/([a-z][a-z0-9-]*)"\s*:', pre))):
    add("UI-C:" + p, "ui-client", f"Trang client #/{p}", "tests/qa/eg_client_matrix.sh + eg_client_flows.sh + smoke.sh", "CHƯA TEST", "qa")

# ---- Ha tang: container, timer, cron, prometheus rules, grafana, gatus
cs = sh("cd infra && set -a; . ./.env 2>/dev/null; set +a; docker compose config --services 2>/dev/null").split()
for s in sorted(cs):
    add("INF-C:" + s, "infra", f"Container compose {s}", "docker inspect health/restart (a_infra.sh)", "CHƯA TEST", "qa")
for t in sorted(glob.glob("infra/host/*.timer")) + sorted(os.path.basename(x) for x in glob.glob("/etc/systemd/system/tradingsys-*.timer")):
    add("INF-T:" + os.path.basename(t), "infra", f"systemd timer {os.path.basename(t)}", "systemctl is-active + lan chay gan nhat", "CHƯA TEST", "qa")
add("INF-T:cron-digest", "infra", "cron */30 infra/ops/digest.sh", "crontab -l + digest.sh chay duoc, DIGEST.md moi", "CHƯA TEST", "qa")
for f in sorted(glob.glob("infra/prometheus/rules*.yml")):
    add("INF-R:" + os.path.basename(f), "infra", f"Luat Prometheus {f}", "Prometheus API /rules: health ok moi luat", "CHƯA TEST", "qa")
add("INF-P:targets", "infra", "Prometheus scrape targets", "a_infra.sh (targets down = 0)", "CHƯA TEST", "qa")
add("INF-P:alertmanager", "infra", "Alertmanager routing", "amtool/ API /api/v2/status", "CHƯA TEST", "qa")
for f in sorted(glob.glob("infra/grafana/dashboards/*.json")):
    add("INF-G:" + os.path.basename(f), "infra", f"Grafana dashboard {os.path.basename(f)}", "JSON hop le + Grafana API /api/search thay duoc", "CHƯA TEST", "qa")
for f in sorted(glob.glob("infra/ops/gatus.d/*.yaml")) + ["infra/ops/gatus.yaml"]:
    n = len(re.findall(r"^\s*- name:", open(f, encoding="utf-8").read(), re.M))
    add("INF-GT:" + os.path.basename(f), "infra", f"Gatus {f} ({n} endpoint)", "log gatus 10 phut khong success=false (a_infra.sh)", "CHƯA TEST", "qa")

# ---- AI
AI = [("ai-trading/classroom/machine.py", "May trang thai hoi sau (phong hoc AI)", "ux"), ("ai-trading/classroom/one_to_ten.py", "Hoc 1 hieu 10", "ux"),
      ("ai-trading/classroom/commands.py", "Nhan y dinh / lenh (VN co dau, khong dau, viet tat)", "ux"), ("ai-trading/classroom/extract.py", "Trich xuat y tuong -> kich ban", "ux"),
      ("ai-trading/classroom/safety.py", "An toan / chong injection", "ux"), ("ai-trading/classroom/store.py", "Bo nho / luu hoi thoai", "ux"),
      ("ai-trading/classroom/llm.py", "LLM client lop hoc (local/API, fallback)", "ux"), ("ai-trading/classroom/checklist.py", "Checklist kich ban", "ux"),
      ("ai-trading/classroom/export.py", "Xuat kich ban", "ux"), ("ai-trading/arena.py", "Arena / consensus AI", "ts"), ("ai-trading/scenario_store.py", "Kho kich ban", "ts"),
      ("briefing/src", "Ban tin sang (LLM briefing)", "ts"), ("nlp/src", "NLP tin tuc (sentiment ONNX)", "ts"), ("data-keeper/src", "Data-keeper (phat hien gap, lap, LLM)", "feed"),
      ("pattern-engine/src", "Pattern engine + scenario_runner/backtest runner", "research"), ("pattern-scan/src", "Quet kich ban live", "research"),
      ("../infra/ops/la_lib/llm.py", "LLMClient local/node pool (la_lib)", "ux"), ("../infra/local-llm", "Local LLM server", "ux")]
for p, d, o in AI:
    add("AI:" + p, "ai", d, "pytest service + golden set (ux/ts); xem docs/handoff/TASK_classroom_ux.md", "CHƯA TEST", o)

# ---- Co cau hinh / kill-switch
flags = set()
for f in glob.glob("infra/.env.example") + glob.glob("infra/env/*.env"):
    for ln in open(f, encoding="utf-8", errors="ignore"):
        m = re.match(r"([A-Z0-9_]*(ENABLED|DISABLE|KILL|FLAG|SWITCH|READONLY|PAPER)[A-Z0-9_]*)=", ln)
        if m: flags.add((m.group(1), f))
for k, f in sorted(flags):
    add("FLAG:" + k, "flag", f"Co cau hinh {k} ({f})", "ton tai trong env + service doc duoc (grep code)", "CHƯA TEST", "qa")

json.dump(dict(generated=sh("date -u +%FT%TZ").strip(), items=items), open("tests/qa/inventory.json", "w"), ensure_ascii=False, indent=1)
# ---- Markdown
def cnt(its):
    c = collections.Counter(i["status"].split()[0].rstrip("*") if not i["status"].startswith(("CHƯA", "BỎ")) else " ".join(i["status"].split()[:2]) for i in its); return c
L = ["# FUNCTION_INVENTORY (phien qa, tong hop)", "", f"Sinh tu dong boi `python3 tests/qa/inventory/build.py` ({sh('date -u +%F').strip()}). Du lieu may doc: `tests/qa/inventory.json`; ket qua test cua QA: `tests/qa/inventory/results.json`.",
     "Hop nhat bang lien ket (khong ghi de): API chi tiet -> `tests/qa/api_inventory.json` + `docs/handoff/stabilize/API_INVENTORY.md` (ts); script/tool, backtest (B-), hieu nang (P-) -> `docs/handoff/FUNCTION_INVENTORY_research.md` (research). Ma `SCR:S-xxx` = ID trong file research.", ""]
tot = collections.Counter(); 
L += ["## Tong ket theo chu phien x trang thai", "", "| Chu | Tong | PASS | FAIL | BO QUA | CHUA TEST |", "|---|---|---|---|---|---|"]
def bucket(s): return "PASS" if s.startswith("PASS") else "FAIL" if s.startswith("FAIL") else "BO" if s.startswith("BỎ") else "CHUA"
by = collections.defaultdict(collections.Counter)
for i in items: by[i["owner"]][bucket(i["status"])] += 1
T = collections.Counter()
for o in sorted(by):
    c = by[o]; T.update(c); L.append(f"| {o} | {sum(c.values())} | {c['PASS']} | {c['FAIL']} | {c['BO']} | {c['CHUA']} |")
L.append(f"| **Tong** | **{sum(T.values())}** | {T['PASS']} | {T['FAIL']} | {T['BO']} | {T['CHUA']} |")
L += ["", "## Theo nhom", "", "| Nhom | Tong | PASS | FAIL | BO QUA | CHUA TEST |", "|---|---|---|---|---|---|"]
bc = collections.defaultdict(collections.Counter)
for i in items: bc[i["cat"]][bucket(i["status"])] += 1
for k, c in sorted(bc.items()): L.append(f"| {k} | {sum(c.values())} | {c['PASS']} | {c['FAIL']} | {c['BO']} | {c['CHUA']} |")
for cat in ["ui-master", "ui-client", "infra", "flag", "ai", "script"]:
    L += ["", f"## {cat}", "", "| ID | Mo ta | Cach test | Trang thai | Chu | Ghi chu |", "|---|---|---|---|---|---|"]
    for i in items:
        if i["cat"] == cat: L.append(f'| {i["id"]} | {i["desc"][:110].replace("|","/")} | {i["test"][:70].replace("|","/")} | {i["status"]} | {i["owner"]} | {i["note"][:140].replace("|","/")} |')
L += ["", "## api", "", "420+ route: danh sach day du trong `tests/qa/api_inventory.json` (ID `API:<service>:<METHOD>:<path>` trong inventory.json, trang thai dong bo tu file do khi chay build.py). Tong hop:", "", "| Chu | Tong | PASS | FAIL | BO QUA | CHUA TEST |", "|---|---|---|---|---|---|"]
ba = collections.defaultdict(collections.Counter)
for i in items:
    if i["cat"] == "api": ba[i["owner"]][bucket(i["status"])] += 1
for o, c in sorted(ba.items()): L.append(f"| {o} | {sum(c.values())} | {c['PASS']} | {c['FAIL']} | {c['BO']} | {c['CHUA']} |")
L += ["", "## CHUA TEST thuoc phien khac (khong phai pham vi QA)", ""]
for o in sorted(by):
    if o == "qa": continue
    un = [i for i in items if i["owner"] == o and bucket(i["status"]) == "CHUA"]
    if not un: continue
    L.append(f"- **{o}**: {len(un)} muc. " + ("Cac nhom: " + ", ".join(f"{k}={v}" for k, v in collections.Counter(i['cat'] for i in un).items())))
    if o != "ts" or len(un) < 40:
        for i in un[:80]: L.append(f"  - {i['id']}")
    else: L.append("  - (API: xem api_inventory.json, status CHƯA TEST; ts dang chay run_api.py)")
L += ["", "## Mục QA con CHUA TEST / FAIL", ""]
for i in items:
    if i["owner"] == "qa" and bucket(i["status"]) in ("CHUA", "FAIL"): L.append(f"- {i['id']}: {i['status']} {i['note']}")
open("docs/handoff/FUNCTION_INVENTORY.md", "w", encoding="utf-8").write("\n".join(L) + "\n")
print(len(items), dict(T))
