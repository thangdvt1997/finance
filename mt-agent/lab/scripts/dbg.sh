#!/bin/bash
# chay terminal thu cong (khong ini) de debug; usage: dbg.sh mt4|mt5 [args]
export WINEPREFIX=/wine WINEDLLOVERRIDES="mscoree,mshtml=d" DISPLAY=:1
pkill -f start-term; pkill -f 'terminal'; wineserver -k; sleep 3
if [ "$1" = mt4 ]; then D="/wine/drive_c/Program Files (x86)/MetaTrader 4"; T=terminal.exe; else D="/wine/drive_c/Program Files/MetaTrader 5"; T=terminal64.exe; fi
cd "$D"; (wine $T /portable $2 >/out/t.log 2>&1 &); sleep ${3:-25}
tail -5 "logs/$(date +%Y%m%d).log" | iconv -f UTF-16LE -t UTF-8 2>/dev/null || tail -5 logs/$(date +%Y%m%d).log
pgrep -a terminal
