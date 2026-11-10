"""Transcription and correction proposal orchestration. Raw STT output is stored verbatim and never edited."""
from __future__ import annotations

import logging
import re

from src.baseline import role_for_transcript
from src.context import AppContext
from src.correction import get_backend
from src.correction.models import LexiconEntry
from src.evaluation.metrics import detect_script
from src.services.errors import ServiceError
from src.stt import STTProviderError, get_provider

logger = logging.getLogger(__name__)
_LANG_RE = re.compile(r"^(indic-auto|[a-z]{2,3}(-[A-Z]{2})?)$")


def transcribe_clip(ctx: AppContext, clip_id: str, language_code: str = "indic-auto", actor: str = "system",
                    run_correction: bool = True) -> dict:
    clip = ctx.repo.get_clip(clip_id)
    if not clip:
        raise ServiceError("Clip not found.", "clip_not_found", 404)
    if clip["permission_status"] == "denied":
        raise ServiceError("Permission for this recording is 'denied'; it will not be sent to any STT provider.",
                           "permission_denied", 403)
    if not _LANG_RE.match(language_code):
        raise ServiceError("The STT baseline experiment setting must look like 'mr-IN' or 'indic-auto'.", "bad_language_code", 422)
    try:
        provider = get_provider(ctx.settings)
        result = provider.transcribe(clip["path"], language_code)
    except STTProviderError as exc:
        logger.warning("Transcription failed for %s: %s", clip_id, exc)
        raise ServiceError(str(exc), exc.code, exc.status) from exc

    transcript = ctx.repo.add_transcript({
        "clip_id": clip_id, "provider": result.provider, "model": result.model,
        "language_code_requested": result.language_code_requested,
        "detected_language_code": result.detected_language_code, "request_id": result.request_id,
        "transcript_raw": result.transcript, "script": detect_script(result.transcript),
        "latency_s": result.latency_s, "raw_response": result.raw_response,
        "is_synthetic": 1 if result.is_synthetic else 0, "experiment_role": role_for_transcript(result.provider)})
    # NOTE: provider-detected language is stored on the transcript only. It never modifies the source's declared dialect.
    ctx.repo.audit(actor, "transcribe", "clip", clip_id, {"provider": result.provider, "transcript_id": transcript["id"],
                                                          "experiment_role": transcript["experiment_role"]})
    if run_correction:
        propose_corrections(ctx, transcript["id"], actor=actor)
    return transcript


def import_transcript(ctx: AppContext, clip_id: str, text: str, label: str = "external", language_code: str = "",
                      actor: str = "system", run_correction: bool = True) -> dict:
    """Attach a transcript produced elsewhere (e.g. results of an earlier STT experiment). Clearly labelled 'imported'."""
    if not ctx.repo.get_clip(clip_id):
        raise ServiceError("Clip not found.", "clip_not_found", 404)
    text = (text or "").strip()
    if not text:
        raise ServiceError("Transcript text is empty.", "empty_text", 422)
    t = ctx.repo.add_transcript({
        "clip_id": clip_id, "provider": "imported", "provider_label": (label or "external")[:80], "model": None,
        "language_code_requested": language_code or None, "detected_language_code": None, "request_id": None,
        "transcript_raw": text,  # stored verbatim (only surrounding whitespace trimmed)
        "script": detect_script(text), "latency_s": None, "raw_response": None,
        "experiment_role": role_for_transcript("imported")})
    ctx.repo.audit(actor, "import_transcript", "clip", clip_id, {"label": label, "transcript_id": t["id"]})
    if run_correction:
        propose_corrections(ctx, t["id"], actor=actor)
    return t


def propose_corrections(ctx: AppContext, transcript_id: int, backend_name: str = "rule-based",
                        actor: str = "system") -> list[dict]:
    t = ctx.repo.get_transcript(transcript_id)
    if not t:
        raise ServiceError("Transcript not found.", "transcript_not_found", 404)
    lexicon = [LexiconEntry.from_row(r) for r in ctx.repo.list_lexicon(enabled_only=True)]
    stats = {rid: v for rid, v in ctx.repo.suggestion_stats_by_rule().items()}
    proposals = get_backend(backend_name).propose(t["transcript_raw"], lexicon, stats)

    existing = ctx.repo.list_suggestions(transcript_id)
    decided = {(s["start_char"], s["end_char"], s["replacement"]) for s in existing if s["status"] != "pending"}
    occupied = [(s["start_char"], s["end_char"]) for s in existing if s["status"] != "pending"]
    ctx.repo.clear_pending_suggestions(transcript_id)
    fresh = []
    for p in proposals:
        key = (p.start_char, p.end_char, p.replacement)
        if key in decided or any(p.start_char < b and a < p.end_char for a, b in occupied):
            continue  # never re-propose over spans a human already decided
        fresh.append(p.to_dict())
    ctx.repo.add_suggestions(transcript_id, fresh)
    logger.info("Transcript %s: %d new proposals from %s", transcript_id, len(fresh), backend_name)
    return ctx.repo.list_suggestions(transcript_id)
