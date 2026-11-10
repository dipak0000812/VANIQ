"""Applying reviewed suggestions to raw text. The raw transcript is never modified in storage;
corrected text is always derived from raw + human decisions."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _effective_replacement(s: dict) -> str:
    return s["final_replacement"] if s["status"] == "modified" and s.get("final_replacement") is not None \
        else s["replacement"]


def apply_suggestions(raw: str, suggestions: list[dict], include_pending: bool = False) -> str:
    """Return `raw` with accepted/modified suggestions applied.

    include_pending=True produces a *preview* of "accept everything"; it is never stored as a result.
    Suggestions whose stored original no longer matches the text at their span are skipped (and logged),
    as are overlapping ones.
    """
    wanted = {"accepted", "modified"} | ({"pending"} if include_pending else set())
    chosen = sorted((s for s in suggestions if s["status"] in wanted), key=lambda s: (s["start_char"], s["id"]))
    out, cursor = [], 0
    for s in chosen:
        a, b = s["start_char"], s["end_char"]
        if a < cursor:
            logger.warning("Skipping overlapping suggestion %s", s.get("id"))
            continue
        if raw[a:b] != s["original"]:
            logger.warning("Skipping suggestion %s: text at span changed", s.get("id"))
            continue
        out.append(raw[cursor:a])
        out.append(_effective_replacement(s))
        cursor = b
    out.append(raw[cursor:])
    return "".join(out)


def render_segments(raw: str, suggestions: list[dict]) -> list[dict]:
    """Split raw text into plain and suggestion segments so UIs need not rely on string offsets."""
    segs, cursor = [], 0
    for s in sorted(suggestions, key=lambda s: (s["start_char"], s["id"])):
        a, b = s["start_char"], s["end_char"]
        if a < cursor or raw[a:b] != s["original"]:
            continue
        if a > cursor:
            segs.append({"text": raw[cursor:a], "suggestion_id": None})
        segs.append({"text": raw[a:b], "suggestion_id": s["id"], "status": s["status"],
                     "replacement": _effective_replacement(s)})
        cursor = b
    if cursor < len(raw):
        segs.append({"text": raw[cursor:], "suggestion_id": None})
    return segs
