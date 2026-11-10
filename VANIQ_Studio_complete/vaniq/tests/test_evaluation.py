import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
from src.evaluation.metrics import normalize_text, calculate_wer, calculate_cer, detect_script

def test_normalization():
    assert normalize_text("Hello, World!") == "hello world"

def test_metrics_identical():
    assert calculate_wer("a b", "a b") == 0.0
    assert calculate_cer("abc", "abc") == 0.0

def test_metrics_exceed_one():
    # When hypothesis is very different from reference, WER/CER can exceed 1.0
    assert calculate_wer("a", "b c d e f g h i j") > 1.0

def test_empty_ref():
    assert calculate_wer("", "word") == 1.0
    assert calculate_cer("", "word") == 1.0

def test_script_detection():
    # Devanagari (e.g., नमस्कार)
    assert detect_script("नमस्कार") == "Devanagari"
    # Gujarati (e.g., નમસ્તે)
    assert detect_script("નમસ્તે") == "Gujarati"
    # Latin
    assert detect_script("Hello") == "Latin"
    # Empty
    assert detect_script("") == "Unknown"

def test_script_mismatch():
    ref = "नमस्कार"
    hyp = "નમસ્તે"
    assert detect_script(ref) != detect_script(hyp)
