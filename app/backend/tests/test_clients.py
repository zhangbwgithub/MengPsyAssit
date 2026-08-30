"""T-S1.17 来访者档案 API 测试（离线）。

覆盖：clients CRUD 全链（建/列表/编辑/删除 + 自动 code 回填 + session_count 口径 +
重名与非法 status/start_date 422）；SessionPatch 挂/解绑 client_id；会话列表/详情/导出
富化 client_id/client_name；旧库不传新字段建来访者不炸（列自愈路径）。
"""

from __future__ import annotations

from datetime import date

from psyapp.db import build_engine, create_session_factory, init_db
from psyapp.enums import ClientStatus, SessionStatus
from psyapp.models import Client, Session
from sqlalchemy.orm import Session as OrmSession


def _factory(client):
    return create_session_factory(client.app.state.engine)


def _make_client(client, **kwargs) -> int:
    db = _factory(client)()
    try:
        defaults = {"user_id": 1, "code": "X", "name": "张三", "status": "active"}
        defaults.update(kwargs)
        c = Client(**defaults)
        db.add(c)
        db.commit()
        db.refresh(c)
        return c.id
    finally:
        db.close()


def _make_session(client, **kwargs) -> int:
    db = _factory(client)()
    try:
        defaults = {
            "user_id": 1,
            "mode": "in_person",
            "status": SessionStatus.DONE,
        }
        defaults.update(kwargs)
        s = Session(**defaults)
        db.add(s)
        db.commit()
        db.refresh(s)
        return s.id
    finally:
        db.close()


def _post(client, payload):
    resp = client.post("/clients", json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _list(client):
    resp = client.get("/clients")
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["clients"]


# ── CRUD 全链 ────────────────────────────────────────────────────


def test_clients_crud_full_chain(client):
    # 建：name 必填；未传 code 自动回填 C+client_id
    a = _post(client, {"name": "张三", "gender": "女", "age": 30, "start_date": "2025-01-02"})
    assert a["client_id"] > 0
    assert a["code"] == f"C{a['client_id']}"
    assert a["name"] == "张三"
    assert a["gender"] == "女"
    assert a["age"] == 30
    assert a["status"] == "active"
    assert a["start_date"] == "2025-01-02"
    assert a["session_count_auto"] == 0
    assert a["session_count_manual"] is None
    assert a["session_count"] == 0

    # 有 code + disabled 状态
    b = _post(client, {"name": "李四", "code": "L4", "status": "disabled"})
    assert b["code"] == "L4"
    assert b["status"] == "disabled"

    # 重名 422（含空白）
    assert client.post("/clients", json={"name": "张三"}).status_code == 422
    assert client.post("/clients", json={"name": "  "}).status_code == 422
    assert client.post("/clients", json={"age": 1}).status_code == 422

    # start_date 非法格式 422；age 非整数由 pydantic 自然 422
    assert client.post("/clients", json={"name": "王五", "start_date": "2025/01/01"}).status_code == 422
    assert client.post("/clients", json={"name": "王五", "age": "x"}).status_code == 422
    # 非法 status 422
    assert client.post("/clients", json={"name": "王五", "status": "done"}).status_code == 422

    # 列表：active 优先 + start_date 降序（无日期按 id 降序兜底）
    rows = _list(client)
    assert [r["name"] for r in rows] == ["张三", "李四"]

    # session_count：自动计名下会话（所有状态）；手工值优先
    _make_session(client, client_id=a["client_id"], status="done")
    _make_session(client, client_id=a["client_id"], status="failed")
    rows = _list(client)
    by_name = {r["name"]: r for r in rows}
    assert by_name["张三"]["session_count_auto"] == 2
    assert by_name["张三"]["session_count"] == 2

    resp = client.patch(f"/clients/{a['client_id']}", json={"session_count_manual": 5})
    assert resp.status_code == 200, resp.text
    by_name = {r["name"]: r for r in _list(client)}
    assert by_name["张三"]["session_count_manual"] == 5
    assert by_name["张三"]["session_count_auto"] == 2
    assert by_name["张三"]["session_count"] == 5

    # 编辑：部分字段（只改传入字段）
    resp = client.patch(f"/clients/{a['client_id']}", json={"phone": "13800000000"})
    assert resp.status_code == 200, resp.text
    c = resp.json()["data"]
    assert c["phone"] == "13800000000"
    assert c["gender"] == "女"  # 未传字段保持不变
    assert c["session_count_manual"] == 5

    # 编辑重名 422（含与自己之外的同名）、空白名 422
    assert client.patch(f"/clients/{b['client_id']}", json={"name": "张三"}).status_code == 422
    assert client.patch(f"/clients/{a['client_id']}", json={"name": "  "}).status_code == 422
    # 编辑非法 status 422
    assert client.patch(f"/clients/{a['client_id']}", json={"status": "done"}).status_code == 422
    # 编辑非法 start_date 422
    assert client.patch(f"/clients/{a['client_id']}", json={"start_date": "bad"}).status_code == 422
    # 不存在 404
    assert client.patch("/clients/99999", json={"name": "x"}).status_code == 404
    assert client.delete("/clients/99999").status_code == 404

    # 删除：名下会话 client_id 置 null，记录保留；affected_sessions 正确
    resp = client.delete(f"/clients/{a['client_id']}")
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"] == {"deleted": a["client_id"], "affected_sessions": 2}

    db = _factory(client)()
    try:
        assert db.get(Client, a["client_id"]) is None
        sessions = (
            db.query(Session).filter(Session.client_id == a["client_id"]).all()
        )
        assert sessions == []
        assert db.query(Session).filter(Session.user_id == 1).count() == 2
    finally:
        db.close()

    assert [r["name"] for r in _list(client)] == ["李四"]


# ── SessionPatch 挂 client_id ────────────────────────────────────


def test_session_patch_client_id_bind_unbind_and_404(client):
    client_id = _make_client(client, code="C9", name="王五")
    session_id = _make_session(client)

    # 挂接
    resp = client.patch(f"/sessions/{session_id}", json={"client_id": client_id})
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["client_id"] == client_id
    detail = client.get(f"/sessions/{session_id}").json()["data"]
    assert detail["client_id"] == client_id
    assert detail["client_name"] == "王五"

    # 不存在 404
    resp = client.patch(f"/sessions/{session_id}", json={"client_id": 99999})
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"

    # 显式 null 解绑
    resp = client.patch(f"/sessions/{session_id}", json={"client_id": None})
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["client_id"] is None
    detail = client.get(f"/sessions/{session_id}").json()["data"]
    assert detail["client_id"] is None
    assert detail["client_name"] is None

    # 不传 client_id 时不影响已有字段（只挂 tags 不清 client_id）
    client.patch(f"/sessions/{session_id}", json={"client_id": client_id})
    resp = client.patch(f"/sessions/{session_id}", json={"tags": ["x"]})
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["client_id"] == client_id


# ── 列表/详情/导出富化 client_id/client_name ──────────────────────


def test_sessions_list_detail_export_carry_client_name(client):
    client_id = _make_client(client, code="C1", name="赵六")
    session_id = _make_session(client, client_id=client_id)

    listed = client.get("/sessions").json()["data"]["sessions"]
    assert len(listed) == 1
    assert listed[0]["client_id"] == client_id
    assert listed[0]["client_name"] == "赵六"

    detail = client.get(f"/sessions/{session_id}").json()["data"]
    assert detail["client_id"] == client_id
    assert detail["client_name"] == "赵六"

    exported = client.get("/export/sessions").json()["data"]["sessions"]
    assert len(exported) == 1
    assert exported[0]["client_id"] == client_id
    assert exported[0]["client_name"] == "赵六"

    # 无来访者时详情/列表 client_id 与 client_name 均为 null
    free_session_id = _make_session(client)
    free = client.get(f"/sessions/{free_session_id}").json()["data"]
    assert free["client_id"] is None
    assert free["client_name"] is None


# ── 旧库兼容：不传新字段建来访者不炸（列自愈路径）──────────────


def test_old_clients_table_heals_new_columns(app_settings):
    engine = build_engine(app_settings)
    with engine.begin() as conn:
        conn.exec_driver_sql(
            """
            CREATE TABLE clients (
                id INTEGER NOT NULL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                code VARCHAR(64) NOT NULL,
                note TEXT,
                status VARCHAR(16) NOT NULL
            )
            """
        )
        conn.exec_driver_sql(
            "INSERT INTO clients (id, user_id, code, note, status) "
            "VALUES (1, 1, 'old', NULL, 'active')"
        )

    init_db(engine, app_settings)

    with engine.connect() as conn:
        columns = [row[1] for row in conn.exec_driver_sql("PRAGMA table_info(clients)")]

    for column in (
        "name",
        "gender",
        "age",
        "phone",
        "emergency_contact",
        "emergency_phone",
        "start_date",
        "session_count_manual",
    ):
        assert column in columns, f"clients 未补齐 {column}，实际列={columns}"

    with OrmSession(engine) as db:
        row = db.get(Client, 1)
        row.name = "旧档案"
        row.start_date = date(2025, 1, 1)
        db.commit()
        assert db.get(Client, 1).name == "旧档案"
        assert db.get(Client, 1).start_date == date(2025, 1, 1)
        assert db.get(Client, 1).status == ClientStatus.ACTIVE
