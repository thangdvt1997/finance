"""Detector: máy trạng thái theo từng nến ĐÃ ĐÓNG cho 1 (symbol, tf).

Vòng đời mỗi setup: forming -> armed -> triggered | invalid (triggered/invalid là trạng thái cuối).
KHÔNG look-ahead: feed(bar_i) chỉ dùng nến <= i. KHÔNG repaint: sự kiện đã phát không bị sửa; đổi ý chỉ bằng sự kiện `invalid` mới.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .common import Ctx, Setup
from .patterns import PATTERNS
from .series import TF_SECONDS, Bar, Series
from .zigzag import ZigZag


@dataclass
class Signal:
    pattern: str
    symbol: str
    tf: str
    state: str                 # forming | armed | triggered | invalid
    score: float
    levels: dict
    steps: list[dict]
    bar_ts: datetime           # ts_open của nến đã đóng làm đổi trạng thái
    ts: datetime               # thời điểm nến đóng (= bar_ts + tf) — lúc tín hiệu được biết
    setup_id: str
    side: str = "sell"
    reason: str | None = None
    bar_index: int = 0
    points: list[dict] = field(default_factory=list)   # toạ độ pivot [{label,t,p}] để vẽ (không ảnh hưởng logic)

    def to_payload(self) -> dict:
        def clean(v):
            return round(float(v), 5) if isinstance(v, (int, float)) else v
        return {
            "pattern": self.pattern, "tf": self.tf, "symbol": self.symbol, "state": self.state, "side": self.side,
            "score": self.score, "levels": {k: clean(v) for k, v in self.levels.items() if v is not None},
            "steps": [{"id": s["id"], "label": s["label"], "ok": s["ok"], "detail": s["detail"]} for s in self.steps],
            "ts": self.ts.isoformat(), "bar_ts": self.bar_ts.isoformat(), "setup_id": self.setup_id,
            "reason": self.reason, "points": [dict(p) for p in self.points], "info_only": True,
            "disclaimer": "Tín hiệu kỹ thuật chỉ để tham khảo/paper, không phải khuyến nghị đầu tư và không tự đặt lệnh.",
        }


class Detector:
    def __init__(self, symbol: str, tf: str, specs: dict[str, dict], enabled: list[str] | None = None):
        self.symbol, self.tf = symbol, tf
        self.dt = timedelta(seconds=TF_SECONDS.get(tf, 900))
        any_spec = next(iter(specs.values()))["params"]
        self.p = any_spec
        self.s = Series(any_spec["atr_period"], any_spec.get("lead_long_body_atr", any_spec["long_body_atr"]))
        ks = any_spec["zigzag_atr"]
        self.zzs = [ZigZag(k) for k in sorted(ks if isinstance(ks, list) else [ks])]
        self.zz = self.zzs[0]
        self.patterns = {k: PATTERNS[k](v) for k, v in specs.items() if k in PATTERNS and (enabled is None or k in enabled)}
        self.warmup = int(any_spec.get("warmup_bars", 60))
        self._pvs: list[list] = [[] for _ in self.zzs]
        self._cache: dict = {}
        self.active: dict[str, Setup] = {}
        self.terminal: set[str] = set()
        self._emitted: set[tuple[str, str]] = set()
        self.fam_rank: dict[str, int] = {}     # trạng thái cao nhất đã phát theo họ setup (cùng mẫu hình + cùng đáy neo)
        self.fam_done: set[str] = set()        # họ đã kết thúc (triggered/invalid) -> không phát thêm

    # ------------------------------------------------------------------
    def _sig(self, su_pattern: str, key: str, state: str, score: float, levels: dict, steps: list[dict], i: int,
             reason: str | None = None, points: list[dict] | None = None) -> Signal:
        ts = self.s.ts[i]
        return Signal(su_pattern, self.symbol, self.tf, state, score, levels, steps, ts, ts + self.dt, key, reason=reason, bar_index=i,
                      points=list(points or []))

    RANK = {"forming": 1, "armed": 2}

    def _family_alive(self, fam: str) -> bool:
        return any(su.family == fam for su in self.active.values())

    def feed(self, bar: Bar) -> list[Signal]:
        s = self.s
        if (s.ts and bar.ts <= s.ts[-1]) or not bar.valid():
            return []
        i = s.append(bar)
        out: list[Signal] = []
        ctx = Ctx(s, self._pvs[0], i, self._cache)
        # 1) kiểm tra kích hoạt / huỷ cho các setup còn sống (cấu trúc đã chốt ở nến i-1)
        trig: dict[str, list[tuple[Setup, dict]]] = {}
        dead: list[tuple[Setup, str]] = []
        for key, su in list(self.active.items()):
            res = self.patterns[su.pattern].check(ctx, su, i)
            if res is None:
                continue
            kind, info = res
            del self.active[key]
            self.terminal.add(key)
            if kind == "triggered":
                trig.setdefault(su.pattern, []).append((su, info))
            else:
                dead.append((su, info["reason"]))
        for pid, lst in trig.items():          # nhiều neo/thang cùng kích hoạt trên 1 nến -> chỉ phát bản điểm cao nhất
            lst.sort(key=lambda t: -t[1]["score"])
            for n, (su, info) in enumerate(lst):
                fam = su.family
                if n == 0 and fam not in self.fam_done:
                    out.append(self._sig(pid, su.key, "triggered", info["score"], info["levels"], info["steps"], i, points=su.points))
                    self._emitted.add((su.key, "triggered"))
                self.fam_done.add(fam)
                for k2 in [k for k, v in self.active.items() if v.family == fam]:
                    del self.active[k2]
                    self.terminal.add(k2)
        for su, reason in dead:
            fam = su.family
            if fam in self.fam_done or self._family_alive(fam):
                continue
            if self.fam_rank.get(fam, 0) >= 2:      # chỉ setup đã `armed` mới phát invalid; forming chết thì lặng lẽ bỏ (có thể hình thành lại với đỉnh khác)
                out.append(self._sig(su.pattern, su.key, "invalid", su.score, su.levels, su.steps, i, reason, su.points))
                self.fam_done.add(fam)
        # 2) cập nhật swing
        for z in self.zzs:
            z.update(i, bar.o, bar.h, bar.l, bar.c, s.atr[i])
        self._pvs = [z.view() for z in self.zzs]
        # 3) quét cấu trúc tại nến i (dùng cho nến i+1)
        if i + 1 >= self.warmup:
            seen: set[str] = set()
            for pid, pat in self.patterns.items():
                best: dict[str, Setup] = {}
                for pv in self._pvs:                       # đa thang swing: cùng khoá -> giữ bản điểm cao nhất
                    for su in pat.scan(Ctx(s, pv, i, self._cache, self._pvs[0])):
                        if su.key not in best or su.score > best[su.key].score:
                            best[su.key] = su
                setups = sorted(best.values(), key=lambda x: -x.score)[: int(self.p.get("max_setups_per_pattern", 4))]
                for su in setups:
                    if su.key in self.terminal or su.family in self.fam_done:
                        continue
                    seen.add(su.key)
                    self.active[su.key] = su
                    r = self.RANK[su.state]
                    if r > self.fam_rank.get(su.family, 0) and (su.state == "armed" or self.p.get("emit_forming", True)):
                        self.fam_rank[su.family] = r
                        self._emitted.add((su.key, su.state))
                        out.append(self._sig(pid, su.key, su.state, su.score, su.levels, su.steps, i, points=su.points))
            for key in [k for k in self.active if k not in seen]:
                su = self.active.pop(key)
                if su.state == "armed":
                    self.terminal.add(key)
                    if not self._family_alive(su.family) and su.family not in self.fam_done:
                        self.fam_done.add(su.family)
                        out.append(self._sig(su.pattern, key, "invalid", su.score, su.levels, su.steps, i, "cấu trúc không còn thoả", su.points))
        return out

    def feed_many(self, bars: list[Bar]) -> list[Signal]:
        res: list[Signal] = []
        for b in bars:
            res.extend(self.feed(b))
        return res
