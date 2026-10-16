#!/usr/bin/env python3
"""tokens_report.py - đếm token Claude (log Claude Code) + local (data/la/tokens.jsonl) -> docs/handoff/TOKENS.md + metric textfile.
Claude: message.usage của dòng assistant, khử trùng theo message.id (mỗi block lặp usage). Gồm cả subagent (jsonl lồng).
Số Claude là ĐO từ log; local đo từ usage của server nếu có, else ước lượng; tỉ lệ là xấp xỉ (tổng token thô, không quy đổi giá/cache)."""
import glob, json, os, time, collections
R = os.environ.get("TS_ROOT", "/root/trading-system")
OUT = f"{R}/docs/handoff/TOKENS.md"
PROM = os.environ.get("TOKENS_PROM", f"{R}/data/la/tokens.prom")  # root có thể symlink/copy vào textfile-exporter (/var/lib/tradingsys-backup/)
roots = [d for d in ("/home/cc/.claude/projects", "/root/.claude/projects") if os.path.isdir(d)]
seen = set(); day = collections.defaultdict(lambda: [0, 0, 0, 0, 0]); sess = collections.defaultdict(lambda: [0, 0, 0, 0, ""])
mdl = collections.defaultdict(lambda: [0, 0, 0, 0, 0])
for rt in roots:
    for p in glob.glob(f"{rt}/**/*.jsonl", recursive=True):
        b = os.path.basename(p)
        sid = (p.split("/subagents/")[0].rsplit("/", 1)[-1][:8] + "/" + b[6:12]) if "/subagents/" in p else b[:8]
        try: fh = open(p, errors="ignore")
        except Exception: continue
        for ln in fh:
            if '"usage"' not in ln: continue
            try: d = json.loads(ln)
            except Exception: continue
            m = d.get("message") or {}; u = m.get("usage")
            if not u or d.get("type") != "assistant": continue
            k = m.get("id") or d.get("uuid")
            if k in seen: continue
            seen.add(k)
            v = [u.get("input_tokens", 0), u.get("output_tokens", 0), u.get("cache_read_input_tokens", 0), u.get("cache_creation_input_tokens", 0)]
            dy = (d.get("timestamp") or "")[:10] or "?"
            for tgt in (day[dy], mdl[(dy, m.get("model", "?"))]):
                for i in range(4): tgt[i] += v[i]
                tgt[4] += 1
            s = sess[(dy, sid)]
            for i in range(4): s[i] += v[i]
            s[4] = m.get("model", "?")
loc = collections.defaultdict(lambda: [0, 0, 0]); locd = collections.defaultdict(lambda: [0, 0])
try:
    for ln in open(f"{R}/data/la/tokens.jsonl"):
        try: d = json.loads(ln)
        except Exception: continue
        dy = (d.get("ts") or "")[:10]
        pt = d.get("prompt_tokens", d.get("input_tokens", 0)) or 0; ct = d.get("completion_tokens", d.get("output_tokens", 0)) or 0
        t = d.get("task", "?")
        loc[(dy, t)][0] += pt; loc[(dy, t)][1] += ct; loc[(dy, t)][2] += 1
        locd[dy][0] += pt; locd[dy][1] += ct
except FileNotFoundError: pass
f = lambda n: f"{n:,}".replace(",", ".")
L = [f"# TOKENS (tự sinh {time.strftime('%Y-%m-%d %H:%M')}) - infra/ops/tokens_report.py", "",
     "Claude: ĐO từ log ~/.claude (input/output/cache_read/cache_creation, khử trùng theo message.id). Local: từ data/la/tokens.jsonl (usage do server trả; thiếu = 0).",
     "Tỉ lệ = local / (local + Claude input+output, KHÔNG tính cache_read) - XẤP XỈ, chưa lọc riêng task cơ học; mục tiêu >= 50% cho task cơ học.", "",
     "## Claude theo ngày", "| Ngày | Lượt | input | output | cache_read | cache_create |", "|---|---|---|---|---|---|"]
for dy in sorted(day, reverse=True)[:10]:
    a = day[dy]; L.append(f"| {dy} | {a[4]} | {f(a[0])} | {f(a[1])} | {f(a[2])} | {f(a[3])} |")
L += ["", "## Claude theo model (10 ngày gần nhất)", "| Ngày | Model | Lượt | input | output | cache_read |", "|---|---|---|---|---|---|"]
for (dy, m) in sorted(mdl, reverse=True)[:20]:
    a = mdl[(dy, m)]; L.append(f"| {dy} | {m} | {a[4]} | {f(a[0])} | {f(a[1])} | {f(a[2])} |")
L += ["", "## Claude theo phiên (top 15 theo output, mã phiên 8 ký tự đầu)", "| Ngày | Phiên | Model | input | output | cache_read |", "|---|---|---|---|---|---|"]
for (dy, sid), a in sorted(sess.items(), key=lambda x: -x[1][1])[:15]:
    L.append(f"| {dy} | {sid} | {a[4]} | {f(a[0])} | {f(a[1])} | {f(a[2])} |")
L += ["", "## Local theo ngày/loại task", "| Ngày | Task | Lượt | prompt | completion |", "|---|---|---|---|---|"]
for (dy, t) in sorted(loc, reverse=True)[:30]:
    a = loc[(dy, t)]; L.append(f"| {dy} | {t} | {a[2]} | {f(a[0])} | {f(a[1])} |")
if not loc: L.append("| - | (chưa có dữ liệu) | 0 | 0 | 0 |")
L += ["", "## Tỉ lệ local / (local + Claude)", "| Ngày | Local | Claude in+out | Tỉ lệ |", "|---|---|---|---|"]
tl = tc = 0
for dy in sorted(set(day) | set(locd), reverse=True)[:10]:
    lo = sum(locd[dy]) if dy in locd else 0; cl = (day[dy][0] + day[dy][1]) if dy in day else 0
    L.append(f"| {dy} | {f(lo)} | {f(cl)} | {100*lo/(lo+cl):.1f}% |" if lo + cl else f"| {dy} | 0 | 0 | - |")
for dy in locd: tl += sum(locd[dy])
for dy in day: tc += day[dy][0] + day[dy][1]
ratio = tl / (tl + tc) if tl + tc else 0
L += ["", f"Tổng: local {f(tl)}, Claude in+out {f(tc)}, tỉ lệ {100*ratio:.1f}%."]
open(OUT, "w").write("\n".join(L) + "\n")
today = time.strftime("%Y-%m-%d", time.gmtime())
P = ["# TYPE ts_claude_tokens_today gauge"]
for i, k in enumerate(("input", "output", "cache_read", "cache_creation")):
    P.append(f'ts_claude_tokens_today{{kind="{k}"}} {day[today][i] if today in day else 0}')
P += ["# TYPE ts_local_tokens_today gauge"]
for i, k in enumerate(("prompt", "completion")):
    P.append(f'ts_local_tokens_today{{kind="{k}"}} {locd[today][i] if today in locd else 0}')
P += ["# TYPE ts_local_token_ratio gauge", f"ts_local_token_ratio {ratio:.4f}", "# TYPE ts_tokens_report_timestamp gauge", f"ts_tokens_report_timestamp {int(time.time())}"]
try:
    tmp = PROM + ".tmp"; open(tmp, "w").write("\n".join(P) + "\n"); os.replace(tmp, PROM)
except Exception as e: print("prom skip:", e)
print("ok", len(seen), "lượt Claude")
