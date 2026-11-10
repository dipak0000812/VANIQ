"""Workflow engine. Nodes are real operations; an edge is real data flow.

Each node has typed ports. `clips` carries clip ids; `transcripts` carries (clip, transcript) pairs and is accepted anywhere
`clips` is; `report` and `file` are terminal outputs. An edge is valid only if the producer's output type is accepted by the
consumer's input type, and the executor passes exactly the producer's output to the consumer.

Consequential nodes (STT provider call, dataset export) require human approval before a run starts.
`human_review_gate` passes only clips a person has verified; it never verifies anything.
"""
from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from src.baseline import sanitize_provider_response
from src.context import AppContext
from src.services import transcribe as transcribe_svc
from src.services.errors import ServiceError
from src.services.evaluation_service import run_evaluation
from src.services.export import clip_exclusion_reason, export_dataset
from src.services.validation import probe_audio
from src.storage.repo import REVIEW_STATUSES

logger = logging.getLogger(__name__)
MAX_NODES = 40


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class NodeType:
    type: str
    title: str
    description: str
    accepts: Optional[str]            # None = source node (no input)
    produces: str
    consequential: bool
    config: dict                      # name -> {"type","default","options"?,"required"?}
    run: Callable[[AppContext, dict, Optional[dict], str], dict]
    category: str = "Data"


def accepts_type(consumer_accepts: Optional[str], producer_out: str) -> bool:
    if consumer_accepts is None:
        return False
    if consumer_accepts == producer_out:
        return True
    return consumer_accepts == "clips" and producer_out == "transcripts"      # a transcript set projects onto its clips


def _clips(ids): return {"type": "clips", "clip_ids": list(dict.fromkeys(ids))}


def _ids(data: dict) -> list[str]:
    return list(data.get("clip_ids", []))


# ---------------------------------------------------------------- node implementations
def n_select(ctx, cfg, data, actor):
    status = cfg.get("review_status") or "any"
    rows = ctx.repo.list_clips(review_status=None if status == "any" else status, source_id=cfg.get("source_id") or None)
    denied = [c for c in rows if c["permission_status"] == "denied"]
    rows = [c for c in rows if c["permission_status"] != "denied"]
    if cfg.get("only_untranscribed"):
        rows = [c for c in rows if c["transcript_count"] == 0]
    return {"output": _clips([c["id"] for c in rows]), "summary": f"{len(rows)} clip(s) selected" +
            (f"; {len(denied)} excluded because permission is denied" if denied else "")}


def n_validate(ctx, cfg, data, actor):
    ok, dropped = [], []
    for cid in _ids(data):
        c = ctx.repo.get_clip(cid)
        problem = None
        if not c or not os.path.isfile(c["path"]):
            problem = "audio file missing"
        else:
            try:
                info = probe_audio(c["path"])
                if info.duration_s < 0.2:
                    problem = "too short"
            except ServiceError as exc:
                problem = exc.message
        (dropped.append({"clip_id": cid, "problem": problem}) if problem else ok.append(cid))
    return {"output": _clips(ok), "summary": f"{len(ok)} valid, {len(dropped)} dropped", "details": {"dropped": dropped}}


def n_stt(ctx, cfg, data, actor):
    ids, items, errors = _ids(data), [], []
    for cid in ids:
        try:
            t = transcribe_svc.transcribe_clip(ctx, cid, cfg["language_code"], actor=actor, run_correction=False)
            items.append({"clip_id": cid, "transcript_id": t["id"]})
        except ServiceError as exc:
            errors.append({"clip_id": cid, "code": exc.code, "message": exc.message})
    if ids and not items:
        raise ServiceError(f"No clip could be transcribed. First error: {errors[0]['message']}", errors[0]["code"], 502)
    return {"output": {"type": "transcripts", "clip_ids": [i["clip_id"] for i in items], "items": items},
            "summary": f"{len(items)} baseline transcript(s) created under setting {cfg['language_code']}" +
                       (f"; {len(errors)} failed" if errors else ""),
            "details": {"errors": errors, "experiment_role": "baseline"}}


def n_propose(ctx, cfg, data, actor):
    total = 0
    for it in data.get("items", []):
        total += len(transcribe_svc.propose_corrections(ctx, it["transcript_id"], actor=actor))
    return {"output": data, "summary": f"{total} suggestion(s) pending human review"}


def n_gate(ctx, cfg, data, actor):
    passed, waiting = [], []
    for cid in _ids(data):
        c = ctx.repo.get_clip(cid)
        (passed if c and c["review_status"] == "verified" and c.get("reference_transcript") else waiting).append(cid)
    return {"output": _clips(passed), "summary": f"{len(passed)} human-verified clip(s) passed; {len(waiting)} waiting for a human",
            "details": {"waiting_for_human": waiting}}


def n_eligibility(ctx, cfg, data, actor):
    keep, excluded = [], {}
    for cid in _ids(data):
        c = ctx.repo.get_clip(cid)
        r = clip_exclusion_reason(c, cfg["visibility"], False, True) if c else "missing"
        if r is None:
            keep.append(cid)
        else:
            excluded[r] = excluded.get(r, 0) + 1
    return {"output": _clips(keep), "summary": f"{len(keep)} eligible for a {cfg['visibility']} export", "details": {"excluded_by_reason": excluded}}


def n_evaluate(ctx, cfg, data, actor):
    r = run_evaluation(ctx, clip_ids=_ids(data), language_code=cfg.get("language_code") or None)
    return {"output": {"type": "report", "run_id": r.get("run_id"), "claims": r["claims"]},
            "summary": f"{r['sample_count_scored']} sample(s) scored; Ahirani claim allowed: {r['claims']['ahirani_stt_performance_claim_allowed']}",
            "details": {"by_role": {k: v["n_scored"] for k, v in r["by_role"].items()}, "warnings": r["warnings"]}}


def n_export(ctx, cfg, data, actor):
    out = export_dataset(ctx, cfg["visibility"], False, True, "workflow-export", clip_ids=_ids(data))
    m = out["manifest"]
    return {"output": {"type": "file", "download": f"/api/exports/download/{os.path.basename(out['zip_path'])}"},
            "summary": f"{m['clip_count']} clip(s) exported ({m['visibility']})", "details": {"excluded_counts": m["excluded_counts"]}}


_VIS = {"type": "select", "options": ["public", "internal"], "default": "public"}
NODE_TYPES: dict[str, NodeType] = {n.type: n for n in [
    NodeType("select_clips", "Select clips", "Choose recordings' clips by review status; denied-permission clips are never selected.",
             None, "clips", False, {"review_status": {"type": "select", "options": ["any", *REVIEW_STATUSES], "default": "any"},
                                    "only_untranscribed": {"type": "boolean", "default": False},
                                    "source_id": {"type": "string", "default": ""}}, n_select, "Intake"),
    NodeType("validate_audio", "Validate audio", "Drop clips whose audio is missing, unreadable or too short.", "clips", "clips", False, {}, n_validate, "Intake"),
    NodeType("stt_baseline", "STT baseline", "Send clips to the STT provider as a baseline experiment (never Ahirani performance).",
             "clips", "transcripts", True, {"language_code": {"type": "select", "options": ["mr-IN", "indic-auto"], "default": "mr-IN", "required": True}},
             n_stt, "Baseline"),
    NodeType("propose_corrections", "Propose corrections", "Run lexicon corrections; suggestions stay pending for a human.",
             "transcripts", "transcripts", False, {}, n_propose, "Review"),
    NodeType("human_review_gate", "Human review gate", "Pass only clips a person has verified. Never verifies anything itself.",
             "clips", "clips", False, {}, n_gate, "Review"),
    NodeType("check_eligibility", "Check eligibility", "Keep only clips eligible for the chosen export visibility.", "clips", "clips", False,
             {"visibility": _VIS}, n_eligibility, "Export"),
    NodeType("evaluate", "Evaluate", "WER/CER on the incoming verified clips, separated by experiment role.", "clips", "report", False,
             {"language_code": {"type": "string", "default": ""}}, n_evaluate, "Evaluation"),
    NodeType("export_dataset", "Export dataset", "Create a permission-gated export of the incoming clips.", "clips", "file", True,
             {"visibility": _VIS}, n_export, "Export"),
]}


def describe_node_types() -> list[dict]:
    return [{"type": n.type, "title": n.title, "description": n.description, "accepts": n.accepts, "produces": n.produces,
             "consequential": n.consequential, "config": n.config, "category": n.category} for n in NODE_TYPES.values()]


# ---------------------------------------------------------------- validation
def validate_graph(graph: dict) -> list[str]:
    errors: list[str] = []
    nodes, edges = graph.get("nodes"), graph.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        return ["Graph must have 'nodes' and 'edges' lists."]
    if not nodes:
        return ["Add at least one node."]
    if len(nodes) > MAX_NODES:
        return [f"At most {MAX_NODES} nodes are allowed."]
    ids = [n.get("id") for n in nodes]
    if len(set(ids)) != len(ids) or any(not isinstance(i, str) or not i for i in ids):
        return ["Node ids must be unique non-empty strings."]
    by_id = {n["id"]: n for n in nodes}
    for n in nodes:
        nt = NODE_TYPES.get(n.get("type"))
        if not nt:
            errors.append(f"Node {n['id']}: unknown type {n.get('type')!r}.")
            continue
        cfg = n.get("config") or {}
        for key, spec in nt.config.items():
            val = cfg.get(key, spec.get("default"))
            if spec.get("required") and val in (None, ""):
                errors.append(f"Node {n['id']} ({nt.title}): '{key}' is required.")
            if spec["type"] == "select" and val not in spec["options"]:
                errors.append(f"Node {n['id']} ({nt.title}): '{key}' must be one of {spec['options']}.")
        for key in cfg:
            if key not in nt.config:
                errors.append(f"Node {n['id']} ({nt.title}): unknown setting '{key}'.")
    incoming: dict[str, list[str]] = {i: [] for i in by_id}
    for e in edges:
        a, b = e.get("from"), e.get("to")
        if a not in by_id or b not in by_id:
            errors.append(f"Edge {a}→{b} references a missing node.")
            continue
        incoming[b].append(a)
        pa, pb = NODE_TYPES.get(by_id[a].get("type")), NODE_TYPES.get(by_id[b].get("type"))
        if pa and pb and not accepts_type(pb.accepts, pa.produces):
            errors.append(f"Cannot connect {pa.title} (outputs {pa.produces}) to {pb.title} "
                          f"({'takes no input' if pb.accepts is None else 'expects ' + pb.accepts}).")
    for i, srcs in incoming.items():
        nt = NODE_TYPES.get(by_id[i].get("type"))
        if not nt:
            continue
        if nt.accepts is None and srcs:
            errors.append(f"Node {i} ({nt.title}) is a source and cannot have an input.")
        elif nt.accepts is not None and len(srcs) != 1:
            errors.append(f"Node {i} ({nt.title}) needs exactly one input connection (has {len(srcs)}).")
    if not errors and _topo(by_id, edges) is None:
        errors.append("The workflow contains a cycle.")
    return errors


def _topo(by_id: dict, edges: list) -> Optional[list[str]]:
    indeg = {i: 0 for i in by_id}
    adj: dict[str, list[str]] = {i: [] for i in by_id}
    for e in edges:
        adj[e["from"]].append(e["to"]); indeg[e["to"]] += 1
    q, order = [i for i, d in indeg.items() if d == 0], []
    while q:
        n = q.pop(0); order.append(n)
        for m in adj[n]:
            indeg[m] -= 1
            if indeg[m] == 0:
                q.append(m)
    return order if len(order) == len(by_id) else None


def consequential_nodes(graph: dict) -> list[str]:
    return [n["id"] for n in graph["nodes"] if NODE_TYPES[n["type"]].consequential]


# ---------------------------------------------------------------- run lifecycle
def create_run(ctx: AppContext, workflow_id: str, actor: str, background: bool = True) -> dict:
    wf = ctx.repo.get_workflow(workflow_id)
    if not wf:
        raise ServiceError("Workflow not found.", "workflow_not_found", 404)
    errors = validate_graph(wf["graph"])
    if errors:
        raise ServiceError("Workflow is invalid: " + " ".join(errors), "invalid_workflow", 422)
    needs = bool(consequential_nodes(wf["graph"]))
    run = ctx.repo.create_workflow_run(workflow_id, actor, "awaiting_approval" if needs else "ready", wf["graph"])
    ctx.repo.audit(actor, "workflow_run_created", "workflow_run", run["id"], {"workflow": workflow_id, "needs_approval": needs})
    if not needs:
        _start(ctx, run["id"], actor, background, "ready")
    return ctx.repo.get_workflow_run(run["id"])


def approve_run(ctx: AppContext, run_id: str, reviewer: str, background: bool = True) -> dict:
    reviewer = (reviewer or "").strip()[:60]
    if not reviewer:
        raise ServiceError("A reviewer name is required to approve.", "reviewer_required", 422)
    run = ctx.repo.get_workflow_run(run_id)
    if not run:
        raise ServiceError("Run not found.", "run_not_found", 404)
    if run["status"] != "awaiting_approval":
        raise ServiceError(f"This run is {run['status']} and cannot be approved.", "bad_state", 409)
    ctx.repo.update_workflow_run(run_id, approved_by=reviewer, approved_at=_now())
    ctx.repo.audit(reviewer, "workflow_run_approved", "workflow_run", run_id, {"consequential_nodes": consequential_nodes(run["graph"])})
    _start(ctx, run_id, reviewer, background, "awaiting_approval")
    return ctx.repo.get_workflow_run(run_id)


def reject_run(ctx: AppContext, run_id: str, reviewer: str) -> dict:
    run = ctx.repo.get_workflow_run(run_id)
    if not run:
        raise ServiceError("Run not found.", "run_not_found", 404)
    if run["status"] != "awaiting_approval":
        raise ServiceError(f"This run is {run['status']} and cannot be rejected.", "bad_state", 409)
    states = {k: {"status": "skipped"} for k in run["node_states"]}
    ctx.repo.update_workflow_run(run_id, status="rejected", node_states=states, finished_at=_now())
    ctx.repo.audit((reviewer or "anonymous-reviewer")[:60], "workflow_run_rejected", "workflow_run", run_id)
    return ctx.repo.get_workflow_run(run_id)


def _start(ctx, run_id, actor, background, expected):
    if not ctx.repo.transition_run("workflow_runs", run_id, expected, "running"):
        raise ServiceError("This run is not in a startable state.", "bad_state", 409)
    if background:
        threading.Thread(target=execute, args=(ctx, run_id, actor), daemon=True, name=f"wf-run-{run_id}").start()
    else:
        execute(ctx, run_id, actor)


def execute(ctx: AppContext, run_id: str, actor: str) -> None:
    run = ctx.repo.get_workflow_run(run_id)
    graph, states = run["graph"], run["node_states"]
    by_id = {n["id"]: n for n in graph["nodes"]}
    order = _topo(by_id, graph["edges"]) or []
    producer_of = {e["to"]: e["from"] for e in graph["edges"]}
    outputs: dict[str, dict] = {}
    failed_msg: Optional[str] = None
    try:
        for nid in order:
            nt = NODE_TYPES[by_id[nid]["type"]]
            if failed_msg:
                states[nid] = {"status": "skipped"}
                continue
            cfg = {k: (by_id[nid].get("config") or {}).get(k, spec.get("default")) for k, spec in nt.config.items()}
            data = outputs.get(producer_of.get(nid)) if nt.accepts else None
            states[nid] = {"status": "running", "started_at": _now()}
            ctx.repo.update_workflow_run(run_id, node_states=states)
            try:
                res = nt.run(ctx, cfg, data, actor)
                outputs[nid] = res["output"]
                states[nid] = {"status": "done", "summary": res.get("summary", ""), "output_type": nt.produces,
                               "output_count": len(res["output"].get("clip_ids", [])) if "clip_ids" in res["output"] else None,
                               "details": sanitize_provider_response(res.get("details"), [ctx.settings.gnani_api_key]),
                               "output_ref": {k: v for k, v in res["output"].items() if k in ("download", "run_id")},
                               "finished_at": _now()}
            except ServiceError as exc:
                states[nid] = {"status": "failed", "error": {"code": exc.code, "message": exc.message}, "finished_at": _now()}
                failed_msg = f"{nt.title}: {exc.message}"
            except Exception as exc:                                   # noqa: BLE001 - recorded, never swallowed silently
                logger.exception("Workflow node failed")
                states[nid] = {"status": "failed", "error": {"code": "internal_error", "message": f"{type(exc).__name__}: {exc}"}, "finished_at": _now()}
                failed_msg = f"{nt.title}: {type(exc).__name__}: {exc}"
            ctx.repo.audit(actor, f"workflow_node_{states[nid]['status']}", "workflow_run", run_id, {"node": nid, "type": nt.type})
            ctx.repo.update_workflow_run(run_id, node_states=states)
    finally:
        ctx.repo.update_workflow_run(run_id, status="failed" if failed_msg else "completed", node_states=states,
                                     finished_at=_now(), error=failed_msg)
        ctx.repo.audit(actor, "workflow_run_failed" if failed_msg else "workflow_run_completed", "workflow_run", run_id)


# ---------------------------------------------------------------- templates (original VANIQ workflows)
def _g(nodes, edges):
    return {"nodes": [{"id": i, "type": t, "config": c, "x": x, "y": y} for i, t, c, x, y in nodes],
            "edges": [{"from": a, "to": b} for a, b in edges]}


TEMPLATES = [
    ("tpl-intake", "Recording intake", "Intake", "Select new clips and validate their audio.",
     _g([("n1", "select_clips", {"only_untranscribed": True}, 40, 60), ("n2", "validate_audio", {}, 300, 60)], [("n1", "n2")])),
    ("tpl-baseline", "STT baseline experiment", "Baseline", "Run a Marathi-setting STT baseline on untranscribed clips and queue corrections for review. Not Ahirani recognition.",
     _g([("n1", "select_clips", {"only_untranscribed": True}, 40, 60), ("n2", "validate_audio", {}, 280, 60),
         ("n3", "stt_baseline", {"language_code": "mr-IN"}, 520, 60), ("n4", "propose_corrections", {}, 760, 60)],
        [("n1", "n2"), ("n2", "n3"), ("n3", "n4")])),
    ("tpl-evaluation", "Verified clips to evaluation", "Evaluation", "Pass only human-verified clips to the evaluation report.",
     _g([("n1", "select_clips", {}, 40, 60), ("n2", "human_review_gate", {}, 280, 60), ("n3", "evaluate", {}, 520, 60)],
        [("n1", "n2"), ("n2", "n3")])),
    ("tpl-dataset", "Dataset preparation", "Export", "Verified clips, eligibility check, then a permission-gated export.",
     _g([("n1", "select_clips", {}, 40, 60), ("n2", "human_review_gate", {}, 280, 60), ("n3", "check_eligibility", {"visibility": "public"}, 520, 60),
         ("n4", "export_dataset", {"visibility": "public"}, 760, 60)], [("n1", "n2"), ("n2", "n3"), ("n3", "n4")])),
]


def ensure_templates(ctx: AppContext) -> None:
    for wid, name, cat, desc, graph in TEMPLATES:
        if not ctx.repo.get_workflow(wid):
            ctx.repo.save_workflow(wid, name, cat, desc, graph, is_template=True)
