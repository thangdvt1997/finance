#!/bin/bash
# Bien dich EA feed (mount /feedsrc = mt-agent/MQL5) vao terminal feed. Khong dung toi MTAgentReadOnly.
export WINEPREFIX=/wine WINEDLLOVERRIDES="mscoree,mshtml=d" DISPLAY=:1
D="/wine/drive_c/Program Files/MetaTrader 5"
mkdir -p "$D/MQL5/Include/MTAgent" "$D/MQL5/Experts"
cp /ea/Include/MTAgent/Core.mqh "$D/MQL5/Include/MTAgent/"
cp /feedsrc/Experts/MTAgentMarketFeed.mq5 "$D/MQL5/Experts/"
rm -f "$D/MQL5/Experts/MTAgentMarketFeed.ex5" /out/compile-feed.log
cd "$D"
wine MetaEditor64.exe /portable /compile:'MQL5\Experts\MTAgentMarketFeed.mq5' /log:'C:\compile-feed.log'
sleep 2
cp /wine/drive_c/compile-feed.log /out/compile-feed.log 2>/dev/null
iconv -f UTF-16LE -t UTF-8 /out/compile-feed.log 2>/dev/null || cat /out/compile-feed.log
ls -l "$D/MQL5/Experts/"
