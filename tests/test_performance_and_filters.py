"""Testes automatizados de performance, paginação e filtros estritos."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from analytics.anomalies import count_suspicious_keywords, detect_suspicious_keywords
from app.api.routes import get_db
from app.main import app
from database.models import Base, Municipality, PublicRecord


@pytest.fixture
def test_db_session(tmp_path):
    db_file = tmp_path / "perf_test.db"
    engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    mun_ceres = Municipality(name="Ceres-GO")
    mun_rialma = Municipality(name="Rialma-GO")
    session.add_all([mun_ceres, mun_rialma])
    session.flush()

    # Inserir lote de registros cobrindo diferentes tipos, anos e scores
    records = []
    # Ceres 2026: 3 despesas, 2 licitações, 1 contrato
    records.append(
        PublicRecord(
            municipality_id=mun_ceres.id,
            kind="despesa",
            year=2026,
            title="Empenho Combustível 101",
            favored="POSTO BRASIL LTDA",
            committed_value="5000.00",
            paid_value="5000.00",
            movement_number="101",
            source_url="https://ceres.test/despesa/101",
        )
    )
    records.append(
        PublicRecord(
            municipality_id=mun_ceres.id,
            kind="despesa",
            year=2026,
            title="Empenho Locação de Ambulância",
            favored="LOCADORA SAUDE LTDA",
            committed_value="12000.00",
            paid_value="12000.00",
            movement_number="102",
            source_url="https://ceres.test/despesa/102",
        )
    )
    records.append(
        PublicRecord(
            municipality_id=mun_ceres.id,
            kind="despesa",
            year=2026,
            title="Empenho Ordinário Material de Escritório",
            favored="PAPELARIA CENTRAL",
            committed_value="1500.00",
            paid_value="1500.00",
            movement_number="103",
            source_url="https://ceres.test/despesa/103",
        )
    )
    records.append(
        PublicRecord(
            municipality_id=mun_ceres.id,
            kind="licitacao",
            year=2026,
            title="Dispensa Emergencial de Medicamentos 01/2026",
            process_number="01/2026",
            modality="Dispensa de Licitação",
            value="45000.00",
            status="Homologada",
            source_url="https://ceres.test/licitacao/01",
        )
    )
    records.append(
        PublicRecord(
            municipality_id=mun_ceres.id,
            kind="licitacao",
            year=2026,
            title="Pregão Eletrônico Pavimentação 02/2026",
            process_number="02/2026",
            modality="Pregão Eletrônico",
            value="250000.00",
            status="Aberta",
            source_url="https://ceres.test/licitacao/02",
        )
    )
    records.append(
        PublicRecord(
            municipality_id=mun_ceres.id,
            kind="contrato",
            year=2026,
            title="Termo Aditivo Contratual de TI 10/2026",
            process_number="10/2026",
            favored="TECH SOLUTIONS LTDA",
            value="30000.00",
            source_url="https://ceres.test/contrato/10",
        )
    )

    # Rialma 2025: 1 despesa com combustível
    records.append(
        PublicRecord(
            municipality_id=mun_rialma.id,
            kind="despesa",
            year=2025,
            title="Empenho Aquisição de Combustível para Frotas",
            favored="POSTO CENTRAL RIALMA",
            committed_value="8000.00",
            paid_value="8000.00",
            movement_number="201",
            source_url="https://rialma.test/despesa/201",
        )
    )

    session.add_all(records)
    session.commit()

    yield session

    session.close()
    engine.dispose()


def test_attention_counts_and_queries_with_filters(test_db_session):
    # Total de atenção geral (deve capturar combustível, locação, dispensa emergencial, aditivo)
    total_att = count_suspicious_keywords(test_db_session)
    assert total_att >= 4

    # Filtro por município
    ceres_att = count_suspicious_keywords(test_db_session, municipality="Ceres-GO")
    rialma_att = count_suspicious_keywords(test_db_session, municipality="Rialma-GO")
    assert ceres_att >= 3
    assert rialma_att == 1

    # Filtro por ano
    att_2025 = count_suspicious_keywords(test_db_session, year=2025)
    assert att_2025 == 1

    # detect_suspicious_keywords com paginação e total
    total, items = detect_suspicious_keywords(test_db_session, limit=2, offset=0, with_total=True)
    assert total >= 4
    assert len(items) == 2
    # O primeiro deve ser a dispensa emergencial (score 6)
    assert items[0]["score"] >= 3
    assert "emergencial" in items[0]["keywords"] or "dispensa" in items[0]["keywords"]


def test_api_attention_endpoint_pagination_and_terms(test_db_session):
    app.dependency_overrides[get_db] = lambda: test_db_session
    client = TestClient(app)

    # Consulta padrão
    resp = client.get("/api/attention?limit=2")
    assert resp.status_code == 200
    data = resp.json()
    assert "total" in data
    assert len(data["items"]) == 2

    # Filtro por termo 'combustível'
    resp_term = client.get("/api/attention?term=combustível")
    assert resp_term.status_code == 200
    data_term = resp_term.json()
    assert data_term["total"] == 2  # 1 de Ceres, 1 de Rialma
    for item in data_term["items"]:
        assert "combustível" in item["keywords"] or "combustível" in str(item["reasons"]).lower()

    # Filtro combinado (Ceres + 2026)
    resp_comb = client.get("/api/attention?municipality=Ceres-GO&year=2026")
    assert resp_comb.status_code == 200
    for item in resp_comb.json()["items"]:
        assert item["municipality"] == "Ceres-GO"
        assert item["year"] == 2026

    app.dependency_overrides.clear()


def test_api_records_pagination_and_filters(test_db_session):
    app.dependency_overrides[get_db] = lambda: test_db_session
    client = TestClient(app)

    # Records padrão limit=2
    resp = client.get("/api/records?limit=2&offset=0")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 7
    assert len(data["items"]) == 2

    # Filtro por tipo=despesa
    resp_desp = client.get("/api/records?kind=despesa")
    assert resp_desp.status_code == 200
    assert resp_desp.json()["total"] == 4

    # Filtro por tipo=licitacao
    resp_lic = client.get("/api/records?kind=licitacao")
    assert resp_lic.status_code == 200
    assert resp_lic.json()["total"] == 2

    # Filtro por busca textual 'Ambulância'
    resp_q = client.get("/api/records?q=Ambulância")
    assert resp_q.status_code == 200
    assert resp_q.json()["total"] == 1
    assert "Ambulância" in resp_q.json()["items"][0]["title"]

    app.dependency_overrides.clear()


def test_api_summary_separates_kinds_correctly(test_db_session):
    app.dependency_overrides[get_db] = lambda: test_db_session
    client = TestClient(app)

    resp = client.get("/api/summary")
    assert resp.status_code == 200
    data = resp.json()
    by_kind = data["totals_by_kind"]
    assert by_kind["despesa"] == 4
    assert by_kind["licitacao"] == 2
    assert by_kind["contrato"] == 1

    # Despesas totais financeiras (Decimal formatado como string)
    fin = data["expenses_financial_totals"]
    assert fin["total_empenhado"] == "26500.00"  # 5000 + 12000 + 1500 + 8000
    assert fin["total_pago"] == "26500.00"

    app.dependency_overrides.clear()


def test_api_summary_with_kind_filters(test_db_session):
    app.dependency_overrides[get_db] = lambda: test_db_session
    client = TestClient(app)

    # 1. Ceres-GO 2025 com kind=licitacao (não há licitação em 2025 no mock, só despesa em Rialma e nada em Ceres 2025)
    resp = client.get("/api/summary?municipality=Ceres-GO&year=2025&kind=licitacao")
    assert resp.status_code == 200
    data = resp.json()
    assert data["totals_by_kind"] == {"licitacao": 0}
    assert "despesa" not in data["totals_by_kind"]
    assert data["expenses_financial_totals"]["total_empenhado"] == "0.00"
    assert data["expenses_financial_totals"]["total_pago"] == "0.00"

    # 2. kind=despesa retorna totais financeiros
    resp_desp = client.get("/api/summary?kind=despesa")
    assert resp_desp.status_code == 200
    data_desp = resp_desp.json()
    assert data_desp["totals_by_kind"] == {"despesa": 4}
    assert data_desp["expenses_financial_totals"]["total_empenhado"] == "26500.00"

    # 3. kind=contrato não retorna despesas nem totais financeiros de despesas
    resp_cont = client.get("/api/summary?kind=contrato")
    assert resp_cont.status_code == 200
    data_cont = resp_cont.json()
    assert data_cont["totals_by_kind"] == {"contrato": 1}
    assert "despesa" not in data_cont["totals_by_kind"]
    assert data_cont["expenses_financial_totals"]["total_empenhado"] == "0.00"

    # 4. /api/expenses/summary com kind=licitacao retorna vazio
    resp_exp_lic = client.get("/api/expenses/summary?kind=licitacao")
    assert resp_exp_lic.status_code == 200
    data_exp_lic = resp_exp_lic.json()
    assert data_exp_lic["top_favored"] == []
    assert data_exp_lic["financial_totals"]["total_empenhado"] == "0.00"

    app.dependency_overrides.clear()


def test_html_dash_kind_select_values():
    from pathlib import Path

    html_path = Path(__file__).resolve().parents[1] / "app" / "static" / "index.html"
    content = html_path.read_text(encoding="utf-8")
    assert '<option value="despesa">Despesas</option>' in content
    assert '<option value="licitacao">Licitações</option>' in content
    assert '<option value="contrato">Contratos</option>' in content

