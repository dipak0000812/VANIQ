"""Knowledge: human-written, human-approved project conventions and linguistic references.
VANIQ ships no linguistic content. Editing approved text returns it to draft; approval needs a named person."""
from __future__ import annotations

from src.context import AppContext
from src.services.errors import ServiceError

KINDS = ("convention", "reference", "note")


def _name(actor: str) -> str:
    n = (actor or "").strip()[:60]
    if not n:
        raise ServiceError("A reviewer name is required.", "reviewer_required", 422)
    return n


def create(ctx: AppContext, title: str, kind: str, body: str, provenance: str, actor: str) -> dict:
    if kind not in KINDS:
        raise ServiceError(f"kind must be one of {KINDS}.", "bad_kind", 422)
    if not title.strip() or not body.strip():
        raise ServiceError("Title and body are required.", "empty_text", 422)
    return ctx.repo.add_knowledge(title.strip()[:200], kind, body, (provenance or "").strip()[:300] or f"written by {_name(actor)}", _name(actor))


def edit(ctx: AppContext, kid: int, title: str, body: str, actor: str) -> dict:
    if not ctx.repo.get_knowledge(kid):
        raise ServiceError("Knowledge item not found.", "knowledge_not_found", 404)
    if not title.strip() or not body.strip():
        raise ServiceError("Title and body are required.", "empty_text", 422)
    return ctx.repo.edit_knowledge(kid, title.strip()[:200], body, _name(actor))


def approve(ctx: AppContext, kid: int, actor: str) -> dict:
    item = ctx.repo.get_knowledge(kid)
    if not item:
        raise ServiceError("Knowledge item not found.", "knowledge_not_found", 404)
    if item["status"] == "approved":
        raise ServiceError("Already approved.", "bad_state", 409)
    return ctx.repo.approve_knowledge(kid, _name(actor))


def restore(ctx: AppContext, kid: int, version: int, actor: str) -> dict:
    v = next((x for x in ctx.repo.knowledge_versions(kid) if x["version"] == version), None)
    if not v:
        raise ServiceError("Version not found.", "version_not_found", 404)
    return ctx.repo.edit_knowledge(kid, v["title"], v["body"], _name(actor))   # restoring creates a new draft version
