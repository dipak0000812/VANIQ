from __future__ import annotations

import logging

from src.config import Settings
from src.gnani.client import GnaniAuthError, GnaniClient, GnaniError, GnaniNetworkError
from src.gnani.models import TranscriptionResponse
from src.stt.base import STTNotConfigured, STTProvider, STTProviderError, STTResult

logger = logging.getLogger(__name__)


class GnaniProvider(STTProvider):
    name = "gnani"

    def __init__(self, settings: Settings):
        if not settings.gnani_api_key:
            raise STTNotConfigured()
        self.settings = settings
        self.client = GnaniClient(base_url=settings.gnani_base_url, timeout=settings.gnani_timeout_s,
                                  api_key=settings.gnani_api_key, max_retries=settings.gnani_max_retries)

    def transcribe(self, audio_path: str, language_code: str) -> STTResult:
        try:
            res = self.client.transcribe(audio_path, model=self.settings.gnani_model, language_code=language_code)
        except GnaniAuthError as exc:
            raise STTProviderError("The STT provider rejected the API key. Check GNANI_API_KEY.",
                                   code="stt_auth", status=502) from exc
        except GnaniNetworkError as exc:
            raise STTProviderError("Could not reach the STT provider (network error or timeout). Try again.",
                                   code="stt_network", status=504) from exc
        except GnaniError as exc:
            raise STTProviderError(f"STT provider error: {exc}", code="stt_api", status=502) from exc
        except FileNotFoundError as exc:
            raise STTProviderError(str(exc), code="audio_missing", status=404) from exc

        data = res["data"]
        parsed = TranscriptionResponse.model_validate(data if isinstance(data, dict) else {})
        if parsed.success is False or parsed.transcript is None:
            raise STTProviderError(f"STT provider returned no transcript ({parsed.error or 'unspecified reason'}).",
                                   code="stt_empty", status=502)
        return STTResult(transcript=parsed.transcript, provider=self.name, model=parsed.model or self.settings.gnani_model,
                         language_code_requested=language_code, detected_language_code=parsed.detected_language_code,
                         request_id=parsed.request_id, latency_s=res["latency"], raw_response=data)
