"""Agent run lifecycle: plan -> (auto-run | await approval) -> execute -> audit.

Rules enforced here (and tested):
* a run containing any consequential step does not execute until a named human approves it;
* a step is marked done only after its tool returned; failures carry the real error and skip later steps;
* a run can be executed at most once (atomic status transition);
* tool outputs are sanitised before storage.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Optional

from src.agent import planner
from src.agent.tools import CONSEQUENTIAL, TOOLS, validate_args
from src.baseline import sanitize_provider_response
from src.context import AppContext
from src.services.errors import ServiceError

logger = logging.getLogger(__name__)
MAX_STEPS = 30


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def llm_available() -> bool:
    return False   # no LLM planner is implemented


def status() -> dict:
    return {"mode": planner.MODE, "llm_available": llm_available(), "supported_commands": planner.SUPPORTED,
            "message": "Command mode: no language model is configured. VANIQ understands a fixed set of commands; "
                       "nothing is simulated."}


def _build_steps(raw_steps: list[dict]) -> list[dict]:
    if not raw_steps:
        return []
    if len(raw_steps) > MAX_STEPS:
        raise ServiceError(f"A plan may contain at most {MAX_STEPS} steps.", "too_many_steps", 422)
    steps = []
    for i, s in enumerate(raw_steps, 1):
        model = validate_args(s.get("tool", ""), s.get("args") or {})
        tool = TOOLS[s["tool"]]
        steps.append({"id": i, "tool": tool.name, "title": tool.title, "args": model.model_dump(), "impact": tool.impact,
                      "requires_approval": tool.impact == CONSEQUENTIAL, "status": "pending", "result": None, "error": None,
                      "started_at": None, "finished_at": None})
    return steps


def create_run(ctx: AppContext, actor: str, message: str = "", context: Optional[dict] = None,
               steps: Optional[list[dict]] = None, background: bool = True) -> dict:
    """Plan from a message (command mode) or accept explicit tool steps (skills). Auto-runs only if nothing is consequential."""
    context = context or {}
    note = ""
    if steps is None:
        p = planner.plan(ctx, message, context)
        note = p["message"]
        if p["status"] != "ready":
            run = ctx.repo.create_agent_run(actor, message, planner.MODE, "unsupported" if p["status"] == "unsupported" else "needs_input",
                                            context, [], note)
            ctx.repo.audit(actor, "agent_plan", "agent_run", run["id"], {"status": run["status"]})
            return run
        steps = p["steps"]
    built = _build_steps(steps)
    if not built:
        raise ServiceError("A plan needs at least one step.", "empty_plan", 422)
    needs = any(s["requires_approval"] for s in built)
    run = ctx.repo.create_agent_run(actor, message or "(skill run)", planner.MODE, "awaiting_approval" if needs else "ready",
                                    context, built, note)
    ctx.repo.audit(actor, "agent_plan", "agent_run", run["id"], {"steps": [s["tool"] for s in built], "needs_approval": needs})
    if not needs:
        start(ctx, run["id"], actor, background)
    return ctx.repo.get_agent_run(run["id"])


def approve(ctx: AppContext, run_id: str, reviewer: str, background: bool = True) -> dict:
    reviewer = (reviewer or "").strip()[:60]
    if not reviewer:
        raise ServiceError("A reviewer name is required to approve.", "reviewer_required", 422)
    run = ctx.repo.get_agent_run(run_id)
    if not run:
        raise ServiceError("Run not found.", "run_not_found", 404)
    if run["status"] != "awaiting_approval":
        raise ServiceError(f"This run is {run['status']} and cannot be approved.", "bad_state", 409)
    ctx.repo.update_agent_run(run_id, approved_by=reviewer, approved_at=_now())
    ctx.repo.audit(reviewer, "agent_approve", "agent_run", run_id, {"steps": [s["tool"] for s in run["steps"]]})
    start(ctx, run_id, reviewer, background, expected="awaiting_approval")
    return ctx.repo.get_agent_run(run_id)


def reject(ctx: AppContext, run_id: str, reviewer: str) -> dict:
    run = ctx.repo.get_agent_run(run_id)
    if not run:
        raise ServiceError("Run not found.", "run_not_found", 404)
    if run["status"] != "awaiting_approval":
        raise ServiceError(f"This run is {run['status']} and cannot be rejected.", "bad_state", 409)
    steps = run["steps"]
    for s in steps:
        s["status"] = "skipped"
    ctx.repo.update_agent_run(run_id, status="rejected", steps=steps, finished_at=_now())
    ctx.repo.audit((reviewer or "anonymous-reviewer")[:60], "agent_reject", "agent_run", run_id)
    return ctx.repo.get_agent_run(run_id)


def start(ctx: AppContext, run_id: str, actor: str, background: bool = True, expected: str = "ready") -> None:
    if not ctx.repo.transition_run("agent_runs", run_id, expected, "running"):
        raise ServiceError("This run is not in a startable state.", "bad_state", 409)
    if background:
        threading.Thread(target=execute, args=(ctx, run_id, actor), daemon=True, name=f"agent-run-{run_id}").start()
    else:
        execute(ctx, run_id, actor)


def execute(ctx: AppContext, run_id: str, actor: str) -> None:
    run = ctx.repo.get_agent_run(run_id)
    steps, failed = run["steps"], False
    try:
        for s in steps:
            if failed:
                s["status"] = "skipped"
                continue
            s["status"], s["started_at"] = "running", _now()
            ctx.repo.update_agent_run(run_id, steps=steps)
            try:
                model = validate_args(s["tool"], s["args"])           # re-validate at execution time
                result = TOOLS[s["tool"]].fn(ctx, model, actor)
                s["result"] = sanitize_provider_response(result, [ctx.settings.gnani_api_key])
                s["status"] = "done"
            except ServiceError as exc:
                s["status"], s["error"], failed = "failed", {"code": exc.code, "message": exc.message}, True
            except Exception as exc:                                   # noqa: BLE001 - recorded, never swallowed silently
                logger.exception("Agent step failed")
                s["status"], s["error"], failed = "failed", {"code": "internal_error", "message": f"{type(exc).__name__}: {exc}"}, True
            s["finished_at"] = _now()
            ctx.repo.audit(actor, f"agent_step_{s['status']}", "agent_run", run_id, {"tool": s["tool"], "error": s["error"]})
            ctx.repo.update_agent_run(run_id, steps=steps)
    finally:
        final = "failed" if failed else "completed"
        ctx.repo.update_agent_run(run_id, status=final, steps=steps, finished_at=_now())
        ctx.repo.audit(actor, f"agent_run_{final}", "agent_run", run_id)
