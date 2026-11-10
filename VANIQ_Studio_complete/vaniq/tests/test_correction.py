import pytest

from src.correction import RuleBasedBackend, apply_suggestions, get_backend, render_segments
from src.correction.models import LexiconEntry as L


def props(text, lex, stats=None):
    return RuleBasedBackend().propose(text, lex, stats)


def test_no_lexicon_means_no_linguistic_suggestions():
    assert props("anything at all", []) == []


def test_basic_lexical_match_with_punctuation_and_offsets():
    text = "one dform1, two"
    p = props(text, [L(1, "dform1", "sform1", status="demo")])
    assert len(p) == 1
    assert (text[p[0].start_char:p[0].end_char], p[0].replacement) == ("dform1", "sform1")
    assert p[0].rule_id == "lex:1" and p[0].backend == "rule-based"


def test_unverified_entries_are_flagged_uncertain_with_explanation():
    p = props("dform1", [L(1, "dform1", "sform1", status="candidate", provenance="reviewer X")])[0]
    assert p.uncertain and p.confidence == 0.5
    assert "NOT been verified" in p.explanation and "reviewer X" in p.explanation
    assert "heuristic" in p.confidence_basis


def test_verified_entry_has_higher_confidence_and_is_not_uncertain():
    p = props("dform1", [L(1, "dform1", "s", status="verified", provenance="linguist")])[0]
    assert p.confidence == 0.85 and p.uncertain is False


def test_context_constraints():
    e = L(1, "dform3", "sform3", context_prev="also", status="verified")
    assert props("x also dform3", [e])
    assert not props("x then dform3", [e])
    assert not props("also. dform3", [e])           # does not cross sentence boundary
    assert props("also, dform3", [e])               # commas are fine
    assert not props("dform3", [e])                 # missing previous word


def test_context_next():
    e = L(1, "d4", "s4", context_next="beta", status="verified")
    assert len(props("d4 beta d4 gamma", [e])) == 1


def test_multiword_entry_and_longest_match_wins():
    lex = [L(1, "alpha beta", "AB", status="demo"), L(2, "beta", "B", status="demo")]
    p = props("alpha beta", lex)
    assert [(x.original, x.replacement) for x in p] == [("alpha beta", "AB")]


def test_ambiguous_entries_lower_confidence_and_flag():
    lex = [L(1, "x", "a", status="verified"), L(2, "x", "b", status="verified")]
    p = props("x", lex)
    assert len(p) == 1 and p[0].uncertain and p[0].confidence < 0.85
    assert "different target" in p[0].explanation


def test_disabled_entries_ignored_and_already_target_skipped():
    assert not props("x", [L(1, "x", "y", enabled=False)])
    assert not props("y", [L(1, "y", "y")])


def test_empirical_acceptance_blends_confidence_after_enough_reviews():
    e = L(1, "x", "y", status="candidate")
    base = props("x", [e])[0].confidence
    blended = props("x", [e], {"lex:1": {"accepted": 5, "rejected": 0, "modified": 0}})[0]
    assert blended.confidence > base and "observed acceptance 5/5" in blended.confidence_basis
    few = props("x", [e], {"lex:1": {"accepted": 2, "rejected": 0, "modified": 0}})[0]
    assert few.confidence == base                    # too few decisions: no blending


def test_normalization_proposals_whitespace_and_nfc():
    p = props("a   b", [])
    assert p and p[0].kind == "normalization" and p[0].replacement == " " and not p[0].uncertain
    decomposed = "e\u0301"  # NFD é
    q = props(decomposed, [])
    assert q and q[0].replacement == "\u00e9"


def test_case_insensitive_latin_match_keeps_original_text_in_span():
    p = props("Say DForm1", [L(1, "dform1", "s", status="demo")])
    assert p[0].original == "DForm1"


def test_apply_only_accepted_and_modified_never_pending_or_rejected():
    raw = "aa bb cc"
    sugg = [
        {"id": 1, "start_char": 0, "end_char": 2, "original": "aa", "replacement": "AA", "status": "accepted", "final_replacement": None},
        {"id": 2, "start_char": 3, "end_char": 5, "original": "bb", "replacement": "BB", "status": "pending", "final_replacement": None},
        {"id": 3, "start_char": 6, "end_char": 8, "original": "cc", "replacement": "CC", "status": "modified", "final_replacement": "c2"},
    ]
    assert apply_suggestions(raw, sugg) == "AA bb c2"
    assert apply_suggestions(raw, sugg, include_pending=True) == "AA BB c2"
    sugg[0]["status"] = "rejected"
    assert apply_suggestions(raw, sugg) == "aa bb c2"
    assert raw == "aa bb cc"  # raw string untouched


def test_apply_skips_stale_or_overlapping_suggestions():
    raw = "hello world"
    stale = {"id": 1, "start_char": 0, "end_char": 5, "original": "WRONG", "replacement": "x", "status": "accepted", "final_replacement": None}
    assert apply_suggestions(raw, [stale]) == raw
    a = {"id": 1, "start_char": 0, "end_char": 5, "original": "hello", "replacement": "H", "status": "accepted", "final_replacement": None}
    b = {"id": 2, "start_char": 3, "end_char": 8, "original": "lo wo", "replacement": "Z", "status": "accepted", "final_replacement": None}
    assert apply_suggestions(raw, [a, b]) == "H world"


def test_render_segments_roundtrip():
    raw = "aa bb"
    s = [{"id": 1, "start_char": 3, "end_char": 5, "original": "bb", "replacement": "B", "status": "pending", "final_replacement": None}]
    segs = render_segments(raw, s)
    assert "".join(x["text"] for x in segs) == raw
    assert segs[1]["suggestion_id"] == 1


def test_get_backend_registry():
    assert get_backend("rule-based").name == "rule-based"
    assert get_backend("none").propose("x", []) == []
    with pytest.raises(ValueError):
        get_backend("nonexistent")


def test_devanagari_tokens_with_danda():
    p = props("आम्ही येतो।", [L(1, "येतो", "X", status="demo")])
    assert p and p[0].original == "येतो"
