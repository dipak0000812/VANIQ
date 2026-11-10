"""Text normalization, script detection and WER/CER.

Defect fixed vs. the original pilot code: normalization used `re.sub(r'[^\\w\\s]', '', ...)`, which
deletes Indic vowel signs and viramas (they are combining marks, not `\\w`) and therefore corrupted
Devanagari/Gujarati text before scoring. Normalization now removes only punctuation/symbol/control
characters and keeps letters, combining marks and digits.
"""
from __future__ import annotations

import unicodedata
from collections import Counter
from typing import Dict, List

NORMALIZATION_STEPS = [
    "Unicode NFC normalization",
    "Removal of zero-width joiner/non-joiner and other format characters (category Cf)",
    "Removal of punctuation and symbols (Unicode categories P* and S*, including the danda ।)",
    "Letters, combining vowel signs/viramas and digits are preserved",
    "Lower-casing (affects Latin script only)",
    "Whitespace collapsed to single spaces",
]

_SCRIPT_KEYS = ("DEVANAGARI", "GUJARATI", "LATIN")


def script_profile(text: str) -> Dict[str, int]:
    """Count letters/marks per script (Devanagari, Gujarati, Latin, Other)."""
    counts: Counter = Counter()
    for ch in text or "":
        cat = unicodedata.category(ch)
        if cat[0] not in ("L", "M"):
            continue
        name = unicodedata.name(ch, "")
        for key in _SCRIPT_KEYS:
            if key in name:
                counts[key.capitalize()] += 1
                break
        else:
            counts["Other"] += 1
    return dict(counts)


def detect_script(text: str) -> str:
    """Identify the primary script (Devanagari, Gujarati, Latin) or Other/Unknown."""
    if not text:
        return "Unknown"
    counts = {k: v for k, v in script_profile(text).items() if k != "Other"}
    if not counts:
        return "Other/Unknown"
    return max(counts, key=counts.get)


def is_mixed_script(text: str, threshold: float = 0.2) -> bool:
    prof = {k: v for k, v in script_profile(text).items() if k != "Other"}
    total = sum(prof.values())
    if total == 0 or len(prof) < 2:
        return False
    return sorted(prof.values())[-2] / total >= threshold


def normalize_text(text: str) -> str:
    """Normalize for scoring; see module docstring and NORMALIZATION_STEPS."""
    if not text:
        return ""
    text = unicodedata.normalize("NFC", text)
    kept = []
    for ch in text:
        cat = unicodedata.category(ch)
        if cat == "Cf" or cat[0] in ("P", "S"):
            continue
        kept.append(" " if ch.isspace() or cat == "Cc" else ch)
    return " ".join("".join(kept).split()).lower()


def edit_distance(ref: List[str], hyp: List[str]) -> int:
    """Standard Levenshtein distance (two-row DP)."""
    m, n = len(ref), len(hyp)
    prev = list(range(n + 1))
    for i in range(1, m + 1):
        cur = [i] + [0] * n
        for j in range(1, n + 1):
            cost = 0 if ref[i - 1] == hyp[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
        prev = cur
    return prev[n]


def error_counts(ref: List[str], hyp: List[str]) -> Dict[str, int]:
    """Substitutions / deletions / insertions via DP backtrace."""
    m, n = len(ref), len(hyp)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(m + 1):
        dp[i][0] = i
    for j in range(n + 1):
        dp[0][j] = j
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            cost = 0 if ref[i - 1] == hyp[j - 1] else 1
            dp[i][j] = min(dp[i - 1][j] + 1, dp[i][j - 1] + 1, dp[i - 1][j - 1] + cost)
    i, j, s, d, ins = m, n, 0, 0, 0
    while i > 0 or j > 0:
        if i > 0 and j > 0 and dp[i][j] == dp[i - 1][j - 1] + (0 if ref[i - 1] == hyp[j - 1] else 1):
            s += 0 if ref[i - 1] == hyp[j - 1] else 1
            i, j = i - 1, j - 1
        elif i > 0 and dp[i][j] == dp[i - 1][j] + 1:
            d += 1; i -= 1
        else:
            ins += 1; j -= 1
    return {"substitutions": s, "deletions": d, "insertions": ins, "distance": dp[m][n], "ref_len": m}


def calculate_wer(ref: str, hyp: str) -> float:
    ref_list, hyp_list = ref.split(), hyp.split()
    if not ref_list:
        return 1.0 if hyp_list else 0.0
    return edit_distance(ref_list, hyp_list) / len(ref_list)


def calculate_cer(ref: str, hyp: str) -> float:
    ref_list, hyp_list = list(ref), list(hyp)
    if not ref_list:
        return 1.0 if hyp_list else 0.0
    return edit_distance(ref_list, hyp_list) / len(ref_list)
