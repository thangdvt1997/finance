from __future__ import annotations

import os
from pathlib import Path

import pytest

from pattern_engine.csvio import load_csv
from pattern_engine.specs import load_specs

FIXTURES = Path(__file__).parent / "fixtures"
# cài không-editable (run_tests.sh) -> DEFAULT_DIR trỏ site-packages; chỉ định spec/ của mã nguồn
os.environ.setdefault("PATTERN_SPEC_DIR", str(Path(__file__).resolve().parents[1] / "spec"))


@pytest.fixture(scope="session")
def specs():
    return load_specs()


@pytest.fixture(scope="session")
def xau_bars():
    """XAUUSD M15 2026-09-18 .. 2026-10-08 (UTC) — phủ 3 đoạn ảnh mẫu (xem fixtures/README.md)."""
    return load_csv(FIXTURES / "xauusd_m15_gcf.csv")


def sig_key(s):
    """Dạng so sánh sâu của 1 tín hiệu (không phụ thuộc đối tượng)."""
    return (s.pattern, s.state, s.setup_id, s.bar_index, s.bar_ts.isoformat(), round(s.score, 6), s.reason,
            tuple(sorted((k, round(float(v), 6)) for k, v in s.levels.items())),
            tuple((x["id"], x["ok"], x["detail"]) for x in s.steps))
