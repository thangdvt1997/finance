"""Danh mục cổ phiếu VN: phân ngành + thành phần VN30/VN100/HNX30 + ETF, nạp từ seed/vn_universe.json.

Seed tạo bởi `tools/refresh_vn_universe.py` (vnstock 4 `Listing`, nguồn KBS, không cần key) rồi commit vào repo; thành phần rổ chỉ số đổi theo
kỳ cơ cấu (VN30 mỗi 6 tháng) -> chạy lại script mỗi quý. Phân ngành là của KBS (25 ngành, mịn hơn ICB cấp 1), KHÔNG phải ICB chính thức.
"""
from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from typing import Any


@lru_cache(maxsize=1)
def load_seed() -> dict[str, Any]:
    text = resources.files("vn_market").joinpath("seed/vn_universe.json").read_text(encoding="utf-8")
    return json.loads(text)


def industry_of(code: str) -> tuple[int | None, str | None]:
    v = load_seed()["industries"].get(code.upper())
    return (int(v[0]), v[1]) if v else (None, None)


def group_members(group: str) -> set[str]:
    return set(load_seed()["groups"].get(group, []))


def etf_codes() -> set[str]:
    return set(load_seed().get("etf", []))


def focus_codes() -> set[str]:
    """Rổ theo dõi sâu (lịch sử dài, ratios): VN100 + HNX30 + ETF."""
    return group_members("VN100") | group_members("HNX30") | etf_codes()


def seed_meta() -> dict:
    return load_seed().get("_meta", {})


def enrich_symbol(row: dict) -> dict:
    """Thêm ngành + cờ rổ cho 1 bản ghi `stocks` của VNDirect đã chuẩn hoá {code, floor, kind, ...}."""
    code = row["code"].upper()
    ic, iname = industry_of(code)
    row = {**row, "code": code, "industry_code": ic, "industry_name": iname,
           "in_vn30": code in group_members("VN30"), "in_vn100": code in group_members("VN100"), "in_hnx30": code in group_members("HNX30")}
    row["focus"] = code in focus_codes()
    if row.get("kind") == "ETF":
        row["industry_name"] = row["industry_name"] or "Quỹ ETF"
    return row
