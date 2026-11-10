from __future__ import annotations

from typing import Optional

from src.context import AppContext
from src.correction import apply_suggestions
from src.evaluation.report import evaluate_samples


def build_samples(ctx: AppContext, *, language_code: Optional[str] = None, dialect_label: Optional[str] = None,
                  include_synthetic: Optional[bool] = None, clip_ids: Optional[list[str]] = None) -> tuple[list[dict], dict]:
    """One sample per verified clip, using its most recent transcript (optionally filtered by requested language)."""
    if include_synthetic is None:
        include_synthetic = ctx.settings.is_demo
    samples, skipped = [], {"no_transcript": 0, "synthetic_excluded": 0, "permission_denied": 0, "dialect_filter": 0}
    wanted = set(clip_ids) if clip_ids is not None else None
    for clip in ctx.repo.list_clips(review_status="verified"):
        if wanted is not None and clip["id"] not in wanted:
            continue
        if not clip.get("reference_transcript"):
            continue
        if clip["permission_status"] == "denied":
            skipped["permission_denied"] += 1
            continue
        if dialect_label and clip["dialect_label"] != dialect_label:
            skipped["dialect_filter"] += 1
            continue
        ts = ctx.repo.list_transcripts(clip["id"])
        if language_code:
            ts = [t for t in ts if t["language_code_requested"] == language_code]
        if not ts:
            skipped["no_transcript"] += 1
            continue
        t = ts[-1]
        if t["is_synthetic"] and not include_synthetic:
            skipped["synthetic_excluded"] += 1
            continue
        sugg = ctx.repo.list_suggestions(t["id"])
        samples.append({"clip_id": clip["id"], "reference": clip["reference_transcript"],
                        "raw": t["transcript_raw"], "corrected": apply_suggestions(t["transcript_raw"], sugg),
                        "is_synthetic": bool(t["is_synthetic"]), "experiment_role": t["experiment_role"],
                        "provider": t["provider"], "language_code_requested": t["language_code_requested"]})
    return samples, skipped


def run_evaluation(ctx: AppContext, *, language_code: Optional[str] = None, dialect_label: Optional[str] = None,
                   include_synthetic: Optional[bool] = None, save: bool = True, clip_ids: Optional[list[str]] = None) -> dict:
    samples, skipped = build_samples(ctx, language_code=language_code, dialect_label=dialect_label,
                                     include_synthetic=include_synthetic, clip_ids=clip_ids)
    report = evaluate_samples(samples)
    report["pre_scoring_skipped"] = skipped
    report["mode"] = ctx.settings.mode
    report["filters"] = {"language_code": language_code, "dialect_label": dialect_label,
                         "include_synthetic": ctx.settings.is_demo if include_synthetic is None else include_synthetic}
    if ctx.settings.is_demo or report["contains_synthetic_samples"]:
        report["warnings"].insert(0, "DEMO DATA: these numbers come from synthetic placeholder transcripts and say "
                                     "nothing about real STT or Ahirani accuracy.")
    if save:
        report["run_id"] = ctx.repo.save_eval_run(report["filters"], report)
    return report
