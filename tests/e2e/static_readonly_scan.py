"""Quet tinh: khong co ma/duong nao DAT/SUA/DONG lenh trong repo (Python, MQL4/MQL5, YAML, compose).
Chay: python tests/e2e/static_readonly_scan.py [repo_root]   (khong can mang / Docker)
Exit 1 neu tim thay ky hieu dat lenh o file khong phai test/README."""
import os
import re
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", "..")
# ky hieu dat/sua/xoa/dong lenh cua MT4/MT5 va cac API broker pho bien
PATTERNS = {
    "mt5_py": r"\border_send\b|\border_check\b|\bpositions_close\b|\bTRADE_ACTION_(DEAL|PENDING|SLTP|MODIFY|REMOVE|CLOSE_BY)\b|\bmt5\.(Buy|Sell)\b",
    "mql4": r"\bOrderSend\s*\(|\bOrderClose\s*\(|\bOrderModify\s*\(|\bOrderDelete\s*\(|\bOrderCloseBy\s*\(",
    "mql5": r"\bOrderSend(Async)?\s*\(|\bCTrade\b|\bPositionClose(By)?\s*\(|\bPositionModify\s*\(|\bOrderDelete\s*\(|\bTradeRequest\b|\bMqlTradeRequest\b|#include\s*<Trade[\\/]",
    "generic": r"\b(place|submit|send|create|cancel|close|modify)_order\b|\bexecute_trade\b|\bmarket_order\b|/v\d+/orders?\b",
}
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "egg-info", ".pytest_cache"}
hits, scanned = [], 0
for d, dirs, files in os.walk(ROOT):
    dirs[:] = [x for x in dirs if x not in SKIP_DIRS and not x.endswith(".egg-info")]
    for f in files:
        ext = os.path.splitext(f)[1].lower()
        if ext not in {".py", ".mq4", ".mq5", ".mqh", ".yml", ".yaml", ".sh", ".json", ".toml", ".js", ".ts", ".html"}:
            continue
        p = os.path.join(d, f)
        rel = os.path.relpath(p, ROOT).replace("\\", "/")
        scanned += 1
        try:
            txt = open(p, encoding="utf-8", errors="ignore").read()
        except Exception:
            continue
        is_test = "/tests/" in "/" + rel or rel.startswith("tests/")
        for name, pat in PATTERNS.items():
            for m in re.finditer(pat, txt):
                line = txt.count("\n", 0, m.start()) + 1
                ctx = txt.splitlines()[line - 1].strip()[:110]
                hits.append((rel, line, name, m.group(0), ctx, is_test))
def _comment(h):
    c = h[4].lstrip()
    return c.startswith(("#", "//", "*")) or "KHONG" in c or "NOT " in c


comments = [h for h in hits if not h[5] and _comment(h)]
real = [h for h in hits if not h[5] and not _comment(h)]
for h in comments:
    print(f"  comment/docstring (khong phai ma) {h[0]}:{h[1]} {h[3]!r}")
print(f"scanned {scanned} files; hits total={len(hits)} (trong tests={len(hits)-len(real)}), ngoai tests={len(real)}")
for h in real:
    print(f"  CODE  {h[0]}:{h[1]} [{h[2]}] {h[3]!r}  | {h[4]}")
for h in [x for x in hits if x[5]][:15]:
    print(f"  test  {h[0]}:{h[1]} [{h[2]}] {h[3]!r}  | {h[4]}")
# test ton tai de chan hoi quy
guards = [os.path.join(ROOT, "services/mt-bridge/tests")]
for g in guards:
    if os.path.isdir(g):
        txt = "".join(open(os.path.join(g, f), encoding="utf-8", errors="ignore").read() for f in os.listdir(g) if f.endswith(".py"))
        print("guard test_no_trading_code_anywhere:", "test_no_trading_code_anywhere" in txt, "| test_gateway_is_read_only:", "test_gateway_is_read_only" in txt)
sys.exit(1 if real else 0)
