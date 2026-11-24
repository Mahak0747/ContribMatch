from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.core.exceptions import NotFoundError, register_exception_handlers


def test_unknown_route_uniform_404(client):
    r = client.get("/api/nope")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


def test_wrong_method_405(client):
    r = client.post("/api/health")
    assert r.status_code == 405
    assert "error" in r.json()


def test_cors_allows_frontend_origin(client):
    r = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
    assert r.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_cors_blocks_other_origin(client):
    r = client.get("/api/health", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in r.headers


def _mini_app():
    app = FastAPI()
    register_exception_handlers(app)

    class Body(BaseModel):
        n: int

    @app.get("/nf")
    def nf():
        raise NotFoundError("missing thing")

    @app.get("/boom")
    def boom():
        raise RuntimeError("secret internal detail")

    @app.post("/v")
    def v(b: Body):
        return b

    return app


def test_app_error_handler():
    r = TestClient(_mini_app()).get("/nf")
    assert r.status_code == 404
    assert r.json() == {"error": {"code": "not_found", "message": "missing thing"}}


def test_validation_error_handler():
    r = TestClient(_mini_app()).post("/v", json={"n": "abc"})
    assert r.status_code == 422
    body = r.json()["error"]
    assert body["code"] == "validation_error"
    assert body["details"][0]["field"] == "body.n"


def test_unhandled_error_hides_details():
    r = TestClient(_mini_app(), raise_server_exceptions=False).get("/boom")
    assert r.status_code == 500
    assert "secret" not in r.text
