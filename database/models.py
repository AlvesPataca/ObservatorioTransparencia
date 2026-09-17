from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, TypeDecorator, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.core.money import parse_brl_money


class MoneyType(TypeDecorator):
    impl = Numeric(15, 2, asdecimal=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None or value == "":
            return None
        return parse_brl_money(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return parse_brl_money(value)


class Base(DeclarativeBase):
    pass


class Municipality(Base):
    __tablename__ = "municipalities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC), nullable=False)

    source_checks: Mapped[list["SourceCheck"]] = relationship(
        back_populates="municipality", cascade="all, delete-orphan"
    )
    public_records: Mapped[list["PublicRecord"]] = relationship(
        back_populates="municipality", cascade="all, delete-orphan"
    )


class SourceCheck(Base):
    __tablename__ = "source_checks"
    __table_args__ = (UniqueConstraint("municipality_id", "label", "url", name="uq_source_check"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    municipality_id: Mapped[int] = mapped_column(ForeignKey("municipalities.id"), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    status_code: Mapped[int | None] = mapped_column(Integer)
    content_type: Mapped[str | None] = mapped_column(String(200))
    final_url: Mapped[str | None] = mapped_column(Text)
    accessible: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    blocked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)

    municipality: Mapped[Municipality] = relationship(back_populates="source_checks")


class PublicRecord(Base):
    __tablename__ = "public_records"
    __table_args__ = (
        UniqueConstraint(
            "municipality_id",
            "kind",
            "year",
            "detail_url",
            "process_number",
            "title",
            "movement_type",
            "movement_number",
            name="uq_public_record_municipality_kind_year_detail_url",
        ),
        Index("ix_public_records_mun_yr_kind", "municipality_id", "year", "kind"),
        Index("ix_public_records_att_lookup", "attention_score", "municipality_id", "year"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    municipality_id: Mapped[int] = mapped_column(ForeignKey("municipalities.id"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    year: Mapped[int | None] = mapped_column(Integer, index=True)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    detail_url: Mapped[str | None] = mapped_column(Text)
    process_number: Mapped[str | None] = mapped_column(String(120))
    modality: Mapped[str | None] = mapped_column(String(240))
    object: Mapped[str | None] = mapped_column(Text)
    opening_date: Mapped[str | None] = mapped_column(String(40))
    value: Mapped[Decimal | None] = mapped_column(MoneyType, nullable=True)
    status: Mapped[str | None] = mapped_column(String(120), index=True)
    published_at: Mapped[str | None] = mapped_column(String(40))
    movement_type: Mapped[str | None] = mapped_column(String(40))
    movement_number: Mapped[str | None] = mapped_column(String(120), index=True)
    favored: Mapped[str | None] = mapped_column(Text, index=True)
    movement_date: Mapped[str | None] = mapped_column(String(40), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    committed_value: Mapped[Decimal | None] = mapped_column(MoneyType, nullable=True)
    liquidated_value: Mapped[Decimal | None] = mapped_column(MoneyType, nullable=True)
    paid_value: Mapped[Decimal | None] = mapped_column(MoneyType, nullable=True)
    value_raw: Mapped[str | None] = mapped_column(String(120), nullable=True)
    committed_value_raw: Mapped[str | None] = mapped_column(String(120), nullable=True)
    liquidated_value_raw: Mapped[str | None] = mapped_column(String(120), nullable=True)
    paid_value_raw: Mapped[str | None] = mapped_column(String(120), nullable=True)
    attention_score: Mapped[int] = mapped_column(Integer, default=0, index=True)
    attention_reasons: Mapped[str | None] = mapped_column(Text, nullable=True)
    attention_keywords: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_json: Mapped[str | None] = mapped_column(Text)
    collected_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    municipality: Mapped[Municipality] = relationship(back_populates="public_records")


class SupplierProfile(Base):
    __tablename__ = "supplier_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    normalized_name: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    document: Mapped[str | None] = mapped_column(String(30), index=True, nullable=True)
    document_type: Mapped[str | None] = mapped_column(String(10), nullable=True)
    first_seen_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    first_seen_date: Mapped[str | None] = mapped_column(String(40), nullable=True)
    total_records: Mapped[int] = mapped_column(Integer, default=0)
    total_committed: Mapped[Decimal | None] = mapped_column(MoneyType, default=Decimal("0.00"))
    total_liquidated: Mapped[Decimal | None] = mapped_column(MoneyType, default=Decimal("0.00"))
    total_paid: Mapped[Decimal | None] = mapped_column(MoneyType, default=Decimal("0.00"))
    company_opening_date: Mapped[str | None] = mapped_column(String(40), nullable=True)
    company_status: Mapped[str | None] = mapped_column(String(60), nullable=True)
    company_main_activity: Mapped[str | None] = mapped_column(Text, nullable=True)
    company_size: Mapped[str | None] = mapped_column(String(60), nullable=True)
    sanctions_found: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sanctions_sources_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    external_checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    findings: Mapped[list["AnomalyFinding"]] = relationship(back_populates="supplier")


class AnomalyFinding(Base):
    __tablename__ = "anomaly_findings"
    __table_args__ = (
        Index("ix_anomaly_findings_mun_year_cat", "municipality", "year", "category"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    record_id: Mapped[int | None] = mapped_column(ForeignKey("public_records.id"), nullable=True, index=True)
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("supplier_profiles.id"), nullable=True, index=True)
    municipality_id: Mapped[int | None] = mapped_column(ForeignKey("municipalities.id"), nullable=True, index=True)
    municipality: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    year: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    category: Mapped[str] = mapped_column(String(60), index=True, nullable=False)
    severity: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    score: Mapped[int] = mapped_column(Integer, default=1, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC), nullable=False)

    record: Mapped[PublicRecord | None] = relationship()
    supplier: Mapped[SupplierProfile | None] = relationship(back_populates="findings")



from sqlalchemy import event
from sqlalchemy.orm import Session


@event.listens_for(Session, "before_flush")
def _auto_score_attention(session, flush_context, instances):
    for obj in session.new | session.dirty:
        if isinstance(obj, PublicRecord):
            if not obj.attention_score:
                content = " ".join(filter(None, [obj.title, obj.object, obj.description, obj.favored]))
                if content.strip():
                    import json
                    from analytics.anomalies import score_record_text

                    score, keywords, reasons = score_record_text(content)
                    obj.attention_score = score
                    obj.attention_keywords = json.dumps(keywords, ensure_ascii=False) if keywords else None
                    obj.attention_reasons = json.dumps(reasons, ensure_ascii=False) if reasons else None
