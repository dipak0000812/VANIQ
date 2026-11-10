# Architecture

One Python process: FastAPI serves a JSON API and a static, build-free frontend. SQLite stores everything; audio lives
on disk. No queues, containers or microservices.

```
browser (vanilla JS) ──HTTP──> FastAPI (src/api/app.py)
                                  │ thin handlers
                                  ▼
                            services/  ingest · transcribe · review · evaluation_service · export · demo
                              │          │               │
              dataset_factory/  stt/      correction/     evaluation/
              (ffmpeg, auditok) (gnani,   (backends,      (metrics, report)
                                 demo)     lexicon rules)
                                  ▼
                       storage/repo.py ─ SQLite (data/<mode>/vaniq.db) + files (uploads, normalized, clips, exports)
```

## Data model (src/storage/migrations/0001_init.sql)
`sources` (a recording + provenance + permission) → `clips` (segments, quality, review state, human reference) →
`transcripts` (one per STT/import run; raw text immutable) → `suggestions` (proposed corrections, with human decisions).
Also `lexicon_entries`, `eval_runs`, `audit_log`. Migrations are forward-only numbered SQL files applied at start-up.

## Key decisions
* **Raw is immutable.** Corrected text is always derived: `raw + accepted/modified suggestions`. Pending and rejected
  suggestions never change output (`correction/apply.py`).
* **Demo and live are separate worlds.** `VANIQ_MODE` selects `data/demo` or `data/live`. The demo STT provider is only
  reachable in demo mode; live mode without a key raises `stt_not_configured` rather than mocking.
* **Pluggable correction.** `CorrectionBackend.propose(text, lexicon, rule_stats)` returns spans. A trained model can be
  added in `correction/engine.py::_BACKENDS`; storage records `backend` per suggestion so evaluation can compare backends.
* **Confidence is a heuristic, labelled as such.** Prior from entry status, small bonus for satisfied context, penalty for
  ambiguity, and blended with observed reviewer acceptance once ≥5 decisions exist. Not a probability.
* **Permissions are enforced at export** (`services/export.py`) and STT (denied clips are never sent to a provider).
* **Language detection ≠ dialect identification.** The STT's detected language is stored as `detected_language_code`;
  `dialect_label` is a human assertion.
* **Script handling is explicit.** Cross-script pairs are excluded from scoring; no transliteration.

## Extending
* New STT provider: subclass `stt.base.STTProvider`, register in `stt/factory.py`.
* New correction backend: subclass `CorrectionBackend`; register in `_BACKENDS`; call via `propose_corrections(..., backend_name)`.
* New migration: add `src/storage/migrations/0002_*.sql`.
