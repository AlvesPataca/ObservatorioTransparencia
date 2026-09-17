from decimal import Decimal
import json
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from analytics.anomaly_engine import (
    AnomalyEngine,
    accounting_group_key,
    calculate_percentiles,
    extract_movement_accounting_values,
    is_internal_or_public_entity,
)
from analytics.document_normalizer import (
    clean_digits,
    extract_document_and_name,
    normalize_supplier_name,
    validate_cnpj,
    validate_cpf,
)
from app.main import app
from database.models import AnomalyFinding, Base, Municipality, PublicRecord, SupplierProfile
from external.cnpj_registry import query_cnpj_data
from external.pncp import query_supplier_contracts_pncp
from external.portal_transparencia import check_sanctions_ceis_cnep


# -------------------------------------------------------------
# 1. TESTES DE NORMALIZAÇÃO DE DOCUMENTOS (CPF / CNPJ)
# -------------------------------------------------------------

def test_document_normalizer_clean_digits() -> None:
    assert clean_digits("00.123.456/0001-78") == "00123456000178"
    assert clean_digits("123.456.789-00") == "12345678900"
    assert clean_digits(None) == ""
    assert clean_digits("  abc  ") == ""


def test_cpf_validation() -> None:
    # CPF de teste com dígitos verificadores matematicamente válidos
    assert validate_cpf("52998224725") is True
    # Dígitos iguais consecutivos (inválidos pela regra da Receita)
    assert validate_cpf("11111111111") is False
    assert validate_cpf("00000000000") is False
    # Tamanho incorreto ou dígitos errados
    assert validate_cpf("1234567890") is False
    assert validate_cpf("52998224726") is False


def test_cnpj_validation() -> None:
    # CNPJ de teste com dígitos verificadores válidos
    assert validate_cnpj("11222333000181") is True
    # Dígitos iguais
    assert validate_cnpj("00000000000000") is False
    # Tamanho incorreto (ex: 8 dígitos não devem ser aceitos como CNPJ)
    assert validate_cnpj("63162977") is False
    assert validate_cnpj("11222333000199") is False


def test_extract_document_and_name() -> None:
    # String com 8 dígitos prefixados (ex: código interno do portal), não deve virar CNPJ
    res1 = extract_document_and_name("63.162.977 PAULO JOAQUIM DA SILVA JUNIOR")
    assert res1["document"] is None
    assert res1["document_type"] is None
    assert "PAULO JOAQUIM DA SILVA JUNIOR" in res1["normalized_name"]

    # String com CNPJ de 14 dígitos
    res2 = extract_document_and_name("11.222.333/0001-81 - EMPRESA ALFA SERVICOS LTDA")
    assert res2["document"] == "11.222.333/0001-81"
    assert res2["document_type"] == "CNPJ"
    assert res2["normalized_name"] == "EMPRESA ALFA SERVICOS LTDA"

    # String com CPF de 11 dígitos
    res3 = extract_document_and_name("529.982.247-25 JOAO DA SILVA")
    assert res3["document"] == "529.982.247-25"
    assert res3["document_type"] == "CPF"
    assert res3["normalized_name"] == "JOAO DA SILVA"


# -------------------------------------------------------------
# 2. TESTES DE ADAPTERS EXTERNOS (RESILIÊNCIA E FALLBACK)
# -------------------------------------------------------------

def test_portal_transparencia_graceful_without_key() -> None:
    # Não deve lançar exceção mesmo sem API key
    res = check_sanctions_ceis_cnep("11222333000181", api_key="")
    assert isinstance(res, dict)
    assert res.get("checked") is False
    assert "source" in res


def test_pncp_client_graceful() -> None:
    # CNPJ dummy inválido deve retornar dicionário estruturado sem exceção
    res = query_supplier_contracts_pncp("00000000000000")
    assert isinstance(res, dict)
    assert res.get("checked") is False
    assert "source" in res


def test_cnpj_registry_client_graceful() -> None:
    # CNPJ dummy inválido não deve quebrar e deve retornar dicionário estruturado
    res = query_cnpj_data("00000000000000")
    assert isinstance(res, dict)
    assert res.get("checked") is False


# -------------------------------------------------------------
# 3. TESTES DO MOTOR DE ANOMALIAS (ANOMALY ENGINE)
# -------------------------------------------------------------

@pytest.fixture
def memory_db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test_anomaly.db'}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()

    mun1 = Municipality(name="Ceres-GO")
    mun2 = Municipality(name="Rialma-GO")
    session.add_all([mun1, mun2])
    session.flush()

    yield session, mun1, mun2

    session.close()
    engine.dispose()


def make_record(**kwargs) -> PublicRecord:
    defaults = {
        "kind": "despesa",
        "title": "Despesa Pública",
        "source_url": "https://example.com/despesa",
    }
    defaults.update(kwargs)
    return PublicRecord(**defaults)


def test_value_outlier_detection(memory_db) -> None:
    session, mun1, _ = memory_db

    # Cria lote de despesas comuns e um outlier estatístico extremo (n >= 100)
    records = []
    for i in range(120):
        records.append(
            make_record(
                municipality_id=mun1.id,
                year=2026,
                favored=f"FORNECEDOR COMUM {i}",
                committed_value=Decimal("100.00"),
                liquidated_value=Decimal("100.00"),
                paid_value=Decimal("100.00"),
                movement_date="2026-02-10",
                description="Serviços ordinários de rotina",
            )
        )

    # Registro outlier: R$ 500.000,00 quando a mediana é R$ 100,00
    outlier_rec = make_record(
        municipality_id=mun1.id,
        year=2026,
        source_url="https://example.com/despesa/outlier",
        favored="FORNECEDOR ESPECIAL",
        committed_value=Decimal("500000.00"),
        liquidated_value=Decimal("500000.00"),
        paid_value=Decimal("500000.00"),
        movement_date="2026-02-15",
        description="Locação de máquinas pesadas",
    )
    records.append(outlier_rec)

    session.add_all(records)
    session.commit()

    engine = AnomalyEngine(session)
    count = engine.analyze_all(municipalities=["Ceres-GO"], years=[2026])
    assert count > 0

    findings = session.query(AnomalyFinding).filter_by(category="value_outlier").all()
    assert len(findings) >= 1
    target_finding = [f for f in findings if f.record_id == outlier_rec.id]
    assert len(target_finding) == 1
    assert target_finding[0].severity == "alta"
    assert "outlier estatístico" in target_finding[0].title.lower()
    assert target_finding[0].score >= 7


def test_supplier_concentration_detection(memory_db) -> None:
    session, mun1, _ = memory_db

    # Fornecedor concentra a maior fatia do orçamento
    records = []
    # Total de 10 fornecedores com R$ 10.000 cada = R$ 100.000
    for i in range(10):
        records.append(
            make_record(
                municipality_id=mun1.id,
                year=2025,
                favored=f"FORNECEDOR PEQUENO {i}",
                paid_value=Decimal("10000.00"),
                committed_value=Decimal("10000.00"),
                movement_date="2025-05-10",
            )
        )

    # Fornecedor dominante com R$ 400.000 (80% do total de 500k)
    records.append(
        make_record(
            municipality_id=mun1.id,
            year=2025,
            source_url="https://example.com/despesa/dominante",
            favored="FORNECEDOR DOMINANTE LTDA",
            paid_value=Decimal("400000.00"),
            committed_value=Decimal("400000.00"),
            movement_date="2025-05-12",
        )
    )

    session.add_all(records)
    session.commit()

    engine = AnomalyEngine(session)
    engine.analyze_all(municipalities=["Ceres-GO"], years=[2025])

    findings = session.query(AnomalyFinding).filter_by(category="supplier_concentration").all()
    assert len(findings) >= 1
    dom_finding = findings[0]
    assert dom_finding.severity == "alta"
    assert "concentração" in dom_finding.title.lower()
    assert dom_finding.score >= 8


def test_payment_flow_inconsistency_detection(memory_db) -> None:
    session, mun1, _ = memory_db

    # Pago maior que empenhado: divergência contábil
    inconsistent_rec = make_record(
        municipality_id=mun1.id,
        year=2026,
        source_url="https://example.com/despesa/divergente",
        favored="FORNECEDOR DIVERGENTE",
        committed_value=Decimal("500.00"),
        liquidated_value=Decimal("500.00"),
        paid_value=Decimal("1200.00"),
        movement_date="2026-03-01",
        description="Pagamento de serviços",
    )
    session.add(inconsistent_rec)
    session.commit()

    engine = AnomalyEngine(session)
    engine.analyze_all(municipalities=["Ceres-GO"], years=[2026])

    findings = session.query(AnomalyFinding).filter_by(category="payment_flow_inconsistency").all()
    assert len(findings) >= 1
    assert any(f.record_id == inconsistent_rec.id for f in findings)


def test_accounting_group_key_rules() -> None:
    # Ceres com chave contábil interna comprovada
    rec1 = make_record(raw_json='{"chave_empenho": "[3510-20250126]", "empenho": "3510"}')
    key1, secure1 = accounting_group_key(rec1)
    assert key1 == "chave:3510-20250126"
    assert secure1 is True

    # Ceres com prefixo comprovado com ponto
    rec2 = make_record(movement_number="3510.8.1", year=2026)
    key2, secure2 = accounting_group_key(rec2)
    assert key2 == "empenho:3510_2026"
    assert secure2 is True

    # Sub-movimento isolado como 8 ou 8.1 sem chave comprovada: não inventar relação
    rec3 = make_record(movement_number="8.1", movement_type="Pagamento")
    key3, secure3 = accounting_group_key(rec3)
    assert secure3 is False
    assert "unverified_submov" in key3


def test_payment_flow_empenho_3510_multi_movement_case(memory_db) -> None:
    """Caso artificial solicitado:
    empenho 3510: 7839
    liquidação 8: 1213
    pagamento 8.1: 1213
    A regra NÃO deve marcar como pago > empenhado.
    """
    import json
    session, mun1, _ = memory_db

    rec_emp = make_record(
        municipality_id=mun1.id,
        year=2026,
        favored="TOP PRINT IMPRESSORAS LTDA",
        movement_type="Empenho",
        movement_number="3510",
        committed_value=Decimal("7839.00"),
        liquidated_value=Decimal("0.00"),
        paid_value=Decimal("0.00"),
        movement_date="2026-01-02",
        raw_json=json.dumps({"empenho": "3510", "valor_empenho": "7.839,00", "valor_mov": "7.839,00", "movimento": "Empenho"}),
    )
    rec_liq = make_record(
        municipality_id=mun1.id,
        year=2026,
        favored="TOP PRINT IMPRESSORAS LTDA",
        movement_type="Liquidação",
        movement_number="8",
        committed_value=Decimal("7839.00"),
        liquidated_value=Decimal("1213.00"),
        paid_value=Decimal("0.00"),
        movement_date="2026-01-05",
        raw_json=json.dumps({"empenho": "3510", "numero": "3510.8", "valor_empenho": "7.839,00", "valor_mov": "1.213,00", "movimento": "Liquidação"}),
    )
    rec_pag = make_record(
        municipality_id=mun1.id,
        year=2026,
        favored="TOP PRINT IMPRESSORAS LTDA",
        movement_type="Pagamento",
        movement_number="8.1",
        committed_value=Decimal("7839.00"),
        liquidated_value=Decimal("0.00"),
        paid_value=Decimal("1213.00"),
        movement_date="2026-01-06",
        raw_json=json.dumps({"empenho": "3510", "numero": "3510.8.1", "valor_empenho": "7.839,00", "valor_mov": "1.213,00", "movimento": "Pagamento"}),
    )
    session.add_all([rec_emp, rec_liq, rec_pag])
    session.commit()

    engine = AnomalyEngine(session)
    engine.analyze_all(municipalities=["Ceres-GO"], years=[2026])

    # A regra NÃO deve marcar como pago > empenhado
    findings = session.query(AnomalyFinding).filter_by(category="payment_flow_inconsistency").all()
    inconsistent_ids = [f.record_id for f in findings]
    assert rec_emp.id not in inconsistent_ids
    assert rec_liq.id not in inconsistent_ids
    assert rec_pag.id not in inconsistent_ids
    assert not any("pago superior ao valor empenhado" in f.title.lower() for f in findings)



def test_recurring_payments_detection(memory_db) -> None:
    session, mun1, _ = memory_db

    # Múltiplos pagamentos de valor idêntico e redondo para o mesmo credor (5x de 10.000,00)
    records = []
    for day in [5, 10, 15, 20, 25]:
        records.append(
            make_record(
                municipality_id=mun1.id,
                year=2026,
                favored="CONSULTORIA REPETIDA",
                committed_value=Decimal("10000.00"),
                liquidated_value=Decimal("10000.00"),
                paid_value=Decimal("10000.00"),
                movement_date=f"2026-01-{day:02d}",
                description="Consultoria técnica especializada",
            )
        )
    session.add_all(records)
    session.commit()

    engine = AnomalyEngine(session)
    engine.analyze_all(municipalities=["Ceres-GO"], years=[2026])

    findings = session.query(AnomalyFinding).filter_by(category="recurring_payments").all()
    assert len(findings) >= 1


def test_no_accusatory_terms_in_findings(memory_db) -> None:
    """Garante cumprimento estrito da regra de linguagem técnica e neutra (sem 'fraude', 'crime', 'desvio', etc)."""
    session, mun1, _ = memory_db

    forbidden_terms = ["fraude", "crime", "criminoso", "desvio", "corrupção", "ilegal", "roubo", "ladrao", "culpado"]

    rec = make_record(
        municipality_id=mun1.id,
        year=2026,
        favored="FORNECEDOR AUDITADO",
        committed_value=Decimal("100.00"),
        liquidated_value=Decimal("200.00"),
        paid_value=Decimal("300.00"),
        movement_date="2026-03-01",
        description="Serviços",
    )
    session.add(rec)
    session.commit()

    engine = AnomalyEngine(session)
    engine.analyze_all(municipalities=["Ceres-GO"], years=[2026])

    findings = session.query(AnomalyFinding).all()
    for f in findings:
        text_corpus = f"{f.title} {f.explanation} {f.category}".lower()
        for term in forbidden_terms:
            assert term not in text_corpus, f"Termo proibido '{term}' detectado no achado {f.id}: {text_corpus}"


# -------------------------------------------------------------
# 4. TESTES DA API HTTP /api/anomalies
# -------------------------------------------------------------

def test_api_anomalies_endpoint_returns_expected_structure() -> None:
    client = TestClient(app)
    response = client.get("/api/anomalies")
    assert response.status_code == 200
    data = response.json()
    assert "total" in data
    assert "items" in data
    assert "categories_summary" in data
    assert "severities_summary" in data
    assert isinstance(data["items"], list)


def test_api_anomalies_filtering() -> None:
    client = TestClient(app)
    # Filtro por severidade alta
    resp_alta = client.get("/api/anomalies", params={"severity": "alta", "limit": 5})
    assert resp_alta.status_code == 200
    for item in resp_alta.json()["items"]:
        assert item["severity"] == "alta"

    # Filtro por categoria
    resp_cat = client.get("/api/anomalies", params={"category": "value_outlier", "limit": 5})
    assert resp_cat.status_code == 200
    for item in resp_cat.json()["items"]:
        assert item["category"] == "value_outlier"

    # Paginação
    resp_page = client.get("/api/anomalies", params={"limit": 3, "offset": 0})
    assert resp_page.status_code == 200
    assert len(resp_page.json()["items"]) <= 3


# -------------------------------------------------------------
# 5. TESTES ESPECÍFICOS DE REFINAMENTO GLOBAL
# -------------------------------------------------------------

def test_is_internal_or_public_entity_rules() -> None:
    # Municípios e Prefeituras
    assert is_internal_or_public_entity("MUNICIPIO DE RIALMA", "Rialma-GO") is True
    assert is_internal_or_public_entity("MUNICIPIO DE CERES", "Ceres-GO") is True
    assert is_internal_or_public_entity("PREFEITURA MUNICIPAL DE RIALMA") is True
    assert is_internal_or_public_entity("PREFEITURA MUNICIPAL DE CERES") is True

    # Fundos, Câmaras e Previdência
    assert is_internal_or_public_entity("FUNDO MUNICIPAL DE SAUDE DE CERES") is True
    assert is_internal_or_public_entity("CAMARA MUNICIPAL DE RIALMA") is True
    assert is_internal_or_public_entity("INSTITUTO DE PREVIDENCIA DOS SERVIDORES") is True
    assert is_internal_or_public_entity("RPPS CERES") is True
    assert is_internal_or_public_entity("INSS - RECEITA FEDERAL") is True

    # Fornecedores privados (não devem ser filtrados)
    assert is_internal_or_public_entity("TOP PRINT IMPRESSORAS LTDA") is False
    assert is_internal_or_public_entity("CONSTRUTORA ALFA LTDA") is False
    assert is_internal_or_public_entity("PAULO JOAQUIM DA SILVA JUNIOR") is False
    assert is_internal_or_public_entity(None) is False


def test_supplier_concentration_excludes_municipality_self_payment(memory_db) -> None:
    """Garante que pagamentos para MUNICIPIO DE RIALMA ou MUNICIPIO DE CERES não geram finding."""
    session, mun1, mun2 = memory_db

    records = []
    # Cria despesas onde o próprio município é favorecido com valor maciço (ex: R$ 500.000)
    records.append(
        make_record(
            municipality_id=mun2.id,
            year=2026,
            favored="MUNICIPIO DE RIALMA",
            paid_value=Decimal("500000.00"),
            committed_value=Decimal("500000.00"),
            movement_date="2026-02-10",
        )
    )
    records.append(
        make_record(
            municipality_id=mun2.id,
            year=2026,
            favored="PREFEITURA MUNICIPAL DE RIALMA",
            paid_value=Decimal("200000.00"),
            committed_value=Decimal("200000.00"),
            movement_date="2026-02-12",
        )
    )
    # Pequenos fornecedores privados
    for i in range(10):
        records.append(
            make_record(
                municipality_id=mun2.id,
                year=2026,
                favored=f"PEQUENO FORNECEDOR {i}",
                paid_value=Decimal("20000.00"),
                committed_value=Decimal("20000.00"),
                movement_date="2026-02-15",
            )
        )

    session.add_all(records)
    session.commit()

    engine = AnomalyEngine(session)
    engine.analyze_all(municipalities=["Rialma-GO"], years=[2026])

    findings = session.query(AnomalyFinding).filter_by(category="supplier_concentration").all()
    # Não deve ter gerado concentração para MUNICIPIO DE RIALMA nem PREFEITURA
    for f in findings:
        assert "MUNICIPIO DE RIALMA" not in f.explanation
        assert "PREFEITURA MUNICIPAL DE RIALMA" not in f.explanation


def test_supplier_concentration_detects_concentrated_private_supplier(memory_db) -> None:
    """Garante que fornecedor privado expressivo continua sendo detectado com evidence_json auditável."""
    session, mun1, _ = memory_db

    records = []
    for i in range(10):
        records.append(
            make_record(
                municipality_id=mun1.id,
                year=2026,
                favored=f"FORNECEDOR DIVERSO {i}",
                paid_value=Decimal("10000.00"),
                committed_value=Decimal("10000.00"),
                movement_date="2026-03-10",
            )
        )
    # Fornecedor privado concentrado (R$ 300.000)
    records.append(
        make_record(
            municipality_id=mun1.id,
            year=2026,
            favored="EMPRESA CONCENTRADA ENGENHARIA LTDA",
            paid_value=Decimal("300000.00"),
            committed_value=Decimal("300000.00"),
            movement_date="2026-03-12",
        )
    )

    session.add_all(records)
    session.commit()

    engine = AnomalyEngine(session)
    engine.analyze_all(municipalities=["Ceres-GO"], years=[2026])

    findings = session.query(AnomalyFinding).filter_by(category="supplier_concentration").all()
    priv_findings = [f for f in findings if "EMPRESA CONCENTRADA ENGENHARIA" in f.explanation]
    assert len(priv_findings) == 1
    ev = json.loads(priv_findings[0].evidence_json)
    assert ev["rank"] == 1
    assert ev["percentage"] > 70.0
    assert ev["is_external"] is True


def test_value_outlier_ignores_moderate_values_below_50k(memory_db) -> None:
    """Garante que valor moderado (ex: R$ 11.545,26) NÃO vira outlier, mesmo passando de IQR baixo."""
    session, _, mun2 = memory_db

    # Cria lote de 120 despesas com valores baixos (R$ 50 a R$ 200)
    records = []
    for i in range(120):
        records.append(
            make_record(
                municipality_id=mun2.id,
                year=2026,
                favored=f"FORNECEDOR PADRAO {i}",
                paid_value=Decimal("100.00"),
                committed_value=Decimal("100.00"),
                movement_date="2026-01-10",
            )
        )
    # Valor moderado de R$ 11.545,26 (que anteriormente causava ruído em Rialma 2026)
    moderate_rec = make_record(
        municipality_id=mun2.id,
        year=2026,
        favored="FORNECEDOR MODERADO LTDA",
        paid_value=Decimal("11545.26"),
        committed_value=Decimal("11545.26"),
        movement_date="2026-01-15",
    )
    records.append(moderate_rec)
    session.add_all(records)
    session.commit()

    engine = AnomalyEngine(session)
    engine.analyze_all(municipalities=["Rialma-GO"], years=[2026])

    findings = session.query(AnomalyFinding).filter_by(category="value_outlier").all()
    # O valor de R$ 11.545,26 não deve ser marcado como outlier porque está abaixo do piso de R$ 50.000,00
    assert not any(f.record_id == moderate_rec.id for f in findings)


def test_value_outlier_detects_extreme_values_above_p99_and_50k(memory_db) -> None:
    """Garante que valor extremo (>= P99 e >= R$ 50.000,00) continua sendo detectado."""
    session, _, mun2 = memory_db

    records = []
    for i in range(120):
        records.append(
            make_record(
                municipality_id=mun2.id,
                year=2026,
                favored=f"FORNECEDOR ROTINA {i}",
                paid_value=Decimal("200.00"),
                committed_value=Decimal("200.00"),
                movement_date="2026-01-10",
            )
        )
    # Valor genuinamente atípico e relevante: R$ 180.000,00
    extreme_rec = make_record(
        municipality_id=mun2.id,
        year=2026,
        favored="GRANDE CONSTRUTORA EIRELI",
        paid_value=Decimal("180000.00"),
        committed_value=Decimal("180000.00"),
        movement_date="2026-01-20",
    )
    records.append(extreme_rec)
    session.add_all(records)
    session.commit()

    engine = AnomalyEngine(session)
    engine.analyze_all(municipalities=["Rialma-GO"], years=[2026])

    findings = session.query(AnomalyFinding).filter_by(category="value_outlier").all()
    extreme_findings = [f for f in findings if f.record_id == extreme_rec.id]
    assert len(extreme_findings) == 1
    ev = json.loads(extreme_findings[0].evidence_json)
    assert ev["value"] == 180000.0
    assert ev["sample_size"] >= 100
    assert ev["percentile_rank"] >= 99.0


def test_payment_flow_does_not_trigger_for_negligible_differences(memory_db) -> None:
    """Diferença residual de até R$ 5,00 (explicável por arredondamento) não deve gerar finding."""
    session, mun1, _ = memory_db

    rec = make_record(
        municipality_id=mun1.id,
        year=2026,
        favored="FORNECEDOR CENTAVOS LTDA",
        committed_value=Decimal("1000.00"),
        liquidated_value=Decimal("1000.00"),
        paid_value=Decimal("1002.50"),  # Diferença de R$ 2,50
        movement_date="2026-03-01",
    )
    session.add(rec)
    session.commit()

    engine = AnomalyEngine(session)
    engine.analyze_all(municipalities=["Ceres-GO"], years=[2026])

    findings = session.query(AnomalyFinding).filter_by(category="payment_flow_inconsistency").all()
    assert not any(f.record_id == rec.id for f in findings)

