#!/bin/bash
# usage: put.sh <local path relative to mt-agent/lab> <remote path>
cd /d/Work/Work-do/devops/claude-memory/tools
export SSH_JUMP=<BASTION_IP> MSYS_NO_PATHCONV=1
node sftp-put.js <VPS_IP> "D:/Work/trading-system/mt-agent/lab/$1" "$2"
