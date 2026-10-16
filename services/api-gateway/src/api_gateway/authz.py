"""Phân quyền master/client cho gateway (docs/AUTH.md, docs/CLIENT_PLATFORM.md).

Mô hình tin cậy: gateway KHÔNG tự xác thực người dùng. nginx (web-ui) chạy `auth_request` tới service auth rồi đặt
`X-User-Id`, `X-Role`, `X-Accounts` (+ `X-Auth-Secret` = AUTH_TRUST_SECRET, bí mật chia sẻ nginx<->gateway). Gateway CHỈ tin các header này khi
`X-Auth-Secret` khớp (so sánh hằng thời gian). Có header người dùng mà thiếu/sai secret -> 403 (chống giả mạo kể cả từ kẻ giữ API key).
Không có header người dùng nào -> "service" (dịch vụ nội bộ giữ X-API-Key: reporter, e2e...) = quyền master.
`X-API-Key` vẫn bắt buộc cho mọi request (lớp thứ nhất).

Chính sách MẶC ĐỊNH TỪ CHỐI cho role client: chỉ các đường dẫn trong CLIENT_ALLOW; mọi route mới thêm sau mặc định chỉ master thấy.
Route theo tài khoản: kiểm account_id ∈ accounts của phiên (403 đồng nhất cho cả "không tồn tại" lẫn "của người khác" -> không có oracle).
"""
from __future__ import annotations

import hmac
import re
from dataclasses import dataclass, field

from fastapi import HTTPException, Request

ACC_RE = re.compile(r"^[A-Za-z0-9_.:\-]{1,64}$")
FORBIDDEN = "Không có quyền truy cập"

# role client được gọi (GET trừ khi ghi chú rõ). Mọi thứ khác -> 403.
CLIENT_ALLOW: list[tuple[frozenset[str], re.Pattern]] = [
    (frozenset({"GET"}), re.compile(
        r"^/v1/(me|bars|quotes/latest|news|calendar|experts|expert-signals|expert-opinions|expert-positions|symbols|symbols/classes|risk-windows|risk-windows/status"
        r"|accounts|overview|equity-history|risk/config|user/csrf|briefing(/.*)?|vn/.*|analytics/.*|intel/.*|patterns(/spec|/live|/setup|/trades|/stats|/examples|/media/[0-9]{1,19}\.png|/examples/[A-Za-z0-9_\-][A-Za-z0-9_.\-]{0,79}\.png)?)$")),
    # track-record chuyên gia (track_routes.py): dữ liệu công khai, không có dữ liệu tài khoản. chain/verify KHÔNG nằm đây (chỉ master/service)
    (frozenset({"GET"}), re.compile(r"^/v1/experts/(leaderboard|consensus|feed|methodology|[A-Za-z0-9_.:\-]{1,96}/track-record)$")),
    # tab AI Trading (ai_trading_routes.py): client CHỈ bản rút gọn read-only; lab/ledger/media/jobs = chỉ master
    (frozenset({"GET"}), re.compile(r"^/v1/ai-trading/(overview|strategies|arena|regime|consensus|strategies/[A-Za-z0-9][A-Za-z0-9_.\-]{0,47})$")),
    (frozenset({"GET"}), re.compile(r"^/v1/risk/accounts(/[A-Za-z0-9_.:\-]{1,64})?$")),
    (frozenset({"GET"}), re.compile(r"^/v1/accounts/[A-Za-z0-9_.:\-]{1,64}/orders$")),   # lệnh chờ: kiểm tài khoản bên dưới
    # cảnh báo cá nhân + Web Push: gateway gắn danh tính chủ sở hữu, alert-rules CHỈ trả/ghi bản ghi của chính họ (user_routes.py)
    (frozenset({"GET"}), re.compile(r"^/v1/user/(rules|rule-events|push|limits|limits/history|notifications|client-prefs|push/devices|tickets)$")),
    (frozenset({"POST"}), re.compile(r"^/v1/user/(rules|rules/preview|push/subscribe|push/unsubscribe|push/test|rules/[0-9a-fA-F-]{36}/preview|notifications/read|tickets)$")),
    (frozenset({"PUT", "DELETE"}), re.compile(r"^/v1/user/rules/[0-9a-fA-F-]{36}$")),
    (frozenset({"PUT"}), re.compile(r"^/v1/user/(limits|client-prefs)$")),     # giới hạn/mục tiêu + cài đặt đồng bộ của CHÍNH họ (alert-rules lọc theo chủ + tài khoản)
    (frozenset({"DELETE"}), re.compile(r"^/v1/user/push/devices/[0-9a-f]{16}$")),
    (frozenset({"GET", "PUT", "DELETE"}), re.compile(r"^/v1/journal/.+$")),   # ghi chú/tag: kiểm tài khoản bên dưới
    # báo cáo theo tài khoản (account_reports_routes.py): CHỈ 2 đường GET; client chỉ thấy bản đã phát hành của tài khoản mình. generate/release/schedules = chỉ master.
    (frozenset({"GET"}), re.compile(r"^/v1/account-reports$")),
    (frozenset({"GET"}), re.compile(r"^/v1/account-reports/[A-Za-z0-9_.:\-]{1,64}/\d{4}-\d{2}-\d{2}/(html|pdf)$")),
]


@dataclass(frozen=True)
class Principal:
    kind: str                      # service | master | client   (vai trò phụ support/analyst/auditor = kind "client" bị thu hẹp thêm, xem `role`)
    user_id: str = ""
    accounts: frozenset[str] = field(default_factory=frozenset)
    role: str = ""                 # "" | support | analyst | auditor | expert

    @property
    def is_master(self) -> bool:
        return self.kind in ("service", "master")

    def can(self, account_id: str | None) -> bool:
        return self.is_master or (bool(account_id) and account_id in self.accounts)

    def me(self) -> dict:
        return {"role": self.role or ("master" if self.is_master else "client"), "kind": self.kind, "user_id": self.user_id,
                "accounts": sorted(a for a in self.accounts if not a.startswith(STAFF_SENTINEL)), "all_accounts": self.is_master}


SERVICE = Principal("service")

# Vai trò phụ (docs/FLEET_MGMT.md): MẶC ĐỊNH TỪ CHỐI. Chạy như `client` (mọi nơi khác trong gateway: cache/realtime/user_routes coi là client => an toàn hơn)
# nhưng CHỈ GET trên danh sách trắng đọc dữ liệu, trong phạm vi tài khoản được giao (X-Accounts do auth tính từ nhóm); không /v1/user/*, không ghi.
# auditor không có dữ liệu tài khoản (chỉ /v1/me). Ký hiệu `staff:<role>` được thêm vào accounts để khoá cache KHÁC client thật (không khớp tài khoản MT nào).
STAFF_ROLES = ("support", "analyst", "auditor", "expert")
STAFF_SENTINEL = "staff:"
# Vai "expert" (AI Training Class): dạy + chạy test paper. Không có dữ liệu tài khoản; ngoài /v1/me, /v1/user/csrf và dữ liệu thị trường (GET như analyst)
# chỉ được /v1/ai-trading/class/* (GET/POST/PATCH/PUT/DELETE; ghi cần Origin + CSRF, kiểm ở route). Không đụng cấu hình hệ thống.
_SEG = r"[A-Za-z0-9_\-]{1,64}(?:\.[a-z]{1,4})?"   # không cho '.'/'..'; whitelist chi tiết nằm ở class_routes
CLASS_PATH = re.compile(rf"^/v1/ai-trading/class/(status|templates|demo/script|options/stats|(rooms|memory|methods)(/{_SEG}){{0,6}})$")


def principal_from_headers(headers, trust_secret: str) -> Principal:
    """headers: mapping không phân biệt hoa/thường (Request.headers / WebSocket.headers). Ném HTTPException(403) khi giả mạo/không hợp lệ."""
    uid, role, accs, sec = (headers.get("x-user-id"), headers.get("x-role"), headers.get("x-accounts"), headers.get("x-auth-secret"))
    if not any((uid, role, accs, sec)):
        return SERVICE
    if not trust_secret or not sec or not hmac.compare_digest(sec.encode(), trust_secret.encode()):
        raise HTTPException(403, FORBIDDEN)
    if role == "master":
        return Principal("master", uid or "")
    if role == "client":
        accounts = frozenset(a for a in (accs or "").split(",") if ACC_RE.match(a) and not a.startswith(STAFF_SENTINEL))   # bỏ giá trị lạ, kể cả "*"
        return Principal("client", uid or "", accounts)
    if role in STAFF_ROLES:
        accounts = frozenset(a for a in (accs or "").split(",") if ACC_RE.match(a) and not a.startswith(STAFF_SENTINEL))
        if role in ("auditor", "expert"):
            accounts = frozenset()
        return Principal("client", uid or "", accounts | {STAFF_SENTINEL + role}, role)
    raise HTTPException(403, FORBIDDEN)   # anon / role lạ không bao giờ được vào /v1


def get_principal(request) -> Principal:
    """Principal đã tính bởi dependency `authorize` (request.state); nếu chưa có (route ngoài router /v1) -> tính lại."""
    p = getattr(request.state, "principal", None)
    return p if p is not None else SERVICE


def client_path_allowed(method: str, path: str) -> bool:
    return any(method in methods and rx.match(path) for methods, rx in CLIENT_ALLOW)


def staff_path_allowed(role: str, method: str, path: str) -> bool:
    """support/analyst: chỉ GET dữ liệu đọc (như client, bỏ /v1/user/*). auditor: chỉ /v1/me."""
    if role == "expert":
        if method in ("GET", "POST", "PATCH", "PUT", "DELETE") and CLASS_PATH.match(path):
            return True
        return method == "GET" and (path == "/v1/user/csrf" or (not path.startswith("/v1/user/") and client_path_allowed("GET", path)))
    if method != "GET":
        return False
    if role == "auditor":
        return path == "/v1/me"
    return not path.startswith("/v1/user/") and client_path_allowed("GET", path)


def account_from_request(path: str, query, method: str = "GET") -> list[str]:
    """Các account_id mà request này nhắm tới (để kiểm quyền TRƯỚC khi chạy route)."""
    out = []
    if path == "/v1/equity-history":
        out.append(query.get("account_id") or "")
    if method == "GET" and path in ("/v1/user/limits", "/v1/user/limits/history"):   # PUT: account_id nằm trong body -> alert-rules kiểm tra (404)
        out.append(query.get("account_id") or "")
    m = re.match(r"^/v1/accounts/([^/]+)/orders$", path)
    if m:
        out.append(m.group(1))
    m = re.match(r"^/v1/risk/accounts/([^/]+)$", path)
    if m:
        out.append(m.group(1))
    m = re.match(r"^/v1/journal/([^/]+)(/.*)?$", path)
    if m and not (m.group(1) == "accounts" and not m.group(2)):     # chỉ miễn kiểm cho ĐÚNG /v1/journal/accounts (danh sách đã lọc); /v1/journal/accounts/... = "tài khoản" tên accounts -> kiểm như mọi tài khoản
        out.append(m.group(1))
    if path == "/v1/account-reports":
        out.append(query.get("account_id") or "")
    m = re.match(r"^/v1/account-reports/([^/]+)/[^/]+/[^/]+$", path)
    if m:
        out.append(m.group(1))
    return out


def make_authorize(trust_secret_fn):
    """Dependency cấp router /v1: tính principal, áp chính sách role client."""
    async def authorize(request: Request) -> None:
        p = principal_from_headers(request.headers, trust_secret_fn())
        request.state.principal = p
        if p.kind != "client":
            return
        path = request.url.path
        if p.role:
            if not staff_path_allowed(p.role, request.method, path):
                raise HTTPException(403, FORBIDDEN)
        elif not client_path_allowed(request.method, path):
            raise HTTPException(403, FORBIDDEN)
        for acc in account_from_request(path, request.query_params, request.method):
            if not p.can(acc):
                raise HTTPException(403, FORBIDDEN)
        # query nhiều giá trị account_id (equity-history?account_id=a&account_id=b): cấm, tránh nhập nhằng
        if path == "/v1/equity-history" and len(request.query_params.getlist("account_id")) != 1:
            raise HTTPException(403, FORBIDDEN)
    return authorize


# ---------------- lọc dữ liệu trả về ----------------
def filter_rows(p: Principal, rows, key: str = "account_id"):
    if p.is_master:
        return rows
    return [r for r in rows if (r.get(key) if isinstance(r, dict) else getattr(r, key, None)) in p.accounts]


def filter_payload(p: Principal, path: str, payload):
    """Lọc phản hồi JSON của proxy (journal/risk) cho role client. master/service: nguyên vẹn."""
    if p.is_master or not isinstance(payload, dict):
        return payload
    if path == "/v1/risk/accounts" and isinstance(payload.get("accounts"), list):
        return {**payload, "accounts": filter_rows(p, payload["accounts"])}
    if path == "/v1/journal/accounts" and isinstance(payload.get("items"), list):
        return {**payload, "items": filter_rows(p, payload["items"])}
    return payload


def event_visible(p: Principal, event: dict, strict: bool = False) -> bool:
    """WebSocket: sự kiện có account_id trong payload chỉ được gửi cho chủ tài khoản (master thấy tất cả)."""
    if p.is_master:
        return True
    payload = event.get("payload") if isinstance(event, dict) else None
    if not isinstance(payload, dict):
        return False
    for k in ("account_id", "account"):
        if k in payload:
            return payload[k] in p.accounts
    if strict:      # stream theo tài khoản mà sự kiện không nêu tài khoản -> không gửi cho client
        return False
    for k, v in payload.items():       # tài khoản lồng (vd {"accounts": [...]})
        if k in ("accounts", "account_ids") and isinstance(v, list):
            return all((x.get("account_id") if isinstance(x, dict) else x) in p.accounts for x in v)
    return True


WS_CLIENT_STREAMS = {"md.quotes", "md.bars", "news.items", "news.enriched", "calendar.events", "expert.signals", "expert.positions",
                     "expert.profiles", "analytics.signals", "pattern.signals", "account.snapshots", "account.deals"}
