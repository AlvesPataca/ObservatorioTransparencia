from decimal import Decimal
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from app.main import app
from app.api import routes


def test_health_returns_ok() -> None:
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_api_summary_and_records_return_200() -> None:
    client = TestClient(app)
    assert client.get("/api/summary").status_code == 200
    response = client.get("/api/records")
    assert response.status_code == 200
    assert set(response.json()) >= {"total", "items"}
    assert isinstance(response.json()["items"], list)


def test_records_filters_work() -> None:
    client = TestClient(app)
    response = client.get("/api/records", params={"kind": "licitacao", "limit": 1})
    assert response.status_code == 200
    assert all(record["kind"] == "licitacao" for record in response.json()["items"])
    expenses = client.get("/api/records", params={"kind": "despesa", "limit": 1})
    assert expenses.status_code == 200
    assert all(record["kind"] == "despesa" for record in expenses.json()["items"])


def test_municipalities_are_unique_and_municipality_filter_works() -> None:
    client = TestClient(app)
    municipalities = client.get("/api/municipalities").json()
    assert municipalities == sorted(set(municipalities))
    response = client.get("/api/records", params={"municipality": "Ceres-GO"})
    assert response.status_code == 200
    assert all(record["municipality"] == "Ceres-GO" for record in response.json()["items"])


def test_api_year_filter_and_years_endpoint() -> None:
    client = TestClient(app)
    years_resp = client.get("/api/years")
    assert years_resp.status_code == 200
    assert isinstance(years_resp.json(), list)

    summary_resp = client.get("/api/summary", params={"year": 2026})
    assert summary_resp.status_code == 200
    assert summary_resp.json()["selected_year"] == 2026

    records_resp = client.get("/api/records", params={"year": 2026, "limit": 5})
    assert records_resp.status_code == 200
    for item in records_resp.json()["items"]:
        assert item["year"] == 2026



def test_missing_database_returns_empty_responses(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:")
    empty_session = sessionmaker(bind=engine)
    monkeypatch.setattr(routes, "SessionLocal", empty_session)

    client = TestClient(app)
    summary_data = client.get("/api/summary").json()
    assert summary_data["records_by_municipality"] == {}
    assert summary_data["records_by_kind"] == {}
    assert summary_data["records_missing_value"] == 0
    assert summary_data["attention_count"] == 0
    assert summary_data["expenses_financial_totals"] == {
        "total_empenhado": "0.00",
        "total_liquidado": "0.00",
        "total_pago": "0.00",
    }
    assert client.get("/api/records").json()["items"] == []
    assert client.get("/api/analysis").json()["records_by_kind"] == {}


def test_summary_strict_separation_and_financial_totals() -> None:
    client = TestClient(app)
    # 2026 Summary
    res = client.get("/api/summary", params={"year": 2026})
    assert res.status_code == 200
    data = res.json()
    # Licitações deve contar apenas licitações
    by_kind = data["totals_by_kind"]
    assert "despesa" in by_kind
    assert "licitacao" in by_kind
    assert "contrato" in by_kind
    assert by_kind["licitacao"] < by_kind["despesa"]
    # Totais financeiros de despesa presentes e positivos
    fin = data["expenses_financial_totals"]
    assert Decimal(fin["total_empenhado"]) > 0
    assert Decimal(fin["total_liquidado"]) > 0
    assert Decimal(fin["total_pago"]) > 0


def test_expenses_summary_endpoint() -> None:
    client = TestClient(app)
    res = client.get("/api/expenses/summary")
    assert res.status_code == 200
    data = res.json()
    assert "financial_totals" in data
    assert "by_municipality" in data
    assert "by_year" in data
    assert "top_favored" in data
    assert len(data["top_favored"]) <= 10
    if data["top_favored"]:
        first = data["top_favored"][0]
        assert "favored" in first
        assert "total_empenhado" in first
        assert "total_pago" in first
        assert "movements_count" in first


def test_attention_endpoint_ordering_and_limit() -> None:
    client = TestClient(app)
    res = client.get("/api/attention", params={"limit": 5})
    assert res.status_code == 200
    data = res.json()
    assert "total" in data
    assert "items" in data
    items = data["items"]
    assert len(items) <= 5
    if len(items) >= 2:
        assert items[0]["score"] >= items[1]["score"]
    for item in items:
        assert "score" in item
        assert "reasons" in item
        assert "keywords" in item
        assert item["score"] >= 1


def test_records_pagination_and_text_search() -> None:
    client = TestClient(app)
    # Default limit should be 50
    res = client.get("/api/records")
    assert res.status_code == 200
    data = res.json()
    assert "total" in data
    assert "items" in data
    assert len(data["items"]) <= 50

    # Test pagination offset
    res_page1 = client.get("/api/records", params={"limit": 2, "offset": 0})
    res_page2 = client.get("/api/records", params={"limit": 2, "offset": 2})
    assert res_page1.status_code == 200
    assert res_page2.status_code == 200
    ids_page1 = [r["id"] for r in res_page1.json()["items"]]
    ids_page2 = [r["id"] for r in res_page2.json()["items"]]
    if ids_page1 and ids_page2:
        assert set(ids_page1).isdisjoint(set(ids_page2))

    # Test text search q
    res_q = client.get("/api/records", params={"q": "saude", "limit": 10})
    assert res_q.status_code == 200
    assert "items" in res_q.json()


def test_attention_with_kind_and_q_filters() -> None:
    client = TestClient(app)
    res = client.get("/api/attention", params={"kind": "despesa", "limit": 5})
    assert res.status_code == 200
    data = res.json()
    assert all(item["kind"] == "despesa" for item in data["items"])


def test_attention_score_min_and_term_filters() -> None:
    client = TestClient(app)
    # Score min 3
    res_score = client.get("/api/attention", params={"score_min": 3, "limit": 10})
    assert res_score.status_code == 200
    data_score = res_score.json()
    assert all(item["score"] >= 3 for item in data_score["items"])

    # Term filter
    res_term = client.get("/api/attention", params={"term": "combustível", "limit": 5})
    assert res_term.status_code == 200
    data_term = res_term.json()
    if data_term["items"]:
        first = data_term["items"][0]
        assert "combustível" in first["keywords"] or any("combustível" in r.lower() for r in first["reasons"])


def test_expenses_summary_favored_search_and_limit() -> None:
    client = TestClient(app)
    res = client.get("/api/expenses/summary", params={"limit": 3})
    assert res.status_code == 200
    assert len(res.json()["top_favored"]) <= 3

    # Search with q
    res_q = client.get("/api/expenses/summary", params={"q": "LTDA", "limit": 5})
    assert res_q.status_code == 200
    assert all("LTDA" in f["favored"].upper() for f in res_q.json()["top_favored"])


def test_static_and_dashboard_pages_return_200() -> None:
    client = TestClient(app)
    assert client.get("/dashboard").status_code == 200
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/styles.css").status_code == 200


