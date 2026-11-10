# API

Base URL `http://127.0.0.1:8000`. Interactive docs: `/docs` (OpenAPI). Errors have the shape
`{"error": {"code": "...", "message": "..."}}`. `reviewer` fields are self-declared names recorded in the audit log.

| Method & path | Purpose |
|---|---|
| GET `/api/health` | mode, STT configured, FFmpeg present |
| GET `/api/about` | capability matrix and limitations |
| GET `/api/dashboard` | counts, recent clips, recent audit |
| POST `/api/sources` (multipart: `file`, `speaker_id`, `dialect_label`, `permission_status`, `permitted_usage`, `source_url`, `consent_notes`, `reviewer`) | upload, validate, normalize, segment |
| GET `/api/sources` · PATCH `/api/sources/{id}` | list / update provenance and permission |
| GET `/api/clips?review_status=&source_id=` · GET `/api/clips/{id}` · GET `/api/clips/{id}/audio` | clips; workspace payload; WAV |
| POST `/api/clips/{id}/transcribe` `{language_code}` | STT (503 `stt_not_configured` if no key in live mode) |
| POST `/api/clips/{id}/transcripts/import` `{text,label,language_code}` | attach external transcript |
| POST `/api/transcripts/{id}/propose` | re-run correction proposals (keeps human decisions) |
| POST `/api/transcripts/{id}/corrections` `{start_char,end_char,replacement,expected_original}` | manual correction |
| POST `/api/suggestions/{id}/decision` `{decision: accepted|rejected|modified|pending, final_replacement}` | review |
| POST `/api/suggestions/{id}/promote` | add accepted correction to lexicon as *candidate* |
| POST `/api/clips/{id}/verify` `{reference, reviewer, stt_viewed?}` · `/unverify` · `/reject` | human verification |
| GET/POST `/api/lexicon` · PATCH/DELETE `/api/lexicon/{id}` | lexicon (verified needs provenance) |
| POST `/api/evaluate` `{language_code, dialect_label, include_synthetic}` · GET `/api/evaluations` | evaluation |
| POST `/api/exports` `{visibility: public|internal, include_unknown_internal, require_verified}` · GET `/api/exports` · GET `/api/exports/download/{file}` | export |
| POST `/api/demo/seed` | demo mode only |
| GET `/api/audit` | audit log |

Common error codes: `unsupported_type` 415, `too_large` 413, `bad_audio` 422, `stt_not_configured` 503, `stt_auth`/`stt_api` 502,
`stt_network` 504, `permission_denied` 403, `reviewer_required` 422, `overlap`/`span_mismatch` 409.

Linguistic-integrity fields (P0): transcripts carry `experiment_role` (`baseline` | `human_import`), `experiment_role_label`,
`detected_language_code` (provider detection only) and `provider_response` (sanitised JSON, `null` for imports).
`/api/about` adds `baseline_settings` and `native_support_statement`. `/api/evaluate` adds `by_role` and `claims`.
