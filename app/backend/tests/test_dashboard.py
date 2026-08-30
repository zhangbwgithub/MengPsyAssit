"""T-S1.15 工作台统计 API 测试（离线，临时 SQLite）。

覆盖：空库结构完整；周窗口 / 上周对比 / totals / status_dist / trend 数值；
tag_cloud 词频排序与 Top20 截断；todos 只对 done 计 no_brief/no_tags。
"""

from __future__ import annotations

from datetime import datetime, timedelta

from psyapp.db import create_session_factory
from psyapp.enums import SessionStatus
from psyapp.models import Session, SessionGroup


def _factory(client):
    return create_session_factory(client.app.state.engine)


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


def _monday(dt: datetime) -> datetime:
    return (dt - timedelta(days=dt.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )


def _summary(client) -> dict:
    resp = client.get("/api/dashboard/summary")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    return body["data"]


def test_dashboard_summary_empty_library_returns_full_structure(client):
    data = _summary(client)

    assert set(data.keys()) == {
        "week",
        "totals",
        "status_dist",
        "tag_cloud",
        "trend",
        "todos",
    }

    now = datetime.now()
    monday = _monday(now)
    week = data["week"]
    assert week["start"] == monday.date().isoformat()
    assert week["end"] == (monday + timedelta(days=6)).date().isoformat()
    assert week["sessions"] == 0
    assert week["sessions_prev"] == 0
    assert week["hours"] == 0
    assert week["hours_prev"] == 0
    assert week["avg_minutes"] == 0
    assert week["avg_minutes_prev"] == 0

    assert data["totals"] == {"sessions": 0, "groups": 0}
    assert data["status_dist"] == [
        {"status": "done", "label": "完成", "count": 0},
        {"status": "processing", "label": "处理中", "count": 0},
        {"status": "failed", "label": "失败", "count": 0},
    ]
    assert data["tag_cloud"] == []
    assert data["todos"] == {"no_brief": 0, "no_tags": 0, "failed": 0}

    assert len(data["trend"]) == 14
    assert data["trend"][0]["date"] == (now.date() - timedelta(days=13)).isoformat()
    assert data["trend"][-1]["date"] == now.date().isoformat()
    assert all(item["minutes"] == 0 and item["sessions"] == 0 for item in data["trend"])


def test_dashboard_summary_week_totals_status_dist_and_trend(client):
    now = datetime.now()
    monday = _monday(now)
    prev_monday = monday - timedelta(days=7)
    earlier = monday - timedelta(days=14)

    # 本周 2 条（含 1 failed）+ 上周 1 条 + 更早 1 条（只在 totals，不在 trend）
    _make_session(
        client,
        started_at=monday + timedelta(hours=9),
        duration_sec=1800,
        status=SessionStatus.DONE,
    )
    _make_session(
        client,
        started_at=monday + timedelta(hours=10),
        duration_sec=3600,
        status=SessionStatus.FAILED,
    )
    _make_session(
        client,
        started_at=prev_monday + timedelta(hours=9),
        duration_sec=1800,
        status=SessionStatus.DONE,
    )
    _make_session(
        client,
        started_at=earlier + timedelta(hours=9),
        duration_sec=7200,
        status=SessionStatus.DONE,
    )

    data = _summary(client)

    week = data["week"]
    assert week["sessions"] == 2
    assert week["sessions_prev"] == 1
    assert week["hours"] == 1.5
    assert week["hours_prev"] == 0.5
    assert week["avg_minutes"] == 45.0
    assert week["avg_minutes_prev"] == 30.0

    assert data["totals"] == {"sessions": 4, "groups": 0}
    assert data["status_dist"] == [
        {"status": "done", "label": "完成", "count": 3},
        {"status": "processing", "label": "处理中", "count": 0},
        {"status": "failed", "label": "失败", "count": 1},
    ]

    by_date = {item["date"]: item for item in data["trend"]}
    assert by_date[monday.date().isoformat()] == {
        "date": monday.date().isoformat(),
        "minutes": 90.0,
        "sessions": 2,
    }
    assert by_date[prev_monday.date().isoformat()] == {
        "date": prev_monday.date().isoformat(),
        "minutes": 30.0,
        "sessions": 1,
    }
    # 更早会话（本周一 - 14 天）不在近 14 天窗口内
    assert earlier.date().isoformat() not in by_date


def test_dashboard_tag_cloud_frequency_order_and_top20(client):
    tags = [f"t{i:02d}" for i in range(20)]
    _make_session(client, tags=["hot"], status=SessionStatus.DONE)
    _make_session(client, tags=["hot", *tags], status=SessionStatus.DONE)
    # 空 tags 不计入词云
    _make_session(client, tags=[], status=SessionStatus.DONE)

    data = _summary(client)
    cloud = data["tag_cloud"]

    assert len(cloud) == 20
    assert cloud[0] == {"tag": "hot", "count": 2}
    counts = [item["count"] for item in cloud]
    assert counts == sorted(counts, reverse=True)

    cloud_tags = {item["tag"] for item in cloud}
    assert "hot" in cloud_tags
    assert "t00" in cloud_tags
    # 21 个不同标签，Top20 截断后按字典序最后一个 t19 被裁掉
    assert "t19" not in cloud_tags


def test_dashboard_todos_only_done_counts_no_brief_no_tags(client):
    _make_session(client, brief=None, tags=None, status=SessionStatus.DONE)
    _make_session(client, brief="", tags=[], status=SessionStatus.DONE)
    _make_session(client, brief="有摘要", tags=["咨询"], status=SessionStatus.DONE)
    _make_session(client, brief=None, tags=[], status=SessionStatus.FAILED)
    _make_session(client, brief=None, tags=[], status=SessionStatus.UPLOADING)

    data = _summary(client)
    assert data["todos"] == {"no_brief": 2, "no_tags": 2, "failed": 1}
