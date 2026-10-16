"""Route quản trị đội tài khoản (nginx /auth/admin/*) + nội bộ /internal/fleet/* + khách /auth/client/notify. docs/FLEET_MGMT.md.
Quyền do FleetService kiểm (perm theo vai trò + phạm vi nhóm); module này chỉ định tuyến + kiểm tra đầu vào."""

import hmac
import re
from typing import Annotated, Any, Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from . import roles as R
from .fleet_service import FleetService
from .service import AuthService, Principal

UUID_RE = r"^[0-9a-fA-F-]{36}$"
ACC_RE = r"^[\w.:\-]{1,64}$"


class _S(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class GroupIn(_S):
    name: str = Field(min_length=1, max_length=60)
    description: str = Field(default="", max_length=200)
    color: str = Field(default="", max_length=16)


class GroupPatch(_S):
    name: str | None = Field(default=None, min_length=1, max_length=60)
    description: str | None = Field(default=None, max_length=200)
    color: str | None = Field(default=None, max_length=16)


class MembersIn(_S):
    account_ids: list[str] = Field(min_length=1, max_length=2000)


class PolicyIn(_S):
    ea_offline_grace_min: int = Field(default=5, ge=1, le=1440)
    min_severity: Literal["info", "warning", "critical"] = "info"
    client_notify: bool = False
    auto_assign_user_id: str | None = Field(default=None, pattern=UUID_RE)


class GroupsSetIn(_S):
    group_ids: list[str] = Field(max_length=50)


class TagsIn(_S):
    tags: list[str] = Field(max_length=12)


class ViewIn(_S):
    name: str = Field(min_length=1, max_length=60)
    filters: dict[str, Any] = Field(default_factory=dict)
    shared: bool = False


class NoteIn(_S):
    text: str = Field(min_length=1, max_length=1000)


class BulkPrepIn(_S):
    action: str = Field(max_length=30)
    account_ids: list[str] = Field(min_length=1, max_length=500)
    params: dict[str, Any] = Field(default_factory=dict)


class BulkExecIn(_S):
    confirm_token: str = Field(min_length=10, max_length=80)
    phrase: str = Field(max_length=40)


class ImportPrevIn(_S):
    csv: str = Field(min_length=1, max_length=200_000)


class ImportCommitIn(_S):
    preview_token: str = Field(min_length=10, max_length=80)


class TemplateIn(_S):
    name: str = Field(min_length=1, max_length=80)
    kind: str = Field(max_length=30)
    params: dict[str, Any] = Field(default_factory=dict)
    description: str = Field(default="", max_length=300)


class TemplatePut(_S):
    name: str = Field(min_length=1, max_length=80)
    params: dict[str, Any] = Field(default_factory=dict)
    description: str = Field(default="", max_length=300)


class ScopeIn(_S):
    type: Literal["group", "tag", "account", "all"]
    ref: str = Field(default="", max_length=64)


class AssignIn(_S):
    template_id: str = Field(pattern=UUID_RE)
    scope: ScopeIn
    enabled: bool = True
    notify_client: bool = False


class AssignPatch(_S):
    enabled: bool | None = None
    notify_client: bool | None = None
    scope: ScopeIn | None = None


class AssignIncIn(_S):
    user_id: str | None = Field(default=None, pattern=UUID_RE)


class SnoozeIn(_S):
    minutes: int = Field(ge=5, le=10080)


class TextIn(_S):
    text: str = Field(default="", max_length=1000)


class IncBulkIn(_S):
    ids: list[str] = Field(min_length=1, max_length=100)
    action: Literal["ack", "resolve", "snooze"]
    minutes: int = Field(default=60, ge=5, le=10080)


class StaffIn(_S):
    name: str = Field(min_length=1, max_length=32)
    role: Literal["support", "analyst", "auditor", "expert"]
    display_name: str = Field(default="", max_length=80)
    scope_all: bool = False
    group_ids: list[str] = Field(default_factory=list, max_length=100)


class StaffPatch(_S):
    role: Literal["support", "analyst", "auditor", "expert"] | None = None
    display_name: str | None = Field(default=None, max_length=80)
    scope_all: bool | None = None
    group_ids: list[str] | None = Field(default=None, max_length=100)


class ViewAsIn(_S):
    account_id: str = Field(pattern=ACC_RE)
    reason: str = Field(min_length=1, max_length=300)


class ViewAsEndIn(_S):
    grant_id: str = Field(pattern=UUID_RE)


class NotifyIn(_S):
    enabled: bool


def get_fleet(app: FastAPI) -> FleetService:
    f = getattr(app.state, "fleet", None)
    if f is None:
        f = app.state.fleet = FleetService(app.state.svc)
    return f


def register_fleet(app: FastAPI, *, active, csrf, client_ip, cfg) -> None:
    Active = Annotated[Principal, Depends(active)]
    Csrf = Depends(csrf)
    adm = "/auth/admin"

    def F() -> FleetService:
        return get_fleet(app)

    def uid(v: str) -> str:
        if not re.fullmatch(UUID_RE, v):
            raise HTTPException(404)
        return v

    def acc(v: str) -> str:
        if not re.fullmatch(ACC_RE, v):
            raise HTTPException(404)
        return v

    # ---- fleet + nhóm + tag + views + ghi chú
    @app.get(adm + "/fleet", tags=["fleet"], summary="Danh sách đội tài khoản (lọc/sắp xếp/đếm)")
    async def fleet(p: Active, q: Annotated[str | None, Query(max_length=80)] = None, group: Annotated[str | None, Query(pattern=UUID_RE)] = None,
                    tag: Annotated[str | None, Query(max_length=24)] = None, status: Annotated[str | None, Query(pattern=r"^(active|pending|suspended)$")] = None,
                    ea: Annotated[str | None, Query(pattern=r"^(online|degraded|offline|unknown)$")] = None,
                    compliance: Annotated[str | None, Query(pattern=r"^(green|yellow|red)$")] = None, incident: Annotated[int | None, Query(ge=0, le=1)] = None,
                    sort: Annotated[str | None, Query(pattern=r"^(account_id|label|last_seen|usage|status)$")] = None,
                    dir: Annotated[str | None, Query(pattern=r"^(asc|desc)$")] = None, limit: Annotated[int, Query(ge=1, le=500)] = 200, offset: Annotated[int, Query(ge=0)] = 0):
        return await F().fleet(p, {"q": q, "group": group, "tag": tag, "status": status, "ea": ea, "compliance": compliance, "incident": incident,
                                   "sort": sort, "dir": dir, "limit": limit, "offset": offset})

    @app.get(adm + "/groups", tags=["fleet"])
    async def groups(p: Active):
        return {"items": await F().groups(p)}

    @app.post(adm + "/groups", dependencies=[Csrf], status_code=201, tags=["fleet"])
    async def group_create(body: GroupIn, request: Request, p: Active):
        return await F().create_group(p, body.name, body.description, body.color, client_ip(request))

    @app.patch(adm + "/groups/{gid}", dependencies=[Csrf], tags=["fleet"])
    async def group_patch(gid: str, body: GroupPatch, request: Request, p: Active):
        return await F().update_group(p, uid(gid), body.model_dump(), client_ip(request))

    @app.delete(adm + "/groups/{gid}", dependencies=[Csrf], tags=["fleet"])
    async def group_delete(gid: str, request: Request, p: Active):
        await F().delete_group(p, uid(gid), client_ip(request))
        return {"ok": True}

    @app.post(adm + "/groups/{gid}/members", dependencies=[Csrf], tags=["fleet"])
    async def group_add(gid: str, body: MembersIn, request: Request, p: Active):
        return await F().group_members(p, uid(gid), body.account_ids, None, client_ip(request))

    @app.delete(adm + "/groups/{gid}/members/{account_id}", dependencies=[Csrf], tags=["fleet"])
    async def group_rm(gid: str, account_id: str, request: Request, p: Active):
        return await F().group_members(p, uid(gid), None, acc(account_id), client_ip(request))

    @app.get(adm + "/groups/{gid}/policy", tags=["fleet"])
    async def policy_get(gid: str, p: Active):
        return await F().get_policy(p, uid(gid))

    @app.put(adm + "/groups/{gid}/policy", dependencies=[Csrf], tags=["fleet"])
    async def policy_put(gid: str, body: PolicyIn, request: Request, p: Active):
        return await F().set_group_policy(p, uid(gid), body.model_dump(exclude_none=True), client_ip(request))

    @app.put(adm + "/accounts/{account_id}/groups", dependencies=[Csrf], tags=["fleet"])
    async def acc_groups(account_id: str, body: GroupsSetIn, request: Request, p: Active):
        if any(not re.fullmatch(UUID_RE, g) for g in body.group_ids):
            raise HTTPException(422, "group_id không hợp lệ")
        await F().set_account_groups(p, acc(account_id), body.group_ids, client_ip(request))
        return {"ok": True}

    @app.put(adm + "/accounts/{account_id}/tags", dependencies=[Csrf], tags=["fleet"])
    async def acc_tags(account_id: str, body: TagsIn, request: Request, p: Active):
        return {"tags": await F().set_account_tags(p, acc(account_id), body.tags, client_ip(request))}

    @app.get(adm + "/tags", tags=["fleet"])
    async def tags(p: Active):
        return {"items": await F().tags(p)}

    @app.get(adm + "/views", tags=["fleet"])
    async def views(p: Active):
        return {"items": await F().views(p)}

    @app.post(adm + "/views", dependencies=[Csrf], status_code=201, tags=["fleet"])
    async def view_create(body: ViewIn, p: Active):
        return await F().create_view(p, body.name, body.filters, body.shared)

    @app.delete(adm + "/views/{vid}", dependencies=[Csrf], tags=["fleet"])
    async def view_delete(vid: str, p: Active):
        await F().delete_view(p, uid(vid))
        return {"ok": True}

    @app.get(adm + "/accounts/{account_id}/notes", tags=["fleet"])
    async def notes(account_id: str, p: Active):
        return {"items": await F().notes(p, acc(account_id))}

    @app.post(adm + "/accounts/{account_id}/notes", dependencies=[Csrf], status_code=201, tags=["fleet"])
    async def note_add(account_id: str, body: NoteIn, request: Request, p: Active):
        return await F().add_note(p, acc(account_id), body.text, client_ip(request))

    # ---- bulk / import
    @app.post(adm + "/bulk/prepare", dependencies=[Csrf], tags=["fleet"], summary="Bước 1/2: xem trước thao tác hàng loạt")
    async def bulk_prepare(body: BulkPrepIn, request: Request, p: Active):
        return await F().bulk_prepare(p, body.action, body.account_ids, body.params, client_ip(request))

    @app.post(adm + "/bulk/execute", dependencies=[Csrf], tags=["fleet"], summary="Bước 2/2: xác nhận bằng cụm 'XAC NHAN <n>'")
    async def bulk_execute(body: BulkExecIn, request: Request, p: Active):
        return await F().bulk_execute(p, body.confirm_token, body.phrase, client_ip(request))

    @app.post(adm + "/import/preview", dependencies=[Csrf], tags=["fleet"])
    async def import_preview(body: ImportPrevIn, request: Request, p: Active):
        return await F().import_preview(p, body.csv, client_ip(request))

    @app.post(adm + "/import/commit", dependencies=[Csrf], tags=["fleet"])
    async def import_commit(body: ImportCommitIn, request: Request, p: Active):
        return await F().import_commit(p, body.preview_token, client_ip(request))

    # ---- luật + tuân thủ
    @app.get(adm + "/rules/presets", tags=["rules"])
    async def presets(p: Active):
        F().need(p, "compliance.read")
        return F().presets()

    @app.get(adm + "/rules/templates", tags=["rules"])
    async def templates(p: Active):
        return {"items": await F().templates(p)}

    @app.post(adm + "/rules/templates", dependencies=[Csrf], status_code=201, tags=["rules"])
    async def template_create(body: TemplateIn, request: Request, p: Active):
        return await F().create_template(p, body.name, body.kind, body.params, body.description, client_ip(request))

    @app.put(adm + "/rules/templates/{tid}", dependencies=[Csrf], tags=["rules"])
    async def template_put(tid: str, body: TemplatePut, request: Request, p: Active):
        return await F().update_template(p, uid(tid), body.name, body.params, body.description, client_ip(request))

    @app.delete(adm + "/rules/templates/{tid}", dependencies=[Csrf], tags=["rules"])
    async def template_delete(tid: str, request: Request, p: Active):
        await F().delete_template(p, uid(tid), client_ip(request))
        return {"ok": True}

    @app.get(adm + "/rules/assignments", tags=["rules"])
    async def assignments(p: Active):
        return {"items": await F().assignments(p)}

    @app.post(adm + "/rules/assignments", dependencies=[Csrf], status_code=201, tags=["rules"])
    async def assign_create(body: AssignIn, request: Request, p: Active):
        return await F().create_assignment(p, body.template_id, body.scope.type, body.scope.ref, body.enabled, body.notify_client, client_ip(request))

    @app.patch(adm + "/rules/assignments/{aid}", dependencies=[Csrf], tags=["rules"])
    async def assign_patch(aid: str, body: AssignPatch, request: Request, p: Active):
        f = {"enabled": body.enabled, "notify_client": body.notify_client}
        if body.scope:
            f.update(scope_type=body.scope.type, scope_ref=body.scope.ref)
        return await F().update_assignment(p, uid(aid), f, client_ip(request))

    @app.delete(adm + "/rules/assignments/{aid}", dependencies=[Csrf], tags=["rules"])
    async def assign_delete(aid: str, request: Request, p: Active):
        await F().delete_assignment(p, uid(aid), client_ip(request))
        return {"ok": True}

    @app.get(adm + "/compliance", tags=["rules"], summary="Bảng tuân thủ luật toàn đội")
    async def compliance(p: Active, group: Annotated[str | None, Query(pattern=UUID_RE)] = None, tag: Annotated[str | None, Query(max_length=24)] = None,
                         status: Annotated[str | None, Query(pattern=r"^(green|yellow|red|na)$")] = None, assignment: Annotated[str | None, Query(pattern=UUID_RE)] = None,
                         limit: Annotated[int, Query(ge=1, le=2000)] = 1000):
        return await F().compliance(p, {"group": group, "tag": tag, "status": status, "assignment": assignment, "limit": limit})

    # ---- sự cố
    @app.get(adm + "/incidents", tags=["incidents"])
    async def incidents(p: Active, status: Annotated[str | None, Query(pattern=r"^(open|ack|snoozed|resolved|active)$")] = None,
                        severity: Annotated[str | None, Query(pattern=r"^(info|warning|critical)$")] = None, assignee: Annotated[str | None, Query(max_length=40)] = None,
                        kind: Annotated[str | None, Query(pattern=r"^(rule|budget|ea|other)$")] = None, group: Annotated[str | None, Query(pattern=UUID_RE)] = None,
                        account: Annotated[str | None, Query(pattern=ACC_RE)] = None, group_by: Annotated[str | None, Query(pattern=r"^cause$")] = None,
                        limit: Annotated[int, Query(ge=1, le=500)] = 300):
        if assignee and assignee not in ("me", "none") and not re.fullmatch(UUID_RE, assignee):
            raise HTTPException(422, "assignee không hợp lệ")
        return await F().incidents(p, {"status": status, "severity": severity, "assignee": assignee, "kind": kind, "group": group, "account": account,
                                       "group_by": group_by, "limit": limit})

    @app.get(adm + "/incidents/assignees", tags=["incidents"])
    async def assignees(p: Active):
        return {"items": await F().assignees(p)}

    @app.post(adm + "/incidents/bulk", dependencies=[Csrf], tags=["incidents"])
    async def inc_bulk(body: IncBulkIn, request: Request, p: Active):
        return await F().incidents_bulk(p, body.ids, body.action, body.minutes, client_ip(request))

    @app.get(adm + "/incidents/{iid}", tags=["incidents"])
    async def inc_get(iid: str, p: Active):
        return await F().incident(p, uid(iid))

    @app.post(adm + "/incidents/{iid}/ack", dependencies=[Csrf], tags=["incidents"])
    async def inc_ack(iid: str, request: Request, p: Active):
        return await F().incident_action(p, uid(iid), "ack", client_ip(request))

    @app.post(adm + "/incidents/{iid}/reopen", dependencies=[Csrf], tags=["incidents"])
    async def inc_reopen(iid: str, request: Request, p: Active):
        return await F().incident_action(p, uid(iid), "reopen", client_ip(request))

    @app.post(adm + "/incidents/{iid}/assign", dependencies=[Csrf], tags=["incidents"])
    async def inc_assign(iid: str, body: AssignIncIn, request: Request, p: Active):
        return await F().incident_action(p, uid(iid), "assign", client_ip(request), user_id=body.user_id)

    @app.post(adm + "/incidents/{iid}/snooze", dependencies=[Csrf], tags=["incidents"])
    async def inc_snooze(iid: str, body: SnoozeIn, request: Request, p: Active):
        return await F().incident_action(p, uid(iid), "snooze", client_ip(request), minutes=body.minutes)

    @app.post(adm + "/incidents/{iid}/resolve", dependencies=[Csrf], tags=["incidents"])
    async def inc_resolve(iid: str, body: TextIn, request: Request, p: Active):
        return await F().incident_action(p, uid(iid), "resolve", client_ip(request), text=body.text)

    @app.post(adm + "/incidents/{iid}/notes", dependencies=[Csrf], tags=["incidents"])
    async def inc_note(iid: str, body: TextIn, request: Request, p: Active):
        return await F().incident_action(p, uid(iid), "note", client_ip(request), text=body.text)

    # ---- vai trò / nhân sự
    @app.get(adm + "/roles", tags=["roles"])
    async def roles(p: Active):
        F().need_master(p)
        return {"items": R.matrix()}

    @app.get(adm + "/staff", tags=["roles"])
    async def staff(p: Active):
        return {"items": await F().staff(p)}

    @app.post(adm + "/staff", dependencies=[Csrf], status_code=201, tags=["roles"])
    async def staff_create(body: StaffIn, request: Request, p: Active):
        return await F().create_staff(p, body.name, body.role, body.display_name, body.scope_all, body.group_ids, client_ip(request))

    @app.patch(adm + "/staff/{user_id}", dependencies=[Csrf], tags=["roles"])
    async def staff_patch(user_id: str, body: StaffPatch, request: Request, p: Active):
        return await F().update_staff(p, uid(user_id), body.role, body.scope_all, body.group_ids, body.display_name, client_ip(request))

    # ---- xem như khách (thay route cũ chỉ-audit): lý do bắt buộc + hết hạn
    @app.post(adm + "/view-as", dependencies=[Csrf], tags=["admin"], summary="Xem như khách hàng (chỉ-đọc): lý do bắt buộc, hết hạn")
    async def view_as(body: ViewAsIn, request: Request, p: Active):
        return await F().view_as(p, body.account_id, body.reason, client_ip(request))

    @app.post(adm + "/view-as/end", dependencies=[Csrf], tags=["admin"])
    async def view_as_end(body: ViewAsEndIn, request: Request, p: Active):
        return await F().view_as_end(p, body.grant_id, client_ip(request))

    @app.get(adm + "/view-as/active", tags=["admin"])
    async def view_as_active(p: Active):
        return {"items": await F().view_as_active(p)}

    # ---- khách tự opt-in thông báo push
    @app.get("/auth/client/notify", tags=["auth"])
    async def notify_get(p: Active):
        return await F().client_notify_get(p)

    @app.put("/auth/client/notify", dependencies=[Csrf], tags=["auth"])
    async def notify_put(body: NotifyIn, request: Request, p: Active):
        return await F().client_notify_set(p, body.enabled, client_ip(request))

    # ---- NỘI BỘ (token dịch vụ)
    async def fleet_ok(request: Request) -> None:
        tok = cfg.fleet_token
        if not tok:
            raise HTTPException(503, "service token chưa cấu hình")
        s = request.headers.get("authorization", "")
        if not s.startswith("Bearer ") or not hmac.compare_digest(s[7:].strip().encode(), tok.encode()):
            raise HTTPException(401, "unauthorized")

    FI = Depends(fleet_ok)

    @app.get("/internal/fleet/rules", dependencies=[FI], include_in_schema=False)
    async def int_rules():
        return await F().internal_rules()

    @app.post("/internal/fleet/results", dependencies=[FI], include_in_schema=False)
    async def int_results(body: dict):
        return await F().internal_results(body)

    @app.get("/internal/fleet/scope-accounts", dependencies=[FI], include_in_schema=False)
    async def int_scope(type: Annotated[str, Query(pattern=r"^(group|tag|account|all)$")], ref: Annotated[str, Query(max_length=64)] = ""):
        return await F().scope_accounts(type, ref)

    @app.get("/internal/fleet/account/{account_id}/compliance", dependencies=[FI], include_in_schema=False)
    async def int_acc_comp(account_id: str):
        return await F().account_compliance(acc(account_id))


def start_background(app: FastAPI):
    return get_fleet(app).start()


__all__ = ["register_fleet", "start_background", "get_fleet", "AuthService"]
