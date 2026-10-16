#!/bin/bash
# Usage: vps_run.sh script.py [args]  -- upload research/multiasset/*.py len VPS va chay trong container research-run (nice, 6 cpu, 16g)
cd /d/Work/Work-do/devops/claude-memory/tools || exit 1
export SSH_JUMP=<BASTION_IP> MSYS_NO_PATHCONV=1
for f in /d/Work/trading-system/research/multiasset/*.py /d/Work/trading-system/research/engine.py /d/Work/trading-system/research/strategies.py /d/Work/trading-system/research/pq.py; do b=$(basename $f); node sftp-put.js <VPS_IP> "$(cygpath -w $f)" /root/research/multiasset/$b >/dev/null; done
node ssh-run.js <VPS_IP> "cd /root/research/multiasset && docker run --rm --name research-run --cpus 6 --memory 16g -v /root/research:/root/research -w /root/research/multiasset -e PYTHONPATH=/root/research/pylib:/root/research/multiasset python:3.12-slim nice -n 19 python $* 2>&1 | tail -${TAILN:-120}"
