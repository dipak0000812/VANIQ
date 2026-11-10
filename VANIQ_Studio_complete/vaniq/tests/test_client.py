import pytest
import httpx
from src.gnani.client import GnaniClient, GnaniError, GnaniAuthError, GnaniNetworkError
from unittest.mock import MagicMock, patch
from run_experiments import run_experiment

@pytest.fixture
def wav(tmp_path):
    """Tiny deterministic WAV so tests never depend on private recordings."""
    import numpy as np
    from scipy.io import wavfile
    p = tmp_path / "clip.wav"
    wavfile.write(p, 16000, (np.sin(np.linspace(0, 440, 8000)) * 8000).astype(np.int16))
    return str(p)


def test_missing_api_key(monkeypatch):
    monkeypatch.delenv("GNANI_API_KEY", raising=False)
    with pytest.raises(ValueError, match="GNANI_API_KEY environment variable not set"):
        GnaniClient()

def test_multipart_request_structure(monkeypatch, wav):
    monkeypatch.setenv("GNANI_API_KEY", "test-key-123")
    client = GnaniClient()
    
    with patch("httpx.Client.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "success"}
        mock_post.return_value = mock_response
        
        # Test signature and multipart payload
        client.transcribe(wav, model="prisma-v3.0", language_code="indic-auto")
        
        args, kwargs = mock_post.call_args
        assert kwargs["headers"]["X-API-Key-ID"] == "test-key-123"
        # Confirm model and language_code are in the 'data' (multipart fields)
        assert kwargs["data"]["model"] == "prisma-v3.0"
        assert kwargs["data"]["language_code"] == "indic-auto"
        # Confirm audio_file is in 'files'
        assert "audio_file" in kwargs["files"]

def test_experiment_runner_invocation(monkeypatch):
    monkeypatch.setenv("GNANI_API_KEY", "test-key-123")
    with patch("src.gnani.client.GnaniClient.transcribe") as mock_transcribe:
        mock_transcribe.return_value = {"data": {"status": "success"}, "latency": 0.1}
        with patch("builtins.open", create=True):
            with patch("json.dump"), patch("os.makedirs"):
                run_experiment("TestConfig", "model-x", "lang-y", "dummy.json", audio_path="a.wav")

        mock_transcribe.assert_called_with("a.wav", model="model-x", language_code="lang-y")

def test_api_error_handling(monkeypatch, wav):
    monkeypatch.setenv("GNANI_API_KEY", "test-key-123")
    client = GnaniClient()
    
    with patch("httpx.Client.post") as mock_post:
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError("401", request=None, response=mock_response)
        mock_post.return_value = mock_response
        
        with pytest.raises(GnaniError):
            client.transcribe(wav)


def _resp(status, payload=None):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = payload or {}
    if status >= 400:
        r.raise_for_status.side_effect = httpx.HTTPStatusError(str(status), request=None, response=r)
    return r


def test_auth_error_is_not_retried(monkeypatch, wav):
    c = GnaniClient(api_key="k", max_retries=3, retry_backoff_s=0)
    with patch("httpx.Client.post", return_value=_resp(401)) as post:
        with pytest.raises(GnaniAuthError):
            c.transcribe(wav)
        assert post.call_count == 1


def test_server_error_is_retried_then_succeeds(wav):
    c = GnaniClient(api_key="k", max_retries=2, retry_backoff_s=0)
    with patch("httpx.Client.post", side_effect=[_resp(503), _resp(200, {"transcript": "x"})]) as post:
        out = c.transcribe(wav)
        assert out["data"]["transcript"] == "x"
        assert post.call_count == 2


def test_network_failure_surfaces_as_network_error(wav):
    c = GnaniClient(api_key="k", max_retries=1, retry_backoff_s=0)
    with patch("httpx.Client.post", side_effect=httpx.ConnectError("boom")) as post:
        with pytest.raises(GnaniNetworkError):
            c.transcribe(wav)
        assert post.call_count == 2


def test_missing_audio_file_raises_filenotfound():
    c = GnaniClient(api_key="k")
    with pytest.raises(FileNotFoundError):
        c.transcribe("/nonexistent/file.wav")
