"""FastAPI application. Run with: python -m src.cli serve"""
from __future__ import annotations

import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.about import CAPABILITIES, LIMITATIONS, PRODUCT
from src.baseline import BASELINE_SETTINGS, NATIVE_SUPPORT_STATEMENT, ROLE_LABELS
from src.context import AppContext, build_context
from src.correction import RuleBasedBackend  # noqa: F401  (import check)
from src.logging_setup import setup_logging
from src.agent import runner as agent_runner
from src.agent.tools import describe_tools
from src.services import knowledge as knowledge_svc
from src.services import review
from src.workflows import engine as wf_engine
from src.services.demo import seed_demo
from src.services.errors import ServiceError
from src.services.evaluation_service import run_evaluation
from src.services.export import clip_exclusion_reason, export_dataset
from src.services.ingest import ingest_file
from src.services.transcribe import import_transcript, propose_corrections, transcribe_clip

logger = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).parent / "static"


class TranscribeBody(BaseModel):
    language_code: str = "indic-auto"
    reviewer: str = ""


class ImportBody(BaseModel):
    text: str
    label: str = "external"
    language_code: str = ""
    reviewer: str = ""


class ManualCorrectionBody(BaseModel):
    start_char: int
    end_char: int
    replacement: str
    expected_original: Optional[str] = None
    explanation: str = ""
    reviewer: str = ""


class DecisionBody(BaseModel):
    decision: str
    final_replacement: Optional[str] = None
    reviewer: str = ""


class ReviewerBody(BaseModel):
    reviewer: str = ""


class VerifyBody(BaseModel):
    reference: str
    reviewer: str = ""
    stt_viewed: Optional[bool] = None   # did the reviewer opt in to viewing the STT transcript before writing this?


class RejectBody(BaseModel):
    reviewer: str = ""
    notes: str = ""


class SourcePatch(BaseModel):
    speaker_id: Optional[str] = None
    dialect_label: Optional[str] = None
    permission_status: Optional[str] = None
    permitted_usage: Optional[str] = None
    source_url: Optional[str] = None
    consent_notes: Optional[str] = None
    reviewer: str = ""


class LexiconBody(BaseModel):
    source_form: str = Field(min_length=1, max_length=200)
    target_form: str = Field(min_length=1, max_length=200)
    kind: str = "lexical"
    context_prev: str = ""
    context_next: str = ""
    status: str = "candidate"
    provenance: str = ""
    notes: str = ""
    reviewer: str = ""


class LexiconPatch(BaseModel):
    source_form: Optional[str] = None
    target_form: Optional[str] = None
    kind: Optional[str] = None
    context_prev: Optional[str] = None
    context_next: Optional[str] = None
    status: Optional[str] = None
    provenance: Optional[str] = None
    notes: Optional[str] = None
    enabled: Optional[bool] = None
    reviewer: str = ""


class EvalBody(BaseModel):
    language_code: Optional[str] = None
    dialect_label: Optional[str] = None
    include_synthetic: Optional[bool] = None


class ExportBody(BaseModel):
    visibility: str = "public"
    include_unknown_internal: bool = False
    require_verified: bool = True
    name: str = "vaniq-dataset"


class AgentPlanBody(BaseModel):
    message: str = Field(default="", max_length=2000)
    context: dict = Field(default_factory=dict)
    steps: Optional[list[dict]] = None
    reviewer: str = ""


class ApprovalBody(BaseModel):
    reviewer: str = ""


class WorkflowBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    category: str = "Custom"
    description: str = ""
    graph: dict


class KnowledgeBody(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    kind: str = "convention"
    body: str = Field(min_length=1, max_length=20000)
    provenance: str = ""
    reviewer: str = ""


class KnowledgeEditBody(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=20000)
    reviewer: str = ""


class RestoreBody(BaseModel):
    version: int
    reviewer: str = ""


def _validate_lexicon_fields(f: dict) -> None:
    if f.get("kind") is not None and f["kind"] not in ("lexical", "spelling", "normalization"):
        raise ServiceError("kind must be lexical, spelling or normalization.", "bad_kind", 422)
    if f.get("status") is not None and f["status"] not in ("candidate", "verified", "demo"):
        raise ServiceError("status must be candidate, verified or demo.", "bad_status", 422)
    if f.get("status") == "verified" and not (f.get("provenance") or "").strip() and "provenance" in f:
        raise ServiceError("A verified entry needs provenance (who verified it, or the source).", "provenance_required", 422)


def create_app(ctx: Optional[AppContext] = None) -> FastAPI:
    ctx = ctx or build_context()
    setup_logging(ctx.settings.log_level)
    app = FastAPI(title="VANIQ Local API", version=PRODUCT["version"],
                  description="Voice intelligence for every language. Local, single-user API.")
    app.state.ctx = ctx

    @app.exception_handler(ServiceError)
    async def _service_error(_: Request, exc: ServiceError):
        return JSONResponse(status_code=exc.status, content={"error": {"code": exc.code, "message": exc.message}})

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception):
        logger.exception("Unhandled error")
        return JSONResponse(status_code=500, content={"error": {"code": "internal_error",
                                                                "message": "Unexpected server error. See server logs."}})

    # ---- meta ----------------------------------------------------------------------
    @app.get("/api/health")
    def health():
        return {"status": "ok", "mode": ctx.settings.mode, "stt_configured": ctx.settings.stt_configured,
                "ffmpeg": shutil.which("ffmpeg") is not None, "version": PRODUCT["version"]}

    @app.get("/api/about")
    def about():
        return {"product": PRODUCT, "mode": ctx.settings.mode, "capabilities": CAPABILITIES,
                "limitations": LIMITATIONS,
                "baseline_settings": BASELINE_SETTINGS, "role_labels": ROLE_LABELS,
                "native_support_statement": NATIVE_SUPPORT_STATEMENT,
                "stt": {"configured": ctx.settings.stt_configured, "model": ctx.settings.gnani_model,
                        "active_provider": "demo-mock" if ctx.settings.is_demo else
                        ("gnani" if ctx.settings.stt_configured else "none")}}

    @app.get("/api/dashboard")
    def dashboard():
        return {"mode": ctx.settings.mode, "counts": ctx.repo.counts(),
                "stt_configured": ctx.settings.stt_configured, "recent_clips": ctx.repo.list_clips()[:8],
                "audit": ctx.repo.list_audit(10)}

    # ---- sources / upload ------------------------------------------------------------
    @app.post("/api/sources")
    def upload_source(file: UploadFile = File(...), speaker_id: str = Form("UNKNOWN"),
                      dialect_label: str = Form("UNKNOWN"), permission_status: str = Form("UNKNOWN"),
                      permitted_usage: str = Form("UNKNOWN"), source_url: str = Form("UNKNOWN"),
                      consent_notes: str = Form(""), reviewer: str = Form("")):
        limit = ctx.settings.max_upload_mb * 1024 * 1024
        suffix = os.path.splitext(file.filename or "")[1].lower()
        fd, tmp = tempfile.mkstemp(suffix=suffix, prefix="vaniq_upload_")
        try:
            size = 0
            with os.fdopen(fd, "wb") as out:
                while chunk := file.file.read(1024 * 1024):
                    size += len(chunk)
                    if size > limit:
                        raise ServiceError(f"File exceeds the {ctx.settings.max_upload_mb} MB upload limit.", "too_large", 413)
                    out.write(chunk)
            res = ingest_file(ctx, tmp, file.filename or "upload", source_url=source_url, speaker_id=speaker_id,
                              dialect_label=dialect_label, permission_status=permission_status,
                              permitted_usage=permitted_usage, consent_notes=consent_notes,
                              actor=reviewer or "uploader")
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
        return {"source": res.source, "clips": res.clips, "duplicate": res.duplicate,
                "segmentation_status": res.segmentation_status}

    @app.get("/api/sources")
    def list_sources():
        return ctx.repo.list_sources()

    @app.patch("/api/sources/{source_id}")
    def patch_source(source_id: str, body: SourcePatch):
        src = ctx.repo.get_source(source_id)
        if not src:
            raise ServiceError("Source not found.", "source_not_found", 404)
        fields = body.model_dump(exclude={"reviewer"}, exclude_none=True)
        from src.storage.repo import PERMISSION_STATUSES, PERMITTED_USAGES
        perm = fields.get("permission_status", src["permission_status"])
        use = fields.get("permitted_usage", src["permitted_usage"])
        if perm not in PERMISSION_STATUSES or use not in PERMITTED_USAGES:
            raise ServiceError("Invalid permission_status or permitted_usage.", "bad_permission", 422)
        if perm != "granted" and use != "UNKNOWN":
            raise ServiceError("permitted_usage can only be set when permission_status is 'granted'.",
                               "inconsistent_permission", 422)
        return ctx.repo.update_source(source_id, fields, actor=body.reviewer or "anonymous-reviewer")

    # ---- clips -----------------------------------------------------------------------
    @app.get("/api/clips")
    def list_clips(review_status: Optional[str] = None, source_id: Optional[str] = None):
        return ctx.repo.list_clips(review_status=review_status, source_id=source_id)

    @app.get("/api/clips/{clip_id}")
    def get_clip(clip_id: str):
        return review.clip_workspace(ctx, clip_id)

    @app.get("/api/clips/{clip_id}/audio")
    def clip_audio(clip_id: str):
        clip = ctx.repo.get_clip(clip_id)
        if not clip or not os.path.isfile(clip["path"]):
            raise ServiceError("Audio not found.", "audio_not_found", 404)
        return FileResponse(clip["path"], media_type="audio/wav")

    @app.post("/api/clips/{clip_id}/transcribe")
    def transcribe(clip_id: str, body: TranscribeBody):
        return transcribe_clip(ctx, clip_id, body.language_code, actor=body.reviewer or "anonymous-reviewer")

    @app.post("/api/clips/{clip_id}/transcripts/import")
    def import_t(clip_id: str, body: ImportBody):
        return import_transcript(ctx, clip_id, body.text, body.label, body.language_code,
                                 actor=body.reviewer or "anonymous-reviewer")

    @app.post("/api/clips/{clip_id}/verify")
    def verify(clip_id: str, body: VerifyBody):
        return review.verify_reference(ctx, clip_id, body.reference, body.reviewer, body.stt_viewed)

    @app.post("/api/clips/{clip_id}/unverify")
    def unverify(clip_id: str, body: ReviewerBody):
        return review.unverify(ctx, clip_id, body.reviewer)

    @app.post("/api/clips/{clip_id}/reject")
    def reject(clip_id: str, body: RejectBody):
        return review.reject_clip(ctx, clip_id, body.reviewer, body.notes)

    # ---- corrections -----------------------------------------------------------------
    @app.post("/api/transcripts/{transcript_id}/propose")
    def propose(transcript_id: int):
        return propose_corrections(ctx, transcript_id)

    @app.post("/api/transcripts/{transcript_id}/corrections")
    def manual_correction(transcript_id: int, body: ManualCorrectionBody):
        return review.add_manual_correction(ctx, transcript_id, body.start_char, body.end_char, body.replacement,
                                            body.reviewer, body.explanation, body.expected_original)

    @app.post("/api/suggestions/{suggestion_id}/decision")
    def decide(suggestion_id: int, body: DecisionBody):
        return review.decide(ctx, suggestion_id, body.decision, body.reviewer, body.final_replacement)

    @app.post("/api/suggestions/{suggestion_id}/promote")
    def promote(suggestion_id: int, body: ReviewerBody):
        return review.promote_to_lexicon(ctx, suggestion_id, body.reviewer)

    # ---- lexicon ---------------------------------------------------------------------
    @app.get("/api/lexicon")
    def lexicon():
        stats = ctx.repo.suggestion_stats_by_rule()
        rows = ctx.repo.list_lexicon()
        for r in rows:
            r["review_stats"] = stats.get(f"lex:{r['id']}", {"accepted": 0, "rejected": 0, "modified": 0})
        return rows

    @app.post("/api/lexicon")
    def add_lexicon(body: LexiconBody):
        fields = body.model_dump(exclude={"reviewer"})
        _validate_lexicon_fields(fields)
        if body.status == "demo" and not ctx.settings.is_demo:
            raise ServiceError("Status 'demo' is reserved for demo mode.", "bad_status", 422)
        return ctx.repo.add_lexicon_entry({**fields, "is_demo": 1 if ctx.settings.is_demo else 0},
                                          actor=body.reviewer or "anonymous-reviewer")

    @app.patch("/api/lexicon/{lid}")
    def patch_lexicon(lid: int, body: LexiconPatch):
        if not ctx.repo.get_lexicon_entry(lid):
            raise ServiceError("Lexicon entry not found.", "lexicon_not_found", 404)
        fields = body.model_dump(exclude={"reviewer"}, exclude_none=True)
        _validate_lexicon_fields(fields)
        current = ctx.repo.get_lexicon_entry(lid)
        if fields.get("status") == "verified" and not (fields.get("provenance") or current["provenance"]).strip():
            raise ServiceError("A verified entry needs provenance.", "provenance_required", 422)
        if "enabled" in fields:
            fields["enabled"] = 1 if fields["enabled"] else 0
        return ctx.repo.update_lexicon_entry(lid, fields, body.reviewer or "anonymous-reviewer")

    @app.delete("/api/lexicon/{lid}")
    def delete_lexicon(lid: int, reviewer: str = ""):
        if not ctx.repo.get_lexicon_entry(lid):
            raise ServiceError("Lexicon entry not found.", "lexicon_not_found", 404)
        ctx.repo.delete_lexicon_entry(lid, reviewer or "anonymous-reviewer")
        return {"deleted": lid}

    # ---- evaluation / export / demo / audit -------------------------------------------
    @app.post("/api/evaluate")
    def evaluate(body: EvalBody):
        return run_evaluation(ctx, language_code=body.language_code, dialect_label=body.dialect_label,
                              include_synthetic=body.include_synthetic)

    @app.get("/api/evaluations")
    def evaluations():
        return ctx.repo.list_eval_runs()

    @app.post("/api/exports")
    def make_export(body: ExportBody):
        res = export_dataset(ctx, body.visibility, body.include_unknown_internal, body.require_verified, body.name)
        return {"download": f"/api/exports/download/{os.path.basename(res['zip_path'])}", "manifest": res["manifest"]}

    @app.get("/api/exports")
    def list_exports():
        d = ctx.settings.exports_dir
        return sorted([f.name for f in d.glob("*.zip")], reverse=True) if d.exists() else []

    @app.get("/api/exports/download/{filename}")
    def download_export(filename: str):
        safe = os.path.basename(filename)
        path = ctx.settings.exports_dir / safe
        if safe != filename or not safe.endswith(".zip") or not path.is_file():
            raise ServiceError("Export not found.", "export_not_found", 404)
        return FileResponse(str(path), media_type="application/zip", filename=safe)

    @app.post("/api/demo/seed")
    def demo_seed():
        return seed_demo(ctx)

    @app.get("/api/audit")
    def audit(limit: int = 100):
        return ctx.repo.list_audit(min(max(limit, 1), 500))

    # ---- studio: sources audio, eligibility ------------------------------------------
    @app.get("/api/sources/{source_id}/audio")
    def source_audio(source_id: str):
        src = ctx.repo.get_source(source_id)
        path = src and (src.get("normalized_path") or src["stored_path"])
        if not src or not path or not os.path.isfile(path):
            raise ServiceError("Audio not found.", "audio_not_found", 404)
        return FileResponse(path, media_type="audio/wav")

    @app.get("/api/datasets/eligibility")
    def eligibility(visibility: str = "public", include_unknown_internal: bool = False, require_verified: bool = True):
        if visibility not in ("public", "internal"):
            raise ServiceError("visibility must be 'public' or 'internal'.", "bad_visibility", 422)
        if visibility == "public" and include_unknown_internal:
            raise ServiceError("Unknown-permission recordings can never be part of a public export.", "unknown_in_public", 422)
        rows, reasons, eligible = [], {}, 0
        for c in ctx.repo.list_clips():
            r = clip_exclusion_reason(c, visibility, include_unknown_internal, require_verified)
            rows.append({"clip_id": c["id"], "source_name": c["source_name"], "eligible": r is None, "reason": r})
            if r is None:
                eligible += 1
            else:
                reasons[r] = reasons.get(r, 0) + 1
        return {"visibility": visibility, "eligible_count": eligible, "total_clips": len(rows), "excluded_by_reason": reasons, "clips": rows}

    # ---- agent -----------------------------------------------------------------------
    @app.get("/api/agent/status")
    def agent_status():
        return agent_runner.status()

    @app.get("/api/agent/tools")
    def agent_tools():
        return describe_tools()

    @app.post("/api/agent/plan")
    def agent_plan(body: AgentPlanBody):
        return agent_runner.create_run(ctx, (body.reviewer or "anonymous-reviewer")[:60], body.message, body.context, body.steps)

    @app.get("/api/agent/runs")
    def agent_runs(limit: int = 30):
        return ctx.repo.list_agent_runs(min(max(limit, 1), 100))

    @app.get("/api/agent/runs/{run_id}")
    def agent_run(run_id: str):
        run = ctx.repo.get_agent_run(run_id)
        if not run:
            raise ServiceError("Run not found.", "run_not_found", 404)
        return run

    @app.post("/api/agent/runs/{run_id}/approve")
    def agent_approve(run_id: str, body: ApprovalBody):
        return agent_runner.approve(ctx, run_id, body.reviewer)

    @app.post("/api/agent/runs/{run_id}/reject")
    def agent_reject(run_id: str, body: ApprovalBody):
        return agent_runner.reject(ctx, run_id, body.reviewer)

    # ---- workflows -------------------------------------------------------------------
    wf_engine.ensure_templates(ctx)

    @app.get("/api/workflows/node-types")
    def wf_node_types():
        return wf_engine.describe_node_types()

    @app.get("/api/workflows")
    def wf_list():
        return ctx.repo.list_workflows()

    def _check_graph(graph: dict) -> None:
        errs = wf_engine.validate_graph(graph)
        if errs:
            raise ServiceError(" ".join(errs), "invalid_workflow", 422)

    @app.post("/api/workflows/validate")
    def wf_validate(body: dict):
        errs = wf_engine.validate_graph(body.get("graph") or {})
        return {"valid": not errs, "errors": errs,
                "consequential_nodes": wf_engine.consequential_nodes(body["graph"]) if not errs else []}

    @app.post("/api/workflows")
    def wf_create(body: WorkflowBody):
        _check_graph(body.graph)
        return ctx.repo.save_workflow(None, body.name, body.category, body.description, body.graph)

    @app.post("/api/workflows/{wid}/duplicate")
    def wf_duplicate(wid: str):
        wf = ctx.repo.get_workflow(wid)
        if not wf:
            raise ServiceError("Workflow not found.", "workflow_not_found", 404)
        return ctx.repo.save_workflow(None, wf["name"] + " (copy)", wf["category"], wf["description"], wf["graph"])

    @app.put("/api/workflows/{wid}")
    def wf_update(wid: str, body: WorkflowBody):
        wf = ctx.repo.get_workflow(wid)
        if not wf:
            raise ServiceError("Workflow not found.", "workflow_not_found", 404)
        if wf["is_template"]:
            raise ServiceError("Templates are read-only. Duplicate it to edit.", "template_readonly", 409)
        _check_graph(body.graph)
        return ctx.repo.save_workflow(wid, body.name, body.category, body.description, body.graph)

    @app.delete("/api/workflows/{wid}")
    def wf_delete(wid: str):
        wf = ctx.repo.get_workflow(wid)
        if not wf:
            raise ServiceError("Workflow not found.", "workflow_not_found", 404)
        if wf["is_template"]:
            raise ServiceError("Templates cannot be deleted.", "template_readonly", 409)
        ctx.repo.delete_workflow(wid)
        return {"deleted": wid}

    @app.post("/api/workflows/{wid}/run")
    def wf_run(wid: str, body: ApprovalBody):
        return wf_engine.create_run(ctx, wid, (body.reviewer or "anonymous-reviewer")[:60])

    @app.get("/api/workflow-runs")
    def wf_runs(workflow_id: Optional[str] = None):
        return ctx.repo.list_workflow_runs(workflow_id)

    @app.get("/api/workflow-runs/{rid}")
    def wf_run_get(rid: str):
        run = ctx.repo.get_workflow_run(rid)
        if not run:
            raise ServiceError("Run not found.", "run_not_found", 404)
        return run

    @app.post("/api/workflow-runs/{rid}/approve")
    def wf_run_approve(rid: str, body: ApprovalBody):
        return wf_engine.approve_run(ctx, rid, body.reviewer)

    @app.post("/api/workflow-runs/{rid}/reject")
    def wf_run_reject(rid: str, body: ApprovalBody):
        return wf_engine.reject_run(ctx, rid, body.reviewer)

    # ---- knowledge -------------------------------------------------------------------
    @app.get("/api/knowledge")
    def k_list(status: Optional[str] = None):
        return ctx.repo.list_knowledge(status if status in ("draft", "approved") else None)

    @app.post("/api/knowledge")
    def k_create(body: KnowledgeBody):
        return knowledge_svc.create(ctx, body.title, body.kind, body.body, body.provenance, body.reviewer)

    @app.put("/api/knowledge/{kid}")
    def k_edit(kid: int, body: KnowledgeEditBody):
        return knowledge_svc.edit(ctx, kid, body.title, body.body, body.reviewer)

    @app.post("/api/knowledge/{kid}/approve")
    def k_approve(kid: int, body: ApprovalBody):
        return knowledge_svc.approve(ctx, kid, body.reviewer)

    @app.get("/api/knowledge/{kid}/versions")
    def k_versions(kid: int):
        if not ctx.repo.get_knowledge(kid):
            raise ServiceError("Knowledge item not found.", "knowledge_not_found", 404)
        return ctx.repo.knowledge_versions(kid)

    @app.post("/api/knowledge/{kid}/restore")
    def k_restore(kid: int, body: RestoreBody):
        return knowledge_svc.restore(ctx, kid, body.version, body.reviewer)

    @app.delete("/api/knowledge/{kid}")
    def k_delete(kid: int, reviewer: str = ""):
        if not ctx.repo.get_knowledge(kid):
            raise ServiceError("Knowledge item not found.", "knowledge_not_found", 404)
        knowledge_svc._name(reviewer)
        ctx.repo.delete_knowledge(kid, reviewer.strip()[:60])
        return {"deleted": kid}

    @app.get("/app")
    def studio_app():
        return FileResponse(str(STATIC_DIR / "app.html"), media_type="text/html")

    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
    return app


def get_app() -> FastAPI:  # for `uvicorn src.api.app:get_app --factory`
    return create_app()
