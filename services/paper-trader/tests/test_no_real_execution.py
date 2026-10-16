"""Quét tĩnh: paper-trader KHÔNG có đường nào tới thực thi thật (broker/MT/mt-bridge, ghi ra ngoài)."""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "paper_trader"
FILES = sorted(SRC.rglob("*.py"))

BANNED_IMPORT_PREFIXES = ("metatrader5", "mt5linux", "mt_bridge", "mt-bridge", "ccxt", "alpaca", "ib_insync", "ibapi", "oandapyv20", "v20", "dwx",
                          "binance", "smtplib", "ftplib", "paramiko", "subprocess", "socket", "requests", "urllib3", "aiohttp", "websockets")
BANNED_CALLS = {"order_send", "place_order", "send_order", "submit_order", "create_order", "market_order", "execute_order", "system", "popen"}
WRITE_METHODS = {"post", "put", "patch", "delete", "request", "send"}


def _tree(p: Path) -> ast.AST:
    return ast.parse(p.read_text(encoding="utf-8"))


def test_sources_exist():
    assert len(FILES) >= 10


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_no_broker_or_network_write_imports(path):
    for n in ast.walk(_tree(path)):
        mods = []
        if isinstance(n, ast.Import):
            mods = [a.name for a in n.names]
        elif isinstance(n, ast.ImportFrom) and n.module:
            mods = [n.module]
        for m in mods:
            assert not m.lower().startswith(BANNED_IMPORT_PREFIXES), f"{path.name}: import bị cấm {m}"


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_no_order_send_calls_or_write_http(path):
    for n in ast.walk(_tree(path)):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
            assert n.func.attr not in BANNED_CALLS, f"{path.name}:{n.lineno} gọi {n.func.attr}"
            if n.func.attr in WRITE_METHODS:
                # chỉ cho phép decorator route FastAPI (@app.post) ở app.py; không client HTTP ghi ở bất kỳ file nào
                assert path.name == "app.py" and isinstance(n.func.value, ast.Name) and n.func.value.id == "app", f"{path.name}:{n.lineno} .{n.func.attr}()"
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name):
            assert n.func.id not in BANNED_CALLS, f"{path.name}:{n.lineno} gọi {n.func.id}"


def test_http_client_only_reads_configured_risk_windows():
    uses = [p.name for p in FILES if "httpx" in p.read_text(encoding="utf-8")]
    assert uses == ["runner.py"]
    src = (SRC / "runner.py").read_text(encoding="utf-8")
    assert re.findall(r"\bc\.(\w+)\(url", src) == ["get"]                  # chỉ GET tới risk_windows_url


def test_no_mt_bridge_or_broker_endpoints_in_code_or_config():
    texts = {p.name: p.read_text(encoding="utf-8") for p in list(ROOT.rglob("*.yaml")) + list(ROOT.rglob("Dockerfile")) + list(ROOT.glob("pyproject.toml"))}
    for name, t in texts.items():
        low = t.lower()
        assert "mt-bridge" not in low and "mt_bridge" not in low and "metatrader" not in low and "bridge_admin_token" not in low, name
    for p in FILES:
        code = "\n".join(l.split("#")[0] for l in p.read_text(encoding="utf-8").splitlines())
        assert not re.search(r"https?://(?!localhost)", re.sub(r'""".*?"""', "", code, flags=re.S)), f"{p.name}: URL ngoài trong code"


def test_compose_block_has_no_bridge_dependency_or_secrets():
    compose = ROOT.parents[1] / "infra" / "docker-compose.tools.yml"
    if not compose.exists():
        pytest.skip("không có compose trong môi trường test")
    text = compose.read_text(encoding="utf-8")
    m = re.search(r"^  paper-trader:\n(.*?)(?=^  [a-z][\w-]*:\n|^networks:)", text, flags=re.S | re.M)
    assert m, "thiếu khối paper-trader"
    block = m.group(1).lower()
    for bad in ("mt-bridge", "bridge_admin_token", "mt5", "metatrader", "broker_"):
        assert bad not in block, bad
    assert "ports:" not in block                                          # không publish cổng ra host
    assert "ts_paper" in block and "ts_ro" in block


def test_only_paper_tables_are_written():
    """Mọi INSERT/UPDATE/DELETE trong repo.py chỉ chạm bảng paper_*."""
    src = (SRC / "repo.py").read_text(encoding="utf-8")
    tables = re.findall(r"(?:INSERT INTO|UPDATE|DELETE FROM)\s+([a-z_]+)", src)
    assert tables and all(t.startswith("paper_") for t in tables), set(tables)
