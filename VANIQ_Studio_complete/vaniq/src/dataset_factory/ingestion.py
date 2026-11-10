import logging
import os
from datetime import datetime
from typing import Optional

from src.dataset_factory.audio import normalize_audio, load_audio
from src.dataset_factory.quality import measure_quality
from src.dataset_factory.segmentation import (
    detect_audio_activity_segments, generate_source_id, generate_clip_id, split_and_save_clips,
    AudioSegmentationError, AudioExtractionError
)
from src.dataset_factory.metadata import UNKNOWN

logger = logging.getLogger(__name__)

def process_source(file_path: str, output_root: str, transcribe: bool = False,
                   source_url: str = UNKNOWN, speaker_id: str = UNKNOWN,
                   dialect: str = UNKNOWN, permission_status: str = UNKNOWN,
                   permitted_usage: str = UNKNOWN) -> str:
    """
    Orchestrate dataset ingestion for a single source file.
    
    Pipeline:
    1. Normalize audio to mono, 16 kHz, PCM S16 LE WAV.
    2. Detect audio activity regions using energy-based segmentation.
    3. If "no_speech": mark source as `needs_review`, generate no clips.
    - If "success": extract clips per detected regions.
    - If "error": raise RuntimeError to prevent false clip generation.
    4. Measure quality metrics (RMS, peak, clipping, silence ratio).
    5. Update metadata.csv idempotently keyed by clip_id.
    
    Provenance fields (source_url, speaker_id, dialect, permission_status, permitted_usage)
    default to UNKNOWN and must be explicitly set by the user.
    Unknown permission is never interpreted as consent.
    """
    # Step 0: Validate source file is readable
    if not os.path.exists(file_path):
        raise RuntimeError(f"Source file does not exist: {file_path}")
    try:
        source_id = generate_source_id(file_path)
    except AudioSegmentationError as e:
        raise RuntimeError(f"Cannot read source file: {e}")
    
    # Define paths
    normalized_dir = os.path.join(output_root, "normalized")
    clips_dir = os.path.join(output_root, "clips")
    metadata_path = os.path.join(output_root, "metadata.csv")
    
    os.makedirs(normalized_dir, exist_ok=True)
    os.makedirs(clips_dir, exist_ok=True)
    
    normalized_path = os.path.join(normalized_dir, f"{source_id}.wav")
    
    # 1. Normalize audio
    logger.info(f"Normalizing {file_path}...")
    if not normalize_audio(file_path, normalized_path):
        raise RuntimeError("Audio normalization failed.")
    
    # 2. Detect audio activity segments
    logger.info("Detecting audio segments...")
    segments, vad_status = detect_audio_activity_segments(normalized_path)
    
    # 3. Handle outcomes
    if vad_status == "error":
        raise RuntimeError(
            f"Audio segmentation failed for {file_path}. "
            "Cannot generate clips from unprocessable audio."
        )
    
    if vad_status == "no_speech":
        logger.warning("No audio activity above threshold. Marking source as needs_review.")
        clips = []
    else:  # "success"
        logger.info(f"Found {len(segments)} audio region(s). Extracting clips...")
        try:
            clips = split_and_save_clips(normalized_path, segments, clips_dir)
        except AudioExtractionError as e:
            raise RuntimeError(f"Clip extraction failed: {e}")
    
    # 4. Measure quality and metadata
    from src.dataset_factory.metadata import MetadataManager
    metadata_manager = MetadataManager(metadata_path)
    
    if not clips:
        # Record no-speech source with needs_review status
        try:
            data, sr = load_audio(normalized_path)
            duration = len(data) / sr if sr > 0 else 0.0
            quality = measure_quality(data, sr)
        except Exception:
            duration = 0.0
            quality = {"rms_dbfs": -100.0, "peak_dbfs": -100.0, "clipping_count": 0, "silence_ratio": 1.0}
        
        metadata_manager.add_or_update_record(
            clip_info={
                "clip_id": source_id,
                "start_time": 0.0,
                "end_time": round(duration, 3),
                "duration": round(duration, 3),
                "source_path": file_path
            },
            quality=quality,
            source_id=source_id,
            source_url=source_url,
            speaker_id=speaker_id,
            dialect=dialect,
            permission_status=permission_status,
            permitted_usage=permitted_usage,
            review_status="needs_review",
            verified=False,
            auto_transcript="",
            manual_transcript="",
            detected_language=""
        )
    else:
        for clip in clips:
            clip["source_path"] = file_path
            data, sr = load_audio(clip["file_path"])
            quality = measure_quality(data, sr)
            
            # Optional transcription
            auto_transcript = ""
            detected_language = ""
            if transcribe:
                try:
                    from src.gnani.client import GnaniClient
                    client = GnaniClient()
                    result = client.transcribe(clip["file_path"])
                    auto_transcript = result.get("data", {}).get("transcript", "")
                    detected_language = result.get("data", {}).get("detected_language_code", "")
                except Exception as e:
                    logger.error("Transcription failed for %s: %s", clip["clip_id"], e)
            
            metadata_manager.add_or_update_record(
                clip_info=clip,
                quality=quality,
                source_id=source_id,
                source_url=source_url,
                speaker_id=speaker_id,
                dialect=dialect,
                permission_status=permission_status,
                permitted_usage=permitted_usage,
                review_status="needs_review",
                verified=False,
                auto_transcript=auto_transcript,
                manual_transcript="",
                detected_language=detected_language
            )
    
    metadata_manager.save()
    logger.info(f"Ingestion complete. Metadata saved to {metadata_path}")
    return metadata_path
