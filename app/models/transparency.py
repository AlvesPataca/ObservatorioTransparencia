from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl


RecordKind = Literal["licitacao", "contrato", "despesa"]


class SourceCheck(BaseModel):
    municipality: str
    label: str
    url: HttpUrl
    status_code: int | None = None
    content_type: str | None = None
    final_url: str | None = None
    accessible: bool = False
    blocked: bool = False
    notes: str | None = None


class PublicRecord(BaseModel):
    municipality: str
    kind: RecordKind
    source_url: HttpUrl
    title: str
    year: int | None = None
    detail_url: str | None = None
    process_number: str | None = None
    modality: str | None = None
    object: str | None = None
    opening_date: str | None = None
    value: str | None = None
    status: str | None = None
    published_at: str | None = None
    movement_type: str | None = None
    movement_number: str | None = None
    favored: str | None = None
    movement_date: str | None = None
    description: str | None = None
    committed_value: str | None = None
    liquidated_value: str | None = None
    paid_value: str | None = None
    value_raw: str | None = None
    committed_value_raw: str | None = None
    liquidated_value_raw: str | None = None
    paid_value_raw: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class CollectionResult(BaseModel):
    municipality: str
    collected_at: datetime = Field(default_factory=datetime.utcnow)
    source_checks: list[SourceCheck] = Field(default_factory=list)
    records: list[PublicRecord] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
