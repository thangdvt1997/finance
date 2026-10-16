"""e2e qua nginx client-ui -> gateway -> alert-rules với 2 tài khoản THỬ (A/B): giới hạn, thông báo, cài đặt, thiết bị push, ticket + kiểm chéo A/B.
Chạy bằng e2e_client_api.sh trên VPS (tạo + XOÁ tài khoản thử). Biến: BASE, A_USER, A_PASS, B_USER, B_PASS (không in mật khẩu)."""
import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = os.environ.get("BASE", "http://127.0.0.1:8581").rstrip("/")
NEWPW = "QaE2e-Pass-" + "x7Kq29mZ"
fails = []


def ok(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + ((" :: " + str(detail)[:140]) if not cond else ""))
    if not cond:
        fails.append(name)


class Sess:
    def __init__(self, user, pw):
        self.cookies = {}                     # cookie phiên có cờ Secure: urllib không gửi qua http -> tự giữ và gửi
        self.op = urllib.request.build_opener()
        self.user, self.csrf = user, None
        self.acc = f"mt5:{user}"
        self.login(pw)

    def raw(self, method, path, body=None, hdr=None):
        h = {"Accept": "application/json", "Origin": BASE, **(hdr or {})}
        if getattr(self, "cookies", None):
            h["Cookie"] = "; ".join(f"{k}={v}" for k, v in self.cookies.items())
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            h["Content-Type"] = "application/json"
        try:
            with self.op.open(urllib.request.Request(BASE + path, data=data, method=method, headers=h), timeout=20) as r:
                for c in r.headers.get_all("Set-Cookie") or []:
                    k, _, v = c.split(";")[0].partition("=")
                    if v:
                        self.cookies[k] = v
                    else:
                        self.cookies.pop(k, None)
                t = r.read().decode()
                return r.status, (json.loads(t) if t else None)
        except urllib.error.HTTPError as e:
            t = e.read().decode()
            try:
                return e.code, json.loads(t)
            except ValueError:
                return e.code, t

    def login(self, pw):
        s, _ = self.raw("POST", "/c/auth/login", {"platform": "mt5", "login": self.user, "secret": pw})
        if s != 200:
            raise SystemExit(f"login {self.user} -> {s}")
        s, cj = self.raw("POST", "/c/auth/change-password", {"current_password": pw, "new_password": NEWPW})
        self.state = f"change-pw {s} {str(cj)[:80]}"
        if s == 200:
            s, _ = self.raw("POST", "/c/auth/login", {"platform": "mt5", "login": self.user, "secret": NEWPW})

    def api(self, method, path, body=None):
        hdr = {}
        if method != "GET":
            time.sleep(2.1)                   # nginx giới hạn ghi 30 yêu cầu/phút/IP (cwrite_rl) — giữ nhịp để test không dính 429
            if not self.csrf:
                cs, cj = self.raw("GET", "/c/api/v1/user/csrf")
                if cs != 200:
                    raise SystemExit(f"csrf {self.user} -> {cs} {str(cj)[:100]} (login/đổi mật khẩu: {self.state})")
                self.csrf = cj["token"]
            hdr["X-CSRF-Token"] = self.csrf
        return self.raw(method, "/c/api/v1" + path, body, hdr)


A, B = Sess(os.environ["A_USER"], os.environ["A_PASS"]), Sess(os.environ["B_USER"], os.environ["B_PASS"])
anon = Sess.__new__(Sess)
anon.op = urllib.request.build_opener()
ok("không phiên -> 401", anon.raw("GET", "/c/api/v1/user/limits?account_id=x")[0] == 401)

# ---- giới hạn
s, j = A.api("PUT", "/user/limits", {"account_id": A.acc, "key": "daily_loss_pct", "value": 5})
ok("A đặt daily_loss=5 -> áp ngay", s == 200 and j["applied"] == "now" and j["value"] == 5, (s, j))
s, j = A.api("PUT", "/user/limits", {"account_id": A.acc, "key": "daily_loss_pct", "value": 8})
ok("A nới lỏng 8 -> pending 24h", s == 200 and j["applied"] == "pending" and j["value"] == 5 and j["pending_value"] == 8 and j["effective_at"], (s, j))
s, j = A.api("GET", f"/user/limits?account_id={A.acc}")
it = {i["key"]: i for i in j["items"]} if s == 200 else {}
ok("GET limits có pending + progress", s == 200 and it["daily_loss_pct"]["pending_value"] == 8
   and j["progress"]["daily_loss_pct"]["level"] in ("unknown", "ok", "warn", "danger", "hit"), (s, j))
s, j = A.api("PUT", "/user/limits", {"account_id": A.acc, "key": "daily_loss_pct", "value": 5})
ok("đặt lại giá trị hiện tại -> huỷ pending", s == 200 and j["applied"] == "cancelled", (s, j))
s, j = A.api("PUT", "/user/limits", {"account_id": A.acc, "key": "max_orders_day", "value": 600})
ok("miền giá trị sai -> 422", s == 422, (s, j))
s, j = A.api("GET", f"/user/limits/history?account_id={A.acc}&limit=10")
ok("lịch sử có bản ghi", s == 200 and len(j["items"]) >= 3, (s, j))
# ---- chéo A/B
for method, path, body in (("GET", f"/user/limits?account_id={A.acc}", None), ("GET", f"/user/limits/history?account_id={A.acc}", None),
                           ("PUT", "/user/limits", {"account_id": A.acc, "key": "daily_loss_pct", "value": 1})):
    s, j = B.api(method, path, body)
    ok(f"B không đụng giới hạn của A: {method} {path[:40]}", s in (403, 404), (s, j))
s, j = A.api("GET", f"/user/limits?account_id={A.acc}")
ok("giới hạn của A không bị B sửa", {i["key"]: i for i in j["items"]}["daily_loss_pct"]["value"] == 5)
# ---- prefs
s, j = A.api("GET", "/user/client-prefs")
ok("prefs rev 0", s == 200 and j["rev"] == 0, (s, j))
s, j = A.api("PUT", "/user/client-prefs", {"rev": 0, "data": {"lang": "vi", "notif": {"rule": {"app": True, "push": False}}}})
ok("prefs PUT rev0 -> rev1", s == 200 and j["rev"] == 1, (s, j))
s, j = A.api("PUT", "/user/client-prefs", {"rev": 0, "data": {"lang": "en"}})
ok("prefs lệch rev -> 409", s == 409, (s, j))
s, j = A.api("PUT", "/user/client-prefs", {"rev": 1, "data": {"hack": 1}})
ok("prefs khoá lạ -> 422", s == 422, (s, j))
s, j = B.api("GET", "/user/client-prefs")
ok("prefs của B tách khỏi A", s == 200 and j["rev"] == 0, (s, j))
# ---- thông báo
s, j = A.api("GET", "/user/notifications?unread=1&limit=20")
ok("notifications GET", s == 200 and "items" in j and "unread" in j, (s, j))
s, j = A.api("POST", "/user/notifications/read", {"all": True})
ok("notifications read all", s == 200 and j["unread"] == 0, (s, j))
# ---- thiết bị push
s, j = A.api("GET", "/user/push/devices")
ok("push devices rỗng", s == 200 and j == [], (s, j))
s, j = A.api("DELETE", "/user/push/devices/0123456789abcdef")
ok("xoá thiết bị lạ -> 404", s == 404, (s, j))
# ---- ticket
s, j = A.api("POST", "/user/tickets", {"account_id": A.acc, "category": "stale_data", "message": "dữ liệu cũ (QA e2e)", "context": {"ea_state": "offline", "age_s": 300}})
tid = j.get("id") if isinstance(j, dict) else None
ok("A tạo ticket", s == 201 and j["status"] == "open", (s, j))
s, j = A.api("POST", "/user/tickets", {"account_id": B.acc, "category": "stale_data", "message": "x"})
ok("ticket với tài khoản của B -> 404", s in (403, 404), (s, j))
s, j = A.api("POST", "/user/tickets", {"account_id": A.acc, "category": "stale_data", "message": "lặp"})
ok("gộp trùng", s == 200 and j.get("merged") and j["id"] == tid, (s, j))
s, j = B.api("GET", "/user/tickets")
ok("B không thấy ticket của A", s == 200 and all(t["id"] != tid for t in j["items"]), (s, j))
s, j = A.api("PUT", f"/user/tickets/{tid}", {"status": "resolved"})
ok("client không PUT ticket", s in (403, 404, 405), (s, j))
s, j = B.api("PUT", f"/user/tickets/{tid}", {"status": "resolved"})
ok("B không PUT ticket của A", s in (403, 404, 405), (s, j))
s, j = A.api("GET", "/user/tickets")
ok("A thấy ticket của mình", s == 200 and any(t["id"] == tid for t in j["items"]) and "owner_user_id" not in j["items"][0], (s, j))
s, j = A.api("POST", "/user/internal/notifications", {"owner_user_id": "xx", "kind": "system", "title": "x"})
ok("không có đường nội bộ qua client", s in (403, 404, 405), (s, j))
print("KẾT QUẢ:", "FAIL " + ", ".join(fails) if fails else "TẤT CẢ PASS")
sys.exit(1 if fails else 0)
