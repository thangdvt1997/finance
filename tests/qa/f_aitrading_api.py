"""QA nhom F: tab AI Trading (the chien luoc, ket qua, arena, lab, Day kich ban moi YAML+anh, job) qua gateway that.
   docker exec -i tradingsys-api-gateway-1 python - < tests/qa/f_aitrading_api.py
Kich ban thu id qa_stab_sc*; don bang f_cleanup.py. Khong chay final_test that."""
import base64, json, os, struct, time, urllib.request, urllib.error, zlib
BASE = "http://localhost:8000/v1/ai-trading"
KEY, SEC = os.environ.get("API_TOKENS", "").split(",")[0], os.environ.get("AUTH_TRUST_SECRET", "")
RES = []
def H(uid, role): return {"X-API-Key": KEY, "X-User-Id": uid, "X-Role": role, "X-Auth-Secret": SEC, "X-Accounts": ""}
def call(who, m, path, body=None, csrf=True):
    h = H(*who); data = None
    if m == "POST":
        if csrf: h["X-CSRF-Token"] = json.loads(urllib.request.urlopen(urllib.request.Request("http://localhost:8000/v1/user/csrf", headers=H(*who))).read())["token"]
        h["Content-Type"] = "application/json"; data = json.dumps(body or {}).encode()
    try: r = urllib.request.urlopen(urllib.request.Request(BASE + path, data=data, headers=h, method=m), timeout=120)
    except urllib.error.HTTPError as e: r = e
    return (r.status if hasattr(r, "status") else r.code), r.read()
def js(b):
    try: return json.loads(b)
    except Exception: return {}
def rec(n, ok, d=""):
    RES.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (" :: " + str(d)[:220] if d else ""), flush=True)
def png():
    def ch(t, d): c = struct.pack(">I", len(d)) + t + d; return c + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + b"\x80\x80\x80" * 8 for _ in range(8))
    return b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", struct.pack(">IIBBBBB", 8, 8, 8, 2, 0, 0, 0)) + ch(b"IDAT", zlib.compress(raw)) + ch(b"IEND", b"")
M, CL, EX = ("qa_stab_m", "master"), ("qa_stab_c", "client"), ("qa_stab_e", "expert")
Y = """id: qa_stab_sc1
name: "QA thu: nen tu choi dinh (Sell)"
summary: "Kich ban thu cua QA, se bi xoa."
side: sell
symbols: [EURUSD]
tfs: [H1]
detector:
  cooldown_bars: 8
  rules:
    - {rule: move_atr, dir: up, bars: 6, min: 2.0}
    - {rule: upper_wick, min_ratio: 0.4}
levels:
  sl: {type: swing_high, bars: 6, buffer_atr: [0.25, 0.5]}
  tp_r: [1.0, 2.0]
  max_hold: 60
"""
def main():
    c, b = call(M, "GET", "/overview"); o = js(b); st = o.get("strategies", [])
    rec("overview master: the chien luoc + canh bao + arena + disclaimer", c == 200 and st and "arena" in o and o.get("disclaimer"), (c, len(st), len(o.get("arena", [])), len(o.get("warnings", []))))
    ids = [s.get("id") for s in st]
    c, b = call(CL, "GET", "/overview"); oc = js(b); rec("overview client (rut gon, khong the kich ban nguoi dung)", c == 200 and all(s.get("origin") != "user" for s in oc.get("strategies", [])), (c, len(oc.get("strategies", []))))
    for sid in ids[:6]:
        c, b = call(M, "GET", f"/strategies/{sid}"); d = js(b); rec(f"the {sid} chi tiet master", c == 200 and d, (c, list(d)[:8]))
        c, b = call(CL, "GET", f"/strategies/{sid}"); rec(f"the {sid} client rut gon", c in (200, 404), c)
    c, b = call(M, "GET", "/strategies/khong-co"); rec("strategy khong ton tai 404", c == 404, c)
    c, b = call(M, "GET", "/strategies/..%2f..%2fetc"); rec("sid traversal chan", c in (400, 404, 422), c)
    c, b = call(M, "GET", "/arena"); a = js(b); rec("arena master", c == 200, (c, list(a)[:6], a.get("note")))
    c, b = call(CL, "GET", "/arena"); rec("arena client", c in (200, 403), c)
    c, b = call(M, "GET", "/lab"); rec("lab master", c == 200, c)
    c, b = call(CL, "GET", "/lab"); rec("lab client bi 403", c == 403, c)
    c, b = call(M, "GET", "/regime"); rec("regime", c == 200, c)
    c, b = call(M, "GET", "/consensus"); rec("consensus", c == 200, c)
    c, b = call(M, "GET", "/guardrail"); rec("guardrail master", c == 200, (c, list(js(b))[:6]))
    c, b = call(M, "GET", "/ledger/verify"); rec("ledger verify hash-chain", c == 200, (c, b[:160]))
    c, b = call(CL, "GET", "/guardrail"); rec("guardrail client 403", c == 403, c)
    c, b = call(M, "GET", "/analyst?symbol=EURUSD"); rec("analyst master (AI giai thich)", c == 200, (c, b[:100]))
    for sid in ids[:2]:
        c, b = call(M, "GET", f"/ledger.csv?strategy={sid}&source=paper"); rec(f"ledger.csv {sid}", c in (200, 404, 422), (c, len(b)))
    c, b = call(CL, "GET", "/ledger.csv?strategy=KB-1"); rec("ledger.csv client 403", c == 403, c)
    # Day kich ban moi
    P = png()
    c, b = call(CL, "POST", "/scenarios", {"yaml": Y}); rec("client khong nap duoc kich ban 403", c == 403, c)
    c, b = call(EX, "POST", "/scenarios", {"yaml": Y}); rec("expert khong nap qua /scenarios (403)", c == 403, c)
    c, b = call(M, "POST", "/scenarios", {"yaml": "id: [broken"}); rec("YAML hong 422", c == 422, (c, b[:100]))
    c, b = call(M, "POST", "/scenarios", {"yaml": "!!python/object/apply:os.system ['id']"}); rec("YAML object tuy y 422", c == 422, (c, b[:100]))
    c, b = call(M, "POST", "/scenarios", {"yaml": Y.replace("qa_stab_sc1", "consensus")}); rec("id trung chien luoc co san 409/422", c in (409, 422), c)
    c, b = call(M, "POST", "/scenarios", {"yaml": Y + "images: [a.png]\n"}); rec("YAML khai bao anh nhung khong tai len 422", c == 422, c)
    c, b = call(M, "POST", "/scenarios", {"yaml": Y + "images: [a.png]\n", "images": {"a.png": base64.b64encode(b"GIF89a....").decode()}}); rec("anh sai magic 422", c == 422, c)
    c, b = call(M, "POST", "/scenarios", {"yaml": Y + "images: [a.png]\n", "images": {"a.png": base64.b64encode(P + b"0" * 720000).decode()}}); rec("anh >700KB 422", c in (413, 422), c)
    c, b = call(M, "POST", "/scenarios", {"yaml": Y + "images: [a.png]\n", "images": {"../a.png": base64.b64encode(P).decode()}}); rec("ten anh traversal 422", c == 422, c)
    c, b = call(M, "POST", "/scenarios", {"yaml": Y}, csrf=False); rec("thieu CSRF 403", c == 403, c)
    c, b = call(M, "POST", "/scenarios", {"yaml": Y + "images: [a.png]\n", "images": {"a.png": base64.b64encode(P).decode()}}); d = js(b)
    rec("nap kich ban YAML + anh hop le 201", c == 201 and d.get("id") == "qa_stab_sc1", (c, b[:200]))
    c, b = call(M, "POST", "/scenarios", {"yaml": Y + "images: [a.png]\n", "images": {"a.png": base64.b64encode(P).decode()}}); rec("nap lai cung id bi tu choi (409/422)", c in (409, 422), c)
    c, b = call(M, "GET", "/scenarios/qa_stab_sc1/images/a.png"); rec("tai anh mau cua kich ban", c == 200 and b[:4] == b"\x89PNG", c)
    c, b = call(CL, "GET", "/scenarios/qa_stab_sc1/images/a.png"); rec("anh mau client 403", c == 403, c)
    c, b = call(M, "GET", "/strategies"); rec("kich ban nguoi dung hien trong danh sach master", any(s.get("id") == "qa_stab_sc1" for s in js(b)), c)
    c, b = call(CL, "GET", "/strategies"); rec("kich ban nguoi dung KHONG hien cho client", all(s.get("id") != "qa_stab_sc1" for s in js(b)) if c == 200 else c == 403, c)
    c, b = call(M, "POST", "/scenarios/qa_stab_sc1/jobs", {"type": "detector_test"}); j = js(b); jid = j.get("id") or j.get("job_id")
    rec("job detector_test tao 202", c == 202 and jid, (c, b[:160]))
    c2, b2 = call(M, "POST", "/scenarios/qa_stab_sc1/jobs", {"type": "detector_test"}); rec("job trung khi dang chay 409", c2 in (409, 202), c2)
    c, b = call(M, "POST", "/scenarios/qa_stab_sc1/jobs", {"type": "final_test", "confirm": "qa_stab_sc1"}); rec("final_test khi chua co dev -> 409 (khong mo khoa)", c == 409, (c, b[:140]))
    c, b = call(M, "POST", "/scenarios/qa_stab_sc1/jobs", {"type": "final_test", "confirm": "SAI"}); rec("final_test sai xac nhan khong chay", c in (409, 422), c)
    c, b = call(M, "POST", "/scenarios/qa_stab_sc1/jobs", {"type": "xyz"}); rec("type job la 422", c == 422, c)
    c, b = call(CL, "POST", "/scenarios/qa_stab_sc1/jobs", {"type": "backtest"}); rec("client tao job 403", c == 403, c)
    if jid:
        stt = None
        for _ in range(60):
            time.sleep(3); c, b = call(M, "GET", f"/jobs/{jid}"); stt = js(b).get("status")
            if stt in ("done", "failed"): break
        rec("job detector_test ket thuc", stt in ("done", "failed"), (stt, str(js(b))[:200]))
    c, b = call(M, "GET", "/scenarios/qa_stab_sc1/jobs"); rec("lich su job", c == 200 and js(b).get("items"), c)
    c, b = call(M, "GET", "/jobs/khong-co"); rec("job khong ton tai 404/422", c in (404, 422), c)
    c, b = call(M, "POST", "/jobs", {"strategy_id": "consensus", "type": "backtest"}); rec("job tren KB-1 (chien luoc co san) bi tu choi 404", c == 404, c)
    c, b = call(M, "POST", "/guardrail/killswitch", {"on": True, "reason": "x"}, csrf=False); rec("killswitch thieu CSRF 403", c == 403, c)
    print(f"TONG {sum(RES)}/{len(RES)} PASS")
main()
