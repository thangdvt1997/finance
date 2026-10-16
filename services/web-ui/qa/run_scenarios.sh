#!/bin/sh
set -e
SRC=$(cd "$(dirname "$0")" && pwd); W=/tmp/qa-ui-scen; mkdir -p $W && chmod 700 $W && cp $SRC/scenarios.mjs $W/; NAME=qa-ui-scen
rm -rf $W/out; U=$(id -u):$(id -g)
docker exec -i tradingsys-auth python - delete $NAME < $SRC/master_user.py >/dev/null 2>&1 || true
docker exec -i tradingsys-auth python - create $NAME < $SRC/master_user.py > $W/pw.txt; chmod 600 $W/pw.txt
RC=0
timeout 500 docker run --rm --name qa-ui-scen-$$ --network host -v "$W:/work" -w /work -e MOCK -e QA_USER=$NAME \
  mcr.microsoft.com/playwright:v1.49.0-jammy sh -c "[ -d node_modules/playwright ] || npm i --no-save --silent playwright@1.49.0; QA_PASS=\$(cat pw.txt) node scenarios.mjs; RC=\$?; chown -R $U out; exit \$RC" || RC=$?
docker exec -i tradingsys-auth python - delete $NAME < $SRC/master_user.py >/dev/null 2>&1 || true
rm -f $W/pw.txt; exit $RC
