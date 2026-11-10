"""Before/after-correction evaluation with transparent script handling.

Rules (see docs/EVALUATION.md):
* Only clips with a human-verified reference are scored. Raw STT output is never a reference.
* If the reference and a hypothesis are written in different primary scripts, the sample is EXCLUDED
  from aggregate WER/CER and reported with the reason. VANIQ does not transliterate, because doing so
  would silently introduce another source of error.
* Before/after metrics are computed on the same paired sample set only.
* Aggregates are corpus-level (total errors / total reference units), plus a macro mean.
* A seeded bootstrap interval for the WER/CER change is shown only when n >= 10 and is labelled as such.
"""
from __future__ import annotations

import random
from typing import Any, Optional

from src.baseline import (NATIVE_AHIRANI_STT_VERIFIED, NATIVE_SUPPORT_STATEMENT, ROLE_BASELINE, ROLE_CANDIDATE,
                          ROLE_LABELS)

from src.evaluation.metrics import (NORMALIZATION_STEPS, detect_script, error_counts, is_mixed_script,
                                    normalize_text)

LIMITATIONS = [
    "Metrics are only as reliable as the human reference transcripts; a single reviewer's judgement is not "
    "inter-annotator agreement.",
    "Small sample sizes give very wide uncertainty. Do not generalise to 'Ahirani accuracy' from a handful of clips.",
    "Ahirani has no standardised orthography; a correct word can be spelled several ways, which inflates WER/CER. "
    "Choose and document a spelling convention for references.",
    "Cross-script samples are excluded rather than transliterated; coverage of the evaluation set is reported.",
    "Corrections are evaluated only where a reviewer accepted or modified them. 'After' scores therefore measure "
    "human-approved corrections, not an autonomous model.",
    "A rule-based lexicon tuned on the same clips it is evaluated on will look better than it generalises. "
    "Evaluate on clips whose words were not used to create lexicon entries.",
    "STT language codes are model-reported language detection, not dialect identification.",
]


def _score(ref_n: str, hyp_n: str) -> dict:
    w = error_counts(ref_n.split(), hyp_n.split())
    c = error_counts(list(ref_n), list(hyp_n))
    return {"wer": (w["distance"] / w["ref_len"]) if w["ref_len"] else None,
            "cer": (c["distance"] / c["ref_len"]) if c["ref_len"] else None,
            "word_errors": w, "char_errors": c}


def _round(x: Optional[float]) -> Optional[float]:
    return None if x is None else round(x, 4)


def evaluate_samples(samples: list[dict], *, seed: int = 1234) -> dict[str, Any]:
    """samples: dicts with clip_id, reference, raw, corrected, optional is_synthetic."""
    rows, included, excluded = [], [], []
    for s in samples:
        ref, raw, corr = s.get("reference") or "", s.get("raw") or "", s.get("corrected") or ""
        ref_script, raw_script, corr_script = detect_script(ref), detect_script(raw), detect_script(corr)
        row: dict[str, Any] = {
            "clip_id": s["clip_id"], "is_synthetic": bool(s.get("is_synthetic")),
            "reference": ref, "raw": raw, "corrected": corr,
            "experiment_role": s.get("experiment_role", ROLE_BASELINE), "provider": s.get("provider"),
            "language_code_requested": s.get("language_code_requested"),
            "reference_script": ref_script, "raw_script": raw_script, "corrected_script": corr_script,
            "corrections_applied": raw != corr, "warnings": [],
        }
        reason = None
        ref_n, raw_n, corr_n = normalize_text(ref), normalize_text(raw), normalize_text(corr)
        if not ref_n:
            reason = "empty_reference"
        elif not raw_n:
            reason = "empty_hypothesis"
        elif ref_script != raw_script or (corr_n and ref_script != corr_script):
            reason = "script_mismatch"
        if is_mixed_script(ref) or is_mixed_script(raw):
            row["warnings"].append("mixed_script_text")
        if reason:
            row["excluded_reason"] = reason
            excluded.append(row)
            rows.append(row)
            continue
        before, after = _score(ref_n, raw_n), _score(ref_n, corr_n)
        row["before"], row["after"] = before, after
        if before["wer"] is not None and before["wer"] > 1.0:
            row["warnings"].append(
                "raw_wer_above_100pct: check that the reference matches this audio (possible wrong/mismatched reference)")
        included.append(row)
        rows.append(row)

    agg = _aggregate(included, seed)
    by_role = _by_role(included, seed)
    if agg:
        agg["scope"] = "all roles combined; NOT an Ahirani performance figure (see claims)"
    return {
        "sample_count_total": len(samples),
        "sample_count_scored": len(included),
        "sample_count_excluded": len(excluded),
        "excluded_by_reason": _count_reasons(excluded),
        "aggregate": agg,
        "by_role": by_role,
        "claims": ahirani_claim_status(by_role),
        "samples": [_jsonable(r) for r in rows],
        "contains_synthetic_samples": any(r["is_synthetic"] for r in rows),
        "normalization": NORMALIZATION_STEPS,
        "script_policy": "Samples whose reference and hypothesis primary scripts differ are excluded, not transliterated.",
        "limitations": LIMITATIONS,
        "warnings": _global_warnings(included, excluded, agg),
    }


def _by_role(rows: list[dict], seed: int) -> dict[str, Any]:
    """Aggregates are always reported per experiment role so baseline numbers stay separate."""
    out: dict[str, Any] = {}
    for role in sorted({r["experiment_role"] for r in rows}):
        group = [r for r in rows if r["experiment_role"] == role]
        agg = _aggregate(group, seed)
        if agg:
            agg["scope"] = ROLE_LABELS.get(role, role)
        out[role] = {
            "label": ROLE_LABELS.get(role, role), "n_scored": len(group), "aggregate": agg,
            "language_codes_requested": sorted({r["language_code_requested"] for r in group if r["language_code_requested"]}),
            "is_ahirani_performance": role == ROLE_CANDIDATE and NATIVE_AHIRANI_STT_VERIFIED,
        }
    return out


def ahirani_claim_status(by_role: dict[str, Any]) -> dict[str, Any]:
    """Ahirani STT performance may only be claimed from 'candidate' results AND an independent verification record.
    In P0 neither exists, so the claim is never allowed and no baseline figure is promoted."""
    cand = by_role.get(ROLE_CANDIDATE)
    allowed = bool(NATIVE_AHIRANI_STT_VERIFIED and cand and cand["n_scored"] > 0)
    return {
        "ahirani_stt_performance_claim_allowed": allowed,
        "ahirani_stt_performance": cand["aggregate"] if allowed else None,
        "statement": NATIVE_SUPPORT_STATEMENT,
        "baseline_scored_samples": by_role.get(ROLE_BASELINE, {}).get("n_scored", 0),
    }


def _count_reasons(excluded: list[dict]) -> dict:
    out: dict[str, int] = {}
    for r in excluded:
        out[r["excluded_reason"]] = out.get(r["excluded_reason"], 0) + 1
    return out


def _corpus(rows: list[dict], phase: str) -> dict:
    we = sum(r[phase]["word_errors"]["distance"] for r in rows)
    wn = sum(r[phase]["word_errors"]["ref_len"] for r in rows)
    ce = sum(r[phase]["char_errors"]["distance"] for r in rows)
    cn = sum(r[phase]["char_errors"]["ref_len"] for r in rows)
    return {"wer": _round(we / wn) if wn else None, "cer": _round(ce / cn) if cn else None,
            "word_errors": we, "ref_words": wn, "char_errors": ce, "ref_chars": cn}


def _aggregate(rows: list[dict], seed: int) -> Optional[dict]:
    if not rows:
        return None
    before, after = _corpus(rows, "before"), _corpus(rows, "after")
    agg: dict[str, Any] = {
        "n": len(rows), "before": before, "after": after,
        "delta_wer": _round(after["wer"] - before["wer"]) if before["wer"] is not None else None,
        "delta_cer": _round(after["cer"] - before["cer"]) if before["cer"] is not None else None,
        "macro_mean_wer_before": _round(sum(r["before"]["wer"] for r in rows) / len(rows)),
        "macro_mean_wer_after": _round(sum(r["after"]["wer"] for r in rows) / len(rows)),
        "samples_changed_by_corrections": sum(1 for r in rows if r["corrections_applied"]),
        "bootstrap_ci": None,
    }
    if len(rows) >= 10:
        rng = random.Random(seed)
        deltas = []
        for _ in range(1000):
            res = [rows[rng.randrange(len(rows))] for _ in rows]
            b, a = _corpus(res, "before")["wer"], _corpus(res, "after")["wer"]
            if b is not None and a is not None:
                deltas.append(a - b)
        deltas.sort()
        agg["bootstrap_ci"] = {"metric": "delta_wer", "level": 0.95, "resamples": 1000, "seed": seed,
                               "low": _round(deltas[int(0.025 * len(deltas))]),
                               "high": _round(deltas[int(0.975 * len(deltas)) - 1]),
                               "note": "Clip-level bootstrap; speaker/session dependence is ignored."}
    return agg


def _global_warnings(included, excluded, agg) -> list[str]:
    w = []
    n = len(included)
    if n == 0:
        w.append("No scorable samples: verify clips (human reference) first.")
    elif n < 30:
        w.append(f"Only {n} scored sample(s): results are anecdotal, not statistically meaningful.")
    if excluded:
        w.append(f"{len(excluded)} sample(s) excluded (see excluded_by_reason).")
    if agg and agg["samples_changed_by_corrections"] == 0:
        w.append("No accepted corrections changed any scored transcript, so before == after.")
    return w


def _jsonable(row: dict) -> dict:
    out = dict(row)
    for k in ("before", "after"):
        if k in out:
            out[k] = {"wer": _round(out[k]["wer"]), "cer": _round(out[k]["cer"]),
                      "word_errors": out[k]["word_errors"], "char_errors": out[k]["char_errors"]}
    return out
