"""Pydantic models: extracted request, carrier options, and API contracts."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.llm.base import CRITICAL_FIELDS


class ExtractedRequest(BaseModel):
    """Structured cargo request produced by the extractor node."""

    origin: str | None = None
    destination: str | None = None
    cargo_type: str | None = None
    weight_t: float | None = None
    volume_m3: float | None = None
    body_type: str | None = None
    date: str | None = None
    payment: Literal["cash", "noncash"] | None = None
    urgent: bool = False
    load_type: Literal["full", "partial"] | None = None
    missing_fields: list[str] = Field(default_factory=list)

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> ExtractedRequest:
        """Coerce a raw extractor dict and compute `missing_fields` (D11)."""
        allowed = set(cls.model_fields) - {"missing_fields"}
        data = {k: v for k, v in (raw or {}).items() if k in allowed}
        # Normalize empty strings to None.
        for k, v in list(data.items()):
            if isinstance(v, str) and not v.strip():
                data[k] = None
        obj = cls(**data)
        obj.missing_fields = [f for f in CRITICAL_FIELDS if getattr(obj, f) in (None, "")]
        return obj

    @property
    def is_complete(self) -> bool:
        return not self.missing_fields


class CarrierOption(BaseModel):
    carrier: str
    truck_plate: str
    body_type: str
    capacity_t: float
    current_city: str
    rating: float
    distance_km: float
    eta_days: int
    price: float
    currency: str
    price_breakdown: dict[str, Any]


# ---- API contracts --------------------------------------------------------

class DispatchRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Free-text cargo request (RU)")
    provider: str | None = Field(default=None, description="Override LLM_PROVIDER")


class StepTrace(BaseModel):
    step: str
    status: str
    detail: Any | None = None


DispatchStatus = Literal["ok", "clarify", "refused", "no_options", "no_route"]


class DispatchResponse(BaseModel):
    status: DispatchStatus
    reply: str
    request: ExtractedRequest | None = None
    clarify_question: str | None = None
    options: list[CarrierOption] = Field(default_factory=list)
    trace: list[StepTrace] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str
    provider: str
    db_ready: bool
