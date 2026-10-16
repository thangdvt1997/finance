"""Vòng lặp worker: nhặt job `queued` cũ nhất trong /state/jobs, chạy TỪNG JOB MỘT trong tiến trình con (nice 15, timeout cứng, kill nhóm tiến trình).
Trạng thái job: queued -> running -> done | failed (timeout cũng là failed, error=timeout). Heartbeat: /state/worker.heartbeat (healthcheck)."""
from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from ai_trading.scenario_store import Store, atomic_write, now

log = logging.getLogger("ai-trading-worker")
STATE = os.getenv("AI_STATE_DIR", "/state")
TIMEOUT_S = int(os.getenv("AI_JOB_TIMEOUT_S", str(25 * 60)))
POLL_S = 3.0


def beat() -> None:
    try:
        atomic_write(Path(STATE) / "worker.heartbeat", str(int(time.time())).encode())
    except OSError:
        pass


def set_job(store: Store, j: dict, **kw) -> None:
    j.update(kw)
    atomic_write(store.jdir / f"{j['id']}.json", json.dumps(j).encode())


def recover(store: Store) -> None:
    for j in store.jobs():
        if j.get("status") == "running":      # worker khởi động lại giữa chừng: không biết đã chạy tới đâu -> failed (test khoá vẫn tính là đã mở nếu marker tồn tại)
            set_job(store, j, status="failed", stage="failed", finished_at=now(), error="worker_restart", message="Worker khởi động lại giữa chừng; hãy chạy lại.")


def run_one(store: Store, j: dict) -> None:
    jid = j["id"]
    set_job(store, j, status="running", stage="start", started_at=now(), progress=0.0, message="Bắt đầu")
    cmd = ["nice", "-n", "15", sys.executable, "-m", "ai_trading_worker.run_job", jid]
    p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, start_new_session=True)  # noqa: S603
    t0 = time.time()
    while p.poll() is None:
        beat()
        if time.time() - t0 > TIMEOUT_S:
            os.killpg(p.pid, signal.SIGKILL)
            p.wait()
            cur = store.job(jid) or j
            set_job(store, cur, status="failed", stage="failed", finished_at=now(), error="timeout", message=f"Quá thời gian tối đa {TIMEOUT_S // 60} phút: đã dừng job.")
            log.warning("job %s timeout", jid)
            return
        time.sleep(1.0)
    cur = store.job(jid) or j
    if cur.get("status") == "running":
        err = (p.stderr.read() or b"")[-300:].decode("utf-8", "replace") if p.stderr else ""
        log.error("job %s exit=%s %s", jid, p.returncode, err.replace("\n", " | ")[-200:])
        set_job(store, cur, status="failed", stage="failed", finished_at=now(), error=f"exit_{p.returncode}", message=f"Job dừng bất thường (mã {p.returncode}).")


def main() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s %(message)s")
    store = Store(STATE)
    (Path(STATE) / "jobs").mkdir(parents=True, exist_ok=True)
    recover(store)
    log.info("worker sẵn sàng (timeout job %ss)", TIMEOUT_S)
    while True:
        beat()
        q = [j for j in store.jobs() if j.get("status") == "queued"]
        if q:
            run_one(store, q[0])
        else:
            time.sleep(POLL_S)


if __name__ == "__main__":
    main()
