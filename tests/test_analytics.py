from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from analytics.anomalies import detect_duplicate_titles, detect_suspicious_keywords
from analytics.reports import records_by_status, records_missing_value
from database.models import Base, Municipality, PublicRecord


def _session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'analytics.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    session = factory()
    municipality = Municipality(name="Ceres-GO")
    session.add(municipality)
    session.flush()
    session.add_all(
        [
            PublicRecord(
                municipality_id=municipality.id,
                kind="licitacao",
                source_url="https://example.test/a",
                title="Contratação emergencial de transporte",
                detail_url="https://example.test/a/1",
                value=None,
                status=None,
            ),
            PublicRecord(
                municipality_id=municipality.id,
                kind="licitacao",
                source_url="https://example.test/a",
                title="Contratação emergencial de transporte",
                detail_url="https://example.test/a/2",
                value="1000",
                status="Aberta",
            ),
        ]
    )
    session.commit()
    return engine, session


def test_detects_duplicate_titles_and_keywords(tmp_path) -> None:
    engine, session = _session(tmp_path)
    try:
        duplicates = detect_duplicate_titles(session)
        findings = detect_suspicious_keywords(session)
        assert duplicates[0]["count"] == 2
        assert "emergencial" in findings[0]["keywords"]
        assert "transporte" not in findings[0]["keywords"]
        assert findings[0]["score"] >= 3
    finally:
        session.close()
        engine.dispose()


def test_reports_handle_null_value_and_status(tmp_path) -> None:
    engine, session = _session(tmp_path)
    try:
        assert len(records_missing_value(session)) == 1
        assert records_by_status(session) == {"Aberta": 1, "Sem status": 1}
    finally:
        session.close()
        engine.dispose()


def test_missing_value_considers_expense_financial_fields(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'mv.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    session = factory()
    mun = Municipality(name="Ceres-GO")
    session.add(mun)
    session.flush()

    session.add_all([
        # Despesa com valor empenhado -> NÃO deve ser missing value
        PublicRecord(
            municipality_id=mun.id,
            kind="despesa",
            source_url="https://example.test/d1",
            title="Despesa com empenho",
            committed_value="500.00",
            liquidated_value="0.00",
            paid_value="0.00",
        ),
        # Despesa sem nenhum valor -> DEVE ser missing value
        PublicRecord(
            municipality_id=mun.id,
            kind="despesa",
            source_url="https://example.test/d2",
            title="Despesa vazia",
            committed_value="0,00",
            liquidated_value=None,
            paid_value="",
        ),
        # Licitação sem valor -> DEVE ser missing value
        PublicRecord(
            municipality_id=mun.id,
            kind="licitacao",
            source_url="https://example.test/l1",
            title="Licitação sem valor",
            value=None,
        ),
        # Licitação com valor -> NÃO deve ser missing value
        PublicRecord(
            municipality_id=mun.id,
            kind="licitacao",
            source_url="https://example.test/l2",
            title="Licitação com valor",
            value="1500.00",
        ),
    ])
    session.commit()

    try:
        missing = records_missing_value(session)
        assert len(missing) == 2
        titles = {m["title"] for m in missing}
        assert "Despesa vazia" in titles
        assert "Licitação sem valor" in titles
        assert "Despesa com empenho" not in titles
        assert "Licitação com valor" not in titles
    finally:
        session.close()
        engine.dispose()


def test_attention_removes_generic_words_and_orders_by_score(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'att.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    session = factory()
    mun = Municipality(name="Ceres-GO")
    session.add(mun)
    session.flush()

    session.add_all([
        # Contrato genérico sem termos específicos -> score 0, não entra
        PublicRecord(
            municipality_id=mun.id,
            kind="contrato",
            source_url="https://example.test/c1",
            title="Aquisição de material de consumo e prestação de serviço",
        ),
        # Termo de peso 1 (combustível)
        PublicRecord(
            municipality_id=mun.id,
            kind="despesa",
            source_url="https://example.test/d1",
            title="Abastecimento de combustível para veículos",
        ),
        # Termos combinados: emergencial (+3) + dispensa (+3) = 6
        PublicRecord(
            municipality_id=mun.id,
            kind="licitacao",
            source_url="https://example.test/l1",
            title="Dispensa emergencial de medicamentos",
        ),
        # Termo de peso 2 (aditivo)
        PublicRecord(
            municipality_id=mun.id,
            kind="contrato",
            source_url="https://example.test/c2",
            title="Termo aditivo de vigência contratual",
        ),
    ])
    session.commit()

    try:
        # Palavras genéricas não devem ser capturadas
        items = detect_suspicious_keywords(session, limit=20)
        assert len(items) == 3
        # O primeiro item deve ter o maior score (Dispensa emergencial: score 6)
        assert items[0]["score"] == 6
        assert items[0]["title"] == "Dispensa emergencial de medicamentos"
        assert "emergencial" in items[0]["keywords"]
        assert "dispensa" in items[0]["keywords"]
        assert len(items[0]["reasons"]) == 2

        # Segundo item: score 2 (aditivo)
        assert items[1]["score"] == 2
        assert items[1]["title"] == "Termo aditivo de vigência contratual"

        # Terceiro item: score 1 (combustível)
        assert items[2]["score"] == 1

        # Teste de limite
        limited = detect_suspicious_keywords(session, limit=2)
        assert len(limited) == 2

        # Teste com with_total=True e filtros
        total, paged = detect_suspicious_keywords(session, limit=2, with_total=True)
        assert total == 3
        assert len(paged) == 2

        # Teste com filtro por tipo (kind)
        total_desp, paged_desp = detect_suspicious_keywords(session, kind="despesa", with_total=True)
        assert total_desp == 1
        assert paged_desp[0]["title"] == "Abastecimento de combustível para veículos"

        # Teste com busca textual (q)
        total_med, paged_med = detect_suspicious_keywords(session, q="medicamentos", with_total=True)
        assert total_med == 1
        assert "medicamentos" in paged_med[0]["title"]
    finally:
        session.close()
        engine.dispose()


def test_detect_suspicious_keywords_in_description_only(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'desc.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    session = factory()
    mun = Municipality(name="Ceres-GO")
    session.add(mun)
    session.flush()

    session.add(
        PublicRecord(
            municipality_id=mun.id,
            kind="despesa",
            source_url="https://example.test/d1",
            title="Empenho Ordinário 1234",
            description="Valor que se empenha referente a locação de veículos utilitários para transporte",
            committed_value="12000.00",
        )
    )
    session.commit()
    try:
        items = detect_suspicious_keywords(session)
        assert len(items) == 1
        assert "locação" in items[0]["keywords"]
        assert items[0]["score"] >= 1
    finally:
        session.close()
        engine.dispose()

