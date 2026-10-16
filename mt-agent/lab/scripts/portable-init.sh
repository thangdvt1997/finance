#!/bin/bash
# usage: portable-init.sh <install dir (unix path)> <terminal exe>
export WINEPREFIX=/wine WINEDLLOVERRIDES="mscoree,mshtml=d" DISPLAY=:1
pkill xmessage
cd "$1"
(wine "$2" /portable >/out/term-init.log 2>&1 &)
sleep 40
ls "$1"
