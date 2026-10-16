#!/bin/bash
# runimp.sh SYM... -> importer in analytics image
docker run --rm --user root -v /root/trading-system/data/research/patterns:/out -v /root/trading-system/services/pattern-research:/app:ro -e PYTHONPATH=/app:/out/.pylib -e PATTERN_DATA=/out --entrypoint python tradingsys-analytics:latest -m pattern_research.import_mt5 "$@"
