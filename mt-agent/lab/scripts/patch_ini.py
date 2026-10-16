#!/usr/bin/env python3
"""patch_ini.py <file> <section> key=value ... : sua file ini UTF-16LE (BOM) cua MT4/MT5, giu nguyen phan con lai."""
import sys, io
path, section, *kvs = sys.argv[1:]
try:
    raw = open(path, 'rb').read()
except FileNotFoundError:
    raw = b''
if raw[:2] == b'\xff\xfe':
    txt = raw[2:].decode('utf-16-le')
elif raw:
    txt = raw.decode('utf-8', 'ignore')
else:
    txt = ''
lines = txt.replace('\r\n', '\n').split('\n')
out, i, found = [], 0, False
want = dict(kv.split('=', 1) for kv in kvs)
cur = None; done = set()
def flush_missing():
    for k, v in want.items():
        if k not in done:
            out.append(f'{k}={v}')
for ln in lines:
    s = ln.strip()
    if s.startswith('[') and s.endswith(']'):
        if cur == section: flush_missing()
        cur = s[1:-1]
        if cur == section: found = True
        out.append(ln); continue
    if cur == section and '=' in ln:
        k = ln.split('=', 1)[0].strip()
        if k in want:
            out.append(f'{k}={want[k]}'); done.add(k); continue
    out.append(ln)
if cur == section: flush_missing()
if not found:
    out.append(f'[{section}]'); flush_missing()
res = '\r\n'.join(l for l in out).rstrip('\r\n') + '\r\n'
open(path, 'wb').write(b'\xff\xfe' + res.encode('utf-16-le'))
