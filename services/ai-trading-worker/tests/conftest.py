import sys
from pathlib import Path

R = Path(__file__).resolve().parents[2]
for p in (R / "ai-trading" / "src", R / "pattern-research", R / "ai-trading-worker" / "src"):
    sys.path.insert(0, str(p))
