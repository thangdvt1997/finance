#!/bin/bash
# chay Python Windows trong Wine: py.sh <script.py|args>
export WINEPREFIX=/wine WINEDLLOVERRIDES="mscoree,mshtml=d" DISPLAY=:1
exec wine 'C:\Python311\python.exe' "$@"
