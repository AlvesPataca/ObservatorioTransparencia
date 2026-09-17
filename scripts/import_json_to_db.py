import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, inspect, or_, select, text
from sqlalchemy.orm import Session, sessionmaker

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.money import parse_brl_money
from database.models import Base, Municipality, PublicRecord, SourceCheck
from database.session import DATABASE_URL, connect_args


def make_session_factory(database_url: str = DATABASE_URL) -> tuple[Any, sessionmaker]:
    engine = create_engine(
        database_url,
        connect_args={"check_same_thread": False} if database_url.startswith("sqlite") else connect_args,
        future=True,
    )
    Base.metadata.create_all(engine)
    migrate_legacy_public_records(engine)
    ensure_public_record_columns(engine)
    return engine, sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def ensure_public_record_columns(engine: Any) -> None:
    if engine.dialect.name != "sqlite":
        return
    existing = {column["name"] for column in inspect(engine).get_columns("public_records")}
    additions = {
        "year": "INTEGER",
        "movement_type": "VARCHAR(40)",
        "movement_number": "VARCHAR(120)",
        "favored": "TEXT",
        "movement_date": "VARCHAR(40)",
        "description": "TEXT",
        "committed_value": "NUMERIC(15, 2)",
        "liquidated_value": "NUMERIC(15, 2)",
        "paid_value": "NUMERIC(15, 2)",
        "value_raw": "VARCHAR(120)",
        "committed_value_raw": "VARCHAR(120)",
        "liquidated_value_raw": "VARCHAR(120)",
        "paid_value_raw": "VARCHAR(120)",
        "attention_score": "INTEGER DEFAULT 0",
        "attention_reasons": "TEXT",
        "attention_keywords": "TEXT",
    }
    with engine.begin() as connection:
        for column, column_type in additions.items():
            if column not in existing:
                connection.execute(text(f'ALTER TABLE public_records ADD COLUMN "{column}" {column_type}'))

        existing_indexes = {index["name"] for index in inspect(engine).get_indexes("public_records") if index.get("name")}
        indexes_to_create = [
            ("ix_public_records_status", "status"),
            ("ix_public_records_movement_date", "movement_date"),
            ("ix_public_records_movement_number", "movement_number"),
            ("ix_public_records_favored", "favored"),
            ("ix_public_records_title", "title"),
            ("ix_public_records_attention_score", "attention_score"),
            ("ix_public_records_mun_yr_kind", "municipality_id, year, kind"),
            ("ix_public_records_att_lookup", "attention_score, municipality_id, year"),
        ]
        for idx_name, idx_cols in indexes_to_create:
            if idx_name not in existing_indexes:
                connection.execute(text(f'CREATE INDEX IF NOT EXISTS "{idx_name}" ON public_records ({idx_cols})'))


def migrate_legacy_public_records(engine: Any) -> None:
    if engine.dialect.name != "sqlite":
        return
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if "public_records" not in tables and "public_records_legacy" not in tables:
        return
    constraints = inspector.get_unique_constraints("public_records") if "public_records" in tables else []
    target_columns = {
        "municipality_id",
        "kind",
        "year",
        "detail_url",
        "process_number",
        "title",
        "movement_type",
        "movement_number",
    }
    has_target_key = any(
        set(constraint.get("column_names") or []) == target_columns
        for constraint in constraints
    )
    temporary_tables = [
        table for table in ("public_records_migration", "public_records_legacy") if table in tables
    ]
    if has_target_key:
        if temporary_tables:
            _copy_public_record_tables(engine, temporary_tables, "public_records")
        return

    migration_tables = []
    if "public_records" in tables:
        with engine.begin() as connection:
            for index in inspect(engine).get_indexes("public_records"):
                if index.get("name"):
                    connection.execute(text(f'DROP INDEX IF EXISTS "{index["name"]}"'))
            connection.execute(text("ALTER TABLE public_records RENAME TO public_records_migration"))
        migration_tables.append("public_records_migration")
    if "public_records_legacy" in tables:
        migration_tables.append("public_records_legacy")
        with engine.begin() as connection:
            for index in inspect(engine).get_indexes("public_records_legacy"):
                if index.get("name"):
                    connection.execute(text(f'DROP INDEX IF EXISTS "{index["name"]}"'))
    Base.metadata.create_all(engine)

    columns = [
        "id",
        "municipality_id",
        "kind",
        "year",
        "source_url",
        "title",
        "detail_url",
        "process_number",
        "modality",
        "object",
        "opening_date",
        "value",
        "status",
        "published_at",
        "movement_type",
        "movement_number",
        "favored",
        "movement_date",
        "description",
        "committed_value",
        "liquidated_value",
        "paid_value",
        "value_raw",
        "committed_value_raw",
        "liquidated_value_raw",
        "paid_value_raw",
        "raw_json",
        "collected_at",
        "created_at",
        "updated_at",
    ]
    _copy_public_record_tables(engine, migration_tables, "public_records", columns)


def _copy_public_record_tables(
    engine: Any,
    source_tables: list[str],
    target_table: str,
    columns: list[str] | None = None,
) -> None:
    columns = columns or [
        "id",
        "municipality_id",
        "kind",
        "year",
        "source_url",
        "title",
        "detail_url",
        "process_number",
        "modality",
        "object",
        "opening_date",
        "value",
        "status",
        "published_at",
        "movement_type",
        "movement_number",
        "favored",
        "movement_date",
        "description",
        "committed_value",
        "liquidated_value",
        "paid_value",
        "value_raw",
        "committed_value_raw",
        "liquidated_value_raw",
        "paid_value_raw",
        "raw_json",
        "collected_at",
        "created_at",
        "updated_at",
    ]

    with engine.begin() as connection:
        for source_table in source_tables:
            old_columns = {column["name"] for column in inspect(engine).get_columns(source_table)}
            copied_columns = [column for column in columns if column != "id" and column in old_columns]
            quoted = ", ".join(f'"{column}"' for column in copied_columns)
            connection.execute(
                text(f'INSERT OR IGNORE INTO "{target_table}" ({quoted}) SELECT {quoted} FROM "{source_table}"')
            )
            connection.execute(text(f'DROP TABLE "{source_table}"'))


def _record_identity(
    kind: str,
    year: int | None,
    detail_url: str | None,
    process_number: Any,
    title: str | None,
    movement_type: Any,
    movement_number: Any,
) -> tuple:
    return (
        kind,
        year,
        detail_url,
        str(process_number) if process_number is not None else None,
        title,
        str(movement_type) if movement_type is not None else None,
        str(movement_number) if movement_number is not None else None,
    )


def import_payload(payload: list[dict[str, Any]], session: Session) -> tuple[int, int, int]:
    municipality_count = 0
    source_check_count = 0
    record_count = 0

    for municipality_data in payload:
        municipality_name = municipality_data["municipality"]
        municipality = session.scalar(select(Municipality).where(Municipality.name == municipality_name))
        if municipality is None:
            municipality = Municipality(name=municipality_name)
            session.add(municipality)
            session.flush()
            municipality_count += 1

        for check_data in municipality_data.get("source_checks", []):
            check = session.scalar(
                select(SourceCheck).where(
                    SourceCheck.municipality_id == municipality.id,
                    SourceCheck.label == check_data["label"],
                    SourceCheck.url == check_data["url"],
                )
            )
            if check is None:
                check = SourceCheck(municipality_id=municipality.id, label=check_data["label"], url=check_data["url"])
                session.add(check)
                source_check_count += 1
            for field in ("status_code", "content_type", "final_url", "accessible", "blocked", "notes"):
                setattr(check, field, check_data.get(field))

        records_list = municipality_data.get("records", [])
        if not records_list:
            continue

        existing_records = list(
            session.scalars(
                select(PublicRecord).where(PublicRecord.municipality_id == municipality.id)
            )
        )
        exact_lookup: dict[tuple, PublicRecord] = {}
        no_year_lookup: dict[tuple, PublicRecord] = {}
        for r in existing_records:
            k = _record_identity(
                r.kind,
                r.year,
                r.detail_url,
                r.process_number,
                r.title,
                r.movement_type,
                r.movement_number,
            )
            exact_lookup[k] = r
            if r.year is None:
                k_no_year = _record_identity(
                    r.kind,
                    None,
                    r.detail_url,
                    r.process_number,
                    r.title,
                    r.movement_type,
                    r.movement_number,
                )
                no_year_lookup[k_no_year] = r

        for idx, record_data in enumerate(records_list):
            detail_url = record_data.get("detail_url")
            record_year = (
                record_data.get("year")
                or municipality_data.get("year")
                or _extract_year_from_record(record_data)
            )
            movement_number = record_data.get("movement_number")
            movement_number_str = str(movement_number) if movement_number is not None else None
            process_number = record_data.get("process_number")
            if not process_number and record_data.get("kind") == "despesa":
                process_number = movement_number_str
            process_number_str = str(process_number) if process_number is not None else None

            title = record_data.get("title") or record_data.get("description") or record_data.get("favored") or "Registro"
            movement_type = record_data.get("movement_type")
            movement_type_str = str(movement_type) if movement_type is not None else None

            key = _record_identity(
                record_data.get("kind", "despesa"),
                record_year,
                detail_url,
                process_number_str,
                title,
                movement_type_str,
                movement_number_str,
            )

            record = exact_lookup.get(key)
            if record is None and record_year is not None:
                key_without_year = _record_identity(
                    record_data.get("kind", "despesa"),
                    None,
                    detail_url,
                    process_number_str,
                    title,
                    movement_type_str,
                    movement_number_str,
                )
                record = no_year_lookup.pop(key_without_year, None)

            raw = record_data.get("raw") or {}
            committed_raw = (
                record_data.get("committed_value_raw")
                or raw.get("valor_empenho")
                or raw.get("valorDoEmpenho")
                or raw.get("valorTotalDoEmpenho")
            )
            liquidated_raw = (
                record_data.get("liquidated_value_raw")
                or raw.get("liquidado")
                or raw.get("valor_liquidacao")
                or raw.get("valorTotalDaLiquidacao")
                or raw.get("valorDaLiquidacao")
            )
            paid_raw = (
                record_data.get("paid_value_raw")
                or raw.get("pagamento")
                or raw.get("valor_pagamento")
                or raw.get("valorTotalDoPagamento")
                or raw.get("valorDoPagamento")
            )
            value_raw = (
                record_data.get("value_raw")
                or raw.get("valor")
                or raw.get("valor_estimado")
                or raw.get("valorEstimado")
                or raw.get("valor_homologado")
                or record_data.get("value")
            )

            committed_val = parse_brl_money(committed_raw) if committed_raw is not None else parse_brl_money(record_data.get("committed_value"))
            liquidated_val = parse_brl_money(liquidated_raw) if liquidated_raw is not None else parse_brl_money(record_data.get("liquidated_value"))
            paid_val = parse_brl_money(paid_raw) if paid_raw is not None else parse_brl_money(record_data.get("paid_value"))
            val = parse_brl_money(value_raw) if value_raw is not None else parse_brl_money(record_data.get("value"))

            values = {
                "municipality_id": municipality.id,
                "kind": record_data.get("kind", "despesa"),
                "year": record_year,
                "source_url": record_data.get("source_url", ""),
                "title": title,
                "detail_url": detail_url,
                "process_number": process_number_str,
                "modality": record_data.get("modality"),
                "object": record_data.get("object"),
                "opening_date": record_data.get("opening_date"),
                "value": val,
                "status": record_data.get("status"),
                "published_at": record_data.get("published_at"),
                "movement_type": movement_type_str,
                "movement_number": movement_number_str,
                "favored": record_data.get("favored"),
                "movement_date": record_data.get("movement_date"),
                "description": record_data.get("description"),
                "committed_value": committed_val,
                "liquidated_value": liquidated_val,
                "paid_value": paid_val,
                "value_raw": str(value_raw) if value_raw is not None else None,
                "committed_value_raw": str(committed_raw) if committed_raw is not None else None,
                "liquidated_value_raw": str(liquidated_raw) if liquidated_raw is not None else None,
                "paid_value_raw": str(paid_raw) if paid_raw is not None else None,
                "raw_json": json.dumps(record_data.get("raw", {}), ensure_ascii=False),
                "collected_at": _parse_datetime(municipality_data.get("collected_at")),
            }
            if record is None:
                record = PublicRecord(**values)
                session.add(record)
                exact_lookup[key] = record
                record_count += 1
            else:
                for field, value in values.items():
                    setattr(record, field, value)
                exact_lookup[key] = record

            if idx > 0 and idx % 2000 == 0:
                session.flush()

        session.flush()

    session.commit()
    return municipality_count, source_check_count, record_count


def _extract_year_from_record(record_data: dict[str, Any]) -> int | None:
    import re
    for field in ("movement_date", "opening_date", "published_at", "title"):
        val = record_data.get(field)
        if val:
            match = re.search(r"\b(20\d{2})\b", str(val))
            if match:
                return int(match.group(1))
    return None


def _parse_datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def import_json(json_path: Path, database_url: str = DATABASE_URL) -> tuple[int, int, int]:
    raw_payload = json.loads(json_path.read_text(encoding="utf-8"))
    payload = raw_payload if isinstance(raw_payload, list) else [raw_payload]
    for item in payload:
        for record in item.get("records", []):
            if item.get("kind") == "despesa" or record.get("kind") == "despesa":
                record["kind"] = "despesa"
                record.setdefault("source_url", item.get("source_url", ""))
                record.setdefault("detail_url", item.get("source_url", ""))
                if "year" in item and "year" not in record:
                    record["year"] = item["year"]
                if not record.get("title"):
                    record["title"] = record.get("description") or record.get("favored") or "Despesa"
                if not record.get("object"):
                    record["object"] = record.get("description")
                if not record.get("process_number"):
                    record["process_number"] = record.get("movement_number")
    engine, session_factory = make_session_factory(database_url)
    try:
        with session_factory() as session:
            return import_payload(payload, session)
    finally:
        engine.dispose()


def main() -> None:
    created = (0, 0, 0)
    imported_files = []

    # Arquivos legados
    legacy_files = [
        PROJECT_ROOT / "data" / "mvp_licitacoes_contratos.json",
        PROJECT_ROOT / "data" / "ceres_despesas.json",
        PROJECT_ROOT / "data" / "rialma_despesas.json",
    ]
    for path in legacy_files:
        if path.exists():
            res = import_json(path)
            created = tuple(left + right for left, right in zip(created, res))
            imported_files.append(path.name)

    # Arquivos particionados históricos
    history_dir = PROJECT_ROOT / "data" / "history"
    if history_dir.exists():
        for history_file in sorted(history_dir.glob("**/*.json")):
            res = import_json(history_file)
            created = tuple(left + right for left, right in zip(created, res))
            imported_files.append(str(history_file.relative_to(PROJECT_ROOT)))

    print(f"Arquivos processados: {len(imported_files)}")
    print(f"Municipios novos: {created[0]}")
    print(f"Source checks novos: {created[1]}")
    print(f"Registros novos: {created[2]}")
    print(f"Banco atualizado: {PROJECT_ROOT / 'data' / 'observatorio.db'}")


if __name__ == "__main__":
    main()

