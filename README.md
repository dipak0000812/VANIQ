 <p align="center">
  <img src="src/api/static/assets/vaniq-logo.svg" alt="VANIQ" width="180" />
</p>

<h1 align="center">VANIQ</h1>

<p align="center">
  <strong>Voice Intelligence for Every Language.</strong>
</p>

<p align="center">
  <em>Building the data foundation for underrepresented languages and dialects.</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/FastAPI-0.115%2B-009688?style=flat-square&logo=fastapi&logoColor=white" alt="FastAPI" />
  <img src="https://img.shields.io/badge/SQLite-Database-003B57?style=flat-square&logo=sqlite&logoColor=white" alt="SQLite" />
  <img src="https://img.shields.io/badge/JavaScript-Vanilla-F7DF1E?style=flat-square&logo=javascript&logoColor=black" alt="JavaScript" />
  <img src="https://img.shields.io/badge/FFmpeg-Audio%20Processing-007808?style=flat-square&logo=ffmpeg&logoColor=white" alt="FFmpeg" />
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Project-VANIQ-6D5AE6?style=flat-square" alt="VANIQ" />
  <img src="https://img.shields.io/badge/Focus-Ahirani%20%2F%20Khandeshi-9333EA?style=flat-square" alt="Ahirani" />
  <img src="https://img.shields.io/badge/License-MIT-22C55E?style=flat-square" alt="MIT License" />
</p>

<p align="center">
  <a href="#problem">Problem</a> •
  <a href="#solution">Solution</a> •
  <a href="#features">Features</a> •
  <a href="#architecture">Architecture</a> •
  <a href="#tech-stack">Tech Stack</a> •
  <a href="#setup">Setup</a> •
  <a href="#team">Team</a>
</p>

---

## Overview

VANIQ is an AI-powered speech-data collection, transcription, linguistic verification, evaluation and dataset-curation platform designed for underrepresented languages and regional dialects.

Its initial focus is **Ahirani (Khandeshi dialect)**.

While speech recognition technology has advanced significantly for widely represented languages, many regional languages and dialects remain underserved by existing speech technology. Building better language technology requires more than a transcription API. It requires reliable audio, linguistic verification, structured datasets and transparent evaluation.

VANIQ brings these processes together in one workspace.

**The VANIQ Pipeline**

```text
Voice Recording
      │
      ▼
Audio Ingestion & Validation
      │
      ▼
Normalization & Segmentation
      │
      ▼
Speech-to-Text Baseline
      │
      ▼
Dialect-Aware Correction
      │
      ▼
Human Linguistic Verification
      │
      ▼
WER / CER Evaluation
      │
      ▼
Permission-Aware Dataset Export
```

> **Important linguistic distinction:** Gnani Prisma documents Marathi support. Native Ahirani speech-recognition support has not been independently established. VANIQ treats provider output as a baseline experiment, not verified Ahirani transcription performance.

---

## Problem

### The Underrepresentation of Regional Languages

Speech recognition systems depend heavily on the quality, quantity and diversity of their training data.

Widely represented languages benefit from extensive datasets, research investment and commercial support. Many regional languages and dialects do not have the same resources.

Ahirani, also known as Khandeshi, is one such regional language community where building reliable speech technology requires dedicated data collection and linguistic validation.

### What Makes This Difficult?

#### 1. Limited Speech Data

- Regional-language recordings are scattered across individuals and communities.
- Audio frequently lacks consistent metadata and speaker information.
- Recordings may have different sample rates, formats and quality levels.
- Collecting usable speech data requires structured workflows.

#### 2. Transcription Challenges

- General-purpose speech recognition systems may not understand regional dialects.
- Language detection does not establish dialect identification.
- Different writing conventions can complicate transcript comparison.
- Automatically generated transcripts require human verification.

#### 3. Lack of Linguistic Verification

- Provider output is not equivalent to ground truth.
- Regional vocabulary and context require fluent human reviewers.
- Corrections need traceability and provenance.
- Unverified text should not silently become training data.

#### 4. Dataset Quality and Permission

- Poor-quality audio can reduce dataset usefulness.
- Missing consent and provenance create data-governance risks.
- Public dataset exports must respect recording permissions.
- Evaluation results need transparent methodology and limitations.

### The Gap

A reliable speech-data workflow must connect audio collection, processing, transcription, human review, evaluation and dataset preparation.

VANIQ is designed to provide that workflow.

---

## Solution

### Our Approach: A Complete Speech-Data Intelligence Workspace

VANIQ combines audio processing, transcription experiments, linguistic correction, human verification and dataset evaluation in a unified platform.

Instead of treating speech recognition as the final output, VANIQ focuses on the complete process required to build useful speech datasets.

### The VANIQ Difference

| Traditional workflow | VANIQ approach |
|---|---|
| Scattered audio files | Structured audio ingestion |
| Inconsistent audio formats | Normalization and segmentation |
| Raw provider transcripts | Explicit STT baseline records |
| Manual transcript corrections | Reviewable correction suggestions |
| Untracked references | Attributed human verification |
| Basic accuracy comparisons | WER/CER with script-aware exclusions |
| Unstructured data collection | Permission-aware dataset exports |

### How It Works

**Step 1: Collect and Process Audio**

- Upload recordings or record through the browser.
- Validate audio format, size and decodability.
- Normalize recordings to 16 kHz mono PCM.
- Segment audio into manageable clips.
- Calculate audio-quality indicators.

**Step 2: Transcribe and Correct**

- Run speech-to-text experiments through the Gnani provider integration.
- Import transcripts from external tools.
- Preserve original provider output.
- Generate correction suggestions using a rule-based lexicon and context engine.
- Review and decide on individual suggestions.

**Step 3: Verify and Evaluate**

- Listen to each recording before entering an independent human reference.
- Track reviewer attribution and verification history.
- Compare raw and corrected transcripts.
- Calculate Word Error Rate (WER) and Character Error Rate (CER).
- Exclude incompatible script pairs rather than silently comparing them.

**Step 4: Build and Export Datasets**

- Organize recordings and clips into datasets.
- Track provenance and permission status.
- Apply export eligibility rules.
- Generate structured dataset archives with manifests and metadata.

---

## Features

### 1. Audio Studio

A dedicated workspace for speech-data processing and linguistic review.

- Audio playback and waveform visualization.
- Recording and clip management.
- Transcript inspection and editing.
- Recording metadata and speaker information.
- Declared dialect and provider-detected language shown separately.
- Processing status and review history.
- Contextual recording inspector.

### 2. AI Assistant

A command-driven assistant designed around VANIQ's speech-data workflows.

- Context-aware application commands.
- Action planning and execution previews.
- Approval and rejection controls.
- Recording and transcript operations.
- Workflow-oriented assistance.
- Activity history.

The current assistant uses structured command execution; it is not represented as an autonomous LLM-based agent.

### 3. Audio Ingestion and Processing

- Audio upload and browser recording.
- Format and file validation.
- FFmpeg-based normalization.
- 16 kHz mono PCM output.
- Energy-based audio activity segmentation using Auditok.
- RMS, peak, clipping and silence-ratio quality indicators.

Energy-based segmentation identifies audible regions; it is not a speech-specific voice activity detector.

### 4. Speech-to-Text Integration

- Gnani Prisma provider integration.
- Configurable language-code experiments.
- Typed provider errors and retry handling.
- Transcript import from external tools.
- Provider response metadata.
- Separate baseline and human-import experiment roles.

Provider-generated transcripts are never automatically treated as ground truth.

### 5. Dialect-Aware Correction

A pluggable correction architecture with an initial rule-based implementation.

- Lexicon-based correction suggestions.
- Neighbouring-word context rules.
- Candidate and verified lexicon entries.
- Human acceptance, rejection and modification.
- Correction history.
- Original transcript preservation.

The correction engine is rule-based, not a trained Ahirani language model. Its lexicon starts empty and requires human-verified entries.

### 6. Human Linguistic Review

- Independent reference transcript entry.
- Reviewer attribution.
- Correction acceptance and rejection.
- Manual transcript corrections.
- Verification and rejection states.
- Audit logging.
- Transcript history.

### 7. Evaluation Engine

Evaluate speech-recognition and correction experiments using:

| Metric | Purpose |
|---|---|
| WER | Word-level edit error rate |
| CER | Character-level edit error rate |
| Before / After | Compare raw and corrected hypotheses |
| Substitutions | Count replaced words or characters |
| Insertions | Count additional words or characters |
| Deletions | Count missing words or characters |

Additional evaluation capabilities:

- Unicode normalization.
- Indic-script detection.
- Script-mismatch exclusion.
- Per-sample and corpus-level metrics.
- Experiment-role grouping.
- Bootstrap uncertainty intervals when the sample count is sufficient.
- Explicit evaluation limitations and claim controls.

### 8. Dataset Management

- Recording and clip organization.
- Dataset eligibility checks.
- Permission-aware exports.
- Public and internal export visibility.
- Structured JSONL and CSV metadata.
- Dataset manifests and dataset cards.
- Speaker anonymization for public exports.

### 9. Knowledge Base

- Language-resource management.
- Linguistic reference materials.
- Versioned knowledge entries.
- Contextual knowledge access within the application.

### 10. Workflow Management

- Workflow templates.
- Visual workflow representation.
- Node and connection management.
- Execution previews.
- Approval-oriented execution.
- Invalid workflow-edge validation.

### 11. Activity and Audit Trail

- Recording ingestion history.
- Transcription activity.
- Correction decisions.
- Human verification events.
- Evaluation history.
- Dataset export activity.

---

## Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| Backend | Python | Core application logic |
| API Framework | FastAPI | REST API and application server |
| Frontend | HTML, CSS, JavaScript | Interactive web application |
| Database | SQLite | Local structured storage |
| Audio Processing | FFmpeg | Audio conversion and normalization |
| Segmentation | Auditok | Energy-based activity segmentation |
| Speech Recognition | Gnani Prisma | STT baseline provider |
| Data Validation | Pydantic | Structured data validation |
| Numerical Processing | NumPy, SciPy | Audio and evaluation operations |
| HTTP Client | HTTPX | External API communication |
| Testing | Pytest | Backend and integration tests |

---

## Architecture

VANIQ uses a modular monolithic architecture. FastAPI serves the frontend and API from one Python application. SQLite stores structured metadata, while audio files and generated exports are stored on disk.

```text
┌──────────────────────────────────────────────────────────────┐
│                       PRESENTATION LAYER                     │
│                                                              │
│  ┌─────────────┐ ┌─────────────┐ ┌────────────────────────┐  │
│  │  VANIQ UI   │ │ Audio Studio│ │ AI Assistant / Workflow│  │
│  │ HTML / CSS  │ │ Waveform    │ │ Review / Dataset UI    │  │
│  │ JavaScript  │ │ Transcript  │ │ Evaluation             │  │
│  └─────────────┘ └─────────────┘ └────────────────────────┘  │
└───────────────────────────┬──────────────────────────────────┘
                            │ HTTP / JSON
                            ▼
┌──────────────────────────────────────────────────────────────┐
│                         API LAYER                             │
│                                                              │
│                       FastAPI Application                    │
│                                                              │
│  Upload │ Clips │ Transcription │ Review │ Evaluation        │
│  Agent  │ Workflows │ Knowledge │ Datasets │ Audit            │
└───────────────────────────┬──────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────┐
│                       SERVICE LAYER                           │
│                                                              │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────────────┐  │
│  │ Ingestion    │ │ Transcription│ │ Correction           │  │
│  │ Service      │ │ Service      │ │ Engine               │  │
│  └──────────────┘ └──────────────┘ └──────────────────────┘  │
│                                                              │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────────────┐  │
│  │ Review       │ │ Evaluation   │ │ Dataset Export       │  │
│  │ Service      │ │ Service      │ │ Service              │  │
│  └──────────────┘ └──────────────┘ └──────────────────────┘  │
└───────────────────────────┬──────────────────────────────────┘
                            │
             ┌──────────────┼────────────────┐
             ▼              ▼                ▼
┌──────────────────┐ ┌──────────────┐ ┌──────────────────────┐
│ Audio Processing│ │ STT Provider │ │ Workflow / Agent     │
│                  │ │              │ │ Execution            │
│ FFmpeg           │ │ Gnani Prisma │ │ Tools and Approvals  │
│ Auditok          │ │ Demo Provider│ │ Knowledge Services   │
└──────────────────┘ └──────────────┘ └──────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────┐
│                         STORAGE LAYER                         │
│                                                              │
│  ┌──────────────────────┐  ┌───────────────────────────────┐ │
│  │ SQLite               │  │ Local File Storage            │ │
│  │ Sources and Clips    │  │ Original Audio                 │ │
│  │ Transcripts          │  │ Normalized Audio               │ │
│  │ Suggestions          │  │ Segmented Clips                │ │
│  │ Evaluations          │  │ Dataset Exports                │ │
│  │ Audit Logs           │  │                                │ │
│  └──────────────────────┘  └───────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

### Architectural Principles

1. **Modular services:** ingestion, transcription, review, correction, evaluation and export are separated into service modules.
2. **Immutable raw transcripts:** corrections are derived from original text and accepted suggestions; original provider output is preserved.
3. **Demo/live isolation:** synthetic demo data and live recordings use separate data directories and provider configurations.
4. **Permission enforcement:** recording permissions are checked before provider submission and dataset export.
5. **Explicit experiment roles:** baseline provider output is not confused with human-imported references or candidate model results.
6. **Traceability:** human decisions and important operations are recorded in the audit log.

---

## Project Structure

```text
VANIQ/
│
├── src/
│   ├── api/
│   │   ├── app.py                 # FastAPI application and API routes
│   │   └── static/
│   │       ├── index.html         # Landing page
│   │       ├── app.html           # Application workspace
│   │       ├── css/               # Application styles
│   │       └── js/                # Frontend modules
│   │
│   ├── agent/
│   │   ├── planner.py             # Command planning
│   │   ├── runner.py              # Agent execution
│   │   └── tools.py               # Available application tools
│   │
│   ├── correction/
│   │   ├── engine.py              # Correction backend
│   │   ├── models.py              # Correction models
│   │   └── apply.py               # Apply accepted corrections
│   │
│   ├── dataset_factory/
│   │   ├── audio.py               # Audio loading and normalization
│   │   ├── ingestion.py           # Dataset ingestion
│   │   ├── segmentation.py        # Audio activity segmentation
│   │   ├── quality.py             # Audio quality metrics
│   │   └── metadata.py            # Dataset metadata
│   │
│   ├── evaluation/
│   │   ├── metrics.py             # WER / CER
│   │   └── report.py              # Evaluation reporting
│   │
│   ├── gnani/
│   │   ├── client.py              # Gnani API client
│   │   └── models.py              # Provider data models
│   │
│   ├── services/
│   │   ├── ingest.py              # Audio ingestion
│   │   ├── transcribe.py          # Transcription
│   │   ├── review.py              # Human review
│   │   ├── evaluation_service.py  # Evaluation execution
│   │   ├── export.py              # Dataset export
│   │   ├── knowledge.py           # Knowledge management
│   │   ├── validation.py          # Validation
│   │   └── demo.py                # Synthetic demo data
│   │
│   ├── storage/
│   │   ├── db.py                  # SQLite connection and migrations
│   │   ├── repo.py                # Repository operations
│   │   └── migrations/            # Database schema migrations
│   │
│   ├── stt/                       # STT provider abstraction
│   ├── workflows/                 # Workflow execution engine
│   ├── cli.py                     # Command-line interface
│   ├── config.py                  # Application configuration
│   └── context.py                 # Application context
│
├── tests/
│   ├── browser/                   # Browser E2E tests
│   └── test_*.py                  # Backend and service tests
│
├── scripts/                       # Development and smoke-test scripts
├── docs/
│   ├── API.md
│   ├── ARCHITECTURE.md
│   ├── DATASET.md
│   ├── EVALUATION.md
│   ├── LIMITATIONS.md
│   └── P0_LINGUISTIC_INTEGRITY.md
│
├── data/                          # Runtime data (not committed)
├── .env.example                   # Configuration template
├── requirements.txt
├── requirements-lock.txt
├── pytest.ini
├── LICENSE
└── README.md
```

---

## Setup

### Prerequisites

| Requirement | Version / Dependency |
|---|---|
| Python | 3.10+ |
| FFmpeg | Required |
| FFprobe | Required |
| pip | Python package manager |
| Gnani API credentials | Only for live transcription |

### Installation

**1. Clone the repository**

```bash
git clone https://github.com/dipak0000812/VANIQ.git
cd VANIQ
```

**2. Create a virtual environment**

Linux / macOS:

```bash
python -m venv .venv
source .venv/bin/activate
```

Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

**3. Install dependencies**

```bash
pip install -r requirements.txt
```

For reproducible dependency versions:

```bash
pip install -r requirements-lock.txt
```

### Run VANIQ in Demo Mode

No API credentials are required for the synthetic demo experience.

Linux / macOS:

```bash
export VANIQ_MODE=demo
python -m src.cli serve
```

Windows PowerShell:

```powershell
$env:VANIQ_MODE="demo"
python -m src.cli serve
```

Open:

```text
http://127.0.0.1:8000
```

Open the application workspace at:

```text
http://127.0.0.1:8000/app
```

Select **Load demo data** from the Home screen.

> Demo mode uses synthetic data and labelled placeholder transcription output. Placeholder transcripts are not transcriptions of the associated audio.

### Configure Live Mode

Create a local `.env` file using `.env.example`:

```env
VANIQ_MODE=live
GNANI_API_KEY=your-gnani-api-key
GNANI_MODEL=prisma-v3.0
```

Then start the application:

```bash
python -m src.cli serve
```

Live mode supports audio ingestion, processing, transcript import, review, evaluation and export. Actual provider transcription requires valid Gnani credentials.

**Never commit `.env` or API credentials.**

---

## CLI Commands

VANIQ provides a command-line interface for common operations.

```bash
# Start the application
python -m src.cli serve

# Seed synthetic demo data
python -m src.cli seed-demo

# Ingest an audio recording
python -m src.cli ingest recording.wav \
    --speaker-id S1 \
    --dialect Ahirani \
    --permission-status granted \
    --permitted-usage private_research

# Transcribe a clip
python -m src.cli transcribe <clip_id> --language-code mr-IN

# Evaluate transcripts
python -m src.cli evaluate

# Export a public dataset
python -m src.cli export --visibility public

# Import a correction lexicon
python -m src.cli import-lexicon my_lexicon.json

# Run tests
python -m pytest -q
```

---

## API Reference

VANIQ exposes a REST API through FastAPI.

Interactive API documentation is available at:

```text
http://127.0.0.1:8000/docs
```

### Core Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/health` | Application health and configuration |
| GET | `/api/about` | Capabilities and limitations |
| GET | `/api/dashboard` | Dashboard statistics and activity |
| POST | `/api/sources` | Upload and process audio |
| GET | `/api/sources` | List recordings |
| PATCH | `/api/sources/{id}` | Update recording metadata |
| GET | `/api/clips` | List audio clips |
| GET | `/api/clips/{id}` | Retrieve clip details |
| POST | `/api/clips/{id}/transcribe` | Run STT |
| POST | `/api/clips/{id}/transcripts/import` | Import a transcript |
| POST | `/api/clips/{id}/verify` | Submit human reference |
| POST | `/api/transcripts/{id}/propose` | Generate correction suggestions |
| POST | `/api/suggestions/{id}/decision` | Review correction suggestions |
| POST | `/api/evaluate` | Run evaluation |
| GET | `/api/evaluations` | Retrieve evaluation history |
| POST | `/api/exports` | Create a dataset export |
| GET | `/api/audit` | Retrieve audit history |

For request and response details, see [docs/API.md](docs/API.md).

---

## Evaluation Methodology

VANIQ evaluates transcripts using human-verified references.

### Word Error Rate

\[
WER = \frac{S + D + I}{N}
\]

Where:

- S = Substitutions
- D = Deletions
- I = Insertions
- N = Number of words in the reference

### Character Error Rate

\[
CER = \frac{S_c + D_c + I_c}{N_c}
\]

Where the edit operations and reference length are measured at character level.

### Evaluation Integrity

VANIQ applies:

- Unicode NFC normalization.
- Indic-script detection.
- Consistent text normalization.
- Explicit script-mismatch handling.
- Paired before-and-after comparisons.
- Per-sample error statistics.
- Corpus-level WER and CER.
- Bootstrap uncertainty intervals when sufficient samples exist.

**Ground truth is the independently human-verified reference.** Provider-generated output is a hypothesis, never ground truth.

Cross-script pairs, such as Devanagari and Gujarati, are excluded from scoring rather than compared without transliteration.

See [docs/EVALUATION.md](docs/EVALUATION.md) for the complete methodology.

---

## Linguistic Integrity and Data Governance

VANIQ is designed to preserve the distinction between language experimentation and verified linguistic evidence.

### Important Principles

1. **Declared dialect is not detected language.** Ahirani is recorded as a human-provided dialect label. Provider language detection is stored separately.
2. **STT output is not ground truth.** Human references are independently entered and verified.
3. **Raw transcripts remain preserved.** Corrections do not silently overwrite original provider output.
4. **Unknown permission is not consent.** Records with unknown or denied permission are not eligible for public export.
5. **Demo data is not real experimental evidence.** Synthetic transcripts and metrics are explicitly labelled.
6. **No unsupported accuracy claims.** A small pilot cannot establish general Ahirani recognition performance.

### Current Limitations

- Native Ahirani STT support has not been established.
- No independently verified Ahirani recognition accuracy is claimed.
- The correction engine is rule-based, not a trained language model.
- The initial correction lexicon does not ship with verified Ahirani vocabulary.
- Dialect identification is not implemented.
- Energy-based segmentation requires calibration and can identify non-speech sounds.
- Reviewer identities are self-declared; authentication is not implemented.
- SQLite and local storage are intended for a single-user local deployment, not concurrent multi-user production.
- The application should not be exposed to untrusted networks.

See [docs/LIMITATIONS.md](docs/LIMITATIONS.md) for additional details.

---

## Testing

Run the backend test suite:

```bash
python -m pytest -q
```

Browser E2E tests are located in:

```text
tests/browser/
```

The project includes tests for:

- Audio ingestion and validation.
- STT client behaviour.
- Transcript correction.
- Linguistic integrity.
- WER/CER evaluation.
- Human review and verification.
- Dataset export permissions.
- Workflow and assistant services.
- Browser interactions.

Testing uses synthetic fixtures and does not require live API credentials.

---

## Documentation

| Document | Description |
|---|---|
| [Architecture](docs/ARCHITECTURE.md) | Application architecture and design decisions |
| [API Reference](docs/API.md) | REST API endpoints |
| [Dataset Preparation](docs/DATASET.md) | Audio ingestion and dataset preparation |
| [Evaluation Methodology](docs/EVALUATION.md) | WER, CER and evaluation methodology |
| [Limitations](docs/LIMITATIONS.md) | Current limitations and unsupported claims |
| [Engineering Handover](HANDOVER.md) | Development and implementation notes |

---

## Team

| Member | Role |
|---|---|
| **Dipak Dhangar** | Project Developer |

---

## License

This project is licensed under the **MIT License**. See [LICENSE](LICENSE) for details.

---

<p align="center">
  <strong>VANIQ — Voice Intelligence for Every Language.</strong>
</p>

<p align="center">
  Building the foundation for more inclusive speech technology, one voice at a time.
</p>
