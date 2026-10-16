"""Tiến trình con: chạy 1 job (python -m ai_trading_worker.run_job <job_id>)."""
import re
import sys

from .runner import run_job

if __name__ == "__main__":
    if len(sys.argv) != 2 or not re.fullmatch(r"[0-9a-f]{32}", sys.argv[1]):
        sys.exit(2)
    sys.exit(run_job(sys.argv[1]))
