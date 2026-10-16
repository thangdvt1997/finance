import pyotp
import pytest
from cryptography.fernet import Fernet

from auth import security as sec
from auth.config import AuthSettings
from auth.service import AuthService


def test_argon2id_hash_and_verify():
    h = sec.hash_password("Correct-Horse-9")
    assert h.startswith("$argon2id$")
    assert sec.verify_password(h, "Correct-Horse-9")
    assert not sec.verify_password(h, "correct-horse-9")
    assert not sec.verify_password("khong-phai-hash", "x")


async def test_averify_dummy_for_unknown_user():
    assert await sec.averify(None, "bat-ky") is False
    h = await sec.ahash("Mat-khau-dai-123")
    assert await sec.averify(h, "Mat-khau-dai-123") and not await sec.averify(h, "sai")


def test_generated_secrets_shape_and_entropy():
    p, c = sec.gen_passcode(), sec.gen_pairing_code()
    assert len(p) == 19 and p.count("-") == 3 and len(c) == 14 and c.count("-") == 2
    assert not set(p.replace("-", "")) & set("ILO01")
    assert len({sec.gen_passcode() for _ in range(200)}) == 200
    assert len(sec.gen_ea_token()) >= 43 and len(sec.gen_hmac_secret()) == 64
    assert sec.gen_session_id() != sec.gen_session_id()


def test_pairing_code_normalisation_matches_bridge_rule():
    assert sec.hash_code("abcd-efgh-jklm") == sec.hash_code("ABCDEFGHJKLM") == sec.sha256_hex("ABCDEFGHJKLM")
    assert sec.hash_code(" abcd efgh ") == sec.sha256_hex("ABCDEFGH")


def test_session_stored_hashed_not_raw():
    sid = sec.gen_session_id()
    assert sec.hash_session(sid) != sid and len(sec.hash_session(sid)) == 64


def test_vault_roundtrip_and_failclosed():
    v = sec.Vault(Fernet.generate_key().decode())
    assert v.ok and v.dec(v.enc("hmac-secret")) == "hmac-secret"
    assert v.dec("rac-rui") is None
    other = sec.Vault(Fernet.generate_key().decode())
    assert other.dec(v.enc("x")) is None            # sai khoá -> không giải mã được
    bad = sec.Vault("")
    assert not bad.ok
    with pytest.raises(RuntimeError):
        bad.enc("x")
    assert not sec.Vault("khong-phai-khoa").ok


def test_password_policy():
    f = lambda pw, **kw: sec.check_password_policy(pw, min_len=10, **kw)  # noqa: E731
    assert f("Ngan1") and f("aaaaaaaaaaaa") and f("1234567890")
    assert f("my12345678pass", login="12345678")                 # chứa ID đăng nhập
    assert f("Mat-khau-moi-1", old="Mat-khau-moi-1")             # trùng mật khẩu cũ
    assert f("x" * 200)
    assert f("Mat-khau-du-manh-7", login="12345678") is None


def test_sliding_window_blocks_and_expires():
    w = sec.SlidingWindow(3, 10)
    for t in (0, 1, 2):
        assert not w.blocked("k", now=t)
        w.hit("k", now=t)
    assert w.blocked("k", now=3) and not w.blocked("khac", now=3)
    assert 1 <= w.retry_after("k", now=3) <= 10
    assert not w.blocked("k", now=12.5)     # hit đầu (t=0) đã hết cửa sổ -> còn 2
    w.reset("k")
    assert w.count("k", now=3) == 0


def test_public_path_rules():
    svc = AuthService(store=None, settings=AuthSettings(public_prefixes=("/c/",)))
    assert svc.public_path("/c/") and svc.public_path("/c/assets/app.js?x=1")
    for p in ("/", "/api/v1/accounts", "/c/../api/v1/accounts", "/api/c/", "/auth/admin/accounts", "/index.html", "/assets/x.js", ""):
        assert not svc.public_path(p), p
    assert not AuthService(store=None, settings=AuthSettings(public_prefixes=("/api/",))).public_path("/api/v1/x")   # /api/ không bao giờ công khai


def test_totp_replay_protection_and_window():
    svc = AuthService(store=None, settings=AuthSettings(secret_key=Fernet.generate_key().decode()))
    secret = pyotp.random_base32()
    user = {"user_id": "u1", "totp_secret_enc": svc.vault.enc(secret)}
    code = pyotp.TOTP(secret).now()
    assert svc._totp_ok(user, code) is True
    assert svc._totp_ok(user, code) is False            # mã đã dùng
    assert svc._totp_ok(user, "abcdef") is False and svc._totp_ok(user, "") is False


def test_master_totp_enforce_flag_default_off():
    from auth.service import Principal
    m = Principal("u1", "master", "master:admin", "Admin", ["*"])
    c = Principal("u2", "client", "mt5:1", "C", ["mt5:1"])
    off = AuthService(store=None, settings=AuthSettings())
    assert off.cfg.master_totp_enforce is False and not off.totp_gate(m, "/api/v1/accounts")   # mặc định không chặn ai
    on = AuthService(store=None, settings=AuthSettings(master_totp_enforce=True))
    assert on.totp_gate(m, "/api/v1/accounts") and on.totp_gate(m, "/api/v1/user/rules?x=1")
    for uri in ("/api/v1/me", "/auth/totp/setup", "/auth/me", "/", "/assets/app.js"):
        assert not on.totp_gate(m, uri), uri
    assert not on.totp_gate(c, "/api/v1/accounts")                                               # chỉ master
    m.totp_enabled = True
    assert not on.totp_gate(m, "/api/v1/accounts")                                               # đã bật TOTP -> qua
