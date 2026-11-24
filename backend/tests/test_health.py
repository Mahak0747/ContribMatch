from app.db import session as db_session


def test_health_ok(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["app"] and body["version"]


def test_health_does_not_leak_secrets(client):
    assert "token" not in client.get("/api/health").text.lower()


def test_health_degraded_when_db_down(client, monkeypatch):
    monkeypatch.setattr("app.api.routes.health.check_db", lambda: False)
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "degraded"
    assert r.json()["database"] == "unavailable"


def test_init_db_idempotent():
    db_session.init_db()
    db_session.init_db()
    assert db_session.check_db()


def test_liveness_endpoint(client):
    r = client.get("/api/health/live")
    assert r.status_code == 200 and r.json() == {"status": "ok"}
