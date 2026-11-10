"""Agent tools: typed, validated operations executed against the real VANIQ services.

Impact levels
  read          no state change
  record        writes VANIQ records only (pending suggestions, an evaluation record); no external effect
  consequential external call or file creation (STT provider, dataset export); needs explicit human approval

HARD LIMITS (by omission, enforced by tests): no tool writes a human reference, verifies a clip, decides a correction
suggestion, edits the lexicon, changes permissions, or approves knowledge.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Callable, Literal, Optional, Type

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.baseline import BASELINE_SETTINGS, NATIVE_SUPPORT_STATEMENT
from src.context import AppContext
from src.evaluation.metrics import detect_script, normalize_text, calculate_wer
from src.services import transcribe as transcribe_svc
from src.services.errors import ServiceError
from src.services.evaluation_service import run_evaluation as run_evaluation_svc
from src.services.export import clip_exclusion_reason, export_dataset
from src.services.validation import probe_audio

READ, RECORD, CONSEQUENTIAL = "read", "record", "consequential"
_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_LANG = re.compile(r"^(indic-auto|[a-z]{2,3}(-[A-Z]{2})?)$")


class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NoArgs(_Args):
    pass


class ClipOpt(_Args):
    clip_id: Optional[str] = None

    @field_validator("clip_id")
    @classmethod
    def _v(cls, v):
        if v is not None and not _ID.match(v):
            raise ValueError("clip_id has an invalid format")
        return v


class SourceOpt(_Args):
    source_id: Optional[str] = None

    @field_validator("source_id")
    @classmethod
    def _v(cls, v):
        if v is not None and not _ID.match(v):
            raise ValueError("source_id has an invalid format")
        return v


class TranscribeArgs(_Args):
    clip_id: str
    language_code: str = Field(description="STT baseline experiment setting, e.g. mr-IN or indic-auto")

    @field_validator("clip_id")
    @classmethod
    def _c(cls, v):
        if not _ID.match(v):
            raise ValueError("clip_id has an invalid format")
        return v

    @field_validator("language_code")
    @classmethod
    def _l(cls, v):
        if not _LANG.match(v):
            raise ValueError("language_code must look like 'mr-IN' or 'indic-auto'")
        return v


class ProposeArgs(_Args):
    transcript_id: int = Field(ge=1)


class EligibilityArgs(_Args):
    visibility: Literal["public", "internal"] = "public"
    include_unknown_internal: bool = False
    require_verified: bool = True

    @model_validator(mode="after")
    def _no_unknown_in_public(self):
        if self.visibility == "public" and self.include_unknown_internal:
            raise ValueError("unknown-permission recordings can never be part of a public export")
        return self


class EvalArgs(_Args):
    language_code: Optional[str] = None

    @field_validator("language_code")
    @classmethod
    def _l(cls, v):
        if v is not None and not _LANG.match(v):
            raise ValueError("language_code must look like 'mr-IN' or 'indic-auto'")
        return v


class ExportArgs(EligibilityArgs):
    name: str = "vaniq-dataset"


@dataclass
class Tool:
    name: str
    title: str
    description: str
    impact: str
    args_model: Type[BaseModel]
    fn: Callable[[AppContext, Any, str], dict]
    skill: str = ""                       # skill grouping shown in the UI


# ------------------------------------------------------------------ implementations
def list_work(ctx: AppContext, a: NoArgs, actor: str) -> dict:
    clips = ctx.repo.list_clips()
    no_transcript = [c["id"] for c in clips if c["transcript_count"] == 0 and c["permission_status"] != "denied"]
    return {"counts": ctx.repo.counts(), "clips_without_transcript": no_transcript,
            "clips_needing_review": [c["id"] for c in clips if c["review_status"] in ("needs_review", "in_review")],
            "verified_clips": [c["id"] for c in clips if c["review_status"] == "verified"]}


def validate_audio(ctx: AppContext, a: SourceOpt, actor: str) -> dict:
    sources = [ctx.repo.get_source(a.source_id)] if a.source_id else ctx.repo.list_sources()
    if a.source_id and sources == [None]:
        raise ServiceError("Source not found.", "source_not_found", 404)
    report, issues = [], 0
    for s in sources:
        entry = {"source_id": s["id"], "name": s["original_name"], "issues": []}
        path = s.get("normalized_path") or s["stored_path"]
        if not os.path.isfile(path):
            entry["issues"].append("audio file missing on disk")
        else:
            try:
                info = probe_audio(path)
                entry.update(duration_s=round(info.duration_s, 2), sample_rate=info.sample_rate, channels=info.channels)
                if info.sample_rate != 16000 or info.channels != 1:
                    entry["issues"].append("normalized audio is not 16 kHz mono")
            except ServiceError as exc:
                entry["issues"].append(exc.message)
        if s["segmentation_status"] == "no_speech":
            entry["issues"].append("no audio activity detected; no clips were created")
        flagged = [{"clip_id": c["id"], "flags": c["quality_flags"]} for c in ctx.repo.list_clips(source_id=s["id"]) if c["quality_flags"]]
        if flagged:
            entry["flagged_clips"] = flagged
            entry["issues"].append(f"{len(flagged)} clip(s) with quality flags")
        issues += len(entry["issues"])
        report.append(entry)
    return {"sources_checked": len(report), "issue_count": issues, "sources": report}


def detect_transcript_mismatch(ctx: AppContext, a: ClipOpt, actor: str) -> dict:
    clips = [ctx.repo.get_clip(a.clip_id)] if a.clip_id else ctx.repo.list_clips()
    if a.clip_id and clips == [None]:
        raise ServiceError("Clip not found.", "clip_not_found", 404)
    flagged, checked, no_ref = [], 0, 0
    for c in clips:
        ref = c.get("reference_transcript")
        if not ref:
            no_ref += 1
            continue
        for t in ctx.repo.list_transcripts(c["id"]):
            checked += 1
            raw, reasons = t["transcript_raw"], []
            rn, hn = normalize_text(ref), normalize_text(raw)
            if not hn:
                reasons.append("empty transcript")
            else:
                if detect_script(ref) != detect_script(raw):
                    reasons.append(f"script differs (reference {detect_script(ref)}, transcript {detect_script(raw)}); this is not language evidence")
                wer = calculate_wer(rn, hn)
                if wer > 1.0:
                    reasons.append(f"word error rate {wer:.0%} is above 100%: the reference or audio may be mismatched")
                lr = len(hn.split()) / max(1, len(rn.split()))
                if lr > 3 or lr < 1 / 3:
                    reasons.append(f"transcript is {lr:.1f}x the reference length")
            if reasons:
                flagged.append({"clip_id": c["id"], "transcript_id": t["id"], "experiment_role": t["experiment_role"], "reasons": reasons})
    return {"transcripts_checked": checked, "clips_without_reference_not_checked": no_ref, "flagged": flagged,
            "note": "Detection only. Nothing was changed; a human decides what to do."}


def reference_workflow_status(ctx: AppContext, a: NoArgs, actor: str) -> dict:
    todo = [{"clip_id": c["id"], "review_status": c["review_status"], "has_transcript": c["transcript_count"] > 0}
            for c in ctx.repo.list_clips() if not c.get("reference_transcript") and c["review_status"] != "rejected"]
    return {"clips_awaiting_human_reference": todo, "count": len(todo),
            "note": "Human references are written and verified by people in the Studio. The agent never writes or verifies them."}


def check_dataset_eligibility(ctx: AppContext, a: EligibilityArgs, actor: str) -> dict:
    if a.visibility == "public" and a.include_unknown_internal:
        raise ServiceError("Unknown-permission recordings can never be part of a public export.", "unknown_in_public", 422)
    rows, eligible, reasons = [], 0, {}
    for c in ctx.repo.list_clips():
        r = clip_exclusion_reason(c, a.visibility, a.include_unknown_internal, a.require_verified)
        rows.append({"clip_id": c["id"], "eligible": r is None, "reason": r})
        if r is None:
            eligible += 1
        else:
            reasons[r] = reasons.get(r, 0) + 1
    return {"visibility": a.visibility, "eligible_count": eligible, "total_clips": len(rows), "excluded_by_reason": reasons, "clips": rows}


def propose_corrections(ctx: AppContext, a: ProposeArgs, actor: str) -> dict:
    sugg = transcribe_svc.propose_corrections(ctx, a.transcript_id, actor=actor)
    return {"transcript_id": a.transcript_id, "suggestions": len(sugg),
            "pending": sum(1 for s in sugg if s["status"] == "pending"),
            "note": "Suggestions are pending. A human accepts, rejects or modifies each one."}


def run_evaluation(ctx: AppContext, a: EvalArgs, actor: str) -> dict:
    r = run_evaluation_svc(ctx, language_code=a.language_code)
    return {"run_id": r.get("run_id"), "scored": r["sample_count_scored"], "total_verified": r["sample_count_total"],
            "excluded_by_reason": r["excluded_by_reason"],
            "by_role": {k: {"label": v["label"], "n_scored": v["n_scored"],
                            "wer_before": (v["aggregate"] or {}).get("before", {}).get("wer"),
                            "wer_after": (v["aggregate"] or {}).get("after", {}).get("wer")} for k, v in r["by_role"].items()},
            "claims": r["claims"], "warnings": r["warnings"]}


def transcribe_clip(ctx: AppContext, a: TranscribeArgs, actor: str) -> dict:
    t = transcribe_svc.transcribe_clip(ctx, a.clip_id, a.language_code, actor=actor)
    return {"transcript_id": t["id"], "provider": t["provider"], "experiment_role": t["experiment_role"],
            "language_code_requested": t["language_code_requested"], "provider_detected_language": t["detected_language_code"],
            "synthetic": bool(t["is_synthetic"]), "characters": len(t["transcript_raw"]), "note": NATIVE_SUPPORT_STATEMENT}


def create_export(ctx: AppContext, a: ExportArgs, actor: str) -> dict:
    out = export_dataset(ctx, a.visibility, a.include_unknown_internal, a.require_verified, a.name)
    m = out["manifest"]
    return {"clip_count": m["clip_count"], "visibility": m["visibility"], "excluded_counts": m["excluded_counts"],
            "download": f"/api/exports/download/{os.path.basename(out['zip_path'])}"}


def list_knowledge(ctx: AppContext, a: NoArgs, actor: str) -> dict:
    items = ctx.repo.list_knowledge("approved")
    return {"approved_items": [{"id": i["id"], "title": i["title"], "kind": i["kind"], "approved_by": i["approved_by"],
                                "body": i["body"][:600]} for i in items], "count": len(items),
            "note": "Only human-approved knowledge is shown. The agent cannot create or approve entries."}


TOOLS: dict[str, Tool] = {t.name: t for t in [
    Tool("list_work", "What needs doing", "Summarise queues: clips without transcripts, awaiting review, verified.", READ, NoArgs, list_work, "Work overview"),
    Tool("validate_audio", "Validate audio", "Re-check stored audio files, format and quality flags for one or all recordings.", READ, SourceOpt, validate_audio, "Audio intake and validation"),
    Tool("detect_transcript_mismatch", "Detect transcript mismatch", "Flag transcripts that look inconsistent with the human reference (script, length, WER above 100%).", READ, ClipOpt, detect_transcript_mismatch, "Transcript mismatch detection"),
    Tool("reference_workflow_status", "Human-reference queue", "List clips still waiting for a human-written reference. Never writes references.", READ, NoArgs, reference_workflow_status, "Human-reference verification workflow"),
    Tool("check_dataset_eligibility", "Check dataset eligibility", "Per-clip export eligibility with reasons, using the real export rules.", READ, EligibilityArgs, check_dataset_eligibility, "Dataset eligibility checks"),
    Tool("list_knowledge", "Read approved knowledge", "Show human-approved project conventions and references.", READ, NoArgs, list_knowledge, "Knowledge"),
    Tool("propose_corrections", "Propose corrections", "Run the lexicon correction engine on a transcript. Creates pending suggestions only.", RECORD, ProposeArgs, propose_corrections, "Transcript review"),
    Tool("run_evaluation", "Generate evaluation report", "WER/CER on human-verified references, per experiment role. Saves an evaluation record.", RECORD, EvalArgs, run_evaluation, "Evaluation report generation"),
    Tool("transcribe_clip", "Run STT baseline", "Send a clip to the STT provider (or the labelled demo provider) as a baseline experiment.", CONSEQUENTIAL, TranscribeArgs, transcribe_clip, "Experiment preparation"),
    Tool("create_export", "Create dataset export", "Export eligible clips. Server-side permission rules always apply.", CONSEQUENTIAL, ExportArgs, create_export, "Dataset eligibility checks"),
]}


def describe_tools() -> list[dict]:
    out = []
    for t in TOOLS.values():
        schema = t.args_model.model_json_schema()
        out.append({"name": t.name, "title": t.title, "description": t.description, "impact": t.impact, "skill": t.skill,
                    "requires_approval": t.impact == CONSEQUENTIAL, "args_schema": schema.get("properties", {}),
                    "required": schema.get("required", [])})
    return out


def validate_args(tool_name: str, args: dict) -> BaseModel:
    tool = TOOLS.get(tool_name)
    if not tool:
        raise ServiceError(f"Unknown tool: {tool_name}", "unknown_tool", 422)
    try:
        return tool.args_model.model_validate(args or {})
    except Exception as exc:  # pydantic ValidationError
        msgs = "; ".join(f"{'.'.join(str(x) for x in e['loc'])}: {e['msg']}" for e in getattr(exc, "errors", lambda: [])()) or str(exc)
        raise ServiceError(f"Invalid arguments for {tool_name}: {msgs}", "invalid_arguments", 422) from exc
