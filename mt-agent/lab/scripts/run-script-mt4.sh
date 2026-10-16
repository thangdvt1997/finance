#!/bin/bash
# MT4 (1280x800), ngay sau khi terminal khoi dong: dong wizard "Open account" + dialog Login (Cancel), mo Navigator>Scripts
# va double-click MTAgentSmoke (chay tren chart dang active). Chi dung ngay sau restart (Navigator dang thu gon).
export DISPLAY=:1
xdotool mousemove 863 568 click 1; sleep 2          # Cancel wizard
xdotool mousemove 451 377 click 1; sleep 2          # Cancel login
xdotool mousemove 63 454 click 1; sleep 1; xdotool key Right; sleep 1   # chon Scripts + mo rong (phim Right)
xdotool mousemove 103 486 click --repeat 2 --delay 150 1; sleep 14   # MTAgentSmoke
import -window root /out/run-script.png
