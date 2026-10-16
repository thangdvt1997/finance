#!/bin/bash
# Đồng bộ services/pattern-engine (+ libs/common khi đổi) lên VPS (/root/pe_dev/w) và chạy lệnh trong container python tạm. KHÔNG chạy gì trên laptop.
#   tools/dev_sync.sh "pytest -q"        |  tools/dev_sync.sh "sh tools/an.sh"
# Đường truyền tới VPS hay ECONNRESET với file lớn (sftp/stdin) -> tải bằng base64 chia mảnh nhỏ qua ssh-run (mỗi mảnh thử lại).
cd /d/Work/trading-system
export MSYS_NO_PATHCONV=1
T=/d/Work/Work-do/devops/claude-memory/tools
PE=services/pattern-engine
H=<VPS_IP>
W=/tmp/pe-sync-$$; mkdir -p $W; trap 'rm -rf $W' EXIT

ssh1() {  # ssh1 "<lệnh>": thử trực tiếp rồi qua bastion, tối đa 6 lần
  for n in 1 2 3 4 5 6; do
    ( cd $T && node ssh-run.js $H "$1" ) && return 0
    ( cd $T && SSH_JUMP=<BASTION_IP> node ssh-run.js $H "$1" ) && return 0
    sleep 3
  done
  return 1
}

put() {   # put <file> <remote>: base64 mảnh 15000 ký tự, ghép trên VPS, kiểm tra md5
  local f=$1 r=$2 want i=0
  want=$(md5sum < "$f" | cut -c1-32)
  base64 -w0 "$f" > $W/b64
  rm -f $W/part-*; split -b 15000 -d -a 3 $W/b64 $W/part-
  ssh1 "rm -f $r.b64; : > $r.b64" || return 1
  for p in $W/part-*; do
    ssh1 "printf '%s' '$(cat $p)' >> $r.b64" || { echo "mảnh lỗi $p" >&2; return 1; }
  done
  ssh1 "base64 -d $r.b64 > $r && test \$(md5sum < $r | cut -c1-32) = $want && echo PUT_OK" | grep -q PUT_OK
}

# 1) mã pattern-engine (nén -9, không fixture)
tar --exclude=__pycache__ --exclude='*.pyc' --exclude='*.egg-info' --exclude=.pytest_cache --exclude=$PE/tests/fixtures -cf - $PE | gzip -9n > $W/pe.tgz
put $W/pe.tgz /root/pe-dev.tgz || { echo "tải pe.tgz thất bại" >&2; exit 3; }
# 2) libs/common + fixture: chỉ tải lại khi đổi
CH=$(cat libs/common/src/tscommon/*.py | md5sum | cut -c1-12)
if [ ! -f /tmp/pe-common-$CH ]; then
  tar --exclude=__pycache__ --exclude='*.egg-info' --exclude=tests -cf - libs/common | gzip -9n > $W/common.tgz
  put $W/common.tgz /root/pe-common.tgz || exit 3
  ssh1 "rm -rf /root/pe_dev/common && mkdir -p /root/pe_dev/common && tar xzf /root/pe-common.tgz -C /root/pe_dev/common" && touch /tmp/pe-common-$CH
fi
FH=$(cat $PE/tests/fixtures/* | md5sum | cut -c1-12)
if [ ! -f /tmp/pe-fx-$FH ]; then
  tar -C $PE/tests/fixtures -cf - . | gzip -9n > $W/fx.tgz
  put $W/fx.tgz /root/pe-fx.tgz || exit 3
  ssh1 "mkdir -p /root/pe_fx/fixtures && tar xzf /root/pe-fx.tgz -C /root/pe_fx/fixtures" && touch /tmp/pe-fx-$FH
fi
# 3) chạy
CMD="${1:-pytest -q}"
ssh1 "set -e; mkdir -p /root/pe_dev && cd /root/pe_dev && rm -rf w && mkdir w && tar xzf /root/pe-dev.tgz -C w && cp -r common/libs w/libs; docker image inspect pe-dev >/dev/null 2>&1 || docker build -q -t pe-dev -f w/services/pattern-engine/tools/dev.Dockerfile w >/dev/null; mkdir -p w/services/pattern-engine/tests/fixtures; cp /root/pe_fx/fixtures/* w/services/pattern-engine/tests/fixtures/ 2>/dev/null || true; docker run --rm -v /root/pe_dev/w:/w -v /root/pe_fx:/fx:ro -w /w/services/pattern-engine -e PYTHONPATH=/w/libs/common/src:/w/services/pattern-engine/src:/w/services/pattern-engine -e PYTHONDONTWRITEBYTECODE=1 pe-dev sh -c '$CMD'"
