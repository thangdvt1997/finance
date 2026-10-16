"""Lưu/khôi phục trạng thái state machine (phiên dạy bền: sống qua restart, tiếp tục ở phiên sau)."""
from __future__ import annotations

from .llm import GuardedLLM
from .machine import Classroom
from .profile import Profile


def dump(c: Classroom) -> dict:
    return {"profile": c.profile.to_dict(), "versions": c.history.versions, "phase": c.phase, "idx": c.idx, "clarified": sorted(c._clarified),
            "reconcile": c._reconcile, "more": c._more, "flags": c.flags[-50:]}


def load(d: dict | None, room: str, llm: GuardedLLM | None) -> Classroom:
    if not d:
        return Classroom(room, llm)
    c = Classroom(room, llm, Profile.from_dict(d["profile"]))
    c.profile.room = room
    c.history.versions = list(d.get("versions") or [])
    c.phase, c.idx = d.get("phase", "intake"), int(d.get("idx", 0))
    c._clarified, c._reconcile, c._more = set(d.get("clarified") or []), d.get("reconcile"), int(d.get("more", 0))
    c.flags = list(d.get("flags") or [])
    return c
