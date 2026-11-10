# Lindy AI: reference analysis

Sources inspected (public, fetched as page content on 2026-11-09): `lindy.ai` (home), `/product/skills`, `/product/memory`,
`/product/routines`. Not inspected: the logged-in app (`chat.lindy.ai`, requires sign-up), `docs.lindy.ai`, pricing, changelog,
Watch and Learn, Meetings, Phone, Apps pages.

## What I could and could not observe
| Observed (from page content) | Not observable here |
|---|---|
| Information architecture, copy, section order, component inventory, interaction concepts described in text | Colours, fonts, spacing, radii, shadows, exact proportions |
| Product concepts: skills, memory, routines, approvals, shared workspace | Animations and scroll choreography (only their existence is implied) |
| Embedded product "scenes" (Slack-style threads, schedule grids, trigger→step chains) as text | The authenticated product UI, agent builder, execution history screens |

The sandbox browser could not resolve either domain (`ERR_NAME_NOT_RESOLVED`), so no screenshots of the references exist.
**Visual fidelity claims in this project are therefore limited to structure and interaction patterns, not pixel values.**
If you can supply screenshots or a screen recording, colours, type scale and spacing can be calibrated afterwards.

## Observed patterns
1. **Narrative, time-anchored marketing**: "One day of my work" walks through 8:00 AM / 2:00 PM / 5:30 PM / 9:41 PM scenes;
   each scene is a small product vignette (message thread, mini report, inbox). Section pattern: eyebrow, large heading, one-line
   promise, vignette card.
2. **Agent as a teammate in a message surface**: messages carry an avatar, an `APP` tag, time, a short summary, and result chips
   ("6 things handled overnight"). Results are cards inside the thread, not separate pages.
3. **Skills**: a skill is a named playbook written in plain English or demonstrated once; "picked automatically", "same result
   for everyone", "plain files you can open and edit". Built-in library (40+), team skills, admin controls.
4. **Memory**: plain, versioned files (`memory/preferences.md`, `clients.md`, `decisions.md`). Each fact shows provenance
   ("You told me", "I noticed", "From a meeting"). Lindy proposes a pattern ("Want me to do that from now on?") and the user confirms.
   Every save is a version that can be restored. Team memory readable by all, editable by admins.
5. **Routines**: schedule or event trigger, plain-English definition, a week grid, a trigger→steps chain
   (`When` → `Lindy` → `Lindy` → `Then`), results reported back in chat.
6. **Control model**: "I prep the work → You approve it → Then it goes out." Lookups just happen; anything with outside
   impact waits for approval until the user says otherwise. Spend caps and a clear paused message.
7. **Progressive complexity**: one prompt box ("Hand me your first job"), then skills, memory and routines as optional depth.
8. **Trust surface**: security, privacy and compliance stated as three plain promises.

## How VANIQ reproduces each pattern (pattern → feature → backend)
| Lindy pattern | VANIQ feature | Backend | Acceptance |
|---|---|---|---|
| Message-thread agent with result cards | **Agent home**: thread with plan cards, step status, result cards | `POST /api/agent/plan`, `GET /api/agent/runs/{id}` | A request produces a stored run; cards reflect real step states |
| "Lookups just happen, outside impact waits" | Safe read steps auto-run; consequential steps (STT call, export) require **Approve** | `POST /api/agent/runs/{id}/approve` | Consequential step never executes before approval (test) |
| Skills as playbooks | **Skills** page: executable capabilities with typed arguments and a Run button | `GET /api/agent/tools`, plan with explicit steps | Each skill card runs a real service and shows its result |
| Memory as editable versioned files | **Knowledge**: project conventions and linguistic references, drafts vs approved, versions, provenance | `/api/knowledge*` | Agent reads only approved items; agent cannot approve or invent entries |
| Routines (trigger → steps) | **Workflows** page: node chain with run history | `/api/workflows*` | Edges are type-checked and executed |
| Narrative marketing scenes | **Landing**: "One day of Ahirani data work" scenes using real product states | static | No fabricated metrics (labelled illustrative or omitted) |
| Activity feed ("handled overnight") | **Activity** feed from `audit_log` + agent runs | `GET /api/audit`, runs | Entries match the database |
| Honest limits | **Command mode** banner when no LLM is configured | `GET /api/agent/status` | Unsupported requests say so; no simulated success |

## Not reproduced (deliberately)
Integrations marketplace, phone/meetings/Slack channels, credits and pricing, testimonials, compliance badges (VANIQ has no
certifications), Lindy's name, logo, avatars and copy. Everything is original VANIQ text and assets.
