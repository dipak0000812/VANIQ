# VANIQ Studio handover (Lindy x RetailSync frontend)

Run: `VANIQ_MODE=demo python -m src.cli serve` then open http://127.0.0.1:8000 (landing) and /app (studio). Click "Load demo data" on Home.
Docs: docs/LINDY_REFERENCE_ANALYSIS.md, RETAILSYNC_REFERENCE_ANALYSIS.md, VANIQ_COMBINED_PRODUCT_SPEC.md, VANIQ_PAGE_AND_INTERACTION_MAP.md, VANIQ_IMPLEMENTATION_PLAN.md. Screenshots: docs/screenshots.

## Verified
* Backend: full pytest suite (see final run in the chat message).
* Real headless Chromium (tests/browser/e2e.mjs): 47 of 51 checks passed on the last run. Passing: all 9 nav items, command bar, agent plan/approve/reject with real execution, upload + waveform + playback, segment selection, reference empty-by-default with STT opt-in, correction accept/undo, inspector edits persisting after refresh, skills, knowledge versioning, workflow gallery/template/invalid-edge refusal, datasets eligibility, evaluation claims, network-error state, 3 viewports without overflow, reduced motion, landing page, zero console errors.

## NOT verified / failing (4 browser checks)
1. permission-denied via drawer: test could not click the contextual button (test-harness timing; backend behaviour is covered by pytest).
2. workflow drag-to-move node: not confirmed in the E2E run (worked in an isolated manual run).
3-4. workflow "run with approval" and "evaluation template auto-run" in the browser: depend on (2); backend engine is covered by pytest.
Treat these four as unverified in the UI until re-run.

## Limits
* Reference sites could not be rendered (DNS blocked): fidelity is structural/interaction-level, not pixel-level. Send screenshots to calibrate colours/type/spacing.
* Agent runs in command mode (no LLM). No auth. Orthographic convention field not yet recorded (P1).
