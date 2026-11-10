# VANIQ Local

**Voice intelligence for every language.**

VANIQ Local is a workflow for building and checking speech data for underrepresented regional languages.
Its first target is **Ahirani (Khandeshi dialect)**.

```
Voice → audio processing → STT baseline → dialect-aware correction → human verification → evaluation → export
```

> **Read this first.** Gnani Prisma documents Marathi support; native Ahirani support has *not* been established.
> VANIQ never claims otherwise, never invents Ahirani vocabulary, and ships a rule-based correction engine with an
> **empty** lexicon that you populate and verify. It is not a trained model. See [docs/LIMITATIONS.md](docs/LIMITATIONS.md).

## Linguistic integrity (P0)
Provider output under `mr-IN` or `indic-auto` is an **STT baseline experiment**, labelled as such everywhere, and is never
reported as Ahirani performance. Provider-detected language is stored beside, never instead of, the recording's declared
dialect. Reference transcripts start empty; STT text is opt-in. Details: [docs/P0_LINGUISTIC_INTEGRITY.md](docs/P0_LINGUISTIC_INTEGRITY.md).

## What it does

| Stage | What happens | Status |
|---|---|---|
| Upload / record | Validate type, size, decodability; browser microphone recording | implemented |
| Normalize + segment | FFmpeg → 16 kHz mono PCM; Auditok energy segmentation; quality metrics | implemented |
| STT baseline | Gnani Prisma via `GNANI_API_KEY`; or import transcripts from elsewhere | implemented (needs key) |
| Correction | Lexicon + context rules propose changes; raw transcript is never edited | implemented (rule-based) |
| Review | Accept / reject / modify each suggestion; manual corrections; audit log | implemented |
| Verification | Human reference transcript per clip, attributed to a named reviewer | implemented |
| Evaluation | WER/CER before vs after corrections; script-mismatch exclusion | implemented |
| Export | Zip with audio, JSONL/CSV, manifest, dataset card; permission-gated | implemented |
| Demo mode | Synthetic data and labelled placeholder STT, no credentials | implemented |
| Trained dialect model, dialect ID, auth | – | **not implemented** |

## Quick start (demo, no credentials)

Requirements: Python 3.10+ and FFmpeg (`ffmpeg` and `ffprobe` on PATH).

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt                         # or requirements-lock.txt for exact tested versions
VANIQ_MODE=demo python -m src.cli serve                 # Windows PowerShell: $env:VANIQ_MODE="demo"; python -m src.cli serve
```

Open http://127.0.0.1:8000, click **Load demo data** on the dashboard. Demo mode keeps its data in `data/demo/`,
shows a banner on every page, and labels every demo transcript "not a transcription of this audio".

## Real use

```bash
cp .env.example .env        # then edit: set GNANI_API_KEY; leave VANIQ_MODE=live
python -m src.cli serve
```

1. **Upload & record**: set speaker, dialect label (your assertion), permission and permitted usage. Leave `UNKNOWN`
   if you do not know; unknown is never treated as consent.
2. **Workspace**: open a clip, press *Transcribe* (try `mr-IN` and `indic-auto`, as in the pilot) or import a transcript.
3. **Dialect lexicon**: add entries you or a fluent reviewer have confirmed. Without entries, only Unicode/whitespace
   hygiene is proposed.
4. **Review** suggestions, then **verify** each clip with a reference you wrote after listening.
5. **Evaluation**, then **Datasets → Create export**.

Without `GNANI_API_KEY`, live mode still supports upload, segmentation, transcript import, review and export. Transcribing
returns a clear "not configured" error; nothing is silently simulated.

## Commands

```bash
python -m src.cli serve                       # web app
VANIQ_MODE=demo python -m src.cli seed-demo   # seed synthetic data without the UI
python -m src.cli ingest recording.wav --speaker-id S1 --dialect Ahirani \
        --permission-status granted --permitted-usage private_research
python -m src.cli transcribe <clip_id> --language-code mr-IN
python -m src.cli import-lexicon my_lexicon.json
python -m src.cli evaluate
python -m src.cli export --visibility public
python -m pytest -q                           # tests (no network, no API key, no private audio needed)
```

Legacy pilot scripts remain: `python run_experiments.py --audio audio/clip_001_16k.wav`, `python evaluate.py`,
`python -m src.dataset_factory.cli ingest ...`.

Lexicon import format (JSON list):
```json
[{"source_form": "…", "target_form": "…", "kind": "lexical", "context_prev": "", "context_next": "",
  "status": "candidate", "provenance": "who/what supports this"}]
```
`status: "verified"` requires `provenance`.

## Configuration

See `.env.example`. Key variables: `VANIQ_MODE` (`live`|`demo`), `GNANI_API_KEY`, `GNANI_MODEL`, `VANIQ_DATA_DIR`,
`VANIQ_MAX_UPLOAD_MB`, `VANIQ_MAX_AUDIO_SECONDS`, `VANIQ_SEG_ENERGY_THRESHOLD`, `VANIQ_SEG_MAX_DUR_S`.
The server binds to `127.0.0.1`; it has **no authentication**, so do not expose it to a network.

## Layout

```
src/config.py, context.py       settings, app context
src/gnani/                      Gnani client (retries, typed errors)
src/stt/                        provider abstraction: gnani, demo-mock
src/dataset_factory/            normalize, segment, quality, legacy CSV ingestion (original modules, fixed)
src/correction/                 CorrectionBackend, RuleBasedBackend, apply/render
src/evaluation/                 metrics + before/after report
src/storage/                    SQLite schema, migrations, repository
src/services/                   ingest, transcribe, review, evaluation, export, demo
src/api/                        FastAPI app + static frontend (no build step)
tests/                          107 tests; synthetic fixtures only
docs/                           architecture, API, dataset, evaluation, limitations
```

## Documentation

[Architecture](docs/ARCHITECTURE.md) · [API](docs/API.md) · [Dataset preparation](docs/DATASET.md) ·
[Evaluation methodology](docs/EVALUATION.md) · [Limitations](docs/LIMITATIONS.md) · [Engineering handover](HANDOVER.md)

## License
MIT, see LICENSE.
