# Engineering handover: VANIQ Local 1.0

## 1. What already existed (audited, not assumed)
Inspected from the ZIP: Gnani client, experiment runner, WER/CER + script detection, FFmpeg normalization, quality metrics,
Auditok segmentation, CSV metadata, 34 tests, pilot results.
Baseline run: **32 passed, 2 failed** (`test_client.py` required a private audio file that is not in the repo).

## 2. Defects found and fixed
| Defect | Impact | Fix |
|---|---|---|
| `normalize_text` removed Indic vowel signs and viramas (`[^\w\s]`) | **Pilot `wer_norm`/`cer_norm` were computed on corrupted text** | Category-based normalization; regression tests |
| Pilot reference "नमस्कार मी एक प्रयोग करतोय" vs transcripts "मना नाव दीपक शे…" gives WER 400% | Reference likely belongs to a different clip; pilot numbers are not meaningful | Evaluation now flags WER > 100%; **you should re-check that reference against the audio** |
| Re-ingesting a clip overwrote manual transcript, verification and review status in `metadata.csv` | Silent loss of human work | Human fields preserved; regression test |
| `VAD_MAX_DURATION = 5 s` split continuous speech mid-phrase | Bad clips | Default 15 s, configurable (`VANIQ_SEG_MAX_DUR_S`) |
| Client: no retry/typed errors, crashed on missing file, `print` logging | Fragile | Retries on 5xx/429/network, `GnaniError` hierarchy, logging |
| Ingestion swallowed transcription errors; README flag `--permitted_usage` mismatched CLI | Confusing | Logging; README corrected |
| `evaluate.py` scored cross-script pairs | Misleading numbers | Cross-script excluded |

## 3. What was added
SQLite storage with migrations; FastAPI backend; build-free frontend (dashboard, upload/record, workspace with inline diff and
review, lexicon, datasets/export, evaluation, about); STT provider abstraction (Gnani, demo-mock); rule-based dialect correction
engine behind a pluggable interface; human review with audit log; verified references; permission-gated export;
script-aware before/after evaluation with bootstrap CI; demo mode and seed data; CLI; docs; 73 new tests.

## 4. What works (verified)
* Test suite: **107 passed** in a clean virtualenv built from `requirements-lock.txt` (Python 3.12, FFmpeg present).
* Server starts; all API routes and all seven UI pages load; accept/review, evaluation and export flows executed end to end
  against the live server using jsdom (no real browser was available).
* Ingest verified for wav, mp3, m4a, ogg and webm/opus (what browsers record).
* Live mode without a key returns 503 `stt_not_configured`; nothing is simulated.

## 5. What was NOT verified or is incomplete
* **No real Gnani call was made** (no key here). Request format is taken from the original client and stored pilot responses;
  tests mock the HTTP layer. Run one real transcription before relying on it.
* **No Ahirani linguistic content is shipped.** The lexicon is empty in live mode; correction quality on real Ahirani is unknown.
* Not manually tested in real browsers (Chrome/Firefox/Safari); microphone recording in particular.
* No authentication; single-user SQLite.
* No trained correction model, no dialect identification, no train/test split tooling.
* Segmentation threshold (50) needs calibration on real recordings.
* `results/` pilot files and any `audio/` or `references/` were deliberately **not** included in the ZIP (private; they remain in your original).

## 6. Run it
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-lock.txt
VANIQ_MODE=demo python -m src.cli serve     # http://127.0.0.1:8000 -> "Load demo data"
python -m pytest -q                          # expect 107 passed
# real use:
cp .env.example .env && edit GNANI_API_KEY   # VANIQ_MODE=live
python -m src.cli serve
```

## 7. Suggested next steps
1. Verify the pilot reference against `clip_001` and re-run Marathi vs auto-detect inside the app (import the old outputs as transcripts).
2. Record a small consented multi-speaker set; agree a spelling convention; have a second fluent reviewer verify.
3. Populate the lexicon from reviewer corrections (candidates → verified with provenance), then evaluate on *held-out* clips.
4. Only then consider a trained correction backend.
