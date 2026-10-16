"""Nạp spec/*.yaml: common.yaml (tham số chung) + kb*.yaml (mỗi kịch bản). Thêm kịch bản mới = thêm YAML + lớp mẫu hình."""
from __future__ import annotations

import os
from copy import deepcopy
from pathlib import Path

import yaml

DEFAULT_DIR = Path(__file__).resolve().parents[2] / "spec"


def spec_dir() -> Path:
    env = os.getenv("PATTERN_SPEC_DIR")
    if env and Path(env).is_dir():
        return Path(env)
    for p in (DEFAULT_DIR, Path("/app/services/pattern-engine/spec")):
        if p.is_dir():
            return p
    return DEFAULT_DIR


def load_specs(directory: str | Path | None = None, overrides: dict | None = None) -> dict[str, dict]:
    """Trả {id: spec} với spec['params'] = common ⊕ riêng ⊕ overrides (overrides = {id|'common': {tham số}})."""
    d = Path(directory) if directory else spec_dir()
    common = yaml.safe_load((d / "common.yaml").read_text(encoding="utf-8"))["params"]
    out: dict[str, dict] = {}
    for f in sorted(d.glob("kb*.yaml")):
        sp = yaml.safe_load(f.read_text(encoding="utf-8"))
        params = {**deepcopy(common), **(sp.get("params") or {}), **((overrides or {}).get("common") or {}),
                  **((overrides or {}).get(sp["id"]) or {})}
        params["_id"] = sp["id"]
        sp["params"] = params
        out[sp["id"]] = sp
    return out
