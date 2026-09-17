from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.money import parse_brl_money
from database.models import Municipality, PublicRecord


def _record_dict(record: PublicRecord) -> dict[str, Any]:
    return {
        "id": record.id,
        "municipality": record.municipality.name if record.municipality else None,
        "kind": record.kind,
        "title": record.title,
        "status": record.status,
        "value": str(record.value) if record.value is not None else None,
        "published_at": record.published_at,
        "opening_date": record.opening_date,
        "modality": record.modality,
        "detail_url": record.detail_url,
    }


def records_by_municipality(
    session: Session,
    year: int | None = None,
    kind: str | None = None,
) -> dict[str, int]:
    stmt = (
        select(Municipality.name, func.count(PublicRecord.id))
        .join(PublicRecord, PublicRecord.municipality_id == Municipality.id)
    )
    if year is not None:
        stmt = stmt.where(PublicRecord.year == year)
    if kind:
        stmt = stmt.where(PublicRecord.kind == kind)
    rows = session.execute(stmt.group_by(Municipality.name).order_by(Municipality.name))
    return {name: total for name, total in rows}


def records_by_kind(
    session: Session,
    year: int | None = None,
    municipality: str | None = None,
    kind: str | None = None,
) -> dict[str, int]:
    stmt = select(PublicRecord.kind, func.count(PublicRecord.id))
    if municipality:
        stmt = stmt.join(Municipality, PublicRecord.municipality_id == Municipality.id).where(Municipality.name == municipality)
    if year is not None:
        stmt = stmt.where(PublicRecord.year == year)
    if kind:
        stmt = stmt.where(PublicRecord.kind == kind)
    rows = session.execute(stmt.group_by(PublicRecord.kind).order_by(PublicRecord.kind))
    res = {k: total for k, total in rows}
    if kind and kind not in res:
        res[kind] = 0
    return res


def records_by_year(
    session: Session,
    municipality: str | None = None,
    kind: str | None = None,
) -> dict[str, int]:
    stmt = select(PublicRecord.year, func.count(PublicRecord.id))
    if municipality:
        stmt = stmt.join(Municipality, PublicRecord.municipality_id == Municipality.id).where(Municipality.name == municipality)
    if kind:
        stmt = stmt.where(PublicRecord.kind == kind)
    rows = session.execute(stmt.group_by(PublicRecord.year).order_by(PublicRecord.year.desc().nullslast()))
    return {str(year) if year is not None else "Sem ano": total for year, total in rows}


def records_by_status(
    session: Session,
    year: int | None = None,
    municipality: str | None = None,
    kind: str | None = None,
) -> dict[str, int]:
    stmt = select(PublicRecord.status, func.count(PublicRecord.id))
    if municipality:
        stmt = stmt.join(Municipality, PublicRecord.municipality_id == Municipality.id).where(Municipality.name == municipality)
    if year is not None:
        stmt = stmt.where(PublicRecord.year == year)
    if kind:
        stmt = stmt.where(PublicRecord.kind == kind)
    rows = session.execute(stmt.group_by(PublicRecord.status).order_by(PublicRecord.status))
    return {status or "Sem status": total for status, total in rows}


def top_modalities(session: Session, limit: int = 10, year: int | None = None) -> list[dict[str, Any]]:
    stmt = (
        select(PublicRecord.modality, func.count(PublicRecord.id))
        .where(PublicRecord.modality.is_not(None), PublicRecord.modality != "")
    )
    if year is not None:
        stmt = stmt.where(PublicRecord.year == year)
    rows = session.execute(
        stmt.group_by(PublicRecord.modality)
        .order_by(func.count(PublicRecord.id).desc(), PublicRecord.modality)
        .limit(limit)
    )
    return [{"modality": modality, "total": total} for modality, total in rows]


def _missing_value_condition():
    from sqlalchemy import and_, or_
    lic_contrato = (
        PublicRecord.kind.in_(["licitacao", "contrato"])
        & (PublicRecord.value.is_(None) | (PublicRecord.value == "") | (PublicRecord.value == 0))
    )
    def _is_empty_or_zero(col):
        return col.is_(None) | (col == 0) | (col == "") | (col == "0") | (col == "0.00") | (col == "0,00")

    despesa = (
        (PublicRecord.kind == "despesa")
        & _is_empty_or_zero(PublicRecord.committed_value)
        & _is_empty_or_zero(PublicRecord.liquidated_value)
        & _is_empty_or_zero(PublicRecord.paid_value)
    )
    return lic_contrato | despesa


def records_missing_value(
    session: Session,
    year: int | None = None,
    municipality: str | None = None,
    kind: str | None = None,
) -> list[dict[str, Any]]:
    stmt = select(PublicRecord).where(_missing_value_condition())
    if municipality:
        stmt = stmt.join(Municipality, PublicRecord.municipality_id == Municipality.id).where(Municipality.name == municipality)
    if year is not None:
        stmt = stmt.where(PublicRecord.year == year)
    if kind:
        stmt = stmt.where(PublicRecord.kind == kind)
    records = session.scalars(stmt.order_by(PublicRecord.id))
    return [_record_dict(record) for record in records]


def count_missing_value(
    session: Session,
    year: int | None = None,
    municipality: str | None = None,
    kind: str | None = None,
) -> int:
    stmt = select(func.count(PublicRecord.id)).where(_missing_value_condition())
    if municipality:
        stmt = stmt.join(Municipality, PublicRecord.municipality_id == Municipality.id).where(Municipality.name == municipality)
    if year is not None:
        stmt = stmt.where(PublicRecord.year == year)
    if kind:
        stmt = stmt.where(PublicRecord.kind == kind)
    return session.scalar(stmt) or 0


def expenses_financial_totals(
    session: Session,
    municipality: str | None = None,
    year: int | None = None,
) -> dict[str, Decimal]:
    stmt = (
        select(
            func.sum(PublicRecord.committed_value),
            func.sum(PublicRecord.liquidated_value),
            func.sum(PublicRecord.paid_value),
        )
        .where(PublicRecord.kind == "despesa")
    )
    if municipality:
        stmt = stmt.join(Municipality, PublicRecord.municipality_id == Municipality.id).where(Municipality.name == municipality)
    if year is not None:
        stmt = stmt.where(PublicRecord.year == year)

    row = session.execute(stmt).first()
    if not row:
        return {"total_empenhado": Decimal("0.00"), "total_liquidado": Decimal("0.00"), "total_pago": Decimal("0.00")}
    emp, liq, pag = row
    return {
        "total_empenhado": parse_brl_money(emp) or Decimal("0.00"),
        "total_liquidado": parse_brl_money(liq) or Decimal("0.00"),
        "total_pago": parse_brl_money(pag) or Decimal("0.00"),
    }


def expenses_financial_by_municipality(
    session: Session,
    year: int | None = None,
) -> dict[str, dict[str, Decimal]]:
    stmt = (
        select(
            Municipality.name,
            func.sum(PublicRecord.committed_value),
            func.sum(PublicRecord.liquidated_value),
            func.sum(PublicRecord.paid_value),
        )
        .join(PublicRecord, PublicRecord.municipality_id == Municipality.id)
        .where(PublicRecord.kind == "despesa")
    )
    if year is not None:
        stmt = stmt.where(PublicRecord.year == year)
    rows = session.execute(stmt.group_by(Municipality.name).order_by(Municipality.name)).all()
    return {
        name: {
            "total_empenhado": parse_brl_money(emp) or Decimal("0.00"),
            "total_liquidado": parse_brl_money(liq) or Decimal("0.00"),
            "total_pago": parse_brl_money(pag) or Decimal("0.00"),
        }
        for name, emp, liq, pag in rows
    }


def expenses_financial_by_year(
    session: Session,
    municipality: str | None = None,
) -> dict[str, dict[str, Decimal]]:
    stmt = (
        select(
            PublicRecord.year,
            func.sum(PublicRecord.committed_value),
            func.sum(PublicRecord.liquidated_value),
            func.sum(PublicRecord.paid_value),
        )
        .where(PublicRecord.kind == "despesa")
    )
    if municipality:
        stmt = stmt.join(Municipality, PublicRecord.municipality_id == Municipality.id).where(Municipality.name == municipality)
    rows = session.execute(stmt.group_by(PublicRecord.year).order_by(PublicRecord.year.desc().nullslast())).all()
    return {
        str(yr) if yr is not None else "Sem ano": {
            "total_empenhado": parse_brl_money(emp) or Decimal("0.00"),
            "total_liquidado": parse_brl_money(liq) or Decimal("0.00"),
            "total_pago": parse_brl_money(pag) or Decimal("0.00"),
        }
        for yr, emp, liq, pag in rows
    }


def expenses_by_favored_top(
    session: Session,
    limit: int = 10,
    municipality: str | None = None,
    year: int | None = None,
    q: str | None = None,
) -> list[dict[str, Any]]:
    stmt = (
        select(
            PublicRecord.favored,
            Municipality.name.label("municipality"),
            PublicRecord.year,
            func.count(PublicRecord.id).label("movements_count"),
            func.sum(PublicRecord.committed_value).label("total_empenhado"),
            func.sum(PublicRecord.liquidated_value).label("total_liquidado"),
            func.sum(PublicRecord.paid_value).label("total_pago"),
        )
        .join(Municipality, PublicRecord.municipality_id == Municipality.id)
        .where(
            PublicRecord.kind == "despesa",
            PublicRecord.favored.is_not(None),
            PublicRecord.favored != "",
        )
    )
    if municipality:
        stmt = stmt.where(Municipality.name == municipality)
    if year is not None:
        stmt = stmt.where(PublicRecord.year == year)
    if q:
        stmt = stmt.where(PublicRecord.favored.ilike(f"%{q.strip()}%"))

    stmt = (
        stmt.group_by(PublicRecord.favored, Municipality.name, PublicRecord.year)
        .order_by(func.sum(PublicRecord.committed_value).desc())
        .limit(limit)
    )

    rows = session.execute(stmt).all()
    results = []
    for r in rows:
        results.append(
            {
                "favored": r.favored,
                "municipality": r.municipality,
                "year": r.year,
                "movements_count": r.movements_count,
                "total_empenhado": parse_brl_money(r.total_empenhado) or Decimal("0.00"),
                "total_liquidado": parse_brl_money(r.total_liquidado) or Decimal("0.00"),
                "total_pago": parse_brl_money(r.total_pago) or Decimal("0.00"),
            }
        )
    return results



def recent_records(session: Session, limit: int = 20) -> list[dict[str, Any]]:
    records = list(session.scalars(select(PublicRecord)))

    def sort_key(record: PublicRecord) -> datetime:
        for value in (record.published_at, record.opening_date):
            if value:
                try:
                    return datetime.strptime(value, "%d/%m/%Y")
                except ValueError:
                    continue
        return record.created_at.replace(tzinfo=None)

    records.sort(key=sort_key, reverse=True)
    return [_record_dict(record) for record in records[:limit]]