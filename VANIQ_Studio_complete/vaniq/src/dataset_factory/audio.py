import logging
import subprocess

import numpy as np
from scipy.io import wavfile

logger = logging.getLogger(__name__)


def normalize_audio(input_path, output_path, target_sr=16000):
    """Normalize audio to mono, target sample rate, and PCM S16 LE using FFmpeg.

    Returns True on success, False on failure (missing FFmpeg, undecodable input).
    """
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-vn", "-ar", str(target_sr), "-ac", "1", "-acodec", "pcm_s16le",
        output_path,
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        return True
    except FileNotFoundError:
        logger.error("FFmpeg executable not found; install FFmpeg and ensure it is on PATH")
        return False
    except subprocess.CalledProcessError as e:
        logger.error("FFmpeg error: %s", (e.stderr or b"").decode(errors="replace")[-500:])
        return False


def load_audio(path):
    """Load a WAV into a numpy array (int16 converted to float32 in [-1, 1])."""
    sr, data = wavfile.read(path)
    if data.dtype == np.int16:
        data = data.astype(np.float32) / 32768.0
    return data, sr
