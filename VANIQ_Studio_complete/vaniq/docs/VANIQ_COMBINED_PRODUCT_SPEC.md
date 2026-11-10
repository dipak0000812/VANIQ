# VANIQ combined product specification

**Voice intelligence for every language.** VANIQ is an AI-native voice-data workspace for collecting, transcribing, correcting,
reviewing, evaluating and managing speech data for underrepresented languages and dialects. Initial focus: Ahirani/Khandeshi.

## 1. Principle: one product, two reference experiences
* **Lindy-inspired layer (the agent):** a message-based assistant that plans, asks approval for consequential actions, executes
  real tools, reports results, keeps versioned plain-text knowledge, and runs chains of steps.
* **RetailSync-inspired layer (the studio):** a professional editor shell (toolbar, left navigation, central canvas, right
  inspector, ⌘K command entry) whose canvas is a recording.
* **Integration:** the agent is present everywhere (right-hand drawer in the studio, full thread on the Home view, ⌘K).
  Every agent request carries the current context (view, selected recording/clip, selected workflow). Manual and agent work edit
  the same records.

## 2. Truth rules (inherited, non-negotiable)
1. Declared dialect (human assertion), provider-detected language, transcript script, orthographic convention and human-verified
   reference are five separate things. Provider output is never relabelled as Ahirani.
2. Gnani is an STT integration and **baseline experiment** provider. No native Ahirani support or performance claim.
3. The agent can never write, overwrite or verify a human reference, accept or reject correction suggestions, or edit lexicon
   entries. It can read, propose (pending suggestions), run baseline STT after approval, evaluate and export after approval.
4. No operation is reported successful until the backend confirms it. Failures show the real error.
5. Permission rules apply to every path (UI, agent, workflow). Unknown/denied permission is never exported publicly.
6. No fabricated metrics, no invented Ahirani vocabulary or rules. Knowledge entries are human-written and human-approved.
7. Without an LLM, the agent runs in an honestly labelled **command mode** (fixed command grammar). Unsupported requests are refused with guidance.

## 3. Information architecture
| Area | Contents | Reference lineage |
|---|---|---|
| Landing (`/`) | Scroll story, three-step "how it works", real-capability inventory, truth statement, CTA to open the studio | Lindy narrative + RetailSync how-it-works |
| Home (`#/home`) | Agent thread, plan/approval cards, context chip, activity feed, quick actions | Lindy |
| Studio (`#/studio`) | Recordings list, waveform canvas with segments, tracks, inspector, toolbar | RetailSync |
| Skills (`#/skills`) | Executable capabilities with typed args and Run | Lindy |
| Knowledge (`#/knowledge`) | Versioned conventions and references, draft → approved | Lindy memory |
| Workflows (`#/workflows`) | Node canvas, templates gallery, run history | Lindy routines × RetailSync canvas |
| Lexicon, Datasets, Evaluation | Existing capabilities in the new shell | RetailSync shell |
| Projects | Single local project ("Ahirani pilot"); the switcher is read-only | RetailSync top bar |

## 4. Agent specification
* **Tools** (typed, validated): `list_work`, `validate_audio`, `detect_transcript_mismatch`, `reference_workflow_status`,
  `check_dataset_eligibility`, `propose_corrections`, `run_evaluation`, `transcribe_clip`*, `create_export`*. (*requires approval)
* **Lifecycle:** `plan` (stored, validated) → auto-run if all steps are read-only/low-impact, otherwise `awaiting_approval` →
  `approve` (named reviewer) → `running` → `completed` / `failed` (per-step results and errors). `reject` ends the run.
* **Modes:** `command` (implemented) and `llm` (interface only; not implemented, not claimed).
* **Audit:** plan, approval, each step and outcome are written to `audit_log`.

## 5. Workflow specification
Nodes are real operations: `select_clips`, `validate_audio`, `stt_baseline`*, `propose_corrections`, `human_review_gate`,
`check_eligibility`, `evaluate`, `export_dataset`*. Ports are typed (`clips`, `transcripts`, `report`, `file`); an edge is allowed
only when the producing node's output type is accepted by the consuming node's input type, and the executor passes exactly that
data along the edge. `human_review_gate` passes only clips a human has verified. It waits and never verifies anything itself.

## 6. Knowledge specification
Items: title, kind (`convention` | `reference` | `note`), body (plain text), status (`draft` | `approved`), provenance
(`written by <name>` / `imported from <source>`), version history. Approval requires a named human. The agent may list and cite approved items; it
cannot create approved items.

## 7. Non-goals
Integrations marketplace, credits, multi-user auth, real-time collaboration, trained correction model, dialect identification, LLM-backed planning (until credentials and evaluation exist).
