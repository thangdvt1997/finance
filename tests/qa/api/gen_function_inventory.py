"""Sinh docs/handoff/FUNCTION_INVENTORY_ts.md tu tests/qa/api_inventory.json + tests/qa/api_extra.json (+ tuy chon tom tat schemathesis).
   python3 tests/qa/api/gen_function_inventory.py [--st-summary 'text']"""
import json, os, sys, time
from collections import Counter

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
inv = json.load(open(os.path.join(ROOT, "tests/qa/api_inventory.json")))
ext = json.load(open(os.path.join(ROOT, "tests/qa/api_extra.json")))
st = sys.argv[sys.argv.index("--st-summary") + 1] if "--st-summary" in sys.argv else ""
c = Counter(x["status"] for x in inv)
ce = Counter("PASS" if x["ok"] else "FAIL" for x in ext)


def perm(x):
    p, s = x["path"], x["service"]
    if p.startswith("/auth/admin"):
        return "master/nhân viên theo perm (+TOTP cho thao tác nhạy cảm)"
    if p in ("/auth/login", "/auth/pair", "/healthz", "/readyz", "/metrics", "/livez"):
        return "công khai (/healthz,/readyz: mạng nội bộ)"
    if s in ("api-gateway", "auth"):
        return "phiên đăng nhập (vai theo authz.py)"
    return "nội bộ X-Internal-Token (qua gateway theo vai)"


L = ["# FUNCTION_INVENTORY_ts — kiểm kê & kiểm thử API (phạm vi ts)", "",
     f"Sinh bởi `tests/qa/api/gen_function_inventory.py` từ `tests/qa/api_inventory.json` + `tests/qa/api_extra.json`. Cập nhật {time.strftime('%Y-%m-%d %H:%M', time.gmtime())} UTC (phiên QA API T1+T1b, 2026-10-16).", "",
     "Công cụ: `tests/qa/api/build_inventory.py` (openapi mọi service) -> `run_api.py` (mọi route: anon / sai vai / IDOR / hợp lệ-biên-sai-quá lớn / schema JSON / p50-p95 / header bảo mật / không lộ secret) -> `run_extra.py` (luồng ghi hợp lệ, /auth/*, SSE/WS, IDOR proxy) -> schemathesis 4.30 (fuzz GET).", "",
     "## Tổng hợp trước / sau", "",
     "| | Số route | PASS | FAIL | BỎ QUA | CHƯA TEST |", "|---|---|---|---|---|---|",
     "| Trước (2026-10-15, API_INVENTORY.md) | 423 | 421 | 0 | 2 | 0 |",
     f"| Sau, lượt 1 (2026-10-16, tải máy 25-30) | {len(inv)} | {c['PASS']-6} | 6 | {c['BỎ QUA']} | 0 |",
     f"| **Sau, chạy lại 6 mục FAIL (tải ~25)** | **{len(inv)}** | **{c['PASS']}** | **{c['FAIL']}** | **{c['BỎ QUA']}** | **{c['CHƯA TEST']}** |", "",
     "6 FAIL lượt 1 đều chỉ là vượt ngân sách p95 500 ms do tải máy 25-30 (equity-history 907, vn/{rest} 1501, ai-trading/regime 1018, patterns/stats 743, intel/correlation/rolling 1405, intel/news/related 642); chạy lại cho p95 20-134 ms -> PASS. Không có lỗi chức năng/bảo mật mới ở lớp route.", "",
     f"Bộ bổ sung T1b (`run_extra.py`): {ce['PASS']} PASS / {ce['FAIL']} FAIL trong {len(ext)} kiểm tra (xem mục 3).", "",
     "Kiểm kê: 24 service quét openapi; `pattern-render` (không chạy, không có container) và `briefing-llm` (llama.cpp, không có openapi FastAPI) -> BỎ QUA có lý do. Route mới so với 2026-10-15: không có thay đổi tập route (ux_api canvas/templates/demo, /health đã nằm trong kiểm kê); 3 route ngoài openapi (`/v1/rt/stats`, `/v1/rt/sse`, `/v1/stream`) được thêm thủ công. 0 mục CHƯA TEST.", ""]
L += ["## 1. Tổng theo service", "", "| Service | Route | PASS | FAIL | BỎ QUA |", "|---|---|---|---|---|"]
by = {}
for x in inv:
    by.setdefault(x["service"], Counter())[x["status"]] += 1
for s, cc in sorted(by.items()):
    L.append(f"| {s} | {sum(cc.values())} | {cc['PASS']} | {cc['FAIL']} | {cc['BỎ QUA']} |")
L += ["", "## 2. Chi tiết từng route", "", "| ID | Service | Method | Path | Quyền | Trạng thái | p95 ms | Ghi chú |", "|---|---|---|---|---|---|---|---|"]
for i, x in enumerate(inv, 1):
    note = (x.get("detail") or "")
    if x.get("name_in_data"):
        note += " [dữ liệu API có tên nguồn; UI che]"
    bad = [k["c"] for k in x.get("checks", []) if not k["ok"]]
    if bad:
        note += " FAIL: " + ",".join(bad)
    L.append(f"| F-{i:03d} | {x['service']} | {x['method']} | `{x['path']}` | {perm(x)} | {x['status']} | {x.get('p95') if x.get('p95') is not None else '-'} | {note.replace('|', '/')[:160]} |")
L += ["", "## 3. Bổ sung T1b — luồng ghi hợp lệ / auth / realtime / IDOR proxy (tài khoản thử, đã dọn)", "", "| Nhóm | Kiểm tra | Kết quả | Chi tiết |", "|---|---|---|---|"]
for x in ext:
    L.append(f"| {x['group']} | {x['id'].split(':', 1)[1]} | {'PASS' if x['ok'] else 'FAIL'} | {x['detail'].replace('|', '/').replace(chr(10), ' ')[:110]} |")
L += ["", "## 4. Fuzz schemathesis (GET, gateway qua nginx, phiên master thử)", "", st or "(xem tests/qa/api_inventory.json)", "",
      "## 5. Chưa phủ (trung thực)", "",
      "- Hành động nguy hiểm/nặng KHÔNG gọi hợp lệ: `ai-trading/guardrail/killswitch`, `ai-trading/jobs|scenarios`, `account-reports/generate|release` (bằng master), `data/recheck`, `class/*` (phòng học: đã có `tests/qa/f_classroom_api.py`, đang được phiên khác sửa), `auth/admin/incidents/*` (cần sự cố thật), `bulk/execute` hợp lệ (chỉ kiểm cụm từ xác nhận sai), `view-as` chỉ start/end. Đã test anon/sai vai/CSRF/dữ liệu sai.",
      "- Route PATCH `auth/admin/accounts|staff`, `users/{id}/accounts` bị nginx web-ui chặn 405 (whitelist, đúng thiết kế) nên chỉ chứng minh bị chặn.",
      "- Service feed (mt-bridge, *-collector, storage-writer, alert-service): chỉ kiểm xác thực, không đụng đường giá realtime.",
      "- WebSocket/SSE: kiểm nhận được sự kiện từ phiên master; độ trễ tick->UI thuộc phiên feed.",
      "- Fuzz schemathesis: chỉ GET, 6 ví dụ/route, loại `rt`, `stream`, `data/report`, `ai-trading/class`; không fuzz route ghi.", ""]
open(os.path.join(ROOT, "docs/handoff/FUNCTION_INVENTORY_ts.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
print("ok", len(L))
