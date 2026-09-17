from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class MunicipalityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class PublicRecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    municipality_id: int
    municipality: str | None = None
    kind: str
    year: int | None = None
    source_url: str
    title: str
    detail_url: str | None = None
    published_at: str | None = None
    movement_type: str | None = None
    movement_number: str | None = None
    favored: str | None = None
    movement_date: str | None = None
    description: str | None = None
    committed_value: Decimal | str | None = None
    liquidated_value: Decimal | str | None = None
    paid_value: Decimal | str | None = None
    value: Decimal | str | None = None
    value_raw: str | None = None
    committed_value_raw: str | None = None
    liquidated_value_raw: str | None = None
    paid_value_raw: str | None = None
    process_number: str | None = None
    modality: str | None = None
    object: str | None = None
    opening_date: str | None = None
    status: str | None = None
    raw_json: str | None = None
    collected_at: Any | None = None
    created_at: Any | None = None
    updated_at: Any | None = None


class ExpensesFinancialTotalsOut(BaseModel):
    total_empenhado: Decimal = Decimal("0.00")
    total_liquidado: Decimal = Decimal("0.00")
    total_pago: Decimal = Decimal("0.00")


class SummaryOut(BaseModel):
    totals_by_municipality: dict[str, int] = Field(default_factory=dict)
    totals_by_kind: dict[str, int] = Field(default_factory=dict)
    totals_by_year: dict[str, int] = Field(default_factory=dict)
    expenses_financial_totals: ExpensesFinancialTotalsOut = Field(default_factory=ExpensesFinancialTotalsOut)
    missing_value_count: int = 0
    attention_count_limited: int = 0

    # Campos de compatibilidade retroativa
    records_by_municipality: dict[str, int] = Field(default_factory=dict)
    records_by_kind: dict[str, int] = Field(default_factory=dict)
    records_by_status: dict[str, int] = Field(default_factory=dict)
    records_missing_value: int = 0
    attention_count: int = 0
    available_years: list[int] = Field(default_factory=list)
    available_municipalities: list[str] = Field(default_factory=list)
    selected_year: int | None = None
    selected_municipality: str | None = None
    selected_kind: str | None = None


class AttentionItemOut(BaseModel):
    id: int
    municipality: str | None = None
    kind: str
    year: int | None = None
    source_url: str | None = None
    title: str
    object: str | None = None
    description: str | None = None
    detail_url: str | None = None
    movement_type: str | None = None
    movement_number: str | None = None
    process_number: str | None = None
    favored: str | None = None
    movement_date: str | None = None
    raw_json: str | None = None
    value: str | None = None
    committed_value: str | None = None
    score: int = 0
    reasons: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    note: str = "Ponto de atenção para análise contextual; não indica irregularidade por si só."


class AttentionPageOut(BaseModel):
    total: int = 0
    items: list[AttentionItemOut] = Field(default_factory=list)
    error: str | None = None


class AnomalyFindingOut(BaseModel):
    id: int
    record_id: int | None = None
    supplier_id: int | None = None
    municipality: str
    year: int | None = None
    category: str
    severity: str
    score: int = 1
    title: str
    explanation: str
    evidence: dict[str, Any] = Field(default_factory=dict)
    evidence_json: str | None = None
    favored: str | None = None
    movement_number: str | None = None
    detail_url: str | None = None
    source_url: str | None = None
    value: str | None = None
    created_at: datetime | None = None


class AnomaliesPageOut(BaseModel):
    total: int = 0
    items: list[AnomalyFindingOut] = Field(default_factory=list)
    categories_summary: dict[str, int] = Field(default_factory=dict)
    severities_summary: dict[str, int] = Field(default_factory=dict)
    error: str | None = None



class FavoredExpenseOut(BaseModel):
    favored: str
    municipality: str
    year: int | None = None
    movements_count: int = 0
    total_empenhado: Decimal = Decimal("0.00")
    total_liquidado: Decimal = Decimal("0.00")
    total_pago: Decimal = Decimal("0.00")


class ExpensesSummaryOut(BaseModel):
    financial_totals: ExpensesFinancialTotalsOut = Field(default_factory=ExpensesFinancialTotalsOut)
    by_municipality: dict[str, dict[str, Decimal]] = Field(default_factory=dict)
    by_year: dict[str, dict[str, Decimal]] = Field(default_factory=dict)
    top_favored: list[FavoredExpenseOut] = Field(default_factory=list)
    selected_municipality: str | None = None
    selected_year: int | None = None


class RecordsPageOut(BaseModel):
    total: int = 0
    items: list[PublicRecordOut] = Field(default_factory=list)
    error: str | None = None


class AnalysisOut(BaseModel):
    records_by_municipality: dict[str, int] = Field(default_factory=dict)
    records_by_kind: dict[str, int] = Field(default_factory=dict)
    records_by_status: dict[str, int] = Field(default_factory=dict)
    top_modalities: list[dict[str, Any]] = Field(default_factory=list)
    records_missing_value: list[dict[str, Any]] = Field(default_factory=list)
    recent_records: list[dict[str, Any]] = Field(default_factory=list)
    duplicate_titles: list[dict[str, Any]] = Field(default_factory=list)
    same_title_across_municipalities: list[dict[str, Any]] = Field(default_factory=list)
    suspicious_keywords: list[dict[str, Any]] = Field(default_factory=list)