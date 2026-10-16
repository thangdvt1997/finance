"""Replay CSV qua detector, in sự kiện. Chạy trên VPS (xem dev_sync.sh).
   python tools/replay.py /fx/xxx.csv [KB-1,KB-2] [--states triggered,armed] [--from 2026-09-21] [--to 2026-10-07]"""
import sys
from pattern_engine.csvio import load_csv, parse_ts
from pattern_engine.detector import Detector
from pattern_engine.specs import load_specs

path = sys.argv[1]
enabled = [x for x in (sys.argv[2].split(",") if len(sys.argv) > 2 and sys.argv[2].startswith("KB") else [])] or None
states = {"triggered", "armed", "invalid", "forming"}
lo = hi = None
for k, a in enumerate(sys.argv):
    if a == "--states":
        states = set(sys.argv[k + 1].split(","))
    if a == "--from":
        lo = parse_ts(sys.argv[k + 1] + ("" if "T" in sys.argv[k + 1] else "T00:00:00Z"))
    if a == "--to":
        hi = parse_ts(sys.argv[k + 1] + ("" if "T" in sys.argv[k + 1] else "T00:00:00Z"))
trace = next((sys.argv[k + 1] for k, a in enumerate(sys.argv) if a == "--trace"), None)
d = Detector("XAUUSD", "M15", load_specs(), enabled)
bars = load_csv(path)
_last = {}
for b in bars:
    sigs = d.feed(b)
    if trace:
        for key, su in d.active.items():
            if trace in key:
                sig = "".join("+" if x["ok"] else "-" for x in su.steps)
                if _last.get(key) != sig and (not lo or b.ts >= lo) and (not hi or b.ts < hi):
                    _last[key] = sig
                    print("  TRACE", b.ts.strftime("%m-%d %H:%M"), key, su.state, sig, " | ".join(x["detail"] for x in su.steps[:5]))
    for sg in sigs:
        if sg.state in states and (not lo or sg.bar_ts >= lo) and (not hi or sg.bar_ts < hi):
            ok = "".join("+" if s["ok"] else "-" for s in sg.steps)
            print(sg.bar_ts.strftime("%m-%d %H:%M"), sg.pattern, sg.state, sg.score, ok, sg.setup_id, sg.reason or "")
print("bars", len(bars), "pivots", len(d.zz.pivots))
