"""DB-backed ingestion: validate -> store -> normalize -> segment -> clip -> quality -> persist.

Reuses the Dataset Factory primitives (FFmpeg normalization, Auditok energy segmentation, quality metrics).
Provenance fields default to UNKNOWN; UNKNOWN permission is never treated as consent.
"""
from __future__ import annotations

import logging
import os
import shutil
from dataclasses import dataclass

from src.context import AppContext
from src.dataset_factory.audio import load_audio, normalize_audio
from src.dataset_factory.quality import measure_quality
from src.dataset_factory.segmentation import (AudioExtractionError, detect_audio_activity_segments,
                                              split_and_save_clips, generate_source_id)
from src.services.errors import ServiceError
from src.services.validation import validate_upload
from src.storage.repo import PERMISSION_STATUSES, PERMITTED_USAGES

logger = logging.getLogger(__name__)


@dataclass
class IngestResult:
    source: dict
    clips: list[dict]
    duplicate: bool
    segmentation_status: str


def quality_flags(q: dict, duration_s: float) -> list[str]:
    flags = []
    if q["rms_dbfs"] < -45:
        flags.append("low_level")
    if q["clipping_count"] > 0:
        flags.append("clipping")
    if q["silence_ratio"] > 0.8:
        flags.append("mostly_silent")
    if duration_s < 1.0:
        flags.append("very_short")
    return flags


def ingest_file(ctx: AppContext, path: str, original_name: str, *, source_url: str = "UNKNOWN",
                speaker_id: str = "UNKNOWN", dialect_label: str = "UNKNOWN", permission_status: str = "UNKNOWN",
                permitted_usage: str = "UNKNOWN", consent_notes: str = "", actor: str = "system") -> IngestResult:
    s, repo = ctx.settings, ctx.repo
    if permission_status not in PERMISSION_STATUSES:
        raise ServiceError(f"permission_status must be one of {PERMISSION_STATUSES}", "bad_permission", 422)
    if permitted_usage not in PERMITTED_USAGES:
        raise ServiceError(f"permitted_usage must be one of {PERMITTED_USAGES}", "bad_usage", 422)
    if permission_status != "granted" and permitted_usage not in ("UNKNOWN",):
        # a usage scope without granted permission is contradictory; keep it explicit
        raise ServiceError("permitted_usage can only be set when permission_status is 'granted'.",
                           "inconsistent_permission", 422)

    info = validate_upload(path, original_name, s)
    source_id = generate_source_id(path)
    existing = repo.get_source(source_id)
    if existing:
        logger.info("Source %s already ingested; returning existing records", source_id)
        return IngestResult(existing, repo.list_clips(source_id=source_id), True, existing["segmentation_status"])

    ext = os.path.splitext(original_name)[1].lower()
    stored = os.path.join(s.uploads_dir, f"{source_id}{ext}")
    shutil.copyfile(path, stored)
    normalized = os.path.join(s.normalized_dir, f"{source_id}.wav")
    if not normalize_audio(stored, normalized):
        os.remove(stored)
        raise ServiceError("Audio could not be converted (FFmpeg failed or is missing).", "normalize_failed", 422)

    segments, status = detect_audio_activity_segments(
        normalized, energy_threshold=s.seg_energy_threshold, max_dur=s.seg_max_dur_s)
    if status == "error":
        os.remove(stored)
        raise ServiceError("Audio segmentation failed; no clips were created.", "segmentation_failed", 422)

    safe_name = os.path.basename(original_name)[:200]
    source = repo.upsert_source({
        "id": source_id, "original_name": safe_name, "stored_path": stored, "normalized_path": normalized,
        "sha256": source_id, "source_url": source_url or "UNKNOWN", "speaker_id": speaker_id or "UNKNOWN",
        "dialect_label": dialect_label or "UNKNOWN", "permission_status": permission_status,
        "permitted_usage": permitted_usage, "consent_notes": consent_notes, "duration_s": round(info.duration_s, 3),
        "segmentation_status": status, "is_demo": 1 if s.is_demo else 0})
    repo.audit(actor, "ingest_source", "source", source_id, {"name": safe_name, "status": status})

    clips: list[dict] = []
    if status == "success":
        try:
            raw_clips = split_and_save_clips(normalized, segments, str(s.clips_dir))
        except AudioExtractionError as exc:
            raise ServiceError(f"Clip extraction failed: {exc}", "extraction_failed", 500) from exc
        for c in raw_clips:
            data, sr = load_audio(c["file_path"])
            q = measure_quality(data, sr)
            clips.append(repo.upsert_clip({
                "id": c["clip_id"], "source_id": source_id, "start_s": c["start_time"], "end_s": c["end_time"],
                "duration_s": c["duration"], "path": c["file_path"], "rms_dbfs": q["rms_dbfs"],
                "peak_dbfs": q["peak_dbfs"], "clipping_count": q["clipping_count"],
                "silence_ratio": q["silence_ratio"], "quality_flags": quality_flags(q, c["duration"])}))
    else:
        logger.warning("Source %s: no audio activity detected; no clips created", source_id)
    return IngestResult(source, clips, False, status)
