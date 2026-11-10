"""Typed view of the Gnani/Vachana STT response.

Only fields observed in real responses stored in this repository's pilot results are modelled
(success, request_id, transcript, model, processing_time, end_to_end_latency,
detected_language_code). Unknown extra fields are preserved in `extra`, never discarded.
"""
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


class TranscriptionResponse(BaseModel):
    model_config = ConfigDict(extra="allow", protected_namespaces=())

    success: Optional[bool] = None
    request_id: Optional[str] = None
    transcript: Optional[str] = None
    model: Optional[str] = None
    processing_time: Optional[float] = None
    end_to_end_latency: Optional[float] = None
    detected_language_code: Optional[str] = None
    error: Optional[str] = None

    @property
    def extra(self) -> dict[str, Any]:
        return dict(self.model_extra or {})
