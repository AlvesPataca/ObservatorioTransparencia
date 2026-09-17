import json

from sqlalchemy import func, select

from database.models import Municipality, PublicRecord
from scripts.import_json_to_db import import_json, make_session_factory


def _write_payload(path) -> None:
    payload = [
        {
            "municipality": "Ceres-GO",
            "source_checks": [
                {
                    "municipality": "Ceres-GO",
                    "label": "Portal - licitacoes",
                    "url": "https://example.test/licitacoes",
                    "status_code": 403,
                    "accessible": False,
                    "blocked": True,
                }
            ],
            "records": [
                {
                    "municipality": "Ceres-GO",
                    "kind": "licitacao",
                    "source_url": "https://example.test/licitacoes",
                    "title": "Compra de materiais",
                    "detail_url": "https://example.test/licitacoes",
                    "process_number": "001/2026",
                    "status": "Aberta",
                },
                {
                    "municipality": "Ceres-GO",
                    "kind": "licitacao",
                    "source_url": "https://example.test/licitacoes",
                    "title": "Compra de equipamentos",
                    "detail_url": "https://example.test/licitacoes",
                    "process_number": "002/2026",
                    "status": "Aberta",
                },
            ],
        },
        {"municipality": "Rialma-GO", "source_checks": [], "records": []},
    ]
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_import_is_idempotent_and_uses_temporary_sqlite(tmp_path) -> None:
    json_path = tmp_path / "records.json"
    database_path = tmp_path / "observatorio.db"
    _write_payload(json_path)
    database_url = f"sqlite:///{database_path}"

    first = import_json(json_path, database_url)
    second = import_json(json_path, database_url)

    assert first == (2, 1, 2)
    assert second == (0, 0, 0)


def test_import_counts_records_by_municipality(tmp_path) -> None:
    json_path = tmp_path / "records.json"
    database_path = tmp_path / "observatorio.db"
    _write_payload(json_path)
    database_url = f"sqlite:///{database_path}"
    import_json(json_path, database_url)

    engine, session_factory = make_session_factory(database_url)
    try:
        with session_factory() as session:
            counts = dict(
                session.execute(
                    select(Municipality.name, func.count(PublicRecord.id))
                    .join(PublicRecord, PublicRecord.municipality_id == Municipality.id, isouter=True)
                    .group_by(Municipality.name)
                ).all()
            )
    finally:
        engine.dispose()

    assert counts == {"Ceres-GO": 2, "Rialma-GO": 0}


def test_imports_ceres_and_rialma_expense_files_idempotently(tmp_path) -> None:
    payloads = [
        {
            "municipality": "Ceres-GO",
            "kind": "despesa",
            "source_url": "https://ceres.test/despesas",
            "records": [{
                "municipality": "Ceres-GO", "kind": "despesa", "source_url": "https://ceres.test/despesas",
                "detail_url": "https://ceres.test/despesas", "title": "Despesa Ceres", "movement_type": "Empenho",
                "movement_number": "1", "favored": "Fornecedor Ceres", "description": "Material",
            }],
        },
        {
            "municipality": "Rialma-GO",
            "kind": "despesa",
            "source_url": "https://rialma.test/despesas",
            "records": [{
                "municipality": "Rialma-GO", "kind": "despesa", "source_url": "https://rialma.test/despesas",
                "detail_url": "https://rialma.test/despesas", "title": "Despesa Rialma", "movement_type": "Pagamento",
                "movement_number": "1", "favored": "Fornecedor Rialma", "description": "Serviço",
            }],
        },
    ]
    import json
    json_path = tmp_path / "expenses.json"

    json_path.write_text(json.dumps(payloads), encoding="utf-8")
    database_url = f"sqlite:///{tmp_path / 'expenses.db'}"
    assert import_json(json_path, database_url)[2] == 2
    assert import_json(json_path, database_url)[2] == 0



def test_import_stores_year_and_separates_by_year(tmp_path) -> None:
    history_2025 = {
        "municipality": "Ceres-GO",
        "kind": "despesa",
        "year": 2025,
        "source_url": "https://ceres.test/despesas",
        "records": [
            {
                "municipality": "Ceres-GO",
                "kind": "despesa",
                "year": 2025,
                "source_url": "https://ceres.test/despesas",
                "movement_type": "Empenho",
                "movement_number": "100",
                "title": "Material 2025",
                "favored": "Fornecedor A",
            }
        ],
    }
    history_2026 = {
        "municipality": "Ceres-GO",
        "kind": "despesa",
        "year": 2026,
        "source_url": "https://ceres.test/despesas",
        "records": [
            {
                "municipality": "Ceres-GO",
                "kind": "despesa",
                "year": 2026,
                "source_url": "https://ceres.test/despesas",
                "movement_type": "Empenho",
                "movement_number": "100",
                "title": "Material 2026",
                "favored": "Fornecedor A",
            }
        ],
    }
    import json
    p2025 = tmp_path / "despesas_2025.json"
    p2026 = tmp_path / "despesas_2026.json"
    p2025.write_text(json.dumps(history_2025), encoding="utf-8")
    p2026.write_text(json.dumps(history_2026), encoding="utf-8")

    database_url = f"sqlite:///{tmp_path / 'test_years.db'}"
    assert import_json(p2025, database_url)[2] == 1
    assert import_json(p2026, database_url)[2] == 1

    engine, session_factory = make_session_factory(database_url)
    try:
        with session_factory() as session:
            records = list(session.scalars(select(PublicRecord).order_by(PublicRecord.year)))
            assert len(records) == 2
            assert records[0].year == 2025
            assert records[1].year == 2026
    finally:
        engine.dispose()
