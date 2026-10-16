"""Kiem tra tinh cho ma MQL (khong bien dich duoc o day): khop ten truong JSON voi schema, can bang ngoac."""
import re
from pathlib import Path

from mtbridge import protocol

AGENT = Path(__file__).resolve().parents[3] / "mt-agent"
FILES = [AGENT / "Include/MTAgent/Core.mqh", AGENT / "MQL4/Experts/MTAgentReadOnly.mq4", AGENT / "MQL5/Experts/MTAgentReadOnly.mq5"]
# moi file MQL do du an viet (Include + MQL4 + MQL5, ke ca script smoke/fixture); lab/ la ha tang, khong phai MQL
ALL_MQL = sorted(p for ext in ("*.mq4", "*.mq5", "*.mqh") for p in AGENT.rglob(ext) if "lab" not in p.relative_to(AGENT).parts)


def strip_comments_and_strings(src: str) -> str:
    pat = re.compile(r'"(?:\\.|[^"\\])*"|//[^\n]*|/\*.*?\*/', re.S)
    return pat.sub(lambda m: '""' if m.group(0).startswith('"') else " ", src)


def test_brackets_balanced():
    for f in FILES:
        s = strip_comments_and_strings(f.read_text(encoding="utf-8"))
        for a, b in ("()", "{}", "[]"):
            assert s.count(a) == s.count(b), f"{f.name}: {a}{b}"
        assert s.count("#ifdef") + s.count("#ifndef") == s.count("#endif"), f.name


def test_json_keys_match_protocol_schema():
    src = FILES[0].read_text(encoding="utf-8")
    keys = set(re.findall(r'\\"(\w+)\\":', src))
    allowed: set[str] = set()
    for m in (protocol.Batch, protocol.AccountIn, protocol.PositionIn, protocol.OrderIn, protocol.QuoteIn, protocol.BarIn, protocol.DealIn, protocol.AgentIn, protocol.RegisterIn):
        allowed |= set(m.model_fields)
    assert keys, "khong tim thay khoa JSON"
    assert keys <= allowed, f"khoa EA khong co trong schema: {keys - allowed}"
    required = set(protocol.Batch.model_fields) - {"positions", "orders", "quotes", "bars", "seq", "server_time", "account"}
    assert required <= keys


def test_ea_is_outbound_only():
    src = "".join(f.read_text(encoding="utf-8") for f in FILES)
    assert "SocketCreate" not in src and "SocketBind" not in src and "SocketListen" not in src  # khong mo cong vao
    assert "WebRequest(\"POST\"" in src


def test_deal_keys_complete():
    """Core.mqh phai phat du moi khoa DealIn (khop ten) va khoa `deals` cua Batch."""
    src = FILES[0].read_text(encoding="utf-8")
    keys = set(re.findall(r'\\"(\w+)\\":', src))
    assert set(protocol.DealIn.model_fields) <= keys, f"thieu khoa deal: {set(protocol.DealIn.model_fields) - keys}"
    assert "deals" in protocol.Batch.model_fields and "deals" in keys
    assert "AGT_MAX_DEALS_BATCH  200" in src or "AGT_MAX_DEALS_BATCH 200" in src


def test_deal_cursor_commit_only_on_ack():
    """Cursor deals chi tien trong AGT_CommitDeals, goi sau 200/409 (giong bars)."""
    src = strip_comments_and_strings(FILES[0].read_text(encoding="utf-8"))
    assert len(re.findall(r"g_deal_cursor_time\s*=\s*g_deal_pending_cursor", src)) == 1
    tick = src[src.index("void AGT_Tick"):]
    assert tick.index("AGT_CommitDeals") < tick.index("else")


def test_ea_has_no_trading_functions():
    """READ-ONLY tuyet doi: khong ham dat/sua/dong lenh o bat ky file MQL nao (tru lab)."""
    assert ALL_MQL, "khong tim thay file MQL"
    banned = [
        "OrderSend", "OrderSendAsync", "OrderModify", "OrderClose", "OrderCloseBy", "OrderDelete",
        "CTrade", "CPositionInfo", "COrderInfo", "Trade.mqh", "PositionOpen", "PositionClose", "PositionModify",
        "PositionClosePartial", "TradeRequest", "MqlTradeRequest", "MqlTradeCheckResult", "OrderCheck",
        "SocketCreate", "SocketBind", "SocketListen", "ShellExecute", "#import", "DllImport",
    ]
    for f in ALL_MQL:
        src = strip_comments_and_strings(f.read_text(encoding="utf-8"))
        for name in banned:
            assert not re.search(r"(?<![A-Za-z0-9_])" + re.escape(name) + r"(?![A-Za-z0-9_])" if name[0].isalpha() else re.escape(name), src), f"{f.name}: {name}"


def test_ea_never_logs_secrets():
    """Token/HMAC khong duoc dua vao Print/Comment/Alert (log Experts va Comment tren chart)."""
    for f in ALL_MQL:
        src = strip_comments_and_strings(f.read_text(encoding="utf-8"))
        for m in re.finditer(r"\b(Print|Comment|Alert|PrintFormat)\s*\(([^;]*)\)\s*;", src, re.S):
            args = re.sub(r"StringLen\([^()]*\)", "", m.group(2))  # do dai thi duoc in, gia tri thi khong
            assert not re.search(r"\b(g_token|g_hmac_secret|Token|HmacSecret|tok|hs)\b", args), f"{f.name}: {m.group(0)[:80]}"


def test_ea_has_pairing_inputs_and_status_display():
    src = (AGENT / "Include/MTAgent/Core.mqh").read_text(encoding="utf-8")
    for needle in ("AGT_Register", "g_pair_code", "g_pair_shown", "/register", "AGT_AgentJson", "code == 202", "code == 403"):
        assert needle in src, needle
    for f in (AGENT / "MQL4/Experts/MTAgentReadOnly.mq4", AGENT / "MQL5/Experts/MTAgentReadOnly.mq5"):
        assert "input string PairCode" in f.read_text(encoding="utf-8")
