"""Giao diện Strategy (plugin). Chiến lược CHỈ trả về MỤC TIÊU danh mục (`Targets`); không ra lệnh, không biết broker,
không thấy dữ liệu sau thời điểm quyết định (engine cắt lịch sử tới bar đã đóng).

Cách thêm chiến lược của bạn (xem README):
  1. Đặt file `my_method.py` vào thư mục PAPER_STRATEGY_DIR (mặc định services/paper-trader/strategies/), hoặc package riêng
     khai báo entry-point nhóm `papertrader.strategies`.
  2. Trong file: kế thừa `Strategy`, gắn `@register("ten_chien_luoc")`, cài `targets(ctx)`.
  3. Thêm tài khoản vào paper.yaml (strategy: ten_chien_luoc, params: {...}); restart service.
"""
from __future__ import annotations

import importlib.metadata as md
import importlib.util
import logging
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from .models import Targets

log = logging.getLogger("paper.strategy")

ENTRY_POINT_GROUP = "papertrader.strategies"


@dataclass(frozen=True)
class StrategyContext:
    """Dữ liệu CHỈ-ĐỌC cho chiến lược tại thời điểm quyết định."""
    now: datetime                                   # = đóng cửa bar tín hiệu (UTC)
    tf: str
    universe: tuple[str, ...]
    history: dict[str, pd.DataFrame]                # symbol -> DataFrame[o,h,l,c,v] index=ts_open (UTC), CHỈ bar đã đóng, tăng dần
    equity: float
    positions: dict[str, float]                     # symbol -> qty hiện tại (chỉ để tham khảo)
    analytics: dict | None = None                   # snapshot phân tích (summary theo symbol) nếu có — KHÔNG point-in-time, tránh dùng khi backtest/replay
    params: dict = field(default_factory=dict)


class Strategy(ABC):
    name: str = ""
    meaningful: bool = True                         # False = chỉ để kiểm thử đường ống, không có ý nghĩa thống kê

    def __init__(self, params: dict | None = None):
        self.params = dict(params or {})

    @property
    def required_history(self) -> int:              # số bar tối thiểu mỗi symbol; thiếu -> Targets(status='warming_up')
        return 1

    @abstractmethod
    def targets(self, ctx: StrategyContext) -> Targets: ...

    def describe(self) -> dict:
        return {"name": self.name, "doc": (self.__doc__ or "").strip().split("\n")[0], "params": self.params,
                "required_history": self.required_history, "meaningful": self.meaningful}


_REGISTRY: dict[str, type[Strategy]] = {}


def register(name: str):
    def deco(cls: type[Strategy]):
        cls.name = name
        _REGISTRY[name] = cls
        return cls
    return deco


def _load_file(path: Path) -> None:
    mod_name = f"paper_user_strategy_{path.stem}"
    spec = importlib.util.spec_from_file_location(mod_name, path)
    if spec is None or spec.loader is None:
        return
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)


def load_plugins(strategy_dir: str | None = None) -> dict[str, type[Strategy]]:
    """Built-in + entry-points + *.py trong thư mục. Lỗi của 1 plugin không làm hỏng các plugin khác."""
    from . import strategies  # noqa: F401  (import tự đăng ký built-in)
    for ep in md.entry_points(group=ENTRY_POINT_GROUP):
        try:
            cls = ep.load()
            _REGISTRY.setdefault(ep.name, cls)
            cls.name = cls.name or ep.name
        except Exception:  # noqa: BLE001
            log.exception("không nạp được entry-point strategy %s", ep.name)
    if strategy_dir and Path(strategy_dir).is_dir():
        for p in sorted(Path(strategy_dir).glob("*.py")):
            if p.name.startswith("_"):
                continue
            try:
                _load_file(p)
            except Exception:  # noqa: BLE001
                log.exception("không nạp được strategy file %s", p)
    return dict(_REGISTRY)


def build(name: str, params: dict | None = None) -> Strategy:
    if name not in _REGISTRY:
        raise KeyError(f"strategy '{name}' chưa đăng ký (có: {sorted(_REGISTRY)})")
    return _REGISTRY[name](params)


def registry() -> dict[str, type[Strategy]]:
    return dict(_REGISTRY)


__all__ = ["Strategy", "StrategyContext", "Targets", "register", "load_plugins", "build", "registry", "Any"]
