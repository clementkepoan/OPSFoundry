from fastapi.testclient import TestClient

from apps.api.main import app


client = TestClient(app)


def test_healthcheck_exposes_registered_workflows() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert "invoice_autoposting" in payload["registered_workflows"]
