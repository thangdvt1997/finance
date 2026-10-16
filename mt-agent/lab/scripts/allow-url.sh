#!/bin/bash
# Tu dong hoa Tools>Options>Experts: them URL vao danh sach WebRequest (MT5; 1280x800). usage: allow-url.sh <url>
# Luu y: danh sach nay duoc terminal luu ma hoa trong Config/settings.ini (khong sua tay bang ini duoc).
export DISPLAY=:1
URL=${1:-http://bridge.lab}
xdotool mousemove 931 634 click 1; sleep 2   # dong wizard "Open account" neu dang hien (Cancel)
xdotool key ctrl+o; sleep 2
xdotool mousemove 510 279 click 1; sleep 2
xdotool mousemove 500 499 click --repeat 2 --delay 150 1; sleep 1
xdotool type --delay 80 "$URL"; xdotool key Return; sleep 1
import -window root /out/allow-url.png
xdotool mousemove 755 634 click 1; sleep 2
if [ "$2" = --save ]; then sleep 3; xdotool key alt+F4; sleep 2; xdotool key Return; fi   # tuy chon: thoat sach de luu settings (terminal tu khoi dong lai)
