"""Typed contracts for every pipeline step (Phase 1) and the trace schema (Phase 2)."""
from __future__ import annotations
from typing import Any, Literal, Optional
from pydantic import BaseModel, Field

DocType = Literal["contract", "invoice", "report", "correspondence"]


class Entity(BaseModel):
    type: Literal["person", "org", "date", "amount", "term"]
    value: str


# ---- Step inputs / outputs -------------------------------------------------
class RawDoc(BaseModel):
    doc_id: str
    text: str

class IntakeOut(BaseModel):
    doc_id: str
    text: str
    char_count: int
    fmt: Literal["text", "markdown", "pdf_text"]
    confidence: int = 5

class ExtractionIn(BaseModel):
    text: str

class ExtractionOut(BaseModel):
    entities: list[Entity]
    confidence: int = Field(ge=1, le=5)

class ClassificationIn(BaseModel):
    text: str
    entities: list[Entity]

class ClassificationOut(BaseModel):
    doc_type: DocType
    rationale: str
    confidence: int = Field(ge=1, le=5)

class SummaryIn(BaseModel):
    text: str
    doc_type: DocType
    entities: list[Entity]

class SummaryOut(BaseModel):
    headline: str
    bullets: list[str]
    doc_type: DocType
    confidence: int = Field(ge=1, le=5)


# ---- Trace schema ----------------------------------------------------------
class Span(BaseModel):
    span_id: str
    step: str
    status: Literal["ok", "error"] = "ok"
    input: dict[str, Any] = {}
    output: Optional[dict[str, Any]] = None
    prompt: str = ""
    raw_response: str = ""
    tokens: int = 0
    latency_ms: float = 0.0
    confidence: Optional[int] = None
    error: Optional[str] = None
    judge: Optional[dict[str, Any]] = None  # filled by the backward analyzer


class Trace(BaseModel):
    trace_id: str
    doc_id: str
    ts: str
    status: Literal["success", "degraded", "failure"] = "success"
    spans: list[Span] = []
    final_output: Optional[dict[str, Any]] = None
    final_score: Optional[float] = None
    meta: dict[str, Any] = {}
    diagnosis: Optional[dict[str, Any]] = None
    flagged: bool = False
    confirmed: bool = False
