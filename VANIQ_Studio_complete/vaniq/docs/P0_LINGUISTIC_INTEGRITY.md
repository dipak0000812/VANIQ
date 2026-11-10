# P0 linguistic integrity: what changed

Implements P0 of `AHIRANI_LINGUISTIC_REQUIREMENTS.md`. No P1/P2 redesign (no declared-dialect field, lexeme tables,
references table, error taxonomy) was started.

| Requirement | Change |
|---|---|
| Remove hardcoded `lang="mr"` | Removed from the transcript and corrected-text boxes. No `lang` is set until a declared-dialect field exists (P1). |
| Independent references | Reference box is empty by default. "Show STT transcript (optional)" reveals raw and corrected text with explicit copy buttons. `stt_viewed` is sent with verification and recorded in the audit log (no schema change). |
| Provider language + raw response in workspace | Each transcript shows provider-detected language, the declared dialect of the recording (separately), the experiment role, and a collapsible provider JSON panel. API: `provider_response` (sanitised), `experiment_role`, `experiment_role_label`. |
| Provider response in internal exports | `provider_response` is included in **internal** exports only, sanitised (credential/config-like keys and the configured API key value are redacted). Public exports omit it. Permission gating is untouched. |
| Baseline labelling | Language codes are labelled "STT baseline experiment setting"; only `indic-auto` and `mr-IN` are suggested; button reads "Run STT baseline". `/api/about` returns `baseline_settings`. |
| `experiment_role` | New `transcripts.experiment_role` (`baseline` / `candidate` / `human_import`). Provider output is always `baseline`; imports are `human_import`; `candidate` is reserved and never assigned. |
| Baseline ≠ Ahirani performance | Evaluation reports results per role (`by_role`) and a `claims` block; `ahirani_stt_performance_claim_allowed` stays false unless candidate-role results exist **and** `NATIVE_AHIRANI_STT_VERIFIED` is set after independent verification. The UI shows the claim notice and never an unlabeled combined table. Exports and the dataset card carry the statement. |

## Migration
`src/storage/migrations/0002_experiment_role.sql` (applied automatically at start-up, forward-only):
adds `transcripts.experiment_role TEXT NOT NULL DEFAULT 'baseline'` with a CHECK constraint, backfills
`provider='imported'` rows to `human_import`, and adds an index. Existing data and queries are unaffected.

## API compatibility
Additive. `POST /api/clips/{id}/verify` accepts an optional `stt_viewed`; old payloads still work. The `aggregate` key in
evaluation output is kept for compatibility and carries a `scope` string stating it is not an Ahirani figure; use `by_role`.

## Not done (by design)
Declared-dialect field and basis, orthography conventions, multiple references, lexeme model, variant-tolerant scoring,
error taxonomy, `lang` derived from declared dialect: P1/P2.
