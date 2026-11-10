from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional


class STTProviderError(Exception):
    """Provider call failed; message is safe to show to the user."""

    def __init__(self, message: str, code: str = "stt_error", status: int = 502):
        super().__init__(message)
        self.code, self.status = code, status


class STTNotConfigured(STTProviderError):
    def __init__(self, message: str = "No STT provider is configured. Set GNANI_API_KEY in .env, "
                                      "or run in demo mode (VANIQ_MODE=demo), or import an existing transcript."):
        super().__init__(message, code="stt_not_configured", status=503)


@dataclass
class STTResult:
    transcript: str
    provider: str                       # gnani | demo-mock
    model: Optional[str]
    language_code_requested: str
    detected_language_code: Optional[str]
    request_id: Optional[str]
    latency_s: Optional[float]
    raw_response: Any
    is_synthetic: bool = False          # True => text is NOT a transcription of the audio


class STTProvider(ABC):
    name = "abstract"

    @abstractmethod
    def transcribe(self, audio_path: str, language_code: str) -> STTResult: ...
