#!/bin/bash
# usage: vnrun.sh script.py [args]   -- upload research/vn/*.py + engine.py/pq.py roi chay trong container tam research-vn
cd /d/Work/Work-do/devops/claude-memory/tools || exit 1
export SSH_JUMP=<BASTION_IP> MSYS_NO_PATHCONV=1
for f in /d/Work/trading-system/research/vn/*.py /d/Work/trading-system/research/engine.py /d/Work/trading-system/research/pq.py; do node sftp-put.js <VPS_IP> "$(cygpath -m $f)" /root/research/vn/$(basename $f) >/dev/null; done
node ssh-run.js <VPS_IP> "cd /root/research/vn && docker run --rm --name research-vn-$$ --cpus ${CPUS:-6} --memory 16g -v /root/research:/root/research -w /root/research/vn -e PYTHONPATH=/root/research/pylib:/root/research/vn python:3.12-slim nice -n 19 python -u $* 2>&1 | tail -${TAILN:-80}"
