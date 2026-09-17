from fastapi.testclient import TestClient

from app.main import app


def test_dashboard_page_is_served() -> None:
    client = TestClient(app)
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert "Observatório Ceres-Rialma" in response.text


def test_dashboard_static_assets_are_served() -> None:
    client = TestClient(app)
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/styles.css").status_code == 200