"""GET /health 基线。"""


def test_health_returns_ok(client):
    resp = client.get("/health")

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "app": "psy-backend", "env": "dev"}
