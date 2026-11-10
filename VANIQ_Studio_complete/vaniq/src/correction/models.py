from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class LexiconEntry:
    """One reviewable correction rule.

    `status` expresses how much the rule can be trusted:
      demo      synthetic placeholder used only by demo mode
      candidate proposed but not yet confirmed by a fluent speaker/linguist
      verified  confirmed by a human reviewer (provenance should say who/what source)
    The project never ships linguistic content of its own; entries come from users.
    """
    id: int
    source_form: str
    target_form: str
    kind: str = "lexical"             # lexical | spelling | normalization
    context_prev: str = ""
    context_next: str = ""
    status: str = "candidate"
    provenance: str = ""
    notes: str = ""
    enabled: bool = True

    @classmethod
    def from_row(cls, row: dict) -> "LexiconEntry":
        return cls(id=row["id"], source_form=row["source_form"], target_form=row["target_form"],
                   kind=row.get("kind", "lexical"), context_prev=row.get("context_prev", "") or "",
                   context_next=row.get("context_next", "") or "", status=row.get("status", "candidate"),
                   provenance=row.get("provenance", "") or "", notes=row.get("notes", "") or "",
                   enabled=bool(row.get("enabled", 1)))


@dataclass
class ProposedCorrection:
    start_char: int
    end_char: int
    original: str
    replacement: str
    kind: str
    backend: str
    rule_id: Optional[str]
    confidence: float
    confidence_basis: str
    explanation: str
    uncertain: bool = True

    def to_dict(self) -> dict:
        return asdict(self)
