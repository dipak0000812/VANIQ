"""Upload validation. Nothing is trusted from the client: size, extension and actual decodability are checked."""
from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass

from src.config import Settings
from src.services.errors import ServiceError

ALLOWED_EXTENSIONS = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".opus", ".webm", ".aac", ".mp4", ".wma"}


@dataclass
class AudioInfo:
    duration_s: float
    codec: str
    sample_rate: int
    channels: int


def validate_upload(path: str, original_name: str, settings: Settings) -> AudioInfo:
    ext = os.path.splitext(original_name or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ServiceError(f"Unsupported file type {ext or '(none)'}. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
                           "unsupported_type", 415)
    size = os.path.getsize(path)
    if size == 0:
        raise ServiceError("The uploaded file is empty.", "empty_file", 400)
    if size > settings.max_upload_mb * 1024 * 1024:
        raise ServiceError(f"File exceeds the {settings.max_upload_mb} MB upload limit.", "too_large", 413)
    info = probe_audio(path)
    if info.duration_s <= 0:
        raise ServiceError("Could not determine audio duration; the file may be corrupt.", "bad_audio", 422)
    if info.duration_s < 0.2:
        raise ServiceError("Audio is shorter than 0.2 seconds.", "too_short", 422)
    if info.duration_s > settings.max_audio_seconds:
        raise ServiceError(f"Audio is {info.duration_s:.0f}s; the limit is {settings.max_audio_seconds}s.", "too_long", 413)
    return info


def probe_audio(path: str) -> AudioInfo:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", path],
            capture_output=True, check=True, timeout=30)
    except FileNotFoundError as exc:
        raise ServiceError("FFmpeg/ffprobe is not installed on the server.", "ffmpeg_missing", 500) from exc
    except subprocess.TimeoutExpired as exc:
        raise ServiceError("Audio inspection timed out.", "probe_timeout", 422) from exc
    except subprocess.CalledProcessError as exc:
        raise ServiceError("The file is not a readable audio file.", "bad_audio", 422) from exc
    try:
        data = json.loads(out.stdout or b"{}")
    except ValueError as exc:
        raise ServiceError("The file is not a readable audio file.", "bad_audio", 422) from exc
    audio = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), None)
    if audio is None:
        raise ServiceError("No audio stream found in the file.", "no_audio_stream", 422)
    raw_dur = audio.get("duration") or data.get("format", {}).get("duration") or 0
    try:
        duration = float(raw_dur)
    except (TypeError, ValueError):
        duration = 0.0
    return AudioInfo(duration_s=duration, codec=audio.get("codec_name", "?"),
                     sample_rate=int(audio.get("sample_rate") or 0), channels=int(audio.get("channels") or 0))
