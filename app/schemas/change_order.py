from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.enums import ApprovalStatus, ChangeOrderType, RoutingDecision
from app.schemas.fields import DateField, ExtractedField, LineItem


class DocumentSection(BaseModel):
    filename: str | None = None
    file_type: str | None = None
    page_count: int | None = None


class ProjectSection(BaseModel):
    name: ExtractedField[str] = Field(default_factory=ExtractedField[str])
    number: ExtractedField[str] = Field(default_factory=ExtractedField[str])
    address: ExtractedField[str] = Field(default_factory=ExtractedField[str])


class Party(BaseModel):
    name: ExtractedField[str] = Field(default_factory=ExtractedField[str])


class PartiesSection(BaseModel):
    owner: Party = Field(default_factory=Party)
    contractor: Party = Field(default_factory=Party)
    subcontractor: Party = Field(default_factory=Party)


class ChangeOrderSection(BaseModel):
    number: ExtractedField[str] = Field(default_factory=ExtractedField[str])
    title: ExtractedField[str] = Field(default_factory=ExtractedField[str])
    reason: ExtractedField[str] = Field(default_factory=ExtractedField[str])
    scope: ExtractedField[str] = Field(default_factory=ExtractedField[str])
    type: ExtractedField[ChangeOrderType] = Field(default_factory=ExtractedField[ChangeOrderType])
    is_proposed: ExtractedField[bool] = Field(default_factory=ExtractedField[bool])


class FinancialsSection(BaseModel):
    line_items: list[LineItem] = Field(default_factory=list)
    subtotal: ExtractedField[Decimal] = Field(default_factory=ExtractedField[Decimal])
    markup_pct: ExtractedField[float] = Field(default_factory=ExtractedField[float])
    markup_amount: ExtractedField[Decimal] = Field(default_factory=ExtractedField[Decimal])
    total: ExtractedField[Decimal] = Field(default_factory=ExtractedField[Decimal])
    original_contract_sum: ExtractedField[Decimal] = Field(default_factory=ExtractedField[Decimal])
    net_previous_changes: ExtractedField[Decimal] = Field(default_factory=ExtractedField[Decimal])
    contract_sum_prior: ExtractedField[Decimal] = Field(default_factory=ExtractedField[Decimal])
    new_contract_sum: ExtractedField[Decimal] = Field(default_factory=ExtractedField[Decimal])


class ScheduleSection(BaseModel):
    days_added: ExtractedField[int] = Field(default_factory=ExtractedField[int])
    revised_completion_date: DateField = Field(default_factory=DateField)


class ApprovalSection(BaseModel):
    status: ExtractedField[ApprovalStatus] = Field(default_factory=ExtractedField[ApprovalStatus])
    approved_by: ExtractedField[str] = Field(default_factory=ExtractedField[str])
    date: DateField = Field(default_factory=DateField)


class ExtractionWarning(BaseModel):
    code: str
    message: str
    field_path: str | None = None


class ChangeOrderExtraction(BaseModel):
    document: DocumentSection = Field(default_factory=DocumentSection)
    project: ProjectSection = Field(default_factory=ProjectSection)
    parties: PartiesSection = Field(default_factory=PartiesSection)
    change_order: ChangeOrderSection = Field(default_factory=ChangeOrderSection)
    financials: FinancialsSection = Field(default_factory=FinancialsSection)
    schedule: ScheduleSection = Field(default_factory=ScheduleSection)
    approval: ApprovalSection = Field(default_factory=ApprovalSection)
    warnings: list[ExtractionWarning] = Field(default_factory=list)


class ExtractionResult(BaseModel):
    source_file: str
    extractions: list[ChangeOrderExtraction] = Field(default_factory=list)
    validation: list[dict[str, Any]] = Field(default_factory=list)
    confidence: list[dict[str, Any]] = Field(default_factory=list)
    routing_decision: RoutingDecision = RoutingDecision.NEEDS_REVIEW
    errors: list[str] = Field(default_factory=list)
