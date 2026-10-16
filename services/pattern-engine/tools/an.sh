python -m pytest -q --tb=short -p no:cacheprovider 2>&1 | tail -15
python tools/dbg_synth.py 2>&1 | grep -E "EVENT|pivots" | tail -8
