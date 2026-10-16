#!/bin/bash
# MT4 (1280x800): Tools>Options>Expert Advisors: bat Allow automated trading + WebRequest (chi click neu chua tick), them URL.
# usage: allow-url-mt4.sh <url> [--save]
export DISPLAY=:1
URL=${1:-http://bridge.lab}
checked() {   # checked X Y : o tick co pixel toi trong vung 9x9 quanh (X,Y)
  import -window root /tmp/ck.png
  m=$(convert /tmp/ck.png -crop 9x9+$(($1-4))+$(($2-4)) +repage -colorspace Gray -format '%[fx:minima]' info:)
  python3 -c "import sys; sys.exit(0 if float('$m') < 0.5 else 1)"
}
xdotool mousemove 859 565 click 1; sleep 1          # dong wizard Open account (Cancel) neu co
xdotool mousemove 195 41 click 1; sleep 1; xdotool mousemove 226 171 click 1; sleep 2   # Tools > Options
xdotool mousemove 595 246 click 1; sleep 1          # tab Expert Advisors
checked 394 289 || { xdotool mousemove 394 289 click 1; sleep 1; }     # Allow automated trading
checked 394 411 || { xdotool mousemove 394 411 click 1; sleep 1; }     # Allow WebRequest
xdotool mousemove 520 441 click --repeat 2 --delay 150 1; sleep 1
xdotool type --delay 80 "$URL"; xdotool key Return; sleep 1
import -window root /out/allow-url-mt4.png
xdotool mousemove 726 566 click 1; sleep 2          # OK
if [ "$2" = --save ]; then sleep 3; xdotool key alt+F4; sleep 2; xdotool key Return; fi
