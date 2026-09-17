from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from analytics.anomalies import (
    count_suspicious_keywords,
    detect_duplicate_titles,
    detect_same_title_across_municipalities,
    detect_suspicious_keywords,
)
from analytics.reports import (
    count_missing_value,
    expenses_by_favored_top,
    expenses_financial_by_municipality,
    expenses_financial_by_year,
    expenses_financial_totals,
    recent_records,
    records_by_kind,
    records_by_municipality,
    records_by_status,
    records_by_year,
    records_missing_value,
    top_modalities,
)
from app.schemas import (
    AnalysisOut,
    AnomaliesPageOut,
    AnomalyFindingOut,
    AttentionItemOut,
    AttentionPageOut,
    ExpensesFinancialTotalsOut,
    ExpensesSummaryOut,
    MunicipalityOut,
    PublicRecordOut,
    RecordsPageOut,
    SummaryOut,
)
from database.models import AnomalyFinding, Municipality, PublicRecord, SupplierProfile
from database.session import SessionLocal


router = APIRouter()


def get_db():
    with SessionLocal() as session:
        yield session


def _record_out(record: PublicRecord) -> dict[str, Any]:
    return {
        "id": record.id,
        "municipality_id": record.municipality_id,
        "municipality": record.municipality.name if record.municipality else None,
        "kind": record.kind,
        "year": record.year,
        "source_url": record.source_url,
        "title": record.title,
        "detail_url": record.detail_url,
        "published_at": record.published_at,
        "movement_type": record.movement_type,
        "movement_number": record.movement_number,
        "favored": record.favored,
        "movement_date": record.movement_date,
        "description": record.description,
        "committed_value": record.committed_value,
        "liquidated_value": record.liquidated_value,
        "paid_value": record.paid_value,
        "value": record.value,
        "value_raw": record.value_raw,
        "committed_value_raw": record.committed_value_raw,
        "liquidated_value_raw": record.liquidated_value_raw,
        "paid_value_raw": record.paid_value_raw,
        "process_number": record.process_number,
        "modality": record.modality,
        "object": record.object,
        "opening_date": record.opening_date,
        "status": record.status,
        "raw_json": record.raw_json,
        "collected_at": record.collected_at,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


def _empty_summary() -> SummaryOut:
    return SummaryOut()


@router.get("/summary", response_model=SummaryOut)
def summary(
    municipality: str | None = Query(default=None),
    year: int | None = Query(default=None),
    kind: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> SummaryOut:
    try:
        years_query = select(PublicRecord.year).where(PublicRecord.year.is_not(None)).distinct()
        available_years = sorted([y for y in db.scalars(years_query) if y is not None], reverse=True)
        available_municipalities = list(db.scalars(select(Municipality.name).order_by(Municipality.name)))

        by_mun = records_by_municipality(db, year=year, kind=kind)
        by_kind = records_by_kind(db, year=year, municipality=municipality, kind=kind)
        by_year = records_by_year(db, municipality=municipality, kind=kind)
        by_status = records_by_status(db, year=year, municipality=municipality, kind=kind)

        # Regra: Se kind for informado e não for 'despesa', não retornar métricas de despesas
        if kind and kind != "despesa":
            fin_totals = {
                "total_empenhado": "0.00",
                "total_liquidado": "0.00",
                "total_pago": "0.00",
                "count": 0,
            }
        else:
            fin_totals = expenses_financial_totals(db, municipality=municipality, year=year)

        missing_count = count_missing_value(db, year=year, municipality=municipality, kind=kind)
        
        # Pontos de revisão auditáveis (com fallback se ainda não indexado)
        anom_stmt = select(func.count(AnomalyFinding.id))
        if municipality:
            anom_stmt = anom_stmt.where(AnomalyFinding.municipality == municipality)
        if year is not None:
            anom_stmt = anom_stmt.where(AnomalyFinding.year == year)
        anom_count = db.scalar(anom_stmt) or 0
        attention_count = anom_count if anom_count > 0 else count_suspicious_keywords(db, municipality=municipality, year=year, kind=kind)

        return SummaryOut(
            totals_by_municipality=by_mun,
            totals_by_kind=by_kind,
            totals_by_year=by_year,
            expenses_financial_totals=ExpensesFinancialTotalsOut(**fin_totals),
            missing_value_count=missing_count,
            attention_count_limited=attention_count,
            records_by_municipality=by_mun,
            records_by_kind=by_kind,
            records_by_status=by_status,
            records_missing_value=missing_count,
            attention_count=attention_count,
            available_years=available_years,
            available_municipalities=available_municipalities,
            selected_year=year,
            selected_municipality=municipality,
            selected_kind=kind,
        )
    except SQLAlchemyError:
        return _empty_summary()


@router.get("/years", response_model=list[int])
def available_years(db: Session = Depends(get_db)) -> list[int]:
    try:
        years_query = select(PublicRecord.year).where(PublicRecord.year.is_not(None)).distinct()
        return sorted([y for y in db.scalars(years_query) if y is not None], reverse=True)
    except SQLAlchemyError:
        return []


@router.get("/municipalities", response_model=list[str])
def municipalities(db: Session = Depends(get_db)) -> list[str]:
    try:
        return list(db.scalars(select(Municipality.name).order_by(Municipality.name)))
    except SQLAlchemyError:
        return []


@router.get("/expenses/summary", response_model=ExpensesSummaryOut)
def expenses_summary(
    municipality: str | None = Query(default=None),
    year: int | None = Query(default=None),
    kind: str | None = Query(default=None),
    q: str | None = Query(default=None),
    limit: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
) -> ExpensesSummaryOut:
    if kind and kind != "despesa":
        return ExpensesSummaryOut()

    try:
        totals = expenses_financial_totals(db, municipality=municipality, year=year)
        by_mun = expenses_financial_by_municipality(db, year=year)
        by_year = expenses_financial_by_year(db, municipality=municipality)
        top_fav = expenses_by_favored_top(db, limit=limit, municipality=municipality, year=year, q=q)

        return ExpensesSummaryOut(
            financial_totals=ExpensesFinancialTotalsOut(**totals),
            by_municipality=by_mun,
            by_year=by_year,
            top_favored=top_fav,
            selected_municipality=municipality,
            selected_year=year,
        )
    except SQLAlchemyError:
        return ExpensesSummaryOut()


@router.get("/records", response_model=RecordsPageOut)
def records(
    municipality: str | None = None,
    kind: str | None = None,
    year: int | None = Query(default=None),
    status: str | None = None,
    q: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> RecordsPageOut:
    try:
        statement = select(PublicRecord).join(Municipality)
        if municipality:
            statement = statement.where(Municipality.name == municipality)
        if kind:
            statement = statement.where(PublicRecord.kind == kind)
        if year is not None:
            statement = statement.where(PublicRecord.year == year)
        if status:
            statement = statement.where(PublicRecord.status == status)
        if q:
            pattern = f"%{q.strip()}%"
            statement = statement.where(
                or_(
                    PublicRecord.title.ilike(pattern),
                    PublicRecord.object.ilike(pattern),
                    PublicRecord.favored.ilike(pattern),
                    PublicRecord.description.ilike(pattern),
                )
            )
        total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
        records_found = db.scalars(
            statement.order_by(
                PublicRecord.year.desc().nullslast(),
                PublicRecord.movement_date.desc().nullslast(),
                PublicRecord.id.desc(),
            )
            .offset(offset)
            .limit(limit)
        )
        return RecordsPageOut(total=total, items=[_record_out(record) for record in records_found])
    except SQLAlchemyError as exc:
        return RecordsPageOut(error=f"Não foi possível consultar os registros: {exc.__class__.__name__}")


@router.get("/records/{record_id}", response_model=PublicRecordOut)
def record_detail(record_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        record = db.scalar(select(PublicRecord).where(PublicRecord.id == record_id))
    except SQLAlchemyError:
        record = None
    if record is None:
        raise HTTPException(status_code=404, detail="Registro não encontrado")
    return _record_out(record)


@router.get("/analysis", response_model=AnalysisOut)
def analysis(db: Session = Depends(get_db)) -> AnalysisOut:
    try:
        return AnalysisOut(
            records_by_municipality=records_by_municipality(db),
            records_by_kind=records_by_kind(db),
            records_by_status=records_by_status(db),
            top_modalities=top_modalities(db),
            records_missing_value=records_missing_value(db),
            recent_records=recent_records(db),
            duplicate_titles=detect_duplicate_titles(db),
            same_title_across_municipalities=detect_same_title_across_municipalities(db),
            suspicious_keywords=detect_suspicious_keywords(db, limit=100),
        )
    except SQLAlchemyError:
        return AnalysisOut()


@router.get("/attention", response_model=AttentionPageOut)
def attention(
    municipality: str | None = Query(default=None),
    year: int | None = Query(default=None),
    kind: str | None = Query(default=None),
    score_min: int = Query(default=1, ge=1),
    term: str | None = Query(default=None),
    q: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> AttentionPageOut:
    try:
        total, items = detect_suspicious_keywords(
            db,
            limit=limit,
            offset=offset,
            municipality=municipality,
            year=year,
            kind=kind,
            q=q,
            min_score=score_min,
            term=term,
            with_total=True,
        )
        return AttentionPageOut(total=total, items=items)
    except SQLAlchemyError as exc:
        return AttentionPageOut(total=0, items=[], error=f"Erro ao consultar pontos de atenção: {exc.__class__.__name__}")


@router.get("/anomalies", response_model=AnomaliesPageOut)
def anomalies(
    municipality: str | None = Query(default=None),
    year: int | None = Query(default=None),
    category: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    supplier: str | None = Query(default=None),
    min_score: int = Query(default=1, ge=1),
    q: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> AnomaliesPageOut:
    import json
    from sqlalchemy.orm import joinedload

    try:
        stmt = (
            select(AnomalyFinding)
            .options(
                joinedload(AnomalyFinding.record),
                joinedload(AnomalyFinding.supplier),
            )
            .where(AnomalyFinding.score >= min_score)
        )

        if municipality:
            stmt = stmt.where(AnomalyFinding.municipality == municipality)
        if year is not None:
            stmt = stmt.where(AnomalyFinding.year == year)
        if category:
            stmt = stmt.where(AnomalyFinding.category == category)
        if severity:
            stmt = stmt.where(AnomalyFinding.severity == severity)
        if supplier:
            stmt = stmt.where(AnomalyFinding.explanation.ilike(f"%{supplier.strip()}%"))
        if q:
            pat = f"%{q.strip()}%"
            stmt = stmt.where(
                or_(
                    AnomalyFinding.title.ilike(pat),
                    AnomalyFinding.explanation.ilike(pat),
                    AnomalyFinding.category.ilike(pat),
                )
            )

        total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0

        # Sumários de categorias e severidades com base nos filtros selecionados
        base_cat_stmt = select(AnomalyFinding.category, func.count(AnomalyFinding.id)).where(AnomalyFinding.score >= min_score)
        if municipality:
            base_cat_stmt = base_cat_stmt.where(AnomalyFinding.municipality == municipality)
        if year is not None:
            base_cat_stmt = base_cat_stmt.where(AnomalyFinding.year == year)
        cat_rows = db.execute(base_cat_stmt.group_by(AnomalyFinding.category)).all()
        categories_summary = {c: count for c, count in cat_rows}

        base_sev_stmt = select(AnomalyFinding.severity, func.count(AnomalyFinding.id)).where(AnomalyFinding.score >= min_score)
        if municipality:
            base_sev_stmt = base_sev_stmt.where(AnomalyFinding.municipality == municipality)
        if year is not None:
            base_sev_stmt = base_sev_stmt.where(AnomalyFinding.year == year)
        sev_rows = db.execute(base_sev_stmt.group_by(AnomalyFinding.severity)).all()
        severities_summary = {s: count for s, count in sev_rows}

        query = stmt.order_by(AnomalyFinding.score.desc(), AnomalyFinding.id.desc()).offset(offset).limit(limit)
        findings = db.scalars(query).all()

        items = []
        for f in findings:
            evidence = {}
            if f.evidence_json:
                try:
                    evidence = json.loads(f.evidence_json)
                except Exception:
                    evidence = {}

            favored = None
            movement_number = None
            detail_url = None
            source_url = None
            val_str = None

            if f.record:
                favored = f.record.favored
                movement_number = f.record.movement_number or f.record.process_number
                detail_url = f.record.detail_url
                source_url = f.record.source_url
                v = f.record.paid_value or f.record.committed_value or f.record.value
                val_str = str(v) if v is not None else None
            elif f.supplier:
                favored = f.supplier.normalized_name
                val_str = str(f.supplier.total_paid) if f.supplier.total_paid else None

            items.append(
                AnomalyFindingOut(
                    id=f.id,
                    record_id=f.record_id,
                    supplier_id=f.supplier_id,
                    municipality=f.municipality,
                    year=f.year,
                    category=f.category,
                    severity=f.severity,
                    score=f.score,
                    title=f.title,
                    explanation=f.explanation,
                    evidence=evidence,
                    evidence_json=f.evidence_json,
                    favored=favored,
                    movement_number=movement_number,
                    detail_url=detail_url,
                    source_url=source_url,
                    value=val_str,
                    created_at=f.created_at,
                )
            )

        return AnomaliesPageOut(
            total=total,
            items=items,
            categories_summary=categories_summary,
            severities_summary=severities_summary,
        )
    except SQLAlchemyError as exc:
        return AnomaliesPageOut(total=0, items=[], error=f"Erro ao consultar pontos de revisão: {exc.__class__.__name__}")