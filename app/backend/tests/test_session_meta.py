"""T-S1.11 记录元数据富化 + 分组 + 编辑/删除 API 测试（离线，fake LLM）。

覆盖：sessions 新列自愈后读写；GET /sessions 富化字段；PATCH tags/brief/group_id
及 brief>100 → 422、非法 group → 404；DELETE 级联（行+音频文件）；分组 CRUD 全链。
"""

from __future__ import annotations

import json
from pathlib import Path

from psyapp.db import build_engine, create_session_factory, init_db
from psyapp.enums import SessionStatus
from psyapp.models import Job, Record, Segment, Session, SessionGroup
from psyapp.providers.base import Segment as AsrSegment
from psyapp.providers.base import TranscriptResult
from psyapp.services import parse_record_json


class FakeASR:
    name = "paraformer"

    def transcribe(self, audio_path, *, speaker_hint=None):
        return TranscriptResult(
            segments=[
                AsrSegment(0, "0", "你好，最近感觉怎么样？", 100, 2000, None),
                AsrSegment(1, "1", "最近睡眠不太好。", 2200, 4000, None),
                AsrSegment(2, "0", "能具体说说吗？", 4300, 6000, None),
                AsrSegment(3, "1", "就是工作压力大，晚上睡不着。", 6400, 9000, None),
            ],
            raw={},
        )


class FakeLLM:
    def __init__(self, responses, name="qwen"):
        self.responses = list(responses)
        self.calls = 0
        self.name = name

    def complete(self, messages, *, schema_hint=None, temperature=0.3):
        self.calls += 1
        return self.responses[min(self.calls - 1, len(self.responses) - 1)]


GOOD_CLEAN = json.dumps(
    {
        "roles": {
            "A": {"role": "T", "label": "咨询师"},
            "B": {"role": "P", "label": "来访者"},
        },
        "paragraphs": [
            {"speaker": "A", "source_seqs": [0], "text": "你好，最近感觉怎么样？"},
            {"speaker": "B", "source_seqs": [1], "text": "最近睡眠不太好。"},
            {"speaker": "A", "source_seqs": [2], "text": "能具体说说吗？"},
            {"speaker": "B", "source_seqs": [3], "text": "就是工作压力大，晚上睡不着。"},
        ],
    },
    ensure_ascii=False,
)

GOOD_RECORD_WITH_META = json.dumps(
    {
        "summary": "来访者自述最近睡眠不好、工作压力大。",
        "counselor_work": "咨询师询问近况并追问细节。",
        "client_reported_topics": ["睡眠", "工作压力"],
        "brief": "来访者自述睡眠不好、工作压力大，咨询师询问近况并追问细节。",
        "tags": ["咨询", "个体"],
    },
    ensure_ascii=False,
)


def _factory(client):
    return create_session_factory(client.app.state.engine)


def _make_session(client, **kwargs) -> tuple[int, str | None]:
    factory = _factory(client)
    db = factory()
    try:
        session = Session(
            user_id=1,
            mode="in_person",
            status=SessionStatus.UPLOADING,
            **kwargs,
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        return session.id, session.audio_path
    finally:
        db.close()


def _make_group(client, name="默认组", **kwargs) -> int:
    factory = _factory(client)
    db = factory()
    try:
        group = SessionGroup(user_id=1, name=name, **kwargs)
        db.add(group)
        db.commit()
        db.refresh(group)
        return group.id
    finally:
        db.close()


# ── T-S1.11 记录元数据：import 自检（验收标准 1）──────────────


def test_import_psyapp_main_ok():
    import psyapp.main  # noqa: F401


# ── 模型自愈与读写 ──────────────────────────────────────────────


def test_init_db_heals_session_meta_columns_and_reads_writes(app_settings):
    """旧 sessions 表（缺 T-S1.11 四列）经 init_db 自动补齐，且新字段可读写。"""
    engine = build_engine(app_settings)
    with engine.begin() as conn:
        conn.exec_driver_sql(
            """
            CREATE TABLE sessions (
                id INTEGER NOT NULL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                client_id INTEGER,
                mode VARCHAR(16) NOT NULL,
                pipeline_mode VARCHAR(8),
                status VARCHAR(16) NOT NULL,
                started_at DATETIME NOT NULL,
                duration_sec INTEGER NOT NULL,
                audio_path VARCHAR(512),
                cleaned_text TEXT,
                raw_transcript TEXT
            )
            """
        )
        conn.exec_driver_sql(
            "INSERT INTO sessions (id, user_id, mode, status, started_at, duration_sec) "
            "VALUES (7, 1, 'in_person', 'uploading', '2025-01-01 00:00:00', 0)"
        )

    init_db(engine, app_settings)

    with engine.connect() as conn:
        columns = [row[1] for row in conn.exec_driver_sql("PRAGMA table_info(sessions)")]

    for column in ("original_filename", "tags", "brief", "group_id"):
        assert column in columns, f"sessions 未补齐 {column}，实际列={columns}"

    from sqlalchemy.orm import Session as OrmSession

    with OrmSession(engine) as session:
        row = session.get(Session, 7)
        row.original_filename = "a.wav"
        row.tags = ["咨询"]
        row.brief = "来访者自述睡眠不好。"
        session.commit()

    with engine.connect() as conn:
        row = conn.exec_driver_sql(
            "SELECT original_filename, tags, brief, group_id FROM sessions WHERE id = 7"
        ).one()
    assert row[0] == "a.wav"
    assert json.loads(row[1]) == ["咨询"]
    assert row[2] == "来访者自述睡眠不好。"
    assert row[3] is None


# ── 上传链路：original_filename/duration/brief/tags ─────────────


def test_upload_full_chain_writes_session_meta(client, monkeypatch):
    """上传保存原始文件名、ffprobe 时长，record 成功后回写 brief/tags。"""
    monkeypatch.setattr("psyapp.routes.probe_duration_seconds", lambda path: 125)
    monkeypatch.setattr("psyapp.routes.get_asr_provider", lambda s: FakeASR())
    llms = iter([FakeLLM([GOOD_CLEAN]), FakeLLM([GOOD_RECORD_WITH_META])])
    monkeypatch.setattr("psyapp.routes.get_llm_provider", lambda s: next(llms))

    resp = client.post(
        "/sessions",
        files={"file": ("原始录音.wav", b"fake-wav-bytes", "audio/wav")},
        data={"mode": "asr"},
    )
    assert resp.status_code == 200, resp.text
    session_id = resp.json()["data"]["session_id"]

    detail = client.get(f"/sessions/{session_id}").json()["data"]
    assert detail["status"] == SessionStatus.DONE
    assert detail["brief"] == "来访者自述睡眠不好、工作压力大，咨询师询问近况并追问细节。"
    assert detail["tags"] == ["咨询", "个体"]

    factory = _factory(client)
    db = factory()
    try:
        session = db.get(Session, session_id)
        assert session.original_filename == "原始录音.wav"
        assert session.duration_sec == 125
        assert session.brief == detail["brief"]
        assert session.tags == detail["tags"]
    finally:
        db.close()

    listed = client.get("/sessions").json()["data"]["sessions"]
    assert listed[0]["original_filename"] == "原始录音.wav"
    assert listed[0]["duration_sec"] == 125
    assert listed[0]["word_count"] == len(detail["cleaned_text"])
    assert listed[0]["tags"] == ["咨询", "个体"]
    assert listed[0]["brief"] == detail["brief"]
    assert listed[0]["group_id"] is None
    assert listed[0]["group_name"] is None


def test_parse_record_json_fills_brief_and_tags_defaults():
    data = parse_record_json(
        json.dumps(
            {
                "summary": "s",
                "counselor_work": "c",
                "client_reported_topics": ["t"],
            },
            ensure_ascii=False,
        )
    )
    assert data["brief"] == ""
    assert data["tags"] == []

    data = parse_record_json(
        json.dumps(
            {
                "summary": "s",
                "counselor_work": "c",
                "client_reported_topics": ["t"],
                "brief": "b",
                "tags": ["咨询", 1, "个体"],
            },
            ensure_ascii=False,
        )
    )
    assert data["brief"] == "b"
    assert data["tags"] == ["咨询", "个体"]


# ── 列表富化与 PATCH ────────────────────────────────────────────


def test_list_sessions_enriched_fields_and_group_name(client):
    group_id = _make_group(client, name="重点个案", tags=["个体"], note="跟进")
    _make_session(
        client,
        original_filename="a.wav",
        duration_sec=60,
        cleaned_text="咨询师: 你好。\n来访者: 最近不好。",
        tags=["咨询"],
        brief="来访者自述最近不好。",
        group_id=group_id,
    )

    data = client.get("/sessions").json()["data"]
    assert len(data["sessions"]) == 1
    row = data["sessions"][0]
    assert row["original_filename"] == "a.wav"
    assert row["duration_sec"] == 60
    assert row["word_count"] == len("咨询师: 你好。\n来访者: 最近不好。")
    assert row["tags"] == ["咨询"]
    assert row["brief"] == "来访者自述最近不好。"
    assert row["group_id"] == group_id
    assert row["group_name"] == "重点个案"


def test_patch_session_meta(client):
    group_id = _make_group(client, name="个案组")
    session_id, _ = _make_session(client)

    resp = client.patch(
        f"/sessions/{session_id}",
        json={"tags": ["咨询", "个体"], "brief": "来访者自述最近状态。", "group_id": group_id},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()["data"]
    assert body["tags"] == ["咨询", "个体"]
    assert body["brief"] == "来访者自述最近状态。"
    assert body["group_id"] == group_id

    detail = client.get(f"/sessions/{session_id}").json()["data"]
    assert detail["tags"] == ["咨询", "个体"]
    assert detail["brief"] == "来访者自述最近状态。"
    assert detail["group_id"] == group_id

    # 只更新传入字段：PATCH 只传 group_id 不应清空 tags/brief
    resp = client.patch(f"/sessions/{session_id}", json={"group_id": None})
    assert resp.status_code == 200, resp.text
    detail = client.get(f"/sessions/{session_id}").json()["data"]
    assert detail["group_id"] is None
    assert detail["tags"] == ["咨询", "个体"]
    assert detail["brief"] == "来访者自述最近状态。"


def test_patch_session_meta_validation_errors(client):
    session_id, _ = _make_session(client)

    resp = client.patch(f"/sessions/{session_id}", json={"brief": "长" * 101})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "validation_error"

    resp = client.patch(f"/sessions/{session_id}", json={"group_id": 99999})
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"

    resp = client.patch("/sessions/99999", json={"tags": ["x"]})
    assert resp.status_code == 404


# ── DELETE 级联 ────────────────────────────────────────────────


def test_delete_session_cascades_rows_and_audio_file(client):
    audio_dir = Path(client.app.state.settings.data_dir) / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    audio_file = audio_dir / "to-delete.wav"
    audio_file.write_bytes(b"fake")

    session_id, _ = _make_session(client, audio_path=str(audio_file))
    factory = _factory(client)
    db = factory()
    try:
        db.add(Segment(session_id=session_id, user_id=1, seq=0, speaker="A", content="x"))
        db.add(
            Record(
                user_id=1,
                session_id=session_id,
                basic_info={"client_reported_topics": []},
            )
        )
        db.add(Job(type="transcribe", session_id=session_id, provider="fake"))
        db.commit()
    finally:
        db.close()

    resp = client.delete(f"/sessions/{session_id}")
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"] == {"deleted": session_id}
    assert not audio_file.exists()

    db = factory()
    try:
        assert db.get(Session, session_id) is None
        assert db.query(Segment).filter(Segment.session_id == session_id).count() == 0
        assert db.query(Record).filter(Record.session_id == session_id).count() == 0
        assert db.query(Job).filter(Job.session_id == session_id).count() == 0
    finally:
        db.close()

    assert client.get(f"/sessions/{session_id}").status_code == 404


# ── 分组 CRUD 全链 ─────────────────────────────────────────────


def test_groups_crud_full_chain(client):
    # 创建
    resp = client.post(
        "/groups", json={"name": "重点个案", "tags": ["个体"], "note": "每周跟进"}
    )
    assert resp.status_code == 200, resp.text
    group = resp.json()["data"]
    group_id = group["group_id"]
    assert group["name"] == "重点个案"
    assert group["tags"] == ["个体"]
    assert group["note"] == "每周跟进"
    assert group["member_count"] == 0

    # 列表（倒序，先建后建顺序）
    second = client.post("/groups", json={"name": "普通个案"}).json()["data"]
    data = client.get("/groups").json()["data"]["groups"]
    assert [g["group_id"] for g in data] == [second["group_id"], group_id]

    # 会话入组后 member_count 更新
    session_id, _ = _make_session(client)
    assert (
        client.patch(f"/sessions/{session_id}", json={"group_id": group_id}).status_code
        == 200
    )
    data = client.get("/groups").json()["data"]["groups"]
    by_id = {g["group_id"]: g for g in data}
    assert by_id[group_id]["member_count"] == 1
    assert by_id[second["group_id"]]["member_count"] == 0

    # 编辑组
    resp = client.patch(
        f"/groups/{group_id}", json={"name": "重点个案（改）", "note": "已调整"}
    )
    assert resp.status_code == 200, resp.text
    group = resp.json()["data"]
    assert group["name"] == "重点个案（改）"
    assert group["tags"] == ["个体"]
    assert group["note"] == "已调整"
    assert group["member_count"] == 1

    # 空名 / 重名 422
    assert client.post("/groups", json={"name": "  "}).status_code == 422
    assert client.post("/groups", json={"name": "普通个案"}).status_code == 422
    assert client.patch(f"/groups/{group_id}", json={"name": "普通个案"}).status_code == 422

    # 删除组：组内 sessions 归未分组，组本身消失
    resp = client.delete(f"/groups/{group_id}")
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"] == {"deleted": group_id}

    detail = client.get(f"/sessions/{session_id}").json()["data"]
    assert detail["group_id"] is None
    groups = client.get("/groups").json()["data"]["groups"]
    assert [g["group_id"] for g in groups] == [second["group_id"]]

    # 不存在的组 404
    assert client.delete(f"/groups/{group_id}").status_code == 404
    assert client.patch(f"/groups/{group_id}", json={"name": "x"}).status_code == 404
