"""Linguistic-integrity constants (P0).

Gnani Prisma documents Marathi support; native Ahirani support has NOT been independently verified. Therefore every
transcript produced by an STT provider in VANIQ is an *STT baseline experiment*, whatever language code was requested.
Nothing in the system may present baseline results as Ahirani performance.
"""
from __future__ import annotations

import copy
import json
import re
from typing import Any, Iterable, Optional

# Stored in transcripts.experiment_role
ROLE_BASELINE = "baseline"          # provider output under a non-Ahirani setting (mr-IN, indic-auto, ...)
ROLE_CANDIDATE = "candidate"        # reserved: provider/model independently verified for Ahirani. Never assigned in P0.
ROLE_HUMAN_IMPORT = "human_import"  # transcript imported from outside VANIQ (provenance label records the origin)
EXPERIMENT_ROLES = (ROLE_BASELINE, ROLE_CANDIDATE, ROLE_HUMAN_IMPORT)

ROLE_LABELS = {
    ROLE_BASELINE: "STT baseline experiment (not Ahirani performance)",
    ROLE_CANDIDATE: "Candidate Ahirani system",
    ROLE_HUMAN_IMPORT: "Imported transcript (produced outside VANIQ)",
}

# Flip only when an independent verification record exists. Controls whether any Ahirani performance claim is allowed.
NATIVE_AHIRANI_STT_VERIFIED = False

NATIVE_SUPPORT_STATEMENT = (
    "Native Ahirani STT support has not been independently verified. Results under Marathi (mr-IN) and indic-auto "
    "settings are STT baseline experiments, not Ahirani performance."
)

# Language codes the UI offers. Both are baseline experiment settings; any other valid code is baseline too.
BASELINE_SETTINGS = {
    "indic-auto": "Provider auto-detects the language. STT baseline experiment setting; detection is not dialect identification.",
    "mr-IN": "Requests Marathi. STT baseline experiment setting; Marathi is not Ahirani.",
}


def role_for_transcript(provider: str) -> str:
    """Role assigned at creation. Provider output is always baseline until Ahirani support is independently verified."""
    return ROLE_HUMAN_IMPORT if provider == "imported" else ROLE_BASELINE


_SENSITIVE_KEY = re.compile(r"(api[-_ ]?key|apikey|token|secret|authorization|password|credential|x-api|headers?|config)",
                            re.IGNORECASE)
REDACTED = "[redacted]"


def sanitize_provider_response(value: Any, secrets: Optional[Iterable[str]] = None) -> Any:
    """Return a copy of a provider response that is safe to show or export.

    * Accepts a dict/list or a JSON string; returns plain Python data (None stays None).
    * Redacts values under credential/config-like keys and any literal occurrence of a known secret.
    The stored provider body should never contain credentials (requests carry them in headers, which are not stored);
    this is defence in depth.
    """
    secret_list = [s for s in (secrets or []) if s]
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return _scrub_str(value, secret_list)
    return _walk(copy.deepcopy(value), secret_list)


def _scrub_str(s: str, secrets: list[str]) -> str:
    for sec in secrets:
        s = s.replace(sec, REDACTED)
    return s


def _walk(v: Any, secrets: list[str]) -> Any:
    if isinstance(v, dict):
        return {k: (REDACTED if _SENSITIVE_KEY.search(str(k)) else _walk(x, secrets)) for k, x in v.items()}
    if isinstance(v, list):
        return [_walk(x, secrets) for x in v]
    if isinstance(v, str):
        return _scrub_str(v, secrets)
    return v
