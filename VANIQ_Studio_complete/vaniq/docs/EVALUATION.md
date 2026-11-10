# Evaluation methodology

* **Ground truth** is the human-verified reference on a clip. STT output is never ground truth.
* **Hypotheses:** *before* = raw STT text; *after* = raw text plus only the corrections a reviewer accepted or modified.
* **Normalization (both sides):** NFC; remove zero-width joiners/format characters; remove punctuation and symbols (including `।`);
  keep letters, vowel signs, viramas, digits; lower-case; collapse whitespace.
  (The original pilot code removed vowel signs and viramas, so earlier `wer_norm/cer_norm` values were computed on corrupted text.)
* **Script handling:** if the reference and hypothesis primary scripts differ (e.g. Devanagari vs Gujarati), the sample is
  excluded and counted by reason. No transliteration is attempted. Mixed-script text is flagged.
* **Metrics:** corpus-level WER (word edit distance ÷ reference words) and CER (character edit distance ÷ reference characters,
  spaces included), before and after, on the same paired samples; substitutions/deletions/insertions are stored per sample.
  A macro-average WER is also reported.
* **Uncertainty:** with n ≥ 10 a seeded 1000-resample clip-level bootstrap gives a 95% interval for the WER change; below 10 none is shown.
* **Sanity flags:** raw WER > 100% is flagged as a possible reference/audio mismatch. The historical pilot reference
  ("नमस्कार मी एक प्रयोग करतोय") has 400% WER against its transcripts, which suggests it belongs to a different recording.
* **Limitations:** see `src/evaluation/report.py::LIMITATIONS` (shown in the UI). Notably, evaluating a lexicon on clips used to
  build it overstates generalization; single reviewers are not inter-annotator agreement.

## Baseline results and Ahirani claims (P0)
Aggregates are reported per `experiment_role`. Provider transcripts (including `mr-IN` and `indic-auto`) are `baseline`
and are never shown as Ahirani performance. The report's `claims` block states that native Ahirani STT support has not been
independently verified, and `ahirani_stt_performance_claim_allowed` is false unless candidate-role results exist and
`NATIVE_AHIRANI_STT_VERIFIED` has been set after independent verification.
