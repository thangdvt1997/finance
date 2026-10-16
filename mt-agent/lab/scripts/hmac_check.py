#!/usr/bin/env python3
"""Kiem chung HMAC end-to-end tren bridge THAT (chay tren VPS host, khong in secret).

Dung:  python3 hmac_check.py <bridge_url> <account_id> <platform> <env_file_with_TOKEN_and_HMAC_lines> <TOKEN_VAR> <HMAC_VAR>
Gui heartbeat (khong du lieu): thieu chu ky -> 401, chu ky sai -> 401, chu ky cho body khac -> 401, dung -> 200, replay nonce -> 409.
"""
import hashlib
import hmac
import json
import sys
import time
import urllib.error
import urllib.request

url, acc, plat, envf, tvar, hvar = sys.argv[1:7]
env = dict(l.strip().split("=", 1) for l in open(envf) if "=" in l and not l.startswith("#"))
token, secret = env[tvar], env[hvar]


def post(body: dict, sig=None, raw=None):
    raw = raw if raw is not None else json.dumps(body).encode()
    h = {"Authorization": f"Bearer {token}", "X-MT-Account": acc, "Content-Type": "application/json"}
    if sig:
        h["X-MT-Sig"] = sig
    try:
        with urllib.request.urlopen(urllib.request.Request(url.rstrip("/") + "/ingest/v1", data=raw, headers=h), timeout=10) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def sig(ts, nonce, raw):
    return hmac.new(secret.encode(), f"{ts}.{nonce}.".encode() + raw, hashlib.sha256).hexdigest()


def batch(nonce):
    return {"v": 1, "account_id": acc, "platform": plat, "ts": int(time.time()), "nonce": nonce, "seq": 0}


res = {}
b = batch("hc-nosig-%d" % time.time())
res["thieu_chu_ky"] = (post(b), 401)
b = batch("hc-bad-%d" % time.time())
res["chu_ky_sai"] = (post(b, sig="00" * 32), 401)
b = batch("hc-other-%d" % time.time())
raw = json.dumps(b).encode()
res["chu_ky_cho_body_khac"] = (post(b, sig=sig(b["ts"], b["nonce"], raw + b" ")), 401)
b = batch("hc-ok-%d" % time.time())
raw = json.dumps(b).encode()
s = sig(b["ts"], b["nonce"], raw)
res["chu_ky_dung"] = (post(b, sig=s, raw=raw), 200)
res["replay_nonce"] = (post(b, sig=s, raw=raw), 409)
ok = True
for k, (got, want) in res.items():
    print(f"{k}: HTTP {got} (mong doi {want}) {'OK' if got == want else 'SAI'}")
    ok &= got == want
sys.exit(0 if ok else 1)
