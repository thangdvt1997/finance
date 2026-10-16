"""Dung tests/qa/api_inventory.json (khung kiem ke, trang thai CHUA TEST) tu openapi cac service.
   1) docker exec -i tradingsys-api-gateway-1 python - < tests/qa/api/gen_inventory.py > /tmp/inv_raw.json
   2) python3 tests/qa/api/build_inventory.py /tmp/inv_raw.json
Runner (run_api.py) ghi ket qua vao cung file."""
import json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "api_inventory.json")
# service -> tien to dich sang duong gateway (route proxy)
VIA = {"paper-trader": [(r"^/paper/", "/v1/paper/"), (r"^/status$", "/v1/paper/status")],
       "vn-market": [(r"^/vn/", "/v1/vn/")], "risk-monitor": [(r"^/risk/", "/v1/risk/")],
       "briefing": [(r"^/briefing/", "/v1/briefing/")], "journal": [(r"^/journal/", "/v1/journal/")],
       "data-keeper": [(r"^/v1/data/", "/v1/data/")], "alert-rules": [(r"^/(rules|prefs|limits|notifications|push|client-prefs|tickets)", "/v1/user/")],
       "ai-trading": [(r"^/class/", "/v1/ai-trading/class/"), (r"^/ai/", "/v1/ai-trading/")],
       "reporter": [(r"^/(reports|account-reports|account-report-schedules)", "/v1/")],
       "track-record": [(r"^/track/", "/v1/experts/")]}
FEED = {"mt-bridge", "market-collector", "news-collector", "expert-collector", "storage-writer", "alert-service"}  # duong gia realtime/feed: thuoc phien feed


def resolve(spec, node, depth=0):
    if depth > 4 or not isinstance(node, dict):
        return node
    if "$ref" in node:
        cur = spec
        for k in node["$ref"].lstrip("#/").split("/"):
            cur = cur.get(k, {})
        return resolve(spec, cur, depth + 1)
    return node


def pinfo(spec, p):
    p = resolve(spec, p)
    s = resolve(spec, p.get("schema", {}))
    t = s.get("type")
    if not t and "anyOf" in s:
        ts = [resolve(spec, x).get("type") for x in s["anyOf"] if resolve(spec, x).get("type") != "null"]
        t = ts[0] if ts else None
    return {"name": p.get("name"), "in": p.get("in"), "type": t, "required": bool(p.get("required")), "enum": s.get("enum"),
            "min": s.get("minimum"), "max": s.get("maximum"), "default": s.get("default")}


def main(raw):
    d = json.load(open(raw))
    inv = []
    for svc, spec in d.items():
        if "error" in spec:
            inv.append({"id": f"{svc}:-", "service": svc, "method": "-", "path": "-", "status": "BỎ QUA",
                        "detail": f"không có openapi ({spec['error']}); service không phơi route HTTP/đã gỡ"})
            continue
        for path, ops in spec["paths"].items():
            for m, op in ops.items():
                if m.upper() not in ("GET", "POST", "PUT", "DELETE", "PATCH"):
                    continue
                params = [pinfo(spec, x) for x in op.get("parameters", [])] + [pinfo(spec, x) for x in ops.get("parameters", []) if isinstance(ops.get("parameters"), list)]
                body = None
                rb = resolve(spec, op.get("requestBody", {}))
                if rb:
                    sch = {}
                    for ct, v in rb.get("content", {}).items():
                        sch = resolve(spec, v.get("schema", {}))
                        body = {"content_type": ct, "required": sch.get("required", []), "props": list(sch.get("properties", {}))[:12]}
                        break
                    body = body or {"content_type": "?", "required": [], "props": []}
                via = None
                for rx, rep in VIA.get(svc, []):
                    if re.match(rx, path):
                        via = re.sub(rx, rep, path, count=1) if rep.endswith("/") else rep
                        if svc in ("reporter",):
                            via = "/v1" + path
                        break
                inv.append({"id": f"{svc}:{m.upper()}:{path}", "service": svc, "method": m.upper(), "path": path,
                            "tags": op.get("tags", []), "summary": (op.get("summary") or "")[:100], "params": params, "body": body,
                            "via_gateway": via, "feed": svc in FEED, "status": "CHƯA TEST", "detail": "", "checks": []})
    json.dump(inv, open(OUT, "w"), ensure_ascii=False, indent=1)
    print(len(inv), "muc")


main(sys.argv[1])
