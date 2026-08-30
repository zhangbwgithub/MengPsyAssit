"""T-S1.13 看板 API 扩展测试（离线，临时 SQLite）。

覆盖：组删除双模式（dissolve 默认保留记录 / with_records 级联清空 / 非法 mode 422）；
批量删除（正常 / 空列表 422 / 不存在或非本人进 missing）；
全量导出（结构 / 条数 / segments / started_at 倒序）；
转写段 PATCH（cleaned_text 重建、content 不动 / 空文本 422 / 会话与段 404）。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from psyapp.db import create_session_factory
from psyapp.enums import SessionStatus
from psyapp.models import Job, Record, Segment, Session, SessionGroup


def _factory(client):
    return create_session_factory(client.app.state.engine)


def _make_group(client, name: str = "测试组") -> int:
    db = _factory(client)()
    try:
        group = SessionGroup(user_id=1, name=name)
        db.add(group)
        db.commit()
        db.refresh(group)
        return group.id
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
        session = Session(**defaults)
        db.add(session)
        db.commit()
        db.refresh(session)
        return session.id
    finally:
        db.close()


def _make_audio_file(client, name: str) -> Path:
    audio_dir = Path(client.app.state.settings.data_dir) / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    audio_file = audio_dir / name
    audio_file.write_bytes(b"fake-audio")
    return audio_file


def _add_child_rows(client, session_id: int) -> None:
    """给会话补 segments/records/jobs 各 1 行（用于级联删除断言）。"""
    db = _factory(client)()
    try:
        db.add(
            Segment(
                session_id=session_id,
                user_id=1,
                seq=0,
                speaker="A",
                role="T",
                role_label="咨询师",
                cleaned_content="你好。",
                content="你好。",
            )
        )
        db.add(
            Record(
                user_id=1,
                session_id=session_id,
                status="done",
                summary="来访者状态平稳。",
                therapist_work="共情回应。",
                basic_info={"client_reported_topics": ["情绪"]},
            )
        )
        db.add(Job(type="record", session_id=session_id, provider="fake"))
        db.commit()
    finally:
        db.close()


def _add_two_segments(client, session_id: int) -> None:
    db = _factory(client)()
    try:
        db.add_all(
            [
                Segment(
                    session_id=session_id,
                    user_id=1,
                    seq=0,
                    speaker="A",
                    role="T",
                    role_label="咨询师",
                    cleaned_content="你好。",
                    content="你好。",
                ),
                Segment(
                    session_id=session_id,
                    user_id=1,
                    seq=1,
                    speaker="B",
                    role="P",
                    role_label="来访者",
                    cleaned_content="最近不好。",
                    content="最近不好。",
                ),
            ]
        )
        db.commit()
    finally:
        db.close()


# ── 组删除双模式 ────────────────────────────────────────────────


def test_delete_group_dissolve_default_keeps_records(client):
    group_id = _make_group(client, name="溶解组")
    audio_file = _make_audio_file(client, "dissolve.wav")
    session_id = _make_session(client, group_id=group_id, audio_path=str(audio_file))
    _add_child_rows(client, session_id)

    resp = client.delete(f"/groups/{group_id}")
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"] == {
        "deleted": group_id,
        "mode": "dissolve",
        "deleted_sessions": [],
    }

    # 组内会话记录保留，仅 group_id 置 null；音频文件保留
    detail = client.get(f"/sessions/{session_id}").json()["data"]
    assert detail["group_id"] is None
    assert len(detail["segments"]) == 1
    assert detail["record"] is not None
    assert audio_file.exists()

    db = _factory(client)()
    try:
        assert db.get(SessionGroup, group_id) is None
        assert db.get(Session, session_id) is not None
        assert db.query(Segment).filter(Segment.session_id == session_id).count() == 1
        assert db.query(Record).filter(Record.session_id == session_id).count() == 1
        assert db.query(Job).filter(Job.session_id == session_id).count() == 1
    finally:
        db.close()


def test_delete_group_with_records_cascades_rows_and_audio(client):
    group_id = _make_group(client, name="连删组")
    audio_file = _make_audio_file(client, "with-records.wav")
    session_id = _make_session(client, group_id=group_id, audio_path=str(audio_file))
    _add_child_rows(client, session_id)

    resp = client.delete(f"/groups/{group_id}", params={"mode": "with_records"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"] == {
        "deleted": group_id,
        "mode": "with_records",
        "deleted_sessions": [session_id],
    }

    assert not audio_file.exists()
    db = _factory(client)()
    try:
        assert db.get(SessionGroup, group_id) is None
        assert db.get(Session, session_id) is None
        assert db.query(Segment).filter(Segment.session_id == session_id).count() == 0
        assert db.query(Record).filter(Record.session_id == session_id).count() == 0
        assert db.query(Job).filter(Job.session_id == session_id).count() == 0
    finally:
        db.close()

    assert client.get(f"/sessions/{session_id}").status_code == 404


def test_delete_group_invalid_mode_returns_422(client):
    group_id = _make_group(client, name="非法模式组")

    resp = client.delete(f"/groups/{group_id}", params={"mode": "bogus"})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "validation_error"

    # 非法 mode 不应动数据
    assert client.get("/groups").json()["data"]["groups"][0]["group_id"] == group_id


# ── 批量删除 ────────────────────────────────────────────────────


def test_bulk_delete_sessions_deletes_owned_and_collects_missing(client):
    audio1 = _make_audio_file(client, "bulk-1.wav")
    audio2 = _make_audio_file(client, "bulk-2.wav")
    session1 = _make_session(client, audio_path=str(audio1))
    session2 = _make_session(client, audio_path=str(audio2))
    _add_child_rows(client, session1)
    _add_child_rows(client, session2)

    resp = client.post(
        "/sessions/bulk-delete",
        json={"session_ids": [session1, 999999, session2]},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"] == {
        "deleted": [session1, session2],
        "missing": [999999],
    }

    assert not audio1.exists()
    assert not audio2.exists()
    db = _factory(client)()
    try:
        assert db.get(Session, session1) is None
        assert db.get(Session, session2) is None
        assert db.query(Segment).filter(Segment.session_id == session1).count() == 0
        assert db.query(Record).filter(Record.session_id == session1).count() == 0
        assert db.query(Job).filter(Job.session_id == session1).count() == 0
    finally:
        db.close()


def test_bulk_delete_empty_list_returns_422(client):
    resp = client.post("/sessions/bulk-delete", json={"session_ids": []})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "validation_error"


def test_bulk_delete_non_owner_session_goes_to_missing(client):
    other_user_session = _make_session(client, user_id=2)
    owned_session = _make_session(client)

    resp = client.post(
        "/sessions/bulk-delete",
        json={"session_ids": [other_user_session, owned_session]},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"] == {
        "deleted": [owned_session],
        "missing": [other_user_session],
    }

    db = _factory(client)()
    try:
        assert db.get(Session, other_user_session) is not None
        assert db.get(Session, owned_session) is None
    finally:
        db.close()


# ── 全量导出 ────────────────────────────────────────────────────


def test_export_sessions_structure_count_segments_and_order(client):
    group_id = _make_group(client, name="导出组")
    old = _make_session(
        client,
        started_at=datetime(2025, 1, 1, 10, 0, 0),
        original_filename="old.wav",
        duration_sec=10,
        tags=["历史"],
        brief="旧会话",
    )
    new = _make_session(
        client,
        started_at=datetime(2025, 1, 2, 10, 0, 0),
        original_filename="new.wav",
        duration_sec=20,
        group_id=group_id,
    )
    _add_child_rows(client, new)

    resp = client.get("/export/sessions")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert set(data.keys()) == {"exported_at", "count", "sessions"}
    assert data["count"] == 2
    assert data["exported_at"]

    sessions = data["sessions"]
    assert [s["session_id"] for s in sessions] == [new, old]

    new_item = sessions[0]
    for field in (
        "session_id",
        "status",
        "mode",
        "pipeline_mode",
        "model_display",
        "started_at",
        "audio_path",
        "segments",
        "cleaned_text",
        "tags",
        "brief",
        "group_id",
        "record",
        "original_filename",
        "duration_sec",
        "group_name",
    ):
        assert field in new_item, f"导出项缺字段: {field}"

    assert new_item["original_filename"] == "new.wav"
    assert new_item["duration_sec"] == 20
    assert new_item["group_name"] == "导出组"
    assert len(new_item["segments"]) == 1
    assert new_item["record"] is not None
    assert new_item["record"]["summary"] == "来访者状态平稳。"

    old_item = sessions[1]
    assert old_item["original_filename"] == "old.wav"
    assert old_item["group_name"] is None
    assert old_item["segments"] == []
    assert old_item["record"] is None


# ── 转写段编辑 ──────────────────────────────────────────────────


def test_patch_segment_rebuilds_cleaned_text_and_keeps_content(client):
    session_id = _make_session(client)
    _add_two_segments(client, session_id)

    resp = client.patch(
        f"/sessions/{session_id}/segments/0", json={"text": "今天感觉怎么样？"}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"] == {
        "session_id": session_id,
        "seq": 0,
        "word_count": len("咨询师: 今天感觉怎么样？\n来访者: 最近不好。"),
    }

    detail = client.get(f"/sessions/{session_id}").json()["data"]
    assert detail["segments"][0]["cleaned_content"] == "今天感觉怎么样？"
    # 原文 content 保留不动（可追溯）
    assert detail["segments"][0]["content"] == "你好。"
    assert detail["segments"][1]["cleaned_content"] == "最近不好。"
    assert detail["cleaned_text"] == "咨询师: 今天感觉怎么样？\n来访者: 最近不好。"

    db = _factory(client)()
    try:
        session = db.get(Session, session_id)
        assert session.cleaned_text == "咨询师: 今天感觉怎么样？\n来访者: 最近不好。"
    finally:
        db.close()


def test_patch_segment_empty_or_blank_text_returns_422(client):
    session_id = _make_session(client)
    _add_two_segments(client, session_id)

    resp = client.patch(f"/sessions/{session_id}/segments/0", json={"text": ""})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "validation_error"

    resp = client.patch(f"/sessions/{session_id}/segments/0", json={"text": "   "})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "validation_error"


def test_patch_segment_missing_session_or_seq_returns_404(client):
    session_id = _make_session(client)
    _add_two_segments(client, session_id)

    resp = client.patch("/sessions/99999/segments/0", json={"text": "x"})
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"

    resp = client.patch(f"/sessions/{session_id}/segments/999", json={"text": "x"})
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"
