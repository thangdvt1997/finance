#!/usr/bin/env python3
"""digest.py - tóm tắt thay đổi bằng LLM local -> docs/handoff/DIGEST.md (<=60 dòng).
Thu: git log mới, *_status.md đổi, status_brief.sh. LLM lỗi => xuất bản không-LLM.
Env: LA_LLM_URL (mặc định http://local-llm:8080; fallback http://tradingsys-briefing-llm:8080),
LA_LLM_MODEL (general), DIGEST_MAXLOAD (60), DIGEST_LLM_TIMEOUT (240)."""
import json, os, subprocess, sys, time, urllib.request, shutil
R = os.environ.get("TS_ROOT", "/root/trading-system")
H = f"{R}/docs/handoff"; OUT = f"{H}/DIGEST.md"; HIST = f"{H}/digest_history"
ST = f"{R}/data/la/digest_state.json"
MAXLOAD = float(os.environ.get("DIGEST_MAXLOAD", 60))

def sh(c, t=60):
    try: return subprocess.run(c, shell=True, capture_output=True, text=True, timeout=t, cwd=R).stdout
    except Exception as e: return f"(lỗi: {e})"

def llm(prompt):
    urls = [os.environ.get("LA_LLM_URL") or "http://local-llm:8080", "http://tradingsys-briefing-llm:8080"]
    models = [os.environ.get("LA_LLM_MODEL", "general"), "briefing"]
    for u, m in zip(urls, models):
        try:
            body = json.dumps({"model": m, "temperature": 0.2, "max_tokens": 500, "messages": [
                {"role": "system", "content": "Bạn tóm tắt tiến độ dự án bằng tiếng Việt, ngắn gọn, gạch đầu dòng, không bịa."},
                {"role": "user", "content": prompt}]}).encode()
            rq = urllib.request.Request(u.rstrip("/") + "/v1/chat/completions", body, {"Content-Type": "application/json"})
            d = json.load(urllib.request.urlopen(rq, timeout=float(os.environ.get("DIGEST_LLM_TIMEOUT", 240))))
            txt = d["choices"][0]["message"]["content"].strip()
            us = d.get("usage", {})
            try:
                os.makedirs(f"{R}/data/la", exist_ok=True)
                with open(f"{R}/data/la/tokens.jsonl", "a") as f:
                    f.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "task": "digest", "model": m,
                        "prompt_tokens": us.get("prompt_tokens", 0), "completion_tokens": us.get("completion_tokens", 0)}) + "\n")
            except Exception: pass
            return txt, m
        except Exception:
            continue
    return None, None

def main():
    if os.getloadavg()[0] > MAXLOAD:
        print("load cao, bỏ qua"); return
    os.makedirs(os.path.dirname(ST), exist_ok=True)
    try: st = json.load(open(ST))
    except Exception: st = {}
    since = st.get("ts", time.time() - 3600)
    iso = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(since))
    log = sh(f"git log --since='{iso}' --no-merges --format='%h %s' | cut -c1-110 | head -40").strip()
    changed = []
    for fn in sorted(os.listdir(H)):
        if fn.endswith("_status.md") or fn in ("PROGRESS.md", "QA_ISSUES.md"):
            p = f"{H}/{fn}"
            if os.path.getmtime(p) > since:
                tail = "".join(open(p, errors="ignore").readlines()[-12:])[:700]
                changed.append(f"### {fn}\n{tail}")
    brief = sh("bash infra/ops/status_brief.sh 2>/dev/null | cut -c1-200 | head -20", 30).strip()
    now = time.strftime("%Y-%m-%d %H:%M", time.localtime())
    quiet = not log and not changed
    summ, model = (None, None)
    if not quiet:
        prompt = f"Commit mới:\n{log or '(không)'}\n\nTệp trạng thái đổi:\n{chr(10).join(changed)[:3500] or '(không)'}\n\nTóm tắt <=12 gạch đầu dòng: việc xong, việc lỗi/chặn, điều cần người dùng quyết."
        summ, model = llm(prompt)
    lines = [f"# DIGEST ({now}) - tự sinh, đọc tệp này thay vì thăm dò", "",
             f"Nguồn tóm tắt: {'LLM local ('+model+')' if summ else 'không-LLM (LLM không sẵn sàng hoặc không có thay đổi)'}; chu kỳ từ {iso}.", "",
             "## Trạng thái nhanh", "```"] + brief.splitlines()[:14] + ["```", "", "## Tóm tắt thay đổi"]
    if quiet: lines.append("- Không có commit/tệp trạng thái mới kể từ lần trước.")
    elif summ: lines += summ.splitlines()[:20]
    else:
        lines += [f"- {l}" for l in log.splitlines()[:15]]
        lines += [f"- tệp trạng thái đổi: {c.splitlines()[0][4:]}" for c in changed[:8]]
    lines = [l[:200] for l in lines][:60]
    os.makedirs(HIST, exist_ok=True)
    if os.path.exists(OUT) and not quiet:
        shutil.copy(OUT, f"{HIST}/DIGEST_{time.strftime('%Y%m%d_%H%M', time.localtime(os.path.getmtime(OUT)))}.md")
        for old in sorted(os.listdir(HIST))[:-24]: os.remove(f"{HIST}/{old}")
    open(OUT, "w").write("\n".join(lines) + "\n")
    json.dump({"ts": time.time()}, open(ST, "w"))
    print("ok", len(lines), "dòng", "llm=" + str(model))

if __name__ == "__main__":
    main()
