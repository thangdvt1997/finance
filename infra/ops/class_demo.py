"""Demo đầu-cuối AI Training Class (chạy TRONG container api-gateway, qua chính gateway với danh tính expert):
   docker exec -i tradingsys-api-gateway-1 python - < infra/ops/class_demo.py | tee /tmp/class_demo.log
Giao kịch bản 3 câu -> AI hỏi -> trả lời checklist -> /quet (job thật ở worker) -> gắn nhãn -> /test (đăng ký giả thuyết, walk-forward, baseline) -> thẻ kết quả.
Không in khoá/bí mật. CHỈ nghiên cứu/paper; không mở test khoá."""
import json
import os
import sys
import time
import urllib.request

PNG_MAGIC = bytes([0x89]) + b"PNG"   # (f-string py3.10 khong cho backslash)
BASE = "http://localhost:8000/v1"
KEY, SEC = os.environ.get("API_TOKENS", "").split(",")[0], os.environ.get("AUTH_TRUST_SECRET", "")
H = {"X-API-Key": KEY, "X-User-Id": "demo-expert-1", "X-Role": "expert", "X-Auth-Secret": SEC, "X-Accounts": ""}


def call(method, path, body=None, raw=False):
    h = dict(H)
    data = None
    if method == "POST":
        h["Content-Type"] = "application/json"
        h["X-CSRF-Token"] = json.loads(urllib.request.urlopen(urllib.request.Request(BASE + "/user/csrf", headers=H)).read())["token"]
        data = json.dumps(body or {}).encode()
    try:
        r = urllib.request.urlopen(urllib.request.Request(BASE + path, data=data, headers=h, method=method), timeout=300)
    except urllib.error.HTTPError as e:
        r = e
    txt = r.read().decode()
    return (r.status if hasattr(r, "status") else r.code), txt


def say(rid, text):
    time.sleep(5.5)          # tôn trọng giới hạn 12 tin/phút/người của gateway
    code, txt = call("POST", f"/ai-trading/class/rooms/{rid}/messages", {"text": text})
    for _ in range(4):
        if code != 429:
            break
        time.sleep(20)
        code, txt = call("POST", f"/ai-trading/class/rooms/{rid}/messages", {"text": text})
    if code != 200:
        print("  !! HTTP", code, txt[:160])
    ev = [json.loads(x[6:]) for x in txt.split("\n\n") if x.startswith("data: ")]
    return code, ev


def ai_reply(ev):
    t = next((e for e in ev if e["type"] == "turn"), None)
    return t["turn"] if t else {"reply": "(không có phản hồi)", "phase": "?"}


def show(who, text):
    print(f"\n[{who}] {text.strip()[:700]}")


BRIEF = ("Kịch bản Sell đảo chiều trên EURUSD và GBPUSD khung H1. Sau nhịp tăng 2 ATR trong 6 nến, xuất hiện nến giảm có bóng trên trên 40%. "
         "Vào Sell khi nến đóng cửa, SL trên đỉnh 6 nến + 0,25 ATR, TP 1R và 2R.")
ANS = [
    "Xu hướng lớn H4 đang đi ngang, biến động vừa phải, giá nằm trên EMA 50 khung H1 sau nhịp hồi.",
    "EURUSD và GBPUSD, khung H1, lọc bằng H4",
    "Nhịp tăng 2 ATR trong 6 nến, sau đó nến giảm có bóng trên 40% biên độ, thân nến giảm 0,3 ATR.",
    "Vào ở giá mở nến kế tiếp sau nến giảm đóng cửa; không chờ hồi.",
    "Huỷ nếu giá vượt đỉnh nhịp 0,5 ATR hoặc sau 3 nến chưa kích hoạt.",
    "SL trên đỉnh 6 nến + 0,25 ATR; TP 1R và 2R; giữ tối đa 60 nến.",
    "Rủi ro 0,5% mỗi lệnh, tối đa 2 lệnh đồng thời.",
    "Chỉ phiên 7-16 UTC, spread dưới 15 điểm, ATR trên 8 pip, tránh 30 phút quanh tin mạnh.",
    "Ví dụ đúng: EURUSD H1 ngày 12/03 nến 09:00. Ví dụ sai: bóng trên 30% nên không vào, vì chưa đủ từ chối.",
    "Thua khi thị trường có xu hướng tăng mạnh liên tục sau tin, nhịp tăng tiếp diễn thay vì đảo chiều.",
    "Buy đối xứng áp dụng được nhưng RSI không đối xứng, cần kiểm lại ngưỡng.",
    "Có thể áp dụng GBPUSD và H4 vì cùng cấu trúc thanh khoản.",
    "Người mua đuổi giá cuối nhịp bị kẹt khi nến từ chối xuất hiện; thanh khoản stop-loss phía trên đỉnh bị quét rồi giá quay lại.",
]


def main():
    code, txt = call("POST", "/ai-trading/class/rooms", {"title": "Demo đầu-cuối: Sell đảo chiều H1"})
    assert code == 201, (code, txt[:200])
    rid = json.loads(txt)["id"]
    print("Phòng:", rid[:8], "... (expert demo-expert-1)")
    show("Chuyên gia", BRIEF)
    code, ev = say(rid, BRIEF)
    t = ai_reply(ev)
    show("AI", t["reply"])
    i = 0
    while t["phase"] == "interview" and i < len(ANS):
        show("Chuyên gia", ANS[i])
        code, ev = say(rid, ANS[i])
        t = ai_reply(ev)
        show("AI", t["reply"][:400])
        i += 1
    print("\n== Pha:", t["phase"], "| bước đã trả lời:", i)
    code, ev = say(rid, "/luu bản đầu sau phỏng vấn")
    show("AI", ai_reply(ev)["reply"])
    code, ev = say(rid, "/bien-the")
    show("AI (học 1 hiểu 10)", ai_reply(ev)["reply"][:600])
    code, ev = say(rid, "/quet limit=8 tf=h1")
    act = next((e["action"] for e in ev if e["type"] == "action"), None)
    print("\n/quet ->", {k: act.get(k) for k in ("status", "scenario_id", "message")} if act else ev)
    if not act or act["status"] == "failed":
        sys.exit(1)
    t0 = time.time()
    while time.time() - t0 < 900:
        time.sleep(5)
        code, txt = call("GET", f"/ai-trading/class/rooms/{rid}/actions/{act['id']}")
        a = json.loads(txt)
        if a["status"] in ("done", "failed"):
            break
    print("Quét:", a["status"], a.get("message"), f"({int(time.time() - t0)}s)")
    code, txt = call("GET", f"/ai-trading/class/rooms/{rid}")
    room = json.loads(txt)
    scan = next((m for m in room["messages"] if m["kind"] == "scan"), None)
    if not scan or not scan["data"]["examples"]:
        print("Không có ví dụ:", scan and scan["text"])
        sys.exit(2)
    exs = scan["data"]["examples"]
    print(scan["text"])
    verd = ["dung", "dung", "gan_dung", "sai", "dung", "sai", "dung", "gan_dung"]
    why = {"sai": "bóng trên chưa đủ dài, giá tiếp tục tăng sau nến giảm"}
    for e, v in zip(exs, verd):
        code, txt = call("POST", f"/ai-trading/class/rooms/{rid}/labels", {"example_id": e["id"], "verdict": v, "reason": why.get(v, "")})
        assert code == 201, txt[:200]
        img = urllib.request.urlopen(urllib.request.Request(BASE + e["image_url"].replace("/api/v1", ""), headers=H)).read()
        print(f"  nhãn {v:9s} {e['symbol']} {e['tf']} {e['ts']}  ảnh {len(img)} byte PNG={img[:4] == PNG_MAGIC}")
    sm = json.loads(txt)["summary"]
    print("Nhãn:", {k: sm[k] for k in ("n_labeled", "n_examples", "coverage", "precision", "precision_strict")}, "|", sm["advice"])
    code, ev = say(rid, "/test")
    act = next(e["action"] for e in ev if e["type"] == "action")
    print("\n/test ->", act["status"], act.get("summary", ""))
    code, txt = call("POST", f"/ai-trading/class/rooms/{rid}/actions/{act['id']}/confirm", {})
    act = json.loads(txt)["action"]
    print("xác nhận ->", act["status"], act.get("scenario_id"))
    t0 = time.time()
    while time.time() - t0 < 1500:
        time.sleep(10)
        code, txt = call("GET", f"/ai-trading/class/rooms/{rid}/actions/{act['id']}")
        a = json.loads(txt)
        if a["status"] in ("done", "failed"):
            break
    print("Test:", a["status"], a.get("message"), f"({int(time.time() - t0)}s)")
    code, txt = call("GET", f"/ai-trading/class/rooms/{rid}?limit=200")
    card = next((m for m in json.loads(txt)["messages"] if m["kind"] == "result_card"), None)
    if card:
        d = card["data"]
        print("\n== THẺ KẾT QUẢ ==", json.dumps({"verdict": d["verdict"], "metrics": d["metrics"]}, ensure_ascii=False))
        for h in d["honesty"]:
            print("  - " + h)
    code, md = call("GET", f"/ai-trading/class/rooms/{rid}/minutes.md")
    print("\nBiên bản:", code, len(md), "ký tự")
    code, txt = call("POST", f"/ai-trading/class/rooms/{rid}/final-test", {"scenario_id": act["scenario_id"], "confirm": act["scenario_id"]})
    print("Expert mở test khoá ->", code, "(phải 403)")


main()
