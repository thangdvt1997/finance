#!/bin/sh
# Kiểm tra hardening các container tradingsys (user, read_only, cap_drop, no-new-privileges, giới hạn mem/pids, healthcheck, mạng).
# Dùng:  sh infra/ops/hardening_audit.sh        -> bảng + dòng "VI PHẠM" nếu có container chạy root / không read_only / không cap_drop / không giới hạn mem.
# Ngoại lệ có chủ đích ghi trong docs/HARDENING.md (docker-socket-proxy: không read_only; gatus: không healthcheck; cadvisor: root).
PROJ="${COMPOSE_PROJECT:-tradingsys}"
docker ps --filter "label=com.docker.compose.project=$PROJ" -q | xargs -r docker inspect --format \
 '{{.Name}}|u={{if .Config.User}}{{.Config.User}}{{else}}ROOT{{end}}|ro={{.HostConfig.ReadonlyRootfs}}|cap={{.HostConfig.CapDrop}}|nnp={{range .HostConfig.SecurityOpt}}{{.}}{{end}}|mem={{.HostConfig.Memory}}|pids={{.HostConfig.PidsLimit}}|hc={{if .Config.Healthcheck}}Y{{else}}N{{end}}|net={{range $k,$v := .NetworkSettings.Networks}}{{$k}},{{end}}' \
 | sed 's#^/tradingsys-##; s#tradingsys_##g' | sort | tee /tmp/hardening_audit.$$
echo "--- VI PHẠM (root / ro=false / cap không drop ALL / mem=0):"
awk -F'|' '$2=="u=ROOT"||$3=="ro=false"||$4!="cap=[ALL]"||$6=="mem=0"{print "  "$0}' /tmp/hardening_audit.$$
rm -f /tmp/hardening_audit.$$
