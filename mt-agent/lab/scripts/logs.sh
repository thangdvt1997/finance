#!/bin/bash
# in log EA/terminal moi nhat (UTF-16 -> UTF-8), tail N
K=$MT_KIND
if [ "$K" = mt4 ]; then D="/wine/drive_c/Program Files (x86)/MetaTrader 4"; else D="/wine/drive_c/Program Files/MetaTrader 5"; fi
for d in "$D/MQL${K#mt}/Logs" "$D/logs" "$D/Logs"; do
  f=$(ls -t "$d"/*.log 2>/dev/null | head -1); [ -n "$f" ] && { echo "== $f"; { if [ "$K" = mt5 ]; then iconv -f UTF-16LE -t UTF-8 "$f"; else cat "$f"; fi; } | tail -${1:-15} | sed -E "s/(Token|PairCode|HmacSecret|Password)=[^; ]*/\1=***/g" | cut -c1-220; }
done
