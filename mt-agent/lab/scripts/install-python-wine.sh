#!/bin/bash
# Cai Python Windows 3.11 + goi MetaTrader5 trong WINEPREFIX cua container mt5 (de thu adapter mt5_direct).
# Nguon: https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe
export WINEPREFIX=/wine WINEDLLOVERRIDES="mscoree,mshtml=d" DISPLAY=:1
cd /tmp
[ -f /dl/python-3.11.9-amd64.exe ] || curl -fsSL -o /dl/python-3.11.9-amd64.exe https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe 2>/dev/null || curl -fsSL -o /tmp/python-3.11.9-amd64.exe https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe
PY=/dl/python-3.11.9-amd64.exe; [ -f $PY ] || PY=/tmp/python-3.11.9-amd64.exe
sha256sum $PY
wine $PY /quiet InstallAllUsers=1 PrependPath=1 Include_test=0 Include_launcher=0 TargetDir='C:\Python311'
wine 'C:\Python311\python.exe' --version
wine 'C:\Python311\python.exe' -m pip install --no-warn-script-location MetaTrader5 pyyaml pydantic 2>&1 | tail -3
