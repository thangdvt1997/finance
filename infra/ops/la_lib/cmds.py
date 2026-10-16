"""Các lệnh la."""
import re, subprocess, sys
from pathlib import Path
from . import llm, router, tools as T
from .agent import run_agent, commit

ROOT = llm.ROOT


def svc_of(path):
    m = re.match(r"(?:\./)?services/([^/]+)/", str(path))
    if m:
        return m.group(1)
    return "common" if str(path).startswith("libs/common") else None


def head_tail(txt, n=6000):
    return txt if len(txt) <= n else txt[: n // 2] + "\n...[cắt]...\n" + txt[-n // 2:]


def ask(kind, instr, body, max_tokens=700):
    return llm.chat([{"role": "system", "content": "Trả lời tiếng Việt, ngắn gọn, chính xác, không bịa."},
                     {"role": "user", "content": f"{instr}\n\n---\n{body}"}], kind=kind, max_tokens=max_tokens)


def simple(kind, a, instr, body_fn, n_files=1):
    """Lệnh 1 lượt (Dễ). --dry-run: chỉ in quyết định router."""
    lvl, why = router.classify(kind, n_files)
    if a.dry_run:
        print(f"[dry-run] {kind}: mức {lvl} ({why}); sẽ chạy local, không ghi gì.")
        return 0
    body = body_fn()
    out = {}

    def runner(i):
        out["t"] = ask(kind, instr, head_tail(body))
        return bool(out["t"].strip()), "ok"
    router.execute(kind, runner, n_files)
    print(out.get("t", ""))
    return 0


def c_summarize(a):
    return simple("summarize", a, "Tóm tắt tệp sau trong tối đa 8 gạch đầu dòng.",
                  lambda: (ROOT / a.file).read_text(errors="replace") if not Path(a.file).is_absolute()
                  else Path(a.file).read_text(errors="replace"))


def c_explain(a):
    return simple("explain-error", a, "Giải thích lỗi này: nguyên nhân khả dĩ nhất và cách sửa (tối đa 6 dòng).",
                  lambda: Path(a.file).read_text(errors="replace") if a.file else sys.stdin.read())


def c_triage(a):
    def body():
        names = subprocess.run(["docker", "ps", "--format", "{{.Names}}"], capture_output=True, text=True).stdout.split()
        cand = [n for n in names if n in (f"tradingsys-{a.service}", f"tradingsys-{a.service}-1")] or \
               [n for n in names if n.startswith(f"tradingsys-{a.service}")]
        if not cand:
            return f"(không tìm thấy container tradingsys-{a.service}*)"
        r = subprocess.run(["docker", "logs", "--tail", "2000", cand[0]], capture_output=True, text=True)
        lines = [l for l in (r.stdout + r.stderr).splitlines()
                 if re.search(r"error|warn|traceback|exception|fail|timeout", l, re.I)]
        seen, uniq = {}, []
        for l in lines:
            k = re.sub(r"\d+", "#", l)[:120]
            seen[k] = seen.get(k, 0) + 1
            if seen[k] == 1:
                uniq.append((k, l[:300]))
        out = ["[x%d] %s" % (seen[k], l) for k, l in uniq[-40:]]
        return "\n".join(out) or "(không có dòng lỗi)"
    return simple("triage-log", a, f"Phân loại lỗi trong log service {a.service}: nhóm theo nguyên nhân, mức nghiêm trọng "
                  "(cao/vừa/thấp), nêu việc nên làm. Tối đa 10 dòng.", body)


def c_commit(a):
    def body():
        d = subprocess.run(["git", "diff", "--cached"], cwd=ROOT, capture_output=True, text=True).stdout
        return d or subprocess.run(["git", "diff", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout
    return simple("commit-msg", a, "Viết commit message tiếng Việt không dấu hoặc có dấu, kiểu 'feat|fix|docs(scope): mô tả' "
                  "(dòng đầu <= 72 ký tự, thêm tối đa 3 gạch đầu dòng chi tiết). Chỉ in message.", body)


def c_run_tests(a):
    if a.dry_run:
        print(f"[dry-run] chạy pytest {a.service} trong container tạm, tóm tắt FAIL bằng LLM local.")
        return 0
    r = T.run_tests(ROOT, a.service)
    print(r[-1500:])
    if r.startswith("rc=0"):
        print("=> XANH")
        router.record("run-tests", "Dễ", "task cơ học", "local", "ok")
        return 0
    return simple("run-tests", a, "Tóm tắt các test FAIL: test nào, vì sao, file nào nên xem (tối đa 8 dòng).", lambda: r)


def _finish(kind, task, a, goal, check, msg, n_files=1, has_repro=False, text=""):
    lvl, why = router.classify(kind, n_files, has_repro, text)
    if a.dry_run:
        print(f"[dry-run] {kind}/{task}: mức {lvl} ({why}). Sẽ tạo worktree nhánh la/{task}, agent tối đa "
              f"{a.max_steps} bước, check bắt buộc; không tự merge.")
        return 0
    res = {}

    def runner(i):
        r = run_agent(ROOT, f"{task}-{i}" if i > 1 else task, goal, check, max_steps=a.max_steps, kind=kind)
        res.update(r)
        print(f"[la] lần {i}: ok={r['ok']} bước={r['steps']} nhánh={r['branch']} — {r['msg'][:150]}")
        return r["ok"], r["msg"]
    ok = router.execute(kind, runner, n_files, has_repro, text)
    if not ok:
        return 1
    print("\n=== DIFF (chưa áp dụng vào main) ===\n" + res["diff"])
    if not a.review:
        commit(res, msg)
        print(f"\nĐÃ commit trên nhánh {res['branch']} (worktree {res['worktree']}); test/lint XANH.\n"
              f"ĐỀ XUẤT MERGE (người/Claude duyệt): git -C {ROOT} merge --no-ff {res['branch']}")
    else:
        print(f"[--review] không commit. Worktree: {res['worktree']}")
    return 0


def _check_for(paths, svcs):
    def check(wt):
        lr = T.lint(wt, paths)
        if not lr.startswith("rc=0"):
            return False, "lint đỏ: " + lr[-300:]
        for s in svcs:
            tr = T.run_tests(wt, s)
            if not tr.startswith("rc=0"):
                return False, f"pytest {s} đỏ: " + tr[-300:]
        return True, "lint + pytest xanh"
    return check


def c_fix_lint(a):
    target = a.path or "."
    lr = T.lint(ROOT, [target])
    if lr.startswith("rc=0"):
        print("Lint sạch, không cần sửa.")
        return 0
    svcs = [s for s in [svc_of(target)] if s]
    goal = f"Sửa các lỗi lint sau (ruff E9,F) trong repo, tối thiểu:\n{lr}\nSau khi sửa chạy run_lint."
    return _finish("fix-lint", "fix-lint", a, goal, _check_for([target], svcs), "fix(lint): sửa lỗi ruff do la local",
                   text=lr[:200]) if not a.dry_run else _finish("fix-lint", "fix-lint", a, goal, None, "")


def c_add_test(a):
    s = svc_of(a.file)
    goal = (f"Viết 1 file test pytest mới cho {a.file} (đặt ở thư mục tests cùng service, tên test_la_*.py). "
            f"Đọc file trước. Test đơn giản, không cần mạng/DB. Rồi run_tests({s}).")
    return _finish("add-test", "add-test-" + Path(a.file).stem, a, goal,
                   _check_for([str(Path(a.file).parent)], [s] if s else []), f"test: them test cho {a.file} (la local)")


def c_docs(a):
    slug = re.sub(r"[^a-z0-9]+", "_", a.topic.lower())
    goal = (f"Viết tài liệu ngắn (<= 60 dòng, tiếng Việt, markdown) về chủ đề '{a.topic}' vào docs/la_{slug}.md. "
            "Dùng grep/read_file để lấy thông tin thật từ repo; không bịa; không ghi secret.")
    ok = lambda wt: (True, "docs đã ghi")
    return _finish("docs", "docs-" + re.sub(r"[^a-z0-9]+", "-", a.topic.lower())[:30], a, goal, ok,
                   f"docs: {a.topic} (la local)")


def c_issue_fix(a):
    qa = (ROOT / "docs/handoff/QA_ISSUES.md").read_text().splitlines()
    hit = [l for l in qa if a.code in l]
    if not hit:
        print(f"Không thấy '{a.code}' trong QA_ISSUES.md")
        return 2
    line = hit[0]
    files = re.findall(r"[\w./-]+\.(?:py|yml|yaml|md|sh|jsx?)", line)
    svcs = sorted({s for f in files for s in [svc_of(f)] if s})
    goal = (f"Lỗi cần sửa (từ QA_ISSUES.md): {line}\nSửa tối thiểu, chỉ file liên quan; rồi run_lint và run_tests.")
    return _finish("issue-fix", "issue-" + re.sub(r"\W+", "-", a.code)[:30], a, goal,
                   _check_for(files or ["."], svcs), f"fix: {a.code} (la local)", n_files=max(1, len(files)),
                   has_repro=bool(svcs), text=line)
