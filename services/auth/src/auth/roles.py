"""Vai trò + quyền (perm) của người dùng quản trị. MẶC ĐỊNH TỪ CHỐI: perm không liệt kê = không có. docs/FLEET_MGMT.md mục 1."""
from __future__ import annotations

STAFF_ROLES = ("support", "analyst", "auditor", "expert")           # vai trò phụ (đăng nhập bằng platform "master")
ADMIN_ROLES = ("master",) + STAFF_ROLES                    # mọi vai trò dùng /auth/admin/*
SENSITIVE_PERMS_MASTER_ONLY = True

ROLE_PERMS: dict[str, frozenset[str]] = {
    "master": frozenset({"*"}),
    "support": frozenset({"fleet.read", "incident.read", "incident.note", "note.write"}),
    "analyst": frozenset({"fleet.read", "compliance.read", "report.read"}),
    "auditor": frozenset({"audit.read"}),
    "expert": frozenset({"class.use"}),           # AI Training Class: dạy + chạy test paper (không có dữ liệu tài khoản, không cấu hình hệ thống)
    "client": frozenset(),
}

ROLE_LABEL = {
    "master": "Quản trị viên (đầy đủ)",
    "support": "Hỗ trợ — chỉ đọc + ghi chú",
    "analyst": "Phân tích — chỉ đọc phân tích/tuân thủ/báo cáo",
    "auditor": "Kiểm toán — chỉ đọc nhật ký kiểm toán",
    "expert": "Chuyên gia — dạy AI trong Lớp học + chạy test paper",
    "client": "Khách hàng",
}


def perms_of(role: str) -> list[str]:
    p = ROLE_PERMS.get(role, frozenset())
    return ["*"] if "*" in p else sorted(p)


def has_perm(role: str, perm: str) -> bool:
    p = ROLE_PERMS.get(role, frozenset())
    return "*" in p or perm in p


def is_admin_role(role: str) -> bool:
    return role in ADMIN_ROLES


def matrix() -> list[dict]:
    allp = sorted({x for v in ROLE_PERMS.values() for x in v if x != "*"})
    return [{"role": r, "label": ROLE_LABEL[r], "perms": perms_of(r), "all_perms": allp} for r in ("master", "support", "analyst", "auditor", "expert", "client")]
