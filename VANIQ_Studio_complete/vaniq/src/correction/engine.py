"""Dialect-aware correction backends.

IMPORTANT HONESTY NOTE
----------------------
`RuleBasedBackend` is a lexicon lookup with optional neighbouring-token context. It is NOT a trained
model and it contains NO built-in Ahirani linguistic knowledge. It only proposes changes that exist
as entries in the lexicon, which humans populate and verify. Its "confidence" is a transparent
heuristic (see `_score`), not a calibrated probability, until enough human review decisions exist
to measure per-rule acceptance rates, which are then blended in and reported.

Nothing here edits the raw transcript. Backends only *propose* spans; a human accepts, rejects or
modifies each proposal (see src/services/review.py).

Replacing/augmenting this with a trained model: subclass `CorrectionBackend`, implement `propose`,
register it in `_BACKENDS`. The rest of the system (storage, review UI, evaluation) is backend-agnostic
and records which backend produced every suggestion.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from abc import ABC, abstractmethod
from typing import Iterable, Optional

from src.correction.models import LexiconEntry, ProposedCorrection

logger = logging.getLogger(__name__)

_PUNCT = ",.;:!?।॥\"'()[]{}…“”‘’"
_TOKEN_RE = re.compile(r"[^\s" + re.escape(_PUNCT) + r"]+")

# Prior trust by lexicon status. Heuristic starting points, NOT probabilities.
_STATUS_PRIOR = {"verified": 0.85, "candidate": 0.50, "demo": 0.50}
_MIN_DECISIONS_FOR_EMPIRICAL = 5


def norm_token(text: str) -> str:
    return unicodedata.normalize("NFC", text).lower()


class CorrectionBackend(ABC):
    name = "abstract"

    @abstractmethod
    def propose(self, text: str, lexicon: Iterable[LexiconEntry],
                rule_stats: Optional[dict] = None) -> list[ProposedCorrection]:
        """Return non-overlapping proposed corrections for `text` (offsets are Python str indices)."""


class NullBackend(CorrectionBackend):
    name = "none"

    def propose(self, text, lexicon, rule_stats=None):
        return []


class _Tok:
    __slots__ = ("text", "norm", "start", "end")

    def __init__(self, text: str, start: int, end: int):
        self.text, self.norm, self.start, self.end = text, norm_token(text), start, end


def _tokenize(text: str) -> list[_Tok]:
    return [_Tok(m.group(0), m.start(), m.end()) for m in _TOKEN_RE.finditer(text)]


class RuleBasedBackend(CorrectionBackend):
    name = "rule-based"

    def propose(self, text: str, lexicon: Iterable[LexiconEntry],
                rule_stats: Optional[dict] = None) -> list[ProposedCorrection]:
        rule_stats = rule_stats or {}
        entries = [e for e in lexicon if e.enabled and e.source_form.strip()]
        candidates: list[tuple[int, ProposedCorrection]] = []  # (priority, proposal)

        candidates += self._normalization_proposals(text)

        toks = _tokenize(text)
        # Ambiguity: the same source form (and context) mapped to different targets
        groups: dict[tuple, set] = {}
        for e in entries:
            groups.setdefault((norm_token(e.source_form), norm_token(e.context_prev), norm_token(e.context_next)),
                              set()).add(norm_token(e.target_form))

        for e in entries:
            src_tokens = [norm_token(t) for t in e.source_form.split()]
            n = len(src_tokens)
            for i in range(len(toks) - n + 1):
                window = toks[i:i + n]
                if [t.norm for t in window] != src_tokens:
                    continue
                if not self._contiguous(text, window):
                    continue
                prev_tok = toks[i - 1] if i > 0 else None
                next_tok = toks[i + n] if i + n < len(toks) else None
                if e.context_prev and (prev_tok is None or prev_tok.norm != norm_token(e.context_prev)
                                       or not self._same_clause(text, prev_tok, window[0])):
                    continue
                if e.context_next and (next_tok is None or next_tok.norm != norm_token(e.context_next)
                                       or not self._same_clause(text, window[-1], next_tok)):
                    continue
                start, end = window[0].start, window[-1].end
                original = text[start:end]
                if unicodedata.normalize("NFC", original) == unicodedata.normalize("NFC", e.target_form):
                    continue  # already in target form
                ambiguous = len(groups[(norm_token(e.source_form), norm_token(e.context_prev),
                                        norm_token(e.context_next))]) > 1
                conf, basis = self._score(e, ambiguous, rule_stats.get(f"lex:{e.id}"))
                explanation = self._explain(e, original, ambiguous)
                priority = (n * 10) + (2 if (e.context_prev or e.context_next) else 0) + (1 if e.status == "verified" else 0)
                candidates.append((priority, ProposedCorrection(
                    start_char=start, end_char=end, original=original, replacement=e.target_form,
                    kind=e.kind, backend=self.name, rule_id=f"lex:{e.id}", confidence=conf,
                    confidence_basis=basis, explanation=explanation,
                    uncertain=(e.status != "verified" or conf < 0.8 or ambiguous))))

        return self._resolve_overlaps(candidates)

    # -- helpers -----------------------------------------------------------------------
    @staticmethod
    def _contiguous(text: str, window: list[_Tok]) -> bool:
        return all(text[window[k].end:window[k + 1].start].strip() == "" for k in range(len(window) - 1))

    @staticmethod
    def _same_clause(text: str, left: _Tok, right: _Tok) -> bool:
        """Context never crosses sentence-final punctuation (. ? ! । ॥); commas and spaces are fine."""
        return re.fullmatch(r"[\s,;:]*", text[left.end:right.start]) is not None

    @staticmethod
    def _normalization_proposals(text: str) -> list[tuple[int, ProposedCorrection]]:
        """Deterministic, language-agnostic hygiene: Unicode NFC and repeated spaces. No linguistic claims."""
        out: list[tuple[int, ProposedCorrection]] = []
        for m in re.finditer(r"[ \t]{2,}", text):
            out.append((1, ProposedCorrection(
                m.start(), m.end(), m.group(0), " ", "normalization", "rule-based", "norm:whitespace", 0.99,
                "deterministic whitespace rule", "Collapses repeated spaces. No linguistic change.", uncertain=False)))
        for t in _tokenize(text):
            nfc = unicodedata.normalize("NFC", t.text)
            if nfc != t.text:
                out.append((1, ProposedCorrection(
                    t.start, t.end, t.text, nfc, "normalization", "rule-based", "norm:nfc", 0.99,
                    "deterministic Unicode rule",
                    "Re-encodes the token as canonical Unicode (NFC); visually identical.", uncertain=False)))
        return out

    @staticmethod
    def _score(e: LexiconEntry, ambiguous: bool, stats: Optional[dict]) -> tuple[float, str]:
        prior = _STATUS_PRIOR.get(e.status, 0.4)
        parts = [f"prior {prior:.2f} from entry status '{e.status}'"]
        conf = prior
        if e.context_prev or e.context_next:
            conf = min(0.95, conf + 0.05)
            parts.append("+0.05 context constraint satisfied")
        if ambiguous:
            conf *= 0.6
            parts.append("x0.6 other lexicon entries map the same form differently")
        if stats:
            decided = stats.get("accepted", 0) + stats.get("rejected", 0) + stats.get("modified", 0)
            if decided >= _MIN_DECISIONS_FOR_EMPIRICAL:
                rate = stats.get("accepted", 0) / decided
                conf = (conf + rate) / 2
                parts.append(f"blended with observed acceptance {stats.get('accepted', 0)}/{decided} reviewer decisions")
        parts.append("heuristic, not a calibrated probability")
        return round(conf, 3), "; ".join(parts)

    @staticmethod
    def _explain(e: LexiconEntry, original: str, ambiguous: bool) -> str:
        msg = (f"Lexicon entry #{e.id} ({e.kind}, status: {e.status}) maps “{e.source_form}” → “{e.target_form}”.")
        if e.context_prev:
            msg += f" Requires previous word “{e.context_prev}”."
        if e.context_next:
            msg += f" Requires next word “{e.context_next}”."
        if e.provenance:
            msg += f" Source: {e.provenance}."
        if e.notes:
            msg += f" Note: {e.notes}"
        if e.status != "verified":
            msg += " This entry has NOT been verified by a human reviewer."
        if ambiguous:
            msg += " Another entry maps the same form to a different target; review carefully."
        return msg

    @staticmethod
    def _resolve_overlaps(cands: list[tuple[int, ProposedCorrection]]) -> list[ProposedCorrection]:
        cands = sorted(cands, key=lambda c: (-c[0], c[1].start_char))
        chosen: list[ProposedCorrection] = []
        for _, p in cands:
            if any(p.start_char < q.end_char and q.start_char < p.end_char for q in chosen):
                logger.debug("Dropping overlapping proposal %s at %d-%d", p.rule_id, p.start_char, p.end_char)
                continue
            chosen.append(p)
        return sorted(chosen, key=lambda p: p.start_char)


_BACKENDS = {"rule-based": RuleBasedBackend, "none": NullBackend}


def get_backend(name: str = "rule-based") -> CorrectionBackend:
    try:
        return _BACKENDS[name]()
    except KeyError:
        raise ValueError(f"Unknown correction backend {name!r}; available: {sorted(_BACKENDS)}") from None
