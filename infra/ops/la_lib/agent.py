"""Agent vòng lặp nhỏ: JSON-action, tối đa N bước, timeout tổng; thay đổi chỉ trong worktree nhánh la/<task>."""
import re, subprocess, time
from pathlib import Path
from . import llm
from .tools import Tools

SYS = """Bạn là agent sửa mã nhỏ. Mỗi lượt trả về DUY NHẤT một JSON, không giải thích thêm:
{"tool": "<tên>", "args": {...}}  hoặc  {"final": "<tóm tắt ngắn việc đã làm>"}
Công cụ: read_file(path,start,end) write_file(path,content: TOÀN BỘ nội dung file) grep(pattern,path) list_dir(path) git_diff() run_tests(service) run_lint(path).
Quy tắc: sửa tối thiểu; đọc file trước khi ghi; không đụng .env/secret; chạy run_lint/run_tests liên quan rồi mới final."""


def sh(args, cwd, check=True):
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    if check and r.returncode:
        raise RuntimeError(f"{' '.join(args)}: {r.stderr[-300:]}")
    return r.stdout


def make_worktree(root: Path, task: str):
    name = re.sub(r"[^a-z0-9._-]", "-", task.lower())[:50]
    wt = llm.DATA / "work" / name
    br = f"la/{name}"
    if wt.exists():
        sh(["git", "worktree", "remove", "--force", str(wt)], root, check=False)
    sh(["git", "branch", "-D", br], root, check=False)
    wt.parent.mkdir(parents=True, exist_ok=True)
    sh(["git", "worktree", "add", "-b", br, str(wt), "HEAD"], root)
    return wt, br


def run_agent(root, task, goal, check, max_steps=12, budget_s=1500, kind="agent"):
    """check(wt)->(ok, msg): kiểm tra BẮT BUỘC (pytest/lint) sau khi agent kết thúc. Trả dict kết quả."""
    wt, br = make_worktree(Path(root), task)
    tools = Tools(wt, root)
    msgs = [{"role": "system", "content": SYS}, {"role": "user", "content": goal}]
    t0, steps, final = time.time(), 0, None
    while steps < max_steps and time.time() - t0 < budget_s:
        steps += 1
        out = llm.chat(msgs, kind=kind, max_tokens=3000)
        act = llm.extract_json(out)
        msgs.append({"role": "assistant", "content": out[:3000]})
        if not act:
            msgs.append({"role": "user", "content": "Không phải JSON hợp lệ. Trả lại đúng một JSON."})
            continue
        if "final" in act:
            final = act["final"]
            break
        res = tools.call(act.get("tool", ""), act.get("args") or {})
        msgs.append({"role": "user", "content": "KẾT QUẢ:\n" + res})
    diff = tools.git_diff()
    ok, msg = (False, "agent không sửa file nào") if not tools.written else check(wt)
    return {"ok": ok, "msg": msg, "branch": br, "worktree": str(wt), "steps": steps, "final": final,
            "diff": diff, "files": sorted(tools.written)}


def commit(res, message):
    wt = res["worktree"]
    sh(["git", "add", "--"] + res["files"], wt)
    sh(["git", "-c", "user.name=la-local", "-c", "user.email=la@local", "commit", "-q", "-m",
        message + "\n\nCo-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"], wt)
