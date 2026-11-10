from __future__ import annotations

from src.config import Settings
from src.stt.base import STTNotConfigured, STTProvider
from src.stt.demo_provider import DemoProvider
from src.stt.gnani_provider import GnaniProvider


def get_provider(settings: Settings, name: str | None = None) -> STTProvider:
    """Demo mode always uses the labelled demo provider. Live mode never falls back to a mock."""
    if settings.is_demo:
        return DemoProvider()
    name = name or "gnani"
    if name == "gnani":
        if not settings.stt_configured:
            raise STTNotConfigured()
        return GnaniProvider(settings)
    raise ValueError(f"Unknown STT provider {name!r}")
