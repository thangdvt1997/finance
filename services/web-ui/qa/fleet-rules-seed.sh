#!/bin/sh
# Seed QA trang Luật & tuân thủ (chạy TRÊN VPS): 3 mẫu, 4 phép gán theo tài khoản cs-*, kết quả tuân thủ giả (xanh/vàng/đỏ/cũ). Dọn: sh fleet-rules-seed.sh clean
# Cần master thử đã đăng nhập: sh /root/fleet_login.sh qa-fleet-rseed
cat > /tmp/rules_seed.py <<'PY'
import json, subprocess, sys, time, datetime
J = "/tmp/qa-fleet/qa-fleet-rseed.cj"
def c(m, p, d=None):
    a = ["curl", "-s", "-b", J, "-H", "Origin: http://127.0.0.1:8580", "-H", "Content-Type: application/json", "-X", m, "http://127.0.0.1:8580/auth/admin" + p]
    if d is not None: a += ["-d", json.dumps(d)]
    for _ in range(10):
        r = subprocess.run(a, capture_output=True, text=True).stdout
        if r.strip(): break
        time.sleep(3)
    time.sleep(1.2)
    try: return json.loads(r)
    except Exception: return {}
def clean():
    for a in c("GET", "/rules/assignments").get("items", []):
        if a["template_name"].startswith("qa-fleet-"): c("DELETE", "/rules/assignments/" + a["id"])
    for t in c("GET", "/rules/templates").get("items", []):
        if t["name"].startswith("qa-fleet-"): c("DELETE", "/rules/templates/" + t["id"])
    for g in c("GET", "/groups").get("items", []):
        if g["name"].startswith("qa-fleet-"): c("DELETE", "/groups/" + g["id"])
    print("cleaned")
if sys.argv[1:] == ["clean"]:
    clean(); sys.exit(0)
clean()
pre = c("GET", "/rules/presets")["presets"]
def mk(n, i):
    r = c("POST", "/rules/templates", {"name": n, "kind": pre[i]["kind"], "params": pre[i]["params"], "description": "Mẫu thử QA"})
    if "id" not in r: print("ERR", n, r)
    return r
t1 = mk("qa-fleet-Lỗ ngày 5%", 0); t2 = mk("qa-fleet-Drawdown 10%", 3); t3 = mk("qa-fleet-Margin 150%", 6)
accs = [a["account_id"] for a in c("GET", "/fleet?limit=20")["items"] if a["label"].startswith("cs-")][:3]
c("POST", "/groups", {"name": "qa-fleet-Nhóm luật", "description": "", "color": "#f59e0b"})
def A(t, acc, en, nt):
    r = c("POST", "/rules/assignments", {"template_id": t["id"], "scope": {"type": "account", "ref": acc}, "enabled": en, "notify_client": nt})
    if "id" not in r: print("ERR assign", acc, r)
    return r
a1 = A(t1, accs[0], True, False); a1b = A(t1, accs[1], True, True); a2 = A(t2, accs[2], True, False); a3 = A(t3, accs[0], False, False); g = [x for x in c("GET", "/groups").get("items", []) if x["name"].startswith("qa-fleet-")]; c("POST", "/rules/assignments", {"template_id": t2["id"], "scope": {"type": "group", "ref": g[0]["id"]}, "enabled": True, "notify_client": False}) if g else None
now = datetime.datetime.now(datetime.timezone.utc)
reset = (now + datetime.timedelta(hours=3, minutes=12)).isoformat()
stale = (now - datetime.timedelta(minutes=25)).isoformat()
r = lambda acc, a, st, u, v, l, h, ev=None: {"account_id": acc, "assignment_id": a["id"], "status": st, "usage_pct": u, "value": v, "limit": l, "headroom": h, "unit": "%", "detail": {}, "reset_at": reset, "evaluated_at": ev or now.isoformat()}
json.dump({"results": [r(accs[0], a1, "red", 112.4, 5.62, 5, 0), r(accs[1], a1b, "yellow", 78.5, 3.9, 5, 1.1), r(accs[2], a2, "green", 22.3, 2.2, 10, 7.8, stale)], "conditions": []}, open("/tmp/rules_res.json", "w"))
print("seeded", len(accs), "accounts")
PY
python3 /tmp/rules_seed.py "$@" || exit 1
[ "$1" = clean ] && exit 0
docker exec -i -e D="$(base64 -w0 /tmp/rules_res.json)" tradingsys-auth python - <<'PY'
import os, urllib.request
rq = urllib.request.Request("http://127.0.0.1:8000/internal/fleet/results", data=__import__("base64").b64decode(os.environ["D"]), headers={"Authorization": "Bearer " + os.environ["FLEET_INTERNAL_TOKEN"], "Content-Type": "application/json"})
print(urllib.request.urlopen(rq).read().decode()[:200])
PY
