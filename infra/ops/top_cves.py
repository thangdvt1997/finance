#!/usr/bin/env python3
"""In CVE CRITICAL/HIGH nổi bật (có bản vá) từ thư mục JSON của trivy_scan.sh. Dùng: top_cves.py <dir> [N]"""
import glob, json, os, sys
d = sys.argv[1]; n = int(sys.argv[2]) if len(sys.argv) > 2 else 6
for f in sorted(glob.glob(os.path.join(d, "*.json"))):
    j = json.load(open(f)); rows = {}
    for r in j.get("Results") or []:
        for v in r.get("Vulnerabilities") or []:
            k = (v["Severity"], v["PkgName"], v["InstalledVersion"], v.get("FixedVersion", "-"))
            rows.setdefault(k, []).append(v["VulnerabilityID"])
    order = {"CRITICAL": 0, "HIGH": 1}
    top = sorted(rows.items(), key=lambda kv: (order[kv[0][0]], kv[0][3] == "-", -len(kv[1])))[:n]
    print(f"## {os.path.basename(f)[:-5]}")
    for (sev, pkg, ins, fix), ids in top:
        print(f"  {sev:8} {pkg} {ins} -> fix {fix} ({len(ids)} CVE, vd {ids[0]})")
