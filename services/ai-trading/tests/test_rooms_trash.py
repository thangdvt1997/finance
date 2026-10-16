"""Test thùng rác phòng: xoá mềm/khôi phục/purge/bulk/tự dọn, phân quyền, IDOR, job đang chạy."""
import datetime as dt

from .test_class_api import E1, E2, M, env, mkroom, say  # noqa: F401


def mem(c, rid, uid, name="X", role="expert", h=M):
    return c.post(f"/class/rooms/{rid}/members", json={"user_id": uid, "name": name, "role": role}, headers=h)


def test_soft_delete_restore_and_hidden(env):
    c, _, _ = env
    rid = mkroom(c)
    r = c.delete(f"/class/rooms/{rid}?reason=rac", headers=E1)
    assert r.status_code == 200 and r.json()["days"] == 30
    assert all(x["id"] != rid for x in c.get("/class/rooms", headers=E1).json()["items"])
    assert all(x["id"] != rid for x in c.get("/class/rooms", headers=M).json()["items"])
    assert c.get(f"/class/rooms/{rid}", headers=M).status_code == 404           # route cũ coi như không tồn tại
    assert c.post(f"/class/rooms/{rid}/messages", json={"text": "hi"}, headers=E1).status_code == 404
    t = c.get("/class/rooms/trash", headers=E1).json()
    assert t["count"] == 1 and t["items"][0]["reason"] == "rac" and t["items"][0]["counts"]["messages"] >= 1
    assert c.get("/class/rooms/trash", headers=E2).json()["count"] == 0         # IDOR
    assert c.post(f"/class/rooms/{rid}/restore", headers=E2).status_code == 404
    assert c.post(f"/class/rooms/{rid}/restore", headers=E1).status_code == 200
    assert c.get(f"/class/rooms/{rid}", headers=E1).status_code == 200
    assert c.get("/class/rooms/trash", headers=M).json()["count"] == 0


def test_authz_delete(env):
    c, _, _ = env
    rid = mkroom(c)
    assert c.delete(f"/class/rooms/{rid}").status_code == 403                   # không danh tính
    assert c.delete(f"/class/rooms/{rid}", headers=E2).status_code == 404       # không phải thành viên
    assert mem(c, rid, "exp2", "E2").status_code == 201
    assert c.delete(f"/class/rooms/{rid}", headers=E2).status_code == 403       # thành viên nhưng không phải chủ
    say(c, rid, "Tôi là chuyên gia 2 đóng góp", E2)
    assert c.delete(f"/class/rooms/{rid}", headers=E1).status_code == 403       # người khác đã đóng góp: chỉ master
    assert c.delete(f"/class/rooms/{rid}", headers=M).status_code == 200
    assert c.delete(f"/class/rooms/{'0' * 32}", headers=M).status_code == 404


def test_purge_master_only_and_cleanup(env):
    c, app, tmp = env
    rid = mkroom(c)
    att = c.post(f"/class/rooms/{rid}/attachments", json={"kind": "note", "name": "a.txt", "text": "ghi chú"}, headers=E1)
    assert att.status_code == 201, att.text
    assert (tmp / "class" / "media" / rid).exists()
    assert c.delete(f"/class/rooms/{rid}/purge", headers=M).status_code == 404  # chưa vào thùng rác
    c.delete(f"/class/rooms/{rid}", headers=E1)
    assert c.delete(f"/class/rooms/{rid}/purge", headers=E1).status_code == 403
    assert c.delete(f"/class/rooms/{rid}/purge", headers=E2).status_code == 404
    assert c.delete(f"/class/rooms/{rid}/purge", headers=M).status_code == 200
    st = app.state.class_store
    for tb in ("class_rooms", "class_messages", "class_members", "class_attachments", "class_room_trash"):
        col = "id" if tb == "class_rooms" else "room_id"
        assert st.q(f"SELECT COUNT(*) FROM {tb} WHERE {col}=?", (rid,))[0][0] == 0, tb
    assert not (tmp / "class" / "media" / rid).exists()
    assert any(a["event"] == "room.purge" for a in st.q("SELECT event FROM class_audit"))


def test_bulk_two_steps(env):
    c, _, _ = env
    ids = [mkroom(c, title=f"Phòng rác {i}") for i in range(3)]
    other = mkroom(c, h=E2, title="Phòng của E2")
    p = c.post("/class/rooms/bulk-delete", json={"step": "prepare", "ids": ids + [other]}, headers=E1)
    assert p.status_code == 200
    d = p.json()
    assert len(d["eligible"]) == 3 and [x["id"] for x in d["rejected"]] == [other] and d["rejected"][0]["reason"] == "không tìm thấy phòng"
    assert c.post("/class/rooms/bulk-delete", json={"step": "confirm", "ids": ids, "token": "bad"}, headers=E1).status_code == 409
    assert c.post("/class/rooms/bulk-delete", json={"step": "confirm", "ids": ids, "token": d["token"]}, headers=E2).status_code == 409   # token gắn người
    cf = c.post("/class/rooms/bulk-delete", json={"step": "confirm", "ids": ids, "token": d["token"]}, headers=E1)
    assert cf.status_code == 200 and sorted(cf.json()["trashed"]) == sorted(ids)
    assert c.post("/class/rooms/bulk-delete", json={"step": "confirm", "ids": ids, "token": d["token"]}, headers=E1).status_code == 409   # dùng 1 lần
    assert c.get("/class/rooms/trash", headers=E1).json()["count"] == 3
    big = [f"{i:032x}" for i in range(51)]
    assert c.post("/class/rooms/bulk-delete", json={"step": "prepare", "ids": big}, headers=M).status_code == 422
    assert c.post("/class/rooms/bulk-delete", json={"step": "x", "ids": ids}, headers=M).status_code == 422
    assert c.get(f"/class/rooms/{other}", headers=E2).status_code == 200      # phòng khác không bị đụng


def test_running_job_blocks(env):
    c, app, _ = env
    rid = mkroom(c)
    st = app.state.class_store
    st.add_action(rid, "test", "running", {}, "exp1")      # chưa có job_id: coi như đang chạy
    r = c.delete(f"/class/rooms/{rid}", headers=E1)
    assert r.status_code == 409 and "nền" in r.json()["detail"]
    a = st.actions(rid)[0]
    st.upd_action(a["id"], status="failed")
    assert c.delete(f"/class/rooms/{rid}", headers=E1).status_code == 200


def test_auto_purge_after_30_days(env):
    c, app, _ = env
    a, b = mkroom(c), mkroom(c, title="Phòng còn hạn")
    c.delete(f"/class/rooms/{a}", headers=E1)
    c.delete(f"/class/rooms/{b}", headers=E1)
    api = app.state.rooms_trash
    assert api["purge_expired"]() == 0
    st = app.state.class_store
    old = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1)).isoformat(timespec="seconds")
    st.x("UPDATE class_room_trash SET purge_after=? WHERE room_id=?", (old, a))
    assert api["purge_expired"]() == 1
    t = c.get("/class/rooms/trash", headers=M).json()
    assert [x["id"] for x in t["items"]] == [b]
    assert st.room(a, include_trashed=True) is None
    assert api["purge_expired"](dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=31)) == 1


def test_hooks_forget_flag(env):
    from ai_trading.classroom import rooms_trash as rt
    c, _, _ = env
    got = []
    rt.ON_TRASH.append(lambda rid, f: got.append((rid, f)))
    try:
        rid = mkroom(c)
        c.delete(f"/class/rooms/{rid}?forget_learned=true", headers=E1)
        assert got == [(rid, True)]
        assert c.get("/class/rooms/trash", headers=E1).json()["items"][0]["forget_learned"] is True
    finally:
        rt.ON_TRASH.clear()
