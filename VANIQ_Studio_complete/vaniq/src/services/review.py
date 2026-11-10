"""Human review: accept / reject / modify suggestions, manual corrections, reference verification."""
from __future__ import annotations

from typing import Optional

from src.baseline import ROLE_LABELS, sanitize_provider_response
from src.context import AppContext
from src.correction import apply_suggestions, render_segments
from src.evaluation.metrics import detect_script
from src.services.errors import ServiceError


def _actor(actor: Optional[str]) -> str:
    return (actor or "").strip()[:60] or "anonymous-reviewer"


def clip_workspace(ctx: AppContext, clip_id: str) -> dict:
    clip = ctx.repo.get_clip(clip_id)
    if not clip:
        raise ServiceError("Clip not found.", "clip_not_found", 404)
    transcripts = []
    for t in ctx.repo.list_transcripts(clip_id):
        sugg = ctx.repo.list_suggestions(t["id"])
        raw = t["transcript_raw"]
        provider_response = sanitize_provider_response(t.get("raw_response"), [ctx.settings.gnani_api_key])
        t = {k: v for k, v in t.items() if k != "raw_response"}
        transcripts.append({
            **t, "provider_response": provider_response, "experiment_role_label": ROLE_LABELS.get(t["experiment_role"]),
            "suggestions": sugg, "segments": render_segments(raw, sugg),
            "corrected_text": apply_suggestions(raw, sugg),
            "preview_if_all_accepted": apply_suggestions(raw, sugg, include_pending=True),
            "pending_count": sum(1 for s in sugg if s["status"] == "pending")})
    return {"clip": clip, "transcripts": transcripts}


def _get_suggestion(ctx: AppContext, suggestion_id: int) -> dict:
    s = ctx.repo.get_suggestion(suggestion_id)
    if not s:
        raise ServiceError("Suggestion not found.", "suggestion_not_found", 404)
    return s


def _touch_review(ctx: AppContext, suggestion: dict, actor: str) -> None:
    t = ctx.repo.get_transcript(suggestion["transcript_id"])
    clip = ctx.repo.get_clip(t["clip_id"])
    if clip["review_status"] == "needs_review":
        ctx.repo.set_review_status(clip["id"], "in_review", actor)


def decide(ctx: AppContext, suggestion_id: int, decision: str, actor: str, final_replacement: Optional[str] = None) -> dict:
    actor = _actor(actor)
    s = _get_suggestion(ctx, suggestion_id)
    if decision == "modified":
        if final_replacement is None or final_replacement == "":
            raise ServiceError("A modified suggestion needs a non-empty replacement.", "empty_replacement", 422)
    elif final_replacement is not None:
        raise ServiceError("final_replacement is only valid when modifying.", "unexpected_replacement", 422)
    if decision not in ("accepted", "rejected", "modified", "pending"):
        raise ServiceError("decision must be accepted, rejected, modified or pending.", "bad_decision", 422)
    updated = ctx.repo.decide_suggestion(suggestion_id, decision, actor, final_replacement)
    _touch_review(ctx, s, actor)
    return updated


def add_manual_correction(ctx: AppContext, transcript_id: int, start_char: int, end_char: int, replacement: str,
                          actor: str, explanation: str = "", expected_original: Optional[str] = None) -> dict:
    actor = _actor(actor)
    t = ctx.repo.get_transcript(transcript_id)
    if not t:
        raise ServiceError("Transcript not found.", "transcript_not_found", 404)
    raw = t["transcript_raw"]
    if not (0 <= start_char < end_char <= len(raw)):
        raise ServiceError("Span is outside the transcript.", "bad_span", 422)
    if expected_original is not None and raw[start_char:end_char] != expected_original:
        raise ServiceError("The selected text does not match the transcript at that position; reload and retry.",
                           "span_mismatch", 409)
    if not replacement.strip():
        raise ServiceError("Replacement must not be empty.", "empty_replacement", 422)
    for s in ctx.repo.list_suggestions(transcript_id):
        if s["status"] in ("accepted", "modified") and start_char < s["end_char"] and s["start_char"] < end_char:
            raise ServiceError("Span overlaps an already accepted correction; undo that one first.", "overlap", 409)
    new_ids = ctx.repo.add_suggestions(transcript_id, [{
        "start_char": start_char, "end_char": end_char, "original": raw[start_char:end_char],
        "replacement": replacement, "kind": "manual", "backend": "human", "rule_id": None, "confidence": None,
        "confidence_basis": "human-entered correction", "explanation": explanation or "Entered by a reviewer.",
        "uncertain": False, "status": "pending"}])
    updated = ctx.repo.decide_suggestion(new_ids[0], "accepted", actor)
    _touch_review(ctx, updated, actor)
    return updated


def verify_reference(ctx: AppContext, clip_id: str, text: str, actor: str, stt_viewed: Optional[bool] = None) -> dict:
    actor = _actor(actor)
    if actor == "anonymous-reviewer":
        raise ServiceError("Provide a reviewer name so verification can be attributed.", "reviewer_required", 422)
    clip = ctx.repo.get_clip(clip_id)
    if not clip:
        raise ServiceError("Clip not found.", "clip_not_found", 404)
    text = (text or "").strip()
    if not text:
        raise ServiceError("Reference transcript is empty.", "empty_text", 422)
    ctx.repo.set_reference(clip_id, text, detect_script(text), actor, stt_viewed)
    return ctx.repo.get_clip(clip_id)


def unverify(ctx: AppContext, clip_id: str, actor: str) -> dict:
    if not ctx.repo.get_clip(clip_id):
        raise ServiceError("Clip not found.", "clip_not_found", 404)
    ctx.repo.clear_reference(clip_id, _actor(actor))
    return ctx.repo.get_clip(clip_id)


def reject_clip(ctx: AppContext, clip_id: str, actor: str, notes: str = "") -> dict:
    if not ctx.repo.get_clip(clip_id):
        raise ServiceError("Clip not found.", "clip_not_found", 404)
    ctx.repo.set_review_status(clip_id, "rejected", _actor(actor))
    if notes:
        ctx.repo.set_clip_notes(clip_id, notes)
    return ctx.repo.get_clip(clip_id)


def promote_to_lexicon(ctx: AppContext, suggestion_id: int, actor: str) -> dict:
    """Turn a human decision into a *candidate* lexicon entry. Never auto-verified."""
    actor = _actor(actor)
    s = _get_suggestion(ctx, suggestion_id)
    if s["status"] not in ("accepted", "modified"):
        raise ServiceError("Only accepted or modified corrections can be added to the lexicon.", "not_accepted", 409)
    target = s["final_replacement"] if s["status"] == "modified" else s["replacement"]
    if s["kind"] in ("normalization",):
        raise ServiceError("Normalization rules are built in and cannot be added to the lexicon.", "bad_kind", 409)
    t = ctx.repo.get_transcript(s["transcript_id"])
    return ctx.repo.add_lexicon_entry({
        "source_form": s["original"], "target_form": target, "kind": "lexical" if s["kind"] == "manual" else s["kind"],
        "status": "candidate", "provenance": f"reviewer {actor} on clip {t['clip_id']}",
        "notes": "Promoted from a reviewed correction; awaiting independent verification."}, actor=actor)
