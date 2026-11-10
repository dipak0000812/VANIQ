import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.config import load_settings  # noqa: E402
from src.context import build_context  # noqa: E402
from src.services.demo import synth_wav  # noqa: E402


def _ctx(tmp_path, monkeypatch, mode, key=None):
    monkeypatch.setenv("VANIQ_MODE", mode)
    monkeypatch.setenv("VANIQ_DATA_DIR", str(tmp_path / "data"))
    if key:
        monkeypatch.setenv("GNANI_API_KEY", key)
    else:
        monkeypatch.delenv("GNANI_API_KEY", raising=False)
    return build_context(load_settings(load_env_file=False))


@pytest.fixture
def live_ctx(tmp_path, monkeypatch):
    return _ctx(tmp_path, monkeypatch, "live")


@pytest.fixture
def live_ctx_with_key(tmp_path, monkeypatch):
    return _ctx(tmp_path, monkeypatch, "live", key="test-key")


@pytest.fixture
def demo_ctx(tmp_path, monkeypatch):
    return _ctx(tmp_path, monkeypatch, "demo")


@pytest.fixture
def tone_wav(tmp_path):
    """Two tone bursts separated by silence -> two segments. Deterministic synthetic fixture (not speech)."""
    p = tmp_path / "tones.wav"
    synth_wav(str(p), freq=440)
    return str(p)


@pytest.fixture
def make_tone(tmp_path):
    def _make(freq, name=None):
        p = tmp_path / (name or f"tone_{int(freq)}.wav")
        synth_wav(str(p), freq=freq)
        return str(p)
    return _make
