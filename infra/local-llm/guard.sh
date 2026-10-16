#!/bin/sh
# Tu choi khoi dong model neu load host > 60 (cap tren 64 luong); chay voi nice 19.
l=$(cut -d' ' -f1 /proc/loadavg); l=${l%.*}
if [ "$l" -gt "${LLM_MAX_LOAD:-60}" ]; then echo "load host cao ($l) - tu choi" >&2; exit 75; fi
exec nice -n 19 "$@"
