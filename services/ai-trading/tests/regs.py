"""Registry dùng cho test: registry thật (thẻ nền) + thẻ KB-1..4 làm fixture (đã dọn khỏi registry thật 2026-10-15, xem docs/handoff/CLEANUP_scenarios.md)."""
import shutil
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_d = Path(tempfile.mkdtemp(prefix="ai_reg_"))
for _src in (ROOT / "registry", ROOT / "tests" / "fixtures" / "registry"):
    for _f in _src.glob("*.yaml"):
        shutil.copy(_f, _d / _f.name)
REG = str(_d)
