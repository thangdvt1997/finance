#!/bin/bash
cd /d/Work/Work-do/devops/claude-memory/tools
export SSH_JUMP=<BASTION_IP> MSYS_NO_PATHCONV=1
node ssh-run.js <VPS_IP> "$1" 2>&1 | cut -c1-${2:-400}
