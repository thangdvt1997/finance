#!/usr/bin/env python3
"""Smoke NHANH (API, không trình duyệt): đăng nhập master thử (mật khẩu đọc từ file, không in) rồi gọi API chính qua nginx.
   python3 s_quick.py BASE_M PWFILE USER   -> thoát 0 xanh / 1 đỏ. Chịu deploy giữa chừng: mỗi lời gọi retry ngắn."""
import base64, hashlib, hmac, json, struct, sys, time, urllib.request, urllib.error

base, pwfile, user = sys.argv[1], sys.argv[2], sys.argv[3]
pw = open(pwfile).read().strip()
jar = {}   # cookie tự quản (cookie của phiên có thể gắn Secure -> CookieJar không gửi qua http nội bộ)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


op = urllib.request.build_opener(_NoRedirect)


def _store(headers):
    for line in headers.get_all("Set-Cookie") or []:
        kv = line.split(";")[0]
        k, _, v = kv.partition("=")
        if v:
            jar[k.strip()] = v.strip()
        else:
            jar.pop(k.strip(), None)
fails = []


def call(method, path, data=None, retries=3):
    code = 0
    for i in range(retries):
        req = urllib.request.Request(base + path, method=method, headers={"Origin": base, "Content-Type": "application/json", "Cookie": "; ".join(f"{k}={v}" for k, v in jar.items())},
                                     data=json.dumps(data).encode() if data is not None else None)
        try:
            r = op.open(req, timeout=15); code = r.status; body = r.read(); _store(r.headers)
        except urllib.error.HTTPError as e:
            code = e.code; body = e.read(); _store(e.headers)
        except Exception:
            code = 0; body = b""
        if code in (200, 302, 401, 403, 404, 422) or i == retries - 1:
            return code, body
        time.sleep(3)
    return code, b""


def totp(sec):
    key = base64.b32decode(sec.upper() + "=" * (-len(sec) % 8))
    h = hmac.new(key, struct.pack(">Q", int(time.time() // 30)), hashlib.sha1).digest()
    o = h[19] & 15
    return "%06d" % ((struct.unpack(">I", h[o:o + 4])[0] & 0x7FFFFFFF) % 10**6)


c, _ = call("POST", "/auth/login", {"platform": "master", "login": user, "secret": pw}, retries=4)
if c != 200:
    print(f"FAIL đăng nhập master thử: {c}"); sys.exit(1)
c, b = call("POST", "/auth/totp/setup", {})
try:
    sec = json.loads(b).get("secret")
except Exception:
    sec = None
if sec:
    c, _ = call("POST", "/auth/totp/enable", {"code": totp(sec)})
    if c != 200:
        time.sleep(31); c, _ = call("POST", "/auth/totp/enable", {"code": totp(sec)})
    if c != 200:
        print(f"FAIL totp/enable: {c}")
for p in ["/auth/me", "/api/v1/me", "/api/v1/user/prefs", "/api/v1/news?limit=5", "/api/v1/calendar", "/api/v1/journal/accounts",
          "/api/v1/bars?symbol=EURUSD&tf=H1&limit=5&order=desc", "/auth/admin/accounts"]:
    c, _ = call("GET", p)
    if c != 200:
        fails.append(f"FAIL API {p.split('?')[0]}: {c}")
c, _ = call("GET", "/api/v1/news", retries=1)  # chưa đăng nhập phải 401 -> dùng opener mới
anon = urllib.request.build_opener()
try:
    r = anon.open(urllib.request.Request(base + "/api/v1/news"), timeout=10); ac = r.status
except urllib.error.HTTPError as e:
    ac = e.code
except Exception:
    ac = 0
if ac not in (401, 302):
    fails.append(f"FAIL anon /api/v1/news: {ac} (mong 401)")
for f in fails:
    print(f)
print("s_quick: %s (%d lỗi)" % ("ĐỎ" if fails else "XANH", len(fails)))
sys.exit(1 if fails else 0)
