"""Client for the Gnani Prisma (Vachana) speech-to-text HTTP API.

Request contract (as used by the original pilot code and confirmed by its stored responses):
  POST {base_url}/stt/v3
  header  X-API-Key-ID: <key>
  form    model, language_code
  file    audio_file

`transcribe()` keeps its original signature and return shape
({"data": <json>, "latency": <seconds>}) so existing callers keep working.
Failures are raised as `GnaniError` subclasses with a user-presentable message.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


class GnaniError(Exception):
    """Base class for STT client failures."""

    def __init__(self, message: str, *, status_code: Optional[int] = None, retryable: bool = False):
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable


class GnaniAuthError(GnaniError):
    pass


class GnaniNetworkError(GnaniError):
    pass


class GnaniAPIError(GnaniError):
    pass


class GnaniClient:
    def __init__(self, base_url: str = "https://api.vachana.ai", timeout: float = 30.0,
                 api_key: Optional[str] = None, max_retries: int = 2, retry_backoff_s: float = 1.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.api_key = api_key or os.getenv("GNANI_API_KEY")
        self.max_retries = max(0, int(max_retries))
        self.retry_backoff_s = retry_backoff_s
        if not self.api_key:
            raise ValueError("GNANI_API_KEY environment variable not set")

    def transcribe(self, audio_path: str, model: str = "prisma-v3.0",
                   language_code: str = "indic-auto") -> dict:
        if not os.path.isfile(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        headers = {"X-API-Key-ID": self.api_key}
        attempt = 0
        while True:
            try:
                return self._post_once(audio_path, headers, model, language_code)
            except GnaniError as exc:
                if exc.retryable and attempt < self.max_retries:
                    delay = self.retry_backoff_s * (2 ** attempt)
                    logger.warning("Gnani request failed (%s); retry %d/%d in %.1fs",
                                   exc, attempt + 1, self.max_retries, delay)
                    time.sleep(delay)
                    attempt += 1
                    continue
                raise

    def _post_once(self, audio_path: str, headers: dict, model: str, language_code: str) -> dict:
        with open(audio_path, "rb") as f:
            files = {"audio_file": (os.path.basename(audio_path), f, "audio/wav")}
            data = {"model": model, "language_code": language_code}
            start = time.perf_counter()
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    response = client.post(f"{self.base_url}/stt/v3", headers=headers,
                                           data=data, files=files)
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                raise GnaniNetworkError(f"Network error contacting STT provider: {exc}",
                                        retryable=True) from exc
            latency = time.perf_counter() - start

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            status = getattr(exc.response, "status_code", None)
            if status in (401, 403):
                raise GnaniAuthError("STT provider rejected the API key", status_code=status) from exc
            if isinstance(status, int) and (status == 429 or status >= 500):
                raise GnaniAPIError(f"STT provider error (HTTP {status})", status_code=status,
                                    retryable=True) from exc
            raise GnaniAPIError(f"STT provider error (HTTP {status})", status_code=status) from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise GnaniAPIError("STT provider returned a non-JSON response") from exc
        logger.info("Gnani STT ok: model=%s lang=%s latency=%.2fs", model, language_code, latency)
        return {"data": payload, "latency": latency}
