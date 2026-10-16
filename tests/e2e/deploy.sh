#!/bin/bash
# Day bo test len VPS: bash deploy.sh   (chay tu may dev; can SSH_JUMP)
T=/d/Work/Work-do/devops/claude-memory/tools
export SSH_JUMP=<BASTION_IP>
export MSYS_NO_PATHCONV=1; cd "$T" && node ssh-run.js <VPS_IP> "mkdir -p /root/qa-e2e/out"
for f in D:/Work/trading-system/tests/e2e/*.py D:/Work/trading-system/tests/e2e/*.sh; do
  node sftp-put.js <VPS_IP> "$f" /root/qa-e2e/$(basename $f) >/dev/null
done
echo deployed
