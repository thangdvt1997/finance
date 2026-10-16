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
/mtlab/compile.sh $K > /out/compile-$K.txt 2>&1; grep Result /out/compile-$K.txt
# 3) .set + startup.ini + cho phep WebRequest
mkdir -p "$D/$M/Presets"
cat > "$D/$M/Presets/MTAgentReadOnly.set" <<SET
BridgeUrl=$BRIDGE/ingest/v1
AccountId=$ACC
Token=$TOKEN
HmacSecret=$HMAC
PairCode=${MT_PAIRCODE:-}
Symbols=${MT_SYMBOLS:-EURUSD}
Timeframes=M1,M5,M15,H1,H4,D1
SendIntervalSec=3
BackfillBars=50
TimeoutMs=5000
AllowInsecureHttp=true
SET
# .set rieng cho tai khoan THAT (PairCode...): /out/ea-$K.set (chmod 600, ngoai git) ghi de .set mac dinh cua lab
[ -f /out/ea-$K.set ] && cp /out/ea-$K.set "$D/$M/Presets/MTAgentReadOnly.set"
mkdir -p "$D/$M/Files"; cp "$D/$M/Presets/MTAgentReadOnly.set" "$D/$M/Files/MTAgentSmoke.set"
# MT4 offline khong chay EA -> che do smoke dung SCRIPT thay vi EA (MT_MODE=smoke)
if [ "${MT_MODE:-ea}" = smoke ] && [ "$K" = mt4 ]; then STARTUP=$'Script=MTAgentSmoke\nScriptParameters=MTAgentReadOnly.set'; else STARTUP=$'Expert=MTAgentReadOnly\nExpertParameters=MTAgentReadOnly.set'; fi
# MT_FIXTURE: "touch /root/mtlab/out/fixture-mt5" roi docker restart -> MOT LAN chay script MTAgentDealFixture thay EA (kiem chung deals bang fixture)
if [ -f /out/fixture-$K ] && [ "$K" = mt5 ]; then
  rm -f /out/fixture-$K
  STARTUP=$'Script=MTAgentDealFixture
ScriptParameters=MTAgentDealFixture.set'
  printf 'BridgeUrl=%s/ingest/v1
AccountId=%s
Token=%s
HmacSecret=%s
AllowInsecureHttp=true
' "$BRIDGE" "$ACC" "$TOKEN" "$HMAC" > "$D/$M/Presets/MTAgentDealFixture.set"
fi
# CHONG BO QUEN JOB (su co 2026-10-15: job-mt5.cfg con sot -> terminal live chay script, canon M1 khuyet ~21h): cfg chuan cua terminal LIVE la
# SYMLINK /out/job-mt5.cfg -> xchg/job-mt5.cfg (data-keeper thay va tu xoa sau DK_JOB_CFG_TTL_S). Khi khoi dong, neu cfg dang symlink va cu hon
# JOB_TTL_MIN phut (mac dinh 120) -> bo qua + doi ten .stale-<ts>, chay EA. cfg file thuong (terminal phu hist) khong bi TTL.
JOB_TTL_MIN=${JOB_TTL_MIN:-120}
if [ -L /out/job-$K.cfg ] && [ -n "$(find -L /out/job-$K.cfg -mmin +$JOB_TTL_MIN 2>/dev/null)" ]; then
  echo "[job-$K.cfg qua han ${JOB_TTL_MIN} phut: BO QUA, chay EA]"
  mv -f "$(readlink -f /out/job-$K.cfg)" "/out/job-$K.cfg.stale-$(date +%Y%m%d%H%M)" 2>/dev/null; rm -f /out/job-$K.cfg
fi
# JOB (xuat lich su/thong tin): /out/job-mt5.cfg 2 dong: ten script, ten .set (trong /out). Giu file => moi lan khoi dong chay job; xoa file de tra EA.
if [ -f /out/job-$K.cfg ] && [ "$K" = mt5 ]; then
  JS=$(sed -n 1p /out/job-$K.cfg | tr -d '
'); JP=$(sed -n 2p /out/job-$K.cfg | tr -d '
')
  [ -f /out/$JP ] && cp /out/$JP "$D/$M/Presets/$JP"
  STARTUP=$'Script='"$JS"$'
ScriptParameters='"$JP"
fi
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
Period=H1
INI
if [ "$K" = mt5 ]; then CFG="$D/Config/common.ini"; else CFG="$D/config/terminal.ini"; fi
# MaxBars: che do JOB (xuat lich su M1 toan bo) can 100M; che do EA chi can vai nghin nen (BackfillBars) -> MT5_MAXBARS_EA
# (mac dinh 100000 ~ 70 ngay M1) de giam RAM terminal (100M: ~4.5g khi chay EA 7 ma).
MAXB=${MT5_MAXBARS_EA:-100000}; [ -f /out/job-$K.cfg ] && MAXB=100000000
[ "$K" = mt5 ] && python3 /mtlab/patch_ini.py "$CFG" Charts MaxBars=$MAXB
python3 /mtlab/patch_ini.py "$CFG" Experts WebRequest=1 "WebRequestUrl=$BRIDGE" AllowLiveTrading=0 Enabled=1
if [ "$K" = mt4 ]; then python3 /mtlab/patch_chr.py "$D/profiles/default/chart01.CHR" "$D/$M/Presets/MTAgentReadOnly.set" $([ "${MT_MODE:-ea}" = smoke ] && echo --strip); fi
# don cac chart da gan EA tu lan chay truoc (tranh nhan ban EA moi lan restart; MT5 luu chart khi thoat)
[ "$K" = mt5 ] && grep -l -a MTAgentReadOnly "$D"/Profiles/Charts/*/*.chr 2>/dev/null | while read -r f; do rm -f "$f"; done
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
  wine $TERM_EXE /portable /config:startup.ini &
  CHILD=$!
  wait $CHILD
  echo "[terminal exited rc=$?] restart in 10s"; sleep 10
done
