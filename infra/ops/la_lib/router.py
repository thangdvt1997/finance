"""Router chính sách: Dễ/Vừa/Khó theo luật; ghi bảng quyết định; thống kê."""
import json, time
from collections import defaultdict
from .llm import DATA

EASY = {"fix-lint", "summarize", "commit-msg", "explain-error", "triage-log", "run-tests", "docs"}
MEDIUM = {"add-test", "issue-fix"}
HARD_WORDS = ("race", "deadlock", "schema", "migration", "security", "auth", "concurren", "thiết kế", "design")
MAX_LOCAL_TRIES = 2     # N: số lần local trước khi leo thang với mức Vừa


def classify(kind, n_files=1, has_repro=False, text=""):
    """-> (level, lý do). Luật: loại task; số file; có test tái hiện; từ khoá khó."""
    t = (text or "").lower()
    if any(w in t for w in HARD_WORDS):
        return "Khó", "chứa từ khoá thiết kế/bảo mật/đồng thời"
    if n_files > 3:
        return "Khó", f"{n_files} file > 3"
    if kind in EASY and n_files <= 1:
        return "Dễ", "task cơ học 1 file"
    if kind in EASY:
        return "Vừa", f"task cơ học nhưng {n_files} file"
    if kind in MEDIUM:
        return ("Vừa", "có test tái hiện") if has_repro or kind == "add-test" else ("Khó", "không có test tái hiện")
    return "Khó", "loại task lạ"


def record(kind, level, reason, route, outcome, tries=1, secs=0.0, note=""):
    DATA.mkdir(parents=True, exist_ok=True)
    rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "kind": kind, "level": level, "reason": reason,
           "route": route, "outcome": outcome, "tries": tries, "secs": round(secs, 1), "note": note[:300]}
    with open(DATA / "decisions.jsonl", "a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def execute(kind, runner, n_files=1, has_repro=False, text=""):
    """runner(try_no)->(ok,note). Dễ->local 1 lần; Vừa->local tối đa N rồi leo thang; Khó->cần Claude."""
    level, reason = classify(kind, n_files, has_repro, text)
    t0 = time.time()
    if level == "Khó":
        record(kind, level, reason, "claude", "cần Claude", 0, 0, reason)
        print(f"[router] Khó ({reason}) -> CẦN CLAUDE, không chạy local.")
        return False
    tries = 1 if level == "Dễ" else MAX_LOCAL_TRIES
    note = ""
    for i in range(1, tries + 1):
        ok, note = runner(i)
        if ok:
            record(kind, level, reason, "local", "ok", i, time.time() - t0, note)
            return True
    esc = "leo thang Claude" if level == "Vừa" else "local thất bại"
    record(kind, level, reason, "claude" if level == "Vừa" else "local", esc, tries, time.time() - t0,
           f"sau {tries} lần local: {note}")
    print(f"[router] {level}: {esc} — lý do: {note[:200]}")
    return False


def stats():
    f = DATA / "decisions.jsonl"
    rows = [json.loads(l) for l in f.read_text().splitlines() if l.strip()] if f.exists() else []
    agg = defaultdict(lambda: defaultdict(int))
    for r in rows:
        a = agg[r["kind"]]
        a["n"] += 1
        a["ok" if r["outcome"] == "ok" else ("esc" if "Claude" in r["outcome"] else "fail")] += 1
    print(f"{'loại task':14}{'tổng':>6}{'local ok':>10}{'leo thang/Claude':>18}{'thất bại':>10}{'tỉ lệ ok':>10}")
    for k, a in sorted(agg.items()):
        print(f"{k:14}{a['n']:>6}{a['ok']:>10}{a['esc']:>18}{a['fail']:>10}{a['ok']*100//a['n']:>9}%")
    if not rows:
        print("(chưa có dữ liệu)")
