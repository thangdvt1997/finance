#!/usr/bin/env python3
"""QA backtest runner (B-001..). Chay: nice -n 19 python3 tests/qa/research/backtest/run_b.py  -> in bang PASS/FAIL, ghi results_b.json.
READ-ONLY voi test khoa: chi dung scenario_runner (chi doc dev). Output vao thu muc tam."""
import hashlib, json, os, re, subprocess, sys, tempfile, shutil, pathlib, gzip
R = pathlib.Path("/root/trading-system"); RUN = R/"data/research/program/R11/scenario_runner.py"
TPL = R/"docs/research/program/scenario_template"
tmp = pathlib.Path(tempfile.mkdtemp(prefix="qa_bt_")); res = []
def rec(i, name, ok, note=""): res.append((i, name, "PASS" if ok else "FAIL", note)); print(i, "PASS" if ok else "FAIL", name, note, flush=True)
def sh(args, timeout=900):
    p = subprocess.run(["nice","-n","19","timeout",str(timeout),sys.executable,*args], capture_output=True, text=True); return p.returncode, p.stdout+p.stderr
def sha(p): return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def runyaml(y, out): return sh([str(RUN), str(y), "--out", str(out)])
def jl(out):
    t = out.read_text() if hasattr(out,'read_text') else out
    return json.loads(t)

exp = {"EXAMPLE_donchian.yaml": (120, 0.469), "EXAMPLE_from_image.yaml": (39, -0.162)}
n = 1
for f,(en,ee) in exp.items():
    o1, o2 = tmp/(f+"1"), tmp/(f+"2")
    rc1, t1 = runyaml(TPL/f, o1); rc2, t2 = runyaml(TPL/f, o2)
    ok = rc1 == 0 and rc2 == 0
    if ok:
        r = json.loads((o1/"report.json").read_text())["result"]
        rec(f"B-{n:03d}", f"{f}: khop so mau (n={en}, E={ee}R)", r["n_trades_oos"]==en and abs(r["expectancy_r_net"]-ee)<0.0015, f"n={r['n_trades_oos']} E={r['expectancy_r_net']:.4f}")
        same = all(sha(o1/x)==sha(o2/x) for x in ["trades.csv","equity.svg"]) and \
               json.loads((o1/"report.json").read_text())["folds"]==json.loads((o2/"report.json").read_text())["folds"]
        r2 = json.loads((o2/"report.json").read_text())["result"]
        for k in ("elapsed_s",): r.pop(k,None); r2.pop(k,None)
        same = same and r==r2
        rec(f"B-{n+1:03d}", f"{f}: tai lap (2 lan chay: hash trades.csv/equity.svg, report.json bang nhau)", same)
    else:
        rec(f"B-{n:03d}", f+": chay", False, (t1+t2)[-300:]); rec(f"B-{n+1:03d}", f+": tai lap", False, "khong chay duoc")
    n += 2
# B-005 so voi run luu san
for f,rid in (("EXAMPLE_donchian.yaml","KB-EX-DONCHIAN"),("EXAMPLE_from_image.yaml","KB-EX-IMG-2DINH")):
    saved = json.loads((R/f"data/research/program/R11/runs/{rid}/report.json").read_text())["result"]
    cur = json.loads(((tmp/(f+"1"))/"report.json").read_text())["result"]
    rec(f"B-{n:03d}", f"{f}: khop ket qua luu san trong runs/{rid}", saved["n_trades_oos"]==cur["n_trades_oos"] and abs(saved["expectancy_r_net"]-cur["expectancy_r_net"])<1e-9 and saved["prereg_sha256"]==cur["prereg_sha256"]); n+=1
# bien: prereg bi sua
import yaml
base = yaml.safe_load((TPL/"EXAMPLE_donchian.yaml").read_text())
def variant(mut, name):
    d = json.loads(json.dumps(base)); mut(d); p = tmp/name; p.write_text(yaml.safe_dump(d, allow_unicode=True)); return p
# schema sai
p = variant(lambda d: d.pop("costs"), "nocost.yaml"); rc,t = runyaml(p, tmp/"o_nocost")
rec(f"B-{n:03d}", "YAML thieu truong bat buoc (costs) -> tu choi co thong bao", rc!=0 and "KHÔNG HỢP LỆ" in t and "Traceback" not in t); n+=1
p = variant(lambda d: d["market"].update(timeframe="M3"), "badtf.yaml"); rc,t = runyaml(p, tmp/"o_tf")
rec(f"B-{n:03d}", "YAML timeframe sai enum -> tu choi", rc!=0 and "KHÔNG HỢP LỆ" in t); n+=1
p = tmp/"junk.yaml"; p.write_text("a: [unclosed\n  - : :"); rc,t = runyaml(p, tmp/"o_junk")
rec(f"B-{n:03d}", "YAML khong parse duoc -> tu choi (khong treo)", rc!=0 and "Traceback" not in t, "Traceback" in t and "co traceback" or ""); n+=1
p = tmp/"empty.yaml"; p.write_text(""); rc,t = runyaml(p, tmp/"o_empty")
rec(f"B-{n:03d}", "YAML rong -> tu choi", rc!=0 and "Traceback" not in t, "traceback" if "Traceback" in t else ""); n+=1
p = variant(lambda d: d["market"].update(symbols=["BTCUSD; rm -rf /"]), "inj_sym.yaml"); rc,t = runyaml(p, tmp/"o_isym")
rec(f"B-{n:03d}", "ten symbol chua ky tu nguy hiem -> schema tu choi", rc!=0 and "KHÔNG HỢP LỆ" in t); n+=1
p = variant(lambda d: d["market"].update(symbols=["NOSUCHSYM"]), "nosym.yaml"); rc,t = runyaml(p, tmp/"o_nosym")
rec(f"B-{n:03d}", "symbol khong co du lieu -> bao loi ro, ma thoat !=0", rc!=0 and "Không có dữ liệu" in t, t.strip()[-120:]); n+=1
p = variant(lambda d: d["market"].update(symbols=["../../etc/passwd"]), "trav.yaml"); rc,t = runyaml(p, tmp/"o_trav")
rec(f"B-{n:03d}", "symbol path traversal -> tu choi", rc!=0 and "KHÔNG HỢP LỆ" in t); n+=1
p = variant(lambda d: d["market"].update(timeframe="M1"), "m1.yaml")  # co the khong thieu; chi kiem khong crash
# DSL injection
for k,expr in enumerate(["__import__('os').system('touch %s/PWNED')" % tmp, "open('/etc/passwd').read()", "close.__class__", "[x for x in close]", "(lambda: 1)()", "exec('1')"]):
    p = variant(lambda d, e=expr: d["entry"].update(long=e), f"inj{k}.yaml"); rc,t = runyaml(p, tmp/f"o_inj{k}")
    rec(f"B-{n:03d}", f"DSL chen ma: {expr[:40]!r} -> bi chan", rc!=0 and not (tmp/"PWNED").exists() and not (tmp/f"o_inj{k}"/"report.json").exists(), "Traceback" in t and "(chan bang exception, khong thong bao than thien)" or ""); n+=1
# sua YAML sau dang ky
o = tmp/"o_prereg"; runyaml(TPL/"EXAMPLE_donchian.yaml", o)
p = variant(lambda d: d["costs"].update(spread_bps=d["costs"]["spread_bps"]+1), "mod.yaml"); rc,t = runyaml(p, o)
rec(f"B-{n:03d}", "sua YAML sau dang ky (cung id) -> TỪ CHỐI", rc!=0 and "TỪ CHỐI" in t); n+=1
# sweep qua lon
p = variant(lambda d: d.__setitem__("params", {f"p{i}": {"default":1,"sweep":[1,2,3,4,5,6,7,8,9,10]} for i in range(3)}), "bigsweep.yaml"); rc,t = sh([str(RUN), str(p), "--out", str(tmp/"o_sw")])
rec(f"B-{n:03d}", "luoi sweep > gioi han -> tu choi", rc!=0 and ("Lưới" in t or "tham số" in t), t.strip()[-100:]); n+=1
# data_scope test khoa
p = variant(lambda d: d["validation"].update(data_scope="test"), "scopetest.yaml"); rc,t = runyaml(p, tmp/"o_sc")
rec(f"B-{n:03d}", "data_scope=test (mo test khoa) -> schema tu choi", rc!=0 and "KHÔNG HỢP LỆ" in t); n+=1
# static: runner khong doc split test
src = RUN.read_text()
rec(f"B-{n:03d}", "ma runner chi doc split train/val, khong co duong mo test", 'isin(["train", "val"])' in src and "order_send" not in src and "OrderSend" not in src); n+=1
# dev rong (MT5 M15 chi co du lieu moi) -> bao loi ro
p = variant(lambda d: (d.__setitem__("id","QA-EMPTYDEV"), d["market"].update(symbols=["EURUSD"], timeframe="M15")), "emptydev.yaml"); rc,t = runyaml(p, tmp/"o_ed")
rec(f"B-{n:03d}", "symbol co file nhung dev rong (0 nen) -> bao loi ro, khong IndexError", rc!=0 and "quá ít" in t and "Traceback" not in t); n+=1
# R10 freeze
fz = json.loads((R/"data/research/program/R10/freeze.json").read_text()); bad = []
for fn,h in fz["code"].items():
    p = R/"data/research/program/R10/code"/fn
    if not p.exists() or sha(p)!=h: bad.append(fn)
rec(f"B-{n:03d}", "R10 freeze.json: hash code khop", not bad, "lech: "+",".join(bad)); n+=1
for key,fn in (("dev_results","dev_results.json"),("panel","panel_d1.parquet")):
    ok = sha(R/"data/research/program/R10"/fn)==fz[key]; rec(f"B-{n:03d}", f"R10 freeze.json: hash {key} khop", ok); n+=1
ph = R/"docs/research/program/R10_preregistration.sha256"
if ph.exists():
    exp_h = ph.read_text().split()[0]; act = sha(R/"docs/research/program/R10_preregistration.md")
    rec(f"B-{n:03d}", "R10 preregistration.md khop .sha256 va freeze.prereg", act==exp_h and (act==fz["prereg"]), f"file={act[:12]} sha256file={exp_h[:12]} freeze={fz['prereg'][:12]}"); n+=1
# ledger test khoa: khong doc noi dung, chi kiem ton tai + khong bi sua? (bo qua)
json.dump(res, open(pathlib.Path(__file__).with_name("results_b.json"),"w"), ensure_ascii=False, indent=1)
shutil.rmtree(tmp, ignore_errors=True)
print("TONG", len(res), "PASS", sum(r[2]=="PASS" for r in res), "FAIL", sum(r[2]=="FAIL" for r in res))
