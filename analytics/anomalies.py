import re
import unicodedata
from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import PublicRecord


# Regras de pontuação para análise de atenção contextual
PATTERN_RULES: list[tuple[re.Pattern, str, int, str]] = [
    (re.compile(r"\bemerg[eê]nc", re.IGNORECASE), "emergencial", 3, "Contratação ou dispensa emergencial"),
    (re.compile(r"\bdispens", re.IGNORECASE), "dispensa", 3, "Contratação direta por dispensa de licitação"),
    (re.compile(r"\binexigib", re.IGNORECASE), "inexigibilidade", 3, "Contratação direta por inexigibilidade"),
    (re.compile(r"\baditiv", re.IGNORECASE), "aditivo", 2, "Termo aditivo de contrato ou valor"),
    (re.compile(r"\bfracionad", re.IGNORECASE), "fracionada", 2, "Indício de compra parcelada ou fracionamento"),
    (re.compile(r"\bparcelad", re.IGNORECASE), "parcelada", 2, "Indício de compra parcelada ou fracionamento"),
    (re.compile(r"\bcombust[ií]v", re.IGNORECASE), "combustível", 1, "Gasto com combustível e abastecimento"),
    (re.compile(r"\blocac", re.IGNORECASE), "locação", 1, "Locação de bens móveis, imóveis ou veículos"),
    (re.compile(r"\bdi[aá]ri", re.IGNORECASE), "diária", 1, "Pagamento ou concessão de diárias"),
]

ATTENTION_KEYWORDS = (
    "emergência",
    "emergencial",
    "dispensa",
    "inexigibilidade",
    "aditivo",
    "fracionada",
    "parcelada",
    "combustível",
    "locação",
    "diária",
)


def _normalize_text(value: str) -> str:
    without_accents = "".join(
        char for char in unicodedata.normalize("NFKD", value.casefold()) if not unicodedata.combining(char)
    )
    return re.sub(r"\s+", " ", without_accents).strip()


def _record_dict(record: PublicRecord) -> dict[str, Any]:
    return {
        "id": record.id,
        "municipality": record.municipality.name if record.municipality else None,
        "kind": record.kind,
        "year": record.year,
        "title": record.title,
        "object": record.object,
        "description": record.description,
        "detail_url": record.detail_url,
    }


def detect_missing_values(session: Session) -> list[dict[str, Any]]:
    records = session.scalars(
        select(PublicRecord)
        .where(PublicRecord.value.is_(None) | (PublicRecord.value == ""))
        .order_by(PublicRecord.id)
    )
    return [_record_dict(record) for record in records]


def _duplicate_groups(session: Session, across_municipalities: bool) -> list[dict[str, Any]]:
    records = list(session.scalars(select(PublicRecord).order_by(PublicRecord.id)))
    groups: dict[tuple[str, ...], list[PublicRecord]] = defaultdict(list)
    for record in records:
        title = _normalize_text(record.title)
        if title:
            key = (title,) if across_municipalities else (record.municipality.name, title)
            groups[key].append(record)

    result = []
    for records_in_group in groups.values():
        municipalities = sorted({record.municipality.name for record in records_in_group})
        if len(records_in_group) > 1 and (not across_municipalities or len(municipalities) > 1):
            result.append(
                {
                    "title": records_in_group[0].title,
                    "count": len(records_in_group),
                    "municipalities": municipalities,
                    "records": [_record_dict(record) for record in records_in_group],
                }
            )
    return result


def detect_duplicate_titles(session: Session) -> list[dict[str, Any]]:
    return _duplicate_groups(session, across_municipalities=False)


def detect_same_title_across_municipalities(session: Session) -> list[dict[str, Any]]:
    return _duplicate_groups(session, across_municipalities=True)


def score_record_text(text: str) -> tuple[int, list[str], list[str]]:
    normalized = _normalize_text(text)
    score = 0
    keywords = []
    reasons = []
    for pattern, label, weight, reason in PATTERN_RULES:
        if pattern.search(normalized):
            score += weight
            keywords.append(label)
            if reason not in reasons:
                reasons.append(reason)
    return score, keywords, reasons


SEARCH_ROOTS = (
    "emergenc",
    "emergênc",
    "emergÊnc",
    "dispens",
    "inexigib",
    "aditiv",
    "fracionad",
    "parcelad",
    "combustiv",
    "combustív",
    "combustÍv",
    "locac",
    "locaç",
    "locaÇ",
    "diari",
    "diári",
    "diÁri",
)


def count_suspicious_keywords(
    session: Session,
    municipality: str | None = None,
    year: int | None = None,
    kind: str | None = None,
) -> int:
    from sqlalchemy import func
    from database.models import Municipality

    stmt = select(func.count(PublicRecord.id)).where(PublicRecord.attention_score >= 1)
    if municipality:
        stmt = stmt.join(Municipality, PublicRecord.municipality_id == Municipality.id).where(Municipality.name == municipality)
    if year is not None:
        stmt = stmt.where(PublicRecord.year == year)
    if kind:
        stmt = stmt.where(PublicRecord.kind == kind)
    return session.scalar(stmt) or 0


def detect_suspicious_keywords(
    session: Session,
    limit: int = 20,
    offset: int = 0,
    municipality: str | None = None,
    year: int | None = None,
    kind: str | None = None,
    q: str | None = None,
    min_score: int = 1,
    term: str | None = None,
    with_total: bool = False,
) -> list[dict[str, Any]] | tuple[int, list[dict[str, Any]]]:
    import json
    from sqlalchemy import func, or_
    from sqlalchemy.orm import joinedload
    from database.models import Municipality

    stmt = select(PublicRecord).where(PublicRecord.attention_score >= min_score)

    if municipality:
        stmt = stmt.join(Municipality, PublicRecord.municipality_id == Municipality.id).where(Municipality.name == municipality)
    if year is not None:
        stmt = stmt.where(PublicRecord.year == year)
    if kind:
        stmt = stmt.where(PublicRecord.kind == kind)
    if q:
        pat = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                PublicRecord.title.ilike(pat),
                PublicRecord.object.ilike(pat),
                PublicRecord.description.ilike(pat),
                PublicRecord.favored.ilike(pat),
            )
        )
    if term:
        t = term.strip()
        stmt = stmt.where(
            or_(
                PublicRecord.attention_keywords.ilike(f"%{t}%"),
                PublicRecord.attention_reasons.ilike(f"%{t}%"),
                PublicRecord.title.ilike(f"%{t}%"),
                PublicRecord.object.ilike(f"%{t}%"),
                PublicRecord.description.ilike(f"%{t}%"),
                PublicRecord.favored.ilike(f"%{t}%"),
            )
        )

    total = 0
    if with_total:
        total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    records = session.scalars(
        stmt.options(joinedload(PublicRecord.municipality))
        .order_by(PublicRecord.attention_score.desc(), PublicRecord.id.desc())
        .offset(offset)
        .limit(limit)
    ).all()

    scored_items = []
    for r in records:
        keywords = []
        reasons = []
        if r.attention_keywords:
            try:
                keywords = json.loads(r.attention_keywords)
            except Exception:
                keywords = [r.attention_keywords]
        if r.attention_reasons:
            try:
                reasons = json.loads(r.attention_reasons)
            except Exception:
                reasons = [r.attention_reasons]

        if not keywords and not reasons:
            content = " ".join(filter(None, [r.title, r.object, r.description, r.favored]))
            _, keywords, reasons = score_record_text(content)

        scored_items.append(
            {
                "id": r.id,
                "municipality": r.municipality.name if r.municipality else None,
                "kind": r.kind,
                "year": r.year,
                "source_url": r.source_url,
                "title": r.title,
                "object": r.object,
                "description": r.description,
                "detail_url": r.detail_url,
                "movement_type": r.movement_type,
                "movement_number": r.movement_number,
                "process_number": r.process_number,
                "favored": r.favored,
                "movement_date": r.movement_date,
                "value": str(r.value) if r.value is not None else None,
                "committed_value": str(r.committed_value) if r.committed_value is not None else None,
                "raw_json": r.raw_json,
                "score": r.attention_score or 0,
                "reasons": reasons,
                "keywords": keywords,
                "note": "Ponto de atenção para análise contextual; não indica irregularidade por si só.",
            }
        )

    if with_total:
        return total, scored_items
    return scored_items