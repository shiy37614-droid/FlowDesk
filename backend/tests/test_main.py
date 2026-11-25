from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health_returns_ok():
    response = client.get("/health")

    assert response.status_code == 200

    assert response.json() == {
        "status": "ok",
        "service": "FlowDesk API",
        "version": "0.1.0",
    }


def test_swagger_docs_are_available():
    response = client.get("/docs")

    assert response.status_code == 200
    assert "Swagger UI" in response.text


def test_openapi_schema_contains_health_route():
    response = client.get("/openapi.json")

    assert response.status_code == 200

    schema = response.json()

    assert "/health" in schema["paths"]


def test_unknown_route_returns_404():
    response = client.get("/not-a-real-route")

    assert response.status_code == 404


def test_health_rejects_unsupported_method():
    response = client.post("/health")

    assert response.status_code == 405
