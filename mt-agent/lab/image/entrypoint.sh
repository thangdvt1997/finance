#!/bin/bash
# env: MT_KIND=mt4|mt5, WINEPREFIX (volume /wine), VNC_PORT (5900)
set -u
export WINEPREFIX=${WINEPREFIX:-/wine}
rm -f /tmp/.X1-lock /tmp/.X11-unix/X1
Xvfb :1 -screen 0 1280x800x24 -nolisten tcp &
sleep 2
fluxbox >/dev/null 2>&1 &
x11vnc -display :1 -forever -shared -nopw -rfbport 5900 -quiet -listen 0.0.0.0 >/var/log/x11vnc.log 2>&1 &
[ -d "$WINEPREFIX/drive_c" ] || { echo "[init] wineboot prefix"; wineboot -i; wineserver -w; }
if [ -x /mtlab/start-$MT_KIND.sh ]; then exec /mtlab/start-$MT_KIND.sh; fi
exec sleep infinity
