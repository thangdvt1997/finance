"""Quet tinh: service journal KHONG co duong dat/sua/dong lenh va CHI ghi bang journal_notes."""
import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "journal"
FORBID = re.compile(r"order_send|OrderSend|OrderClose(?!Time|Price)|OrderModify|OrderDelete|CTrade|PositionClose|place_order|close_position|modify_order|TRADE_ACTION|submit_order", re.I)
WRITE_SQL = re.compile(r"\b(INSERT\s+INTO|UPDATE|DELETE\s+FROM|TRUNCATE(?:\s+TABLE)?|DROP\s+TABLE|ALTER\s+TABLE|CREATE\s+TABLE)\s+([A-Za-z_][A-Za-z0-9_]*)", re.I)


def test_no_trading_code():
    bad = [p.name for p in SRC.rglob("*.py") if FORBID.search(p.read_text(encoding="utf-8"))]
    assert bad == []


def test_only_journal_notes_is_written():
    targets: dict[str, set[str]] = {}
    for p in SRC.rglob("*.py"):
        for m in WRITE_SQL.finditer(p.read_text(encoding="utf-8")):
            if m.group(2).lower() in {"set", "the", "a"}:  # tu trong comment/tieng Anh
                continue
            targets.setdefault(m.group(2).lower(), set()).add(p.name)
    assert set(targets) <= {"journal_notes"}, targets
    assert targets["journal_notes"] == {"notes.py"}  # chi module notes.py duoc phep ghi


def test_readonly_source_has_no_write_sql():
    src = (SRC / "source.py").read_text(encoding="utf-8")
    assert not WRITE_SQL.search(src)
