#!/bin/bash
# usage: compile.sh mt4|mt5   -> copy EA sources (/ea) into portable data dir + compile with MetaEditor; log to /out/compile-<kind>.log
export WINEPREFIX=/wine WINEDLLOVERRIDES="mscoree,mshtml=d" DISPLAY=:1
K=$1
if [ "$K" = mt4 ]; then D="/wine/drive_c/Program Files (x86)/MetaTrader 4"; ED=metaeditor.exe; M=MQL4; EXT=mq4; else D="/wine/drive_c/Program Files/MetaTrader 5"; ED=MetaEditor64.exe; M=MQL5; EXT=mq5; fi
mkdir -p "$D/$M/Include/MTAgent" "$D/$M/Experts"
cp /ea/Include/MTAgent/Core.mqh "$D/$M/Include/MTAgent/"
cp /ea/$M/Experts/MTAgentReadOnly.$EXT "$D/$M/Experts/"
rm -f "$D/$M/Experts/MTAgentReadOnly.ex${EXT: -1}" /out/compile-$K.log
cd "$D"
wine $ED /portable /compile:"$M\Experts\MTAgentReadOnly.$EXT" /log:"C:\compile-$K.log"
sleep 2
cp /wine/drive_c/compile-$K.log /out/compile-$K.log 2>/dev/null
iconv -f UTF-16LE -t UTF-8 /out/compile-$K.log 2>/dev/null || cat /out/compile-$K.log
ls -l "$D/$M/Experts/"

# MT4: bien dich them script smoke (neu co)
if [ "$K" = mt4 ] && [ -f /ea/MQL4/Scripts/MTAgentSmoke.mq4 ]; then
  mkdir -p "$D/MQL4/Scripts"; cp /ea/MQL4/Scripts/MTAgentSmoke.mq4 "$D/MQL4/Scripts/"
  wine $ED /portable /compile:'MQL4\Scripts\MTAgentSmoke.mq4' /log:'C:\compile-smoke.log'; sleep 1
  cp /wine/drive_c/compile-smoke.log /out/compile-smoke.log; cat /out/compile-smoke.log | grep -aE "Result|error|warning"
fi

# MT5: bien dich them script fixture deals (neu co)
if [ "$K" = mt5 ] && [ -f /ea/MQL5/Scripts/MTAgentDealFixture.mq5 ]; then
  mkdir -p "$D/MQL5/Scripts"; cp /ea/MQL5/Scripts/MTAgentDealFixture.mq5 "$D/MQL5/Scripts/"
  wine $ED /portable /compile:'MQL5\Scripts\MTAgentDealFixture.mq5' /log:'C:\compile-fixture.log'; sleep 1
  cp /wine/drive_c/compile-fixture.log /out/compile-fixture.log; iconv -f UTF-16LE -t UTF-8 /out/compile-fixture.log | grep -aE "Result|error|warning"
fi

# MT5: script xuat lich su (doc-chi)
if [ "$K" = mt5 ] && [ -f /ea/MQL5/Scripts/MTAgentExport.mq5 ]; then
  cp /ea/MQL5/Scripts/MTAgentExport.mq5 "$D/MQL5/Scripts/"
  wine $ED /portable /compile:'MQL5\Scripts\MTAgentExport.mq5' /log:'C:\compile-export.log'; sleep 1
  cp /wine/drive_c/compile-export.log /out/compile-export.log; iconv -f UTF-16LE -t UTF-8 /out/compile-export.log | grep -aE "Result|error|warning"
fi
