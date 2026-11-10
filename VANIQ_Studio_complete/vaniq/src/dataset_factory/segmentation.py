import logging
import os
import hashlib
from typing import List, Tuple, Optional
import auditok as au

logger = logging.getLogger(__name__)

# VAD Configuration using Auditok's energy-based segmentation
# 
# Auditok's AudioEnergyValidator computes energy as: 20 * log10(sqrt(dot(x,x)/len(x)))
# on int16 amplitude scale. Default threshold is 50 (on this scale).
# 
# This is NOT a "speech-specific" threshold — it distinguishes audible events from silence.
# It will also detect music, loud environmental sounds, etc.
# 
# Threshold Calibration Note:
# The threshold of 50 is an initial default that requires calibration on real recordings
# for your specific environment (recording equipment, room acoustics, microphone gain).
# Users should verify with their own data and adjust VAD_ENERGY_THRESHOLD accordingly.

VAD_ENERGY_THRESHOLD = 50  # Default from auditok; calibrate on your data

# Segmentation parameters (auditok defaults, documented for clarity)
VAD_MIN_DURATION = 0.2      # Minimum event duration (seconds)
VAD_MAX_DURATION = 15.0     # Maximum event duration (seconds). Was 5.0, which cut continuous speech mid-phrase.
VAD_MAX_SILENCE = 0.3       # Max continuous silence within event (seconds)
VAD_MAX_LEADING_SILENCE = 0.0  # No leading silence prepended
VAD_MAX_TRAILING_SILENCE = 0.15  # Keep 150ms trailing silence for natural fade

class AudioSegmentationError(Exception):
    """Raised when audio segmentation fails completely."""
    pass

class AudioExtractionError(Exception):
    """Raised when audio clip extraction fails."""
    pass

def _file_content_hash(file_path: str) -> str:
    """
    Compute SHA-256 hash of the complete file, streaming to handle large files.
    
    Raises:
        AudioSegmentationError: If the file cannot be read at all.
    """
    sha = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                sha.update(chunk)
        return sha.hexdigest()
    except Exception as e:
        raise AudioSegmentationError(f"Cannot read file for hashing: {file_path}: {e}")

def generate_source_id(file_path: str) -> str:
    """Generate a stable source ID from the complete file's SHA-256 hash.
    
    Stable across file moves and renames because it depends only on content.
    """
    return _file_content_hash(file_path)[:16]

def generate_clip_id(file_path: str, start_time: float, end_time: float,
                     source_hash: Optional[str] = None) -> str:
    """Generate a stable clip ID based on source content hash + timestamps."""
    source_hash = source_hash or _file_content_hash(file_path)
    hash_input = f"{source_hash}:{start_time:.6f}:{end_time:.6f}".encode('utf-8')
    return hashlib.sha256(hash_input).hexdigest()[:16]

def detect_audio_activity_segments(audio_path: str, energy_threshold: float = VAD_ENERGY_THRESHOLD,
                                   max_dur: float = VAD_MAX_DURATION) -> Tuple[List[Tuple[float, float]], str]:
    """Detect audio activity regions using Auditok's energy-based segmentation.
    
    Uses au.split() with AudioEnergyValidator. Returns segments as (start, end) tuples
    and a status string indicating the outcome.
    
    Status values:
    - "success": audio regions detected above threshold
    - "no_speech": no regions above threshold found (silent / sub-threshold audio)
    - "error": VAD execution failed (invalid file, etc.)
    
    Important: This is energy-based segmentation, NOT a speech-specific VAD. It will
    detect any audible event above the threshold (speech, music, loud noise, etc.).
    All generated clips are marked `needs_review` until manual verification.
    
    The Auditok AudioRegion provides .start, .end, and .duration attributes directly.
    """
    segments = []
    status = "error"
    
    try:
        regions = au.split(
            audio_path,
            min_dur=VAD_MIN_DURATION,
            max_dur=max_dur,
            max_silence=VAD_MAX_SILENCE,
            max_leading_silence=VAD_MAX_LEADING_SILENCE,
            max_trailing_silence=VAD_MAX_TRAILING_SILENCE,
            energy_threshold=energy_threshold,
        )
        
        for region in regions:
            start = float(region.start)
            end = float(region.end) if hasattr(region, 'end') else None
            
            if end is None:
                dur = float(region.duration) if hasattr(region, 'duration') else 0.0
                end = start + dur
            
            segments.append((start, end))
        
        status = "no_speech" if not segments else "success"
        
    except Exception as e:
        logger.error("Audio segmentation failed: %s", e)
        segments = []
        status = "error"
    
    return segments, status

def split_and_save_clips(source_path: str, segments: List[Tuple[float, float]], output_dir: str) -> List[dict]:
    """Split source audio into clips using FFmpeg with explicit timestamps.
    
    Uses -ss and -t (duration) for precise, reproducible extraction.
    Preserves mono, 16 kHz, PCM S16 LE output format.
    
    Raises:
        AudioExtractionError: If any clip extraction fails.
    """
    import subprocess
    import json
    
    os.makedirs(output_dir, exist_ok=True)
    clips = []
    extraction_errors = []
    source_hash = _file_content_hash(source_path)
    
    for idx, (start, end) in enumerate(segments):
        duration = end - start
        clip_id = generate_clip_id(source_path, start, end, source_hash=source_hash)
        output_path = os.path.join(output_dir, f"{clip_id}.wav")
        
        # FFmpeg: -ss for start, -t for duration (more precise than -to)
        cmd = [
            "ffmpeg", "-y", "-i", source_path,
            "-ss", str(start),
            "-t", str(duration),
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            output_path
        ]
        try:
            result = subprocess.run(cmd, check=True, capture_output=True)
            
            # Verify the output file
            # Check file exists
            if not os.path.exists(output_path):
                raise subprocess.CalledProcessError(-1, cmd, f"Output file not created: {output_path}")
            
            # Check file size is reasonable (at least 100 bytes for a valid WAV)
            file_size = os.path.getsize(output_path)
            if file_size < 100:
                raise AudioExtractionError(f"Output file too small: {file_size} bytes")
            
            clips.append({
                "clip_id": clip_id,
                "start_time": round(start, 3),
                "end_time": round(end, 3),
                "duration": round(duration, 3),
                "file_path": output_path
            })
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.decode() if e.stderr else str(e)
            extraction_errors.append(f"Clip {idx} failed: {error_msg}")
            logger.error("Extraction failed for clip %s: %s", idx, error_msg)
        except AudioExtractionError as e:
            extraction_errors.append(str(e))
            logger.error("Extraction validation failed: %s", e)
    
    # Report failed extractions as error
    if extraction_errors:
        raise AudioExtractionError("One or more clip extractions failed:\n" + "\n".join(extraction_errors))
            
    return clips

# Backward compatibility alias
detect_speech_segments = detect_audio_activity_segments
