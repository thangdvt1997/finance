"""Luat canh bao (thuan, de test): tra ve danh sach payload `alert` theo CONTRACTS (alerts.out)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from .accounts import AlertRules
from .models import Account, Position


def alert(level: str, title: str, body: str, tags: list[str], dedupe_key: str) -> dict:
    return {"level": level, "title": title, "body": body, "tags": tags, "dedupe_key": dedupe_key}


@dataclass
class _State:
    peak_equity: float = 0.0
    dd_active: bool = False
    margin_state: str = "ok"  # ok|warn|crit
    hb_lost: bool = False
    known_positions: Optional[set[str]] = None  # None = chua co baseline
    seen_unexpected: set[str] = field(default_factory=set)


class AlertEngine:
    """Phat alert theo chuyen trang thai (khong spam moi snapshot); dedupe_key on dinh de alert-service dedupe tiep."""

    def __init__(self):
        self._st: dict[str, _State] = {}

    def _s(self, acc: str) -> _State:
        return self._st.setdefault(acc, _State())

    def on_alive(self, account_id: str, platform: str = "") -> list[dict]:
        """Goi moi khi nhan bat ky du lieu nao tu tai khoan (ke ca heartbeat)."""
        s = self._s(account_id)
        if s.hb_lost:
            s.hb_lost = False
            return [alert("info", f"[{account_id}] EA/terminal ket noi lai", "Da nhan lai du lieu.", [f"account:{account_id}", platform, "heartbeat"], f"hb:{account_id}:recovered")]
        return []

    def on_snapshot(self, account: Account, positions: Optional[list[Position]], rules: AlertRules) -> list[dict]:
        out: list[dict] = []
        s = self._s(account.account_id)
        tag = [f"account:{account.account_id}", account.platform]
        aid = account.account_id


        # drawdown so voi dinh equity (high-water mark trong phien chay)
        s.peak_equity = max(s.peak_equity, account.equity)
        if s.peak_equity > 0:
            dd = (s.peak_equity - account.equity) / s.peak_equity * 100.0
            if dd >= rules.drawdown_pct and not s.dd_active:
                s.dd_active = True
                out.append(alert("crit", f"[{aid}] Drawdown {dd:.1f}%", f"equity={account.equity:.2f} dinh={s.peak_equity:.2f} nguong={rules.drawdown_pct}%", tag + ["drawdown"], f"dd:{aid}"))
            elif dd < rules.drawdown_pct * 0.8 and s.dd_active:
                s.dd_active = False
                out.append(alert("info", f"[{aid}] Drawdown hoi phuc ({dd:.1f}%)", "", tag + ["drawdown"], f"dd:{aid}:recovered"))

        # margin level
        ml = account.margin_level
        new_state = "ok"
        if ml is not None:
            if ml < rules.margin_level_crit:
                new_state = "crit"
            elif ml < rules.margin_level_warn:
                new_state = "warn"
        if new_state != s.margin_state:
            if new_state == "crit":
                out.append(alert("crit", f"[{aid}] Margin level {ml:.0f}% (nguy hiem)", f"nguong crit={rules.margin_level_crit}%", tag + ["margin"], f"margin:{aid}:crit"))
            elif new_state == "warn":
                out.append(alert("warn", f"[{aid}] Margin level thap {ml:.0f}%", f"nguong warn={rules.margin_level_warn}%", tag + ["margin"], f"margin:{aid}:warn"))
            else:
                out.append(alert("info", f"[{aid}] Margin level binh thuong lai", "", tag + ["margin"], f"margin:{aid}:ok"))
            s.margin_state = new_state

        if positions is not None:
            out += self._positions(account, positions, rules, s, tag)
        return out

    def _positions(self, account, positions, rules, s, tag) -> list[dict]:
        out = []
        ids = {p.position_id for p in positions}
        if s.known_positions is None:
            s.known_positions = set(ids)  # baseline: vi the co san luc bat dau khong bao
            return out
        for p in positions:
            if p.position_id in s.known_positions:
                continue
            s.known_positions.add(p.position_id)
            expected = p.magic in rules.expected_magics or p.position_id in rules.expected_tickets
            if rules.new_position and not expected and p.position_id not in s.seen_unexpected:
                s.seen_unexpected.add(p.position_id)
                out.append(
                    alert(
                        "warn",
                        f"[{account.account_id}] Vi the moi ngoai du kien {p.symbol} {p.side} {p.volume}",
                        f"ticket={p.position_id} magic={p.magic} gia mo={p.price_open} comment={p.comment!r}",
                        tag + ["new_position", p.symbol],
                        f"newpos:{account.account_id}:{p.position_id}",
                    )
                )
        return out

    def check_heartbeat(self, account_id: str, last_seen: Optional[datetime], now: datetime, rules: AlertRules, platform: str = "") -> list[dict]:
        s = self._s(account_id)
        if last_seen is None:
            return []  # chua tung ket noi: chua canh bao (tranh spam luc khoi dong)
        age = (now - last_seen).total_seconds()
        if age > rules.heartbeat_timeout_s and not s.hb_lost:
            s.hb_lost = True
            return [alert("crit", f"[{account_id}] Mat heartbeat {age:.0f}s", f"nguong={rules.heartbeat_timeout_s}s; kiem tra terminal/EA/VPS", [f"account:{account_id}", platform, "heartbeat"], f"hb:{account_id}")]
        return []
