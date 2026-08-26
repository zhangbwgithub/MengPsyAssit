"""统一错误响应结构。"""


def test_404_returns_unified_error_structure(client):
    resp = client.get("/no-such-route")

    assert resp.status_code == 404
    body = resp.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "not_found"
    assert "message" in body["error"]
