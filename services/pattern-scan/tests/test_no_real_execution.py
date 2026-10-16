"""Bảo đảm pattern-scan KHÔNG có đường tới lệnh thật: không import SDK broker/MT, không gọi hàm đặt lệnh."""
import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "pattern_scan"
BANNED_IMPORTS = {"MetaTrader5", "mt5", "ccxt", "oandapyV20", "ib_insync", "alpaca_trade_api", "mt_bridge"}
BANNED_CALLS = {"order_send", "place_order", "create_order", "submit_order", "order_check"}


def test_no_broker_paths():
    for f in SRC.rglob("*.py"):
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                assert not {a.name.split(".")[0] for a in n.names} & BANNED_IMPORTS, f
            if isinstance(n, ast.ImportFrom) and n.module:
                assert n.module.split(".")[0] not in BANNED_IMPORTS, f
            if isinstance(n, ast.Attribute):
                assert n.attr not in BANNED_CALLS, f
            if isinstance(n, ast.Name):
                assert n.id not in BANNED_CALLS, f
