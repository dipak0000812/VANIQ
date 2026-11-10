# VANIQ page and interaction map

Format per row: **Interaction** | Reference | Observed pattern → VANIQ reproduction | Operates | API | Acceptance.

## Shell (all app views)
| Interaction | Ref | Pattern → reproduction | Operates | API | Acceptance |
|---|---|---|---|---|---|
| Top toolbar | RS | App-shell bar → project name, current recording, view tabs, save state, Export, Agent toggle | selection, export | `/api/datasets/eligibility` | Export disabled with reason when 0 eligible; save indicator reflects last successful write |
| Left navigation (collapsible) | RS | Tool rail → Home, Studio, Skills, Knowledge, Workflows, Lexicon, Datasets, Evaluation, About | routing | – | Every item loads its view; active item highlighted; collapses to icons |
| ⌘K command bar | RS+L | Quick start → palette: go to view, run skill, ask agent | agent | `/api/agent/plan` | ⌘K/Ctrl+K opens; Esc closes; focus trapped |
| Agent drawer | L | Assistant beside work → right drawer on Studio with current-context chip | agent | `/api/agent/*` | Context chip shows selected recording; closing keeps thread |
| Reviewer identity | – | Name field in the toolbar menu | audit | – | Required before approvals and verification |
| Reduced motion | both | Transitions disabled under `prefers-reduced-motion` | – | – | No animation when set |

## Home (Lindy)
| Interaction | Pattern → reproduction | Operates | API | Acceptance |
|---|---|---|---|---|
| Prompt box "Hand me your first job" | single prompt entry → composer with example chips | agent planner | `POST /api/agent/plan` | Submit creates a run; unsupported text yields an honest message |
| Command-mode banner | honest limits → banner when no LLM | – | `GET /api/agent/status` | Visible whenever mode = command |
| Plan card | "I prep the work" → ordered steps with tool, args, impact badge | run | `GET /api/agent/runs/{id}` | Steps match stored plan |
| Approval card | "You approve it" → Approve / Reject with named reviewer | run | `approve` / `reject` | Consequential steps run only after approve (tested) |
| Step progress | execution feedback → per-step state pending/running/done/failed, polling | run | poll run | State transitions mirror backend |
| Result cards | cards in thread → summary tables/links per tool | run result | – | Numbers come from tool output |
| Error recovery | failed step shows real message and "Retry step" via new plan | run | plan | No success shown on failure |
| Activity feed | "handled overnight" → recent runs and audit entries | audit, runs | `GET /api/agent/runs`, `/api/audit` | Matches DB |
| Empty state | no runs → suggested first jobs | – | – | Shown with zero runs |

## Studio (RetailSync)
| Interaction | Pattern → reproduction | Operates | API | Acceptance |
|---|---|---|---|---|
| Recordings list (left panel) | tool/asset panel → recordings with clip counts, status chips, filter | sources/clips | `/api/sources`, `/api/clips` | Selecting loads canvas |
| Upload & record | Upload & Choose → dialog with provenance + permission, microphone recording | ingest | `POST /api/sources` | Validation errors shown inline; duplicate notice |
| Waveform canvas | canvas → peaks drawn from the recording, segment regions, playhead, zoom | audio | `GET /api/sources/{id}/audio` | Click seeks; region click selects clip; zoom works |
| Transport | audio controls → play/pause, loop segment, time | audio | clip audio | Playback of selected segment |
| Tracks (layers) | layers → Raw STT (read-only), Corrected, Human reference (empty default, STT opt-in) | transcripts, review | existing review APIs | Reference starts empty; copy requires explicit action |
| Inline correction marks | selection editing → marked spans with accept / reject / modify popover | suggestions | `/api/suggestions/{id}/decision` | Raw text never changes |
| Manual correction by selection | selection tool → select in raw track, type replacement | corrections | `/api/transcripts/{id}/corrections` | Span mismatch rejected |
| Contextual AI commands | AI Design Agent → "Run baseline", "Check mismatch", "Eligibility" chips for selection | agent | `/api/agent/plan` | Chip creates plan with clip context |
| Inspector | properties panel → speaker, declared dialect, provider-detected language, script, orthography (shown as "not yet recorded"), provider/model, metadata, consent, verification | clip/source | `GET /api/clips/{id}`, `PATCH /api/sources/{id}` | Edits persist across refresh |
| Verification | – | reference | `POST /api/clips/{id}/verify` | Needs reviewer name; records `stt_viewed` |
| Provider response | – | transcript | workspace payload | Sanitised JSON visible |

## Skills, Knowledge, Workflows (Lindy)
| Interaction | Pattern → reproduction | Operates | API | Acceptance |
|---|---|---|---|---|
| Skill library | built-in skill cards → executable tools, impact badge, argument form | tools | `GET /api/agent/tools` | Run produces a run record |
| Skill "picked automatically" | agent chooses skill | planner | plan | Plan names the tool used |
| Knowledge files | plain versioned files → list, editor, version history, draft/approved, provenance | knowledge | `/api/knowledge*` | Approval needs reviewer; versions restorable |
| Workflow canvas | trigger→steps + node editor → draggable nodes, typed ports, edge drawing, config panel | workflows | `/api/workflows*` | Invalid edge refused with reason; save persists |
| Template gallery | templates with filters → "Use template" | workflows | `GET /api/workflows` | Creates editable copy |
| Run workflow | execution feedback → node states live; approval gate for consequential nodes | workflow run | `/api/workflows/{id}/run`, `/api/workflow-runs/{id}` | Data flows along edges; no run before approval |
| Run history | – | runs | list | Persists across refresh |

## Datasets / Evaluation / Lexicon / About
| Interaction | Operates | API | Acceptance |
|---|---|---|---|
| Eligibility table | per-clip public/internal eligibility with reasons | `GET /api/datasets/eligibility` | Reasons match export rules |
| Export dialog | export | `POST /api/exports` | Permission rules enforced server-side |
| Evaluation | per-role groups, claims block, WER/CER where valid | `POST /api/evaluate` | No Ahirani claim; baseline labelled |
| Lexicon | existing CRUD | `/api/lexicon*` | Verified needs provenance |
| About | capability matrix, limits | `/api/about` | Matches reality |

## States
Every list and panel defines: **empty** (explanatory, with next action), **loading** (skeleton shimmer, reduced-motion safe),
**error** (real message + retry), **success** (toast after backend confirmation).

## Responsive
≥1200px: four regions. 900–1199px: inspector becomes overlay. <900px: bottom tab bar, left nav and inspector as sheets, agent full-screen sheet.
