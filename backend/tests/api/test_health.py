from fastapi.testclient import TestClient

from deepaha.main import app

client = TestClient(app)


def test_liveness() -> None:
    response = client.get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["X-Request-ID"]


def test_readiness() -> None:
    response = client.get("/api/v1/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_version_contract() -> None:
    response = client.get("/api/v1/version")

    assert response.status_code == 200
    assert response.json() == {
        "app": "deepaha-api",
        "version": "0.1.0",
        "api_version": "v1",
        "contract_version": "0.1.0",
    }


def test_valid_request_id_is_preserved() -> None:
    response = client.get(
        "/api/v1/health/live",
        headers={"X-Request-ID": "phase-0-test"},
    )

    assert response.headers["X-Request-ID"] == "phase-0-test"
