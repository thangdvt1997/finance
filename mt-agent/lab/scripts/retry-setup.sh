#!/bin/bash
export WINEPREFIX=/wine WINEDLLOVERRIDES="mscoree,mshtml=d" DISPLAY=:1
pkill -f 'wine.*setup' ; pkill xmessage; sleep 1
winecfg -v ${1:-win10}
(wine /dl/mt5setup.exe /auto >/out/mt5setup.log 2>&1 &)
sleep 40
import -window root /out/s5.png
ls "/wine/drive_c/Program Files"
