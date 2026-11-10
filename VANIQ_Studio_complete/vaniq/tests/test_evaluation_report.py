from src.evaluation.metrics import (detect_script, error_counts, is_mixed_script, normalize_text, calculate_wer)
from src.evaluation.report import evaluate_samples

DEV = "नमस्कार मी एक प्रयोग करतोय"
GUJ = "નમસ્તે મિત્રો"


def test_normalization_preserves_indic_vowel_signs_and_viramas():
    # Regression: original implementation stripped matras/viramas (e.g. 'मी' -> 'म').
    out = normalize_text(DEV + "।")
    assert out == DEV
    assert "ी" in out and "्" in out


def test_normalization_strips_punctuation_zwj_and_case():
    assert normalize_text("Hello,  World!\u200d") == "hello world"
    assert normalize_text("शे, आस्ते।") == "शे आस्ते"


def test_error_counts_breakdown():
    c = error_counts("a b c d".split(), "a x c".split())
    assert c == {"substitutions": 1, "deletions": 1, "insertions": 0, "distance": 2, "ref_len": 4}


def test_script_profile_and_mixed():
    assert detect_script("हॅलो hello") in ("Devanagari", "Latin")
    assert is_mixed_script("नमस्कार hello world") is True
    assert is_mixed_script(DEV) is False
    assert detect_script("123 !!") == "Other/Unknown"


def test_before_after_scoring():
    r = evaluate_samples([{"clip_id": "c1", "reference": "a b c d", "raw": "a x c d", "corrected": "a b c d"}])
    agg = r["aggregate"]
    assert agg["n"] == 1
    assert agg["before"]["wer"] == 0.25 and agg["after"]["wer"] == 0.0
    assert agg["delta_wer"] == -0.25
    assert r["sample_count_scored"] == 1
    assert agg["bootstrap_ci"] is None  # n < 10


def test_script_mismatch_is_excluded_not_scored():
    r = evaluate_samples([{"clip_id": "c1", "reference": DEV, "raw": GUJ, "corrected": GUJ}])
    assert r["sample_count_scored"] == 0
    assert r["excluded_by_reason"] == {"script_mismatch": 1}
    assert r["aggregate"] is None
    assert any("No scorable" in w for w in r["warnings"])


def test_empty_reference_and_hypothesis_excluded():
    r = evaluate_samples([
        {"clip_id": "a", "reference": "", "raw": "x", "corrected": "x"},
        {"clip_id": "b", "reference": "x", "raw": "", "corrected": ""}])
    assert r["excluded_by_reason"] == {"empty_reference": 1, "empty_hypothesis": 1}


def test_high_wer_flags_possible_reference_mismatch():
    r = evaluate_samples([{"clip_id": "c", "reference": "a", "raw": "b c d e f", "corrected": "b c d e f"}])
    assert any("raw_wer_above_100pct" in w for w in r["samples"][0]["warnings"])


def test_pilot_reference_mismatch_is_flagged():
    # The historical pilot compared a short unrelated reference with a long hypothesis: WER 400%.
    ref = "नमस्कार मी एक प्रयोग करतोय"
    hyp = "मना नाव दीपक शे मी इंजिनिअरिंग करी रायनू आस्ते आर सी पी आय टी मा ए आय एम एल ब्रांच शे"
    r = evaluate_samples([{"clip_id": "p", "reference": ref, "raw": hyp, "corrected": hyp}])
    assert r["samples"][0]["before"]["wer"] > 1.0
    assert r["samples"][0]["warnings"]


def test_bootstrap_ci_present_for_ten_or_more_and_deterministic():
    samples = [{"clip_id": str(i), "reference": "a b c", "raw": "a x c", "corrected": "a b c" if i % 2 else "a x c"}
               for i in range(12)]
    r1, r2 = evaluate_samples(samples), evaluate_samples(samples)
    ci = r1["aggregate"]["bootstrap_ci"]
    assert ci is not None and ci["low"] <= ci["high"]
    assert ci == r2["aggregate"]["bootstrap_ci"]


def test_no_change_warning():
    r = evaluate_samples([{"clip_id": "c", "reference": "a b", "raw": "a x", "corrected": "a x"}])
    assert any("before == after" in w for w in r["warnings"])


def test_paired_sets_identical():
    r = evaluate_samples([{"clip_id": "c", "reference": "a b", "raw": "a b", "corrected": "a b"}])
    assert r["aggregate"]["before"]["ref_words"] == r["aggregate"]["after"]["ref_words"] == 2


def test_wer_wrapper_behaviour_unchanged():
    assert calculate_wer("", "x") == 1.0 and calculate_wer("a", "a") == 0.0
