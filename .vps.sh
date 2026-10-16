#!/bin/bash
# helper tạm: bash .vps.sh "<lệnh>"
cd /d/Work/Work-do/devops/claude-memory/tools && export SSH_JUMP=<BASTION_IP> MSYS_NO_PATHCONV=1 && node ssh-run.js <VPS_IP> "$1"
