from src.correction.apply import apply_suggestions, render_segments
from src.correction.engine import CorrectionBackend, RuleBasedBackend, get_backend
from src.correction.models import LexiconEntry, ProposedCorrection

__all__ = ["apply_suggestions", "render_segments", "CorrectionBackend", "RuleBasedBackend", "get_backend",
           "LexiconEntry", "ProposedCorrection"]
