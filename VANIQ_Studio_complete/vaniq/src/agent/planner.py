"""Command-mode planner.

HONEST LIMITS: this is NOT an LLM. It maps a fixed set of phrases to tool calls. Anything it does not recognise is
reported as unsupported, with the list of supported commands. An `llm` planner can implement `Planner.plan` later;
none is implemented or claimed here.
"""
from __future__ import annotations

import re
from typing import Optional

from src.context import AppContext

MODE = "command"
SUPPORTED = [
    "what needs doing / status",
    "validate audio (this recording / all)",
    "check transcript mismatch (this clip / all)",
    "who needs a human reference / review queue",
    "check dataset eligibility (public / internal)",
    "run baseline mr-IN | run baseline indic-auto (this clip / all untranscribed clips)  [needs approval]",
    "propose corrections (this clip)",
    "run evaluation",
    "export dataset (public / internal)  [needs approval]",
    "show knowledge / conventions",
]
_HEX = re.compile(r"\b([0-9a-f]{8,16})\b")


class Plan(dict):
    """status: ready | needs_input | unsupported"""


def _lang(text: str) -> Optional[str]:
    if re.search(r"mr-in|marathi", text):
        return "mr-IN"
    if re.search(r"indic-auto|auto-?detect|\bauto\b", text):
        return "indic-auto"
    return None


def plan(ctx: AppContext, message: str, context: Optional[dict] = None) -> Plan:
    text = (message or "").strip().lower()
    context = context or {}
    clip_id = context.get("clip_id")
    source_id = context.get("source_id")
    m = _HEX.search(text)
    if m and ctx.repo.get_clip(m.group(1)):
        clip_id = m.group(1)

    def ready(steps, msg):
        return Plan(status="ready", message=msg, steps=steps)

    def need(msg):
        return Plan(status="needs_input", message=msg, steps=[])

    if not text:
        return need("Tell me what to do. Try: " + "; ".join(SUPPORTED[:4]) + ".")

    # Refuse human-authority operations explicitly
    if re.search(r"\b(verify|write|set|overwrite|replace)\b.*\breference\b|\baccept\b.*\b(correction|suggestion)s?\b|\bapprove\b.*\bknowledge\b|\bmark\b.*\bverified\b", text):
        return Plan(status="unsupported", steps=[],
                    message="I can't write or verify human references, decide corrections, or approve knowledge. Those are human decisions "
                            "(Studio, Knowledge). I can show who still needs a reference: ask “who needs a human reference”.")

    visibility = "internal" if "internal" in text else "public"
    if re.search(r"\bexport\b|\bdownload dataset\b", text):
        include_unknown = bool(re.search(r"unknown", text)) and visibility == "internal"
        return ready([{"tool": "create_export", "args": {"visibility": visibility, "include_unknown_internal": include_unknown}}],
                     f"I’ll export the eligible clips for a {visibility} dataset. Permission rules apply; this needs your approval.")
    if re.search(r"eligib|can i export|ready to export|exportable", text):
        return ready([{"tool": "check_dataset_eligibility", "args": {"visibility": visibility}}],
                     f"Checking which clips are eligible for a {visibility} export.")
    if re.search(r"evaluat|\bwer\b|\bcer\b|score|report", text):
        return ready([{"tool": "run_evaluation", "args": {"language_code": _lang(text)}}], "Generating the evaluation report from human-verified references.")
    if re.search(r"transcribe|baseline|\bstt\b|run .*(mr-in|marathi|auto)", text):
        lang = _lang(text)
        if not lang:
            return need("Which STT baseline setting should I use: mr-IN (Marathi baseline) or indic-auto (provider auto-detect)? "
                        "Both are baseline experiments, not Ahirani recognition.")
        if re.search(r"\ball\b|every|untranscribed|pending|without", text):
            ids = [c["id"] for c in ctx.repo.list_clips() if c["transcript_count"] == 0 and c["permission_status"] != "denied"][:25]
            if not ids:
                return need("Every clip already has a transcript (or its permission is denied).")
            return ready([{"tool": "transcribe_clip", "args": {"clip_id": i, "language_code": lang}} for i in ids],
                         f"I’ll run the {lang} STT baseline on {len(ids)} clip(s) with no transcript. This sends audio to the provider, so it needs your approval.")
        if not clip_id:
            return need("Select a recording clip first, or say “run baseline mr-IN on all untranscribed clips”.")
        return ready([{"tool": "transcribe_clip", "args": {"clip_id": clip_id, "language_code": lang}}],
                     f"I’ll run the {lang} STT baseline on clip {clip_id[:8]}. This needs your approval.")
    if re.search(r"mismatch|inconsisten|wrong reference|doesn.?t match", text):
        return ready([{"tool": "detect_transcript_mismatch", "args": {"clip_id": clip_id} if clip_id and "all" not in text else {}}],
                     "Comparing transcripts with human references (read-only).")
    if re.search(r"propos|suggest.*correction|correction", text):
        if not clip_id:
            return need("Select a clip with a transcript first.")
        ts = ctx.repo.list_transcripts(clip_id)
        if not ts:
            return need("That clip has no transcript yet. Run a baseline first.")
        return ready([{"tool": "propose_corrections", "args": {"transcript_id": ts[-1]["id"]}}],
                     "Proposing corrections from the lexicon. They stay pending until a human decides.")
    if re.search(r"validate|audio|quality|file", text):
        return ready([{"tool": "validate_audio", "args": {"source_id": source_id} if source_id and "all" not in text else {}}],
                     "Validating stored audio (read-only).")
    if re.search(r"human reference|who needs|review queue|awaiting|verification", text):
        return ready([{"tool": "reference_workflow_status", "args": {}}], "Listing clips still waiting for a human reference.")
    if re.search(r"knowledge|convention|memory", text):
        return ready([{"tool": "list_knowledge", "args": {}}], "Showing human-approved knowledge.")
    if re.search(r"status|what needs|what's|whats|todo|queue|summary|work", text):
        return ready([{"tool": "list_work", "args": {}}], "Summarising the current work queues.")
    return Plan(status="unsupported", steps=[],
                message="I’m running in command mode (no language model is configured), so I only understand a fixed set of requests. "
                        "Supported: " + "; ".join(SUPPORTED) + ".")
