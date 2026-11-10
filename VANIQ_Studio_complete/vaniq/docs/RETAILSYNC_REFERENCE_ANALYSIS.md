# RetailSync AI: reference analysis

Sources inspected (public, fetched as page content): `/` (landing), `/templates`. `/editor` redirects to `/auth`
(login-gated, client-rendered), so **the actual editor was not inspected**. `/features`, `/pricing`, `/docs` and others are linked
but were not fetched.

## What I could and could not observe
| Observed | Not observable |
|---|---|
| Landing structure, copy, feature inventory, templates catalogue, stated stack (Next.js, Fabric.js canvas, Groq LLaMA 3.3, Remove.bg, Pexels, MongoDB) | The editor's real layout proportions, toolbar contents, panel behaviour, colours, animation |
| An editor mock caption: window chrome with `File Edit View`, zoom `100%`, address bar, canvas screenshot | Any screenshot pixels (no browser access to the domain) |
| "Press ⌘K to quick start", "Chat with AI to control your entire editor. 70+ commands" | The command list itself |

The product is a hackathon project ("Tesco Retail Media Hackathon 2025", Team Sarthak). Its editor is therefore described
below only from the landing page's claims. **I did not see it, and VANIQ does not copy any editor internals.**

## Observed patterns
1. **Editor-first product**: the primary call to action opens the editor directly ("Start Creating"), with a login redirect.
2. **App-shell mock**: macOS-style menu bar (`File Edit View`), zoom control, central canvas screenshot.
3. **⌘K quick start** command entry on the landing page.
4. **AI Design Agent**: natural-language control of the canvas ("add shapes, change colors, remove backgrounds, adjust layouts")
   with a count of supported commands (70+). Commands act on the editor's objects.
5. **Template gallery** with size filters (Leaderboard 728x90, Medium Rectangle 300x250, …) and category filters
   (Promotions, Products, Seasonal …), each card ending in "Use Template" which opens the editor with the template preloaded.
6. **Tool inventory language**: Layers ("full control"), Crop ("interactive"), advanced text, asset library, shapes, stickers.
7. **Live compliance validation** while designing ("auto-validates against brand guidelines as you design").
8. **Multi-format export** (15+ sizes, PNG/JPG/WebP).
9. **How it works in three steps**: Upload & Choose, AI Enhancement, Export & Deploy; "challenge" section with three
   problem statistics (these are the product's own marketing claims; VANIQ does not reuse them).

## How VANIQ adapts each pattern
| RetailSync pattern | VANIQ voice-data studio | Backend | Acceptance |
|---|---|---|---|
| Editor-first shell: top bar, left tools, centre canvas, right inspector | **Studio** layout with the same four regions | existing clip/transcript/review APIs | Selecting a clip loads all regions from one workspace payload |
| Canvas = ad | **Canvas = recording**: waveform with segment regions, transcript tracks | new `GET /api/sources/{id}/audio` | Clicking a region selects that clip and seeks audio |
| Right inspector (selected object properties) | Inspector: speaker, declared dialect, provider-detected language, script, orthography, STT provider/model, metadata, consent, verification | `GET /api/clips/{id}`, `PATCH /api/sources/{id}` | Values come from the database; permission edits persist |
| Layers | **Tracks**: raw STT, corrected, human reference (three stacked text layers) | existing | Raw is read-only; reference starts empty |
| ⌘K quick start / AI agent controlling the editor | **Command bar** (⌘K) routed to the agent with current selection as context | `/api/agent/*` | Same agent as the home thread; context includes `clip_id` |
| Templates gallery with filters | **Workflow templates** gallery with category filters (Intake, Baseline, Review, Evaluation, Export) | `/api/workflows` | "Use template" creates an editable workflow |
| Live compliance validation | **Live eligibility**: toolbar and inspector show whether the selected clip may be exported and why not | `GET /api/datasets/eligibility` | Reasons match export rules |
| Multi-format export | Export dialog (public/internal, permission summary) | `POST /api/exports` | Disabled when zero clips are eligible |
| Undo/redo | **Not provided** as a global feature. Corrections are reversible per item ("Undo" sets a suggestion back to pending) | existing | No dead undo button |

## Not reproduced
Fabric.js, retail templates, brand-guideline engine, stock images, background removal, their copy, statistics, team details,
name and logo.
