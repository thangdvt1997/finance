#!/bin/bash
# Entry cua container mtlab-mt4/mt5 (goi tu /entrypoint.sh qua start-$MT_KIND.sh). Idempotent.
export WINEPREFIX=/wine WINEDLLOVERRIDES="mscoree,mshtml=d" DISPLAY=:1
K=$MT_KIND
if [ "$K" = mt4 ]; then D="/wine/drive_c/Program Files (x86)/MetaTrader 4"; TERM_EXE=terminal.exe; SETUP=mt4setup.exe; M=MQL4; EXT=mq4
else D="/wine/drive_c/Program Files/MetaTrader 5"; TERM_EXE=terminal64.exe; SETUP=mt5setup.exe; M=MQL5; EXT=mq5; fi
TOKEN=$(printenv MT_TOKEN_DEMO_${K^^}_01)
HMAC=$(printenv MT_HMAC_DEMO_${K^^}_01)   # secret ky X-MT-Sig (tai khoan lab bat HMAC)
ACC=demo-$K-01
# MT bat buoc host co dau cham trong danh sach WebRequest; MT4 chi dung cong 80/443 ->
# bridge.lab = 127.0.0.1, forwarder :80 -> mt-bridge:8000 (mang tradingsys_internal)
grep -v bridge.lab /etc/hosts > /tmp/hosts.new; cat /tmp/hosts.new > /etc/hosts; echo "127.0.0.1 bridge.lab" >> /etc/hosts
(python3 /mtlab/tcp-fwd.py 127.0.0.1 80 mt-bridge 8000 >/out/fwd-$K.log 2>&1 &)
BRIDGE=${BRIDGE_BASE:-http://bridge.lab}
pkill xmessage
# 1) cai dat (lan dau)
if [ ! -f "$D/$TERM_EXE" ]; then
  echo "[install] $SETUP"; timeout 300 wine /dl/$SETUP /auto; pkill -f terminal; sleep 2
fi
cd "$D"
# 2) khoi tao du lieu portable + bien dich EA
if [ ! -d "$D/$M" ]; then (wine $TERM_EXE /portable &) ; sleep 40; pkill -f terminal; sleep 3; fi
/mtlab/compile-feed.sh > /out/compile-feed.txt 2>&1; grep -a Result /out/compile-feed.txt
# 3) .set + startup.ini + cho phep WebRequest
mkdir -p "$D/$M/Presets" "$D/$M/Files"
# data-keeper (heal) co the ghi danh sach dong bo /out/feed_symbols.txt; uu tien neu co, neu khong dung /ea/feed_symbols.txt
if [ -s /out/feed_symbols.txt ]; then cp /out/feed_symbols.txt "$D/$M/Files/feed_symbols.txt"; else cp /ea/feed_symbols.txt "$D/$M/Files/feed_symbols.txt"; fi
cat > "$D/$M/Presets/MTAgentMarketFeed.set" <<SET
BridgeUrl=$BRIDGE/ingest/v1
AccountId=mt5:${MT_LOGIN}-feed
PairCode=${MT_PAIRCODE:-}
SymbolsFile=feed_symbols.txt
ExcludeSymbols=
ScanMs=${FEED_SCAN_MS:-20}
FlushMs=${FEED_FLUSH_MS:-100}
MaxMsgPerSec=${FEED_MSG_PER_SEC:-10}
MaxQuotesPerBatch=400
HeartbeatSec=5
TimeoutMs=1500
StartDelaySec=${FEED_START_DELAY:-90}
AllowInsecureHttp=true
SET
STARTUP=$'Expert=MTAgentMarketFeed\nExpertParameters=MTAgentMarketFeed.set'
cat > "$D/startup.ini" <<INI
[Common]
$( [ -n "$MT_LOGIN" ] && echo "Login=$MT_LOGIN" )
$( [ -n "$MT_SERVER" ] && echo "Server=$MT_SERVER" )
$( [ -n "$MT_PASSWORD" ] && echo "Password=$MT_PASSWORD" )
[Experts]
AllowLiveTrading=0
AllowDllImport=0
Enabled=1
Account=0
Profile=0
[StartUp]
$STARTUP
Symbol=EURUSD
Period=M1
INI
if [ "$K" = mt5 ]; then CFG="$D/Config/common.ini"; else CFG="$D/config/terminal.ini"; fi
# MaxBars: che do JOB (xuat lich su M1 toan bo) can 100M; che do EA chi can vai nghin nen (BackfillBars) -> MT5_MAXBARS_EA
# (mac dinh 100000 ~ 70 ngay M1) de giam RAM terminal (100M: ~4.5g khi chay EA 7 ma).
MAXB=5000
[ "$K" = mt5 ] && python3 /mtlab/patch_ini.py "$CFG" Charts MaxBars=$MAXB
python3 /mtlab/patch_ini.py "$CFG" Experts WebRequest=1 "WebRequestUrl=$BRIDGE" AllowLiveTrading=0 Enabled=1
if [ "$K" = mt4 ]; then python3 /mtlab/patch_chr.py "$D/profiles/default/chart01.CHR" "$D/$M/Presets/MTAgentReadOnly.set" $([ "${MT_MODE:-ea}" = smoke ] && echo --strip); fi
# don cac chart da gan EA tu lan chay truoc (tranh nhan ban EA moi lan restart; MT5 luu chart khi thoat)
# feed chi can 1 chart (EA): xoa het chart mac dinh/cu de giam CPU ve (Wine/Xvfb)
[ "$K" = mt5 ] && rm -f "$D"/Profiles/Charts/*/*.chr
# GUI sau khi len (them URL WebRequest; MT4 smoke chay script)
nohup setsid /mtlab/post-start.sh $K >/out/post-start-$K.log 2>&1 &
# 4) chay terminal, tu khoi dong lai neu chet
CHILD=
graceful() {   # docker stop -> SIGTERM: dong cua so chinh bang alt+F4 de terminal ghi settings (danh sach URL WebRequest...)
  STOP=1
  xdotool key alt+F4 2>/dev/null; sleep 1; xdotool key Return 2>/dev/null
  for i in $(seq 1 20); do pgrep -f "$TERM_EXE" >/dev/null || break; sleep 1; done
  wineserver -k 2>/dev/null; exit 0
}
trap graceful TERM INT
STOP=0
while [ "$STOP" = 0 ]; do
  # LiveUpdate co the de terminal chay tach roi: dang co terminal thi KHONG mo them (tranh vong lap 12 s)
  if pgrep -f "$TERM_EXE" >/dev/null; then sleep 10; continue; fi
  wine $TERM_EXE /portable /config:startup.ini &
  CHILD=$!
  wait $CHILD
  echo "[terminal exited rc=$?] restart in 10s"; sleep 10
done
