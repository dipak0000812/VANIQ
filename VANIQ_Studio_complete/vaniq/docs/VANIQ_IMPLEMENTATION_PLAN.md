# VANIQ implementation plan

## 1. Decisions
**Frontend stack: stay build-free (ES modules, vanilla JS, CSS variables, SVG/Canvas).** I inspected the existing frontend
(~700 lines vanilla JS served by FastAPI) and the requirements. The target experience (shell, waveform canvas, workflow canvas, agent
thread) needs components, not a framework: Web Audio gives waveform peaks, SVG gives the workflow canvas, CSS gives panels and
motion. A React/Vite migration would add a Node build to a project whose requirement is "straightforward to run locally"
(`pip install` + `python -m src.cli serve`), and I verified a headless browser is available to test either choice. Revisit if
component count outgrows modules. **Backend stays FastAPI/SQLite; no framework change.**

**Agent planner: command mode only.** No LLM credentials exist in this environment and none can be evaluated, so `llm` mode is an
interface, not a feature.

## 2. Backend work (additive, backward compatible)
| Item | Detail | Tests |
|---|---|---|
| Migration `0003` | `agent_runs`, `workflows`, `workflow_runs`, `knowledge_items`, `knowledge_versions` | migration test on populated DB |
| `src/agent/tools.py` | registry of typed tools (pydantic args), impact flag, executor against existing services | each tool, validation errors |
| `src/agent/planner.py` | command-mode intent grammar with context defaults, honest unsupported response | grammar, context, unsupported |
| `src/agent/runner.py` | lifecycle, approval gate, background execution, audit | approval enforcement, failure paths |
| `src/workflows/engine.py` | node registry, port types, graph validation, topological executor | typed edges, cycles, data flow, gate |
| `src/services/knowledge.py` | CRUD, versions, approval | approval requires name, agent read-only |
| Optional params | `clip_ids` on `build_samples` and `select_clips` (default `None` = unchanged) | existing tests unchanged |
| New endpoints | `/api/agent/*`, `/api/workflows*`, `/api/workflow-runs/*`, `/api/knowledge*`, `/api/datasets/eligibility`, `/api/sources/{id}/audio` | API tests incl. permission and security |

Safeguards tested: agent cannot write references, decisions or lexicon; consequential steps need approval; export obeys
permission rules; run results contain no credentials; baseline role and claims block preserved.

## 3. Frontend work
`src/api/static/`: `landing.html` (+`landing.css/js`), `app.html`, `css/{tokens,shell,studio,agent,workflow}.css`,
`js/{api,ui,router,shell,home,studio,waveform,skills,knowledge,workflows,datasets,evaluation,lexicon,about,palette}.js`.
Design tokens in one file; icons as inline SVG set (original). The old single-page app is replaced; its features are carried over
view by view. Motion via CSS transitions/WAAPI; `prefers-reduced-motion` disables it; landing scroll reveal via IntersectionObserver
(no scroll hijacking).

## 4. Phases and exit criteria
| Phase | Deliverable | Exit criterion |
|---|---|---|
| 1–2 | Research + 5 docs | Docs exist (this folder) |
| 3 | This plan | Done |
| 4 | Shell + tokens + router | All nav items load in a real browser |
| 5 | Backend agent/skills/knowledge + Home/Skills/Knowledge UI | Agent tests pass; browser E2E plan→approve→result |
| 6 | Studio with waveform, tracks, inspector | Upload→select→correct→verify E2E in browser |
| 7 | Workflows, datasets, evaluation | Workflow runs end to end; eligibility matches export |
| 8 | Landing | Renders at 3 viewports; no console errors |
| 9 | QA | Backend suite + browser suite + screenshots all pass |
| 10 | Demo script + package | Final zip |

## 5. Validation plan
Backend `pytest`; headless Chromium (Puppeteer) scripts: navigation of every item, upload and playback, correction, verification,
agent approval, workflow execution, permission-denied cases, error states, refresh persistence, three viewports with screenshots.

## 6. Known risks
1. **Reference fidelity is structural, not pixel-level** (references not renderable here). Mitigation: calibrate tokens from user-supplied screenshots.
2. Audio decoding for waveform relies on the browser's Web Audio; headless Chromium support will be verified.
3. Scope is large; anything not verified in the browser will be reported as unverified.
