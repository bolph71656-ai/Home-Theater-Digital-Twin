from fastapi.testclient import TestClient

from htdt.main import app


def test_health_endpoint() -> None:
    client = TestClient(app)

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "version": "0.1.0.dev0",
        "platform_target": "Windows 11 x64",
        "rew_required": False,
        "measurement_hardware_required": False,
    }


def test_root_is_available_without_built_frontend() -> None:
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
