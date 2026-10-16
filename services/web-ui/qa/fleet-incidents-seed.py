"""Seed/dọn sự cố THỬ cho QA trang Sự cố (chạy TRONG container auth; khoá có tiền tố qa-fleet-inc-):
   docker exec -i tradingsys-auth python - seed  < fleet-incidents-seed.py
   docker exec -i tradingsys-auth python - clean < fleet-incidents-seed.py
Dùng API nội bộ POST /internal/fleet/results (conditions[]). `clean` đóng (tự đóng) bằng severity "ok". Không đụng tài khoản demo mt5:99000001."""
import json
import os
import sys
import urllib.request

TOK = os.environ["FLEET_INTERNAL_TOKEN"]
ACCS = ["mt5:100596106", "mt5:98596106", "mt5:99596106"]
SPEC = []
for a in ACCS:   # cụm 3 tài khoản cùng lỗi
    SPEC.append((f"budget:qa-fleet-inc-eq:{a}", a, "critical", "qa-fleet-inc:eq", f"Equity chạm sàn drawdown: {a}", "Equity còn 1,2% trên sàn hạn mức (QA)."))
SPEC.append((f"other:qa-fleet-inc-margin:{ACCS[0]}", ACCS[0], "warning", f"other:qa-fleet-inc-margin:{ACCS[0]}", "Margin level 160% — sát ngưỡng", "Ngưỡng tối thiểu 150% (QA)."))
SPEC.append((f"other:qa-fleet-inc-trades:{ACCS[1]}", ACCS[1], "warning", f"other:qa-fleet-inc-trades:{ACCS[1]}", "Số lệnh trong ngày 46/50", "Sát hạn mức số lệnh mỗi ngày (QA)."))
SPEC.append((f"other:qa-fleet-inc-latency:{ACCS[2]}", ACCS[2], "critical", f"other:qa-fleet-inc-latency:{ACCS[2]}", "Độ trễ EA cao bất thường " + "rất dài " * 8, "Độ trễ trung bình 2400 ms trong 10 phút (QA)."))
for i in range(4):
    a = ACCS[i % 3]
    SPEC.append((f"other:qa-fleet-inc-misc{i}:{a}", a, "warning", f"qa-fleet-inc:misc{i}", f"Sự cố thử số {i + 1}", "Dữ liệu thử cho QA giao diện."))


def post(conds):
    req = urllib.request.Request("http://127.0.0.1:8000/internal/fleet/results", data=json.dumps({"results": [], "conditions": conds}).encode(),
                                 headers={"Authorization": f"Bearer {TOK}", "Content-Type": "application/json"})
    return urllib.request.urlopen(req, timeout=20).read().decode()


cmd = sys.argv[1] if len(sys.argv) > 1 else "seed"
conds = [{"key": k, "account_id": a, "severity": ("ok" if cmd == "clean" else s), "kind": "other", "title": t, "detail": d, "cause_key": c} for k, a, s, c, t, d in SPEC]
print(cmd, post(conds))
