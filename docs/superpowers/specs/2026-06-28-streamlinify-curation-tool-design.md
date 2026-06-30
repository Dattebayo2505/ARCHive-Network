# Streamlinify — FB Export Curation Tool — Design

**Date:** 2026-06-28
**Project:** StreamlinifyArchers (Archers Network / DLSU)
**Status:** Approved design — ready for implementation plan

---

> **Note (2026-06-30):** the **UI-stack decision** here (Jinja2 + Alpine.js, no build step — §4 row
> "UI stack" and §7) is **superseded by** `2026-06-30-svelte-frontend-design.md` (SvelteKit + Skeleton).
> All other parts of this design still hold.

## 1. Overview

A local, single-user **FastAPI** web tool (managed with **uv**) that streamlines the
**weekly Facebook "Download Your Information" (DYI) export curation chore** for the
*Archers Network* page. It turns a raw FB export into a clean, **filtered "ready-to-upload"
folder** that a separate downstream ETL (`PLAN.md` + `ArchersNetworkEERD.md` in the sibling
export repo) loads into PostgreSQL + AWS S3.

This tool owns the **front half** of `docs/Pipeline.md` only: **ingest → validate → curate
(thumbnail selection) → transform**. It explicitly does **not** upload to S3 or write the
database — those are downstream phases that consume this tool's output.

---

## 2. Scope

### In scope
- Ingest a weekly export: drag-drop a `.zip` (unzip it) **or** point at an already-unzipped folder.
- Validate the folder matches the expected FB export structure before doing anything.
- Parse named albums (`posts/album/*.json`) and the profile feed (`posts/profile_posts_1.json`).
- Show photos as **thumbnails** in a browser gallery for selection.
- Enforce the curation rule: **≤10 photos per named album**, **keep ALL non-album photos**.
- Persist selection state so the chore can be paused and resumed.
- Produce a **filtered mirror** of the export (the "ready" folder), leaving the original untouched.

### Out of scope (downstream / separate phases)
- AWS S3 upload.
- PostgreSQL load / the EERD schema (`media`, `photo_album`, `hashtags`, …).
- Caption hoisting and hashtag extraction into DB tables — the tool **preserves** the source
  JSON (filtered) so the downstream ETL can still do this; it does not perform the ETL itself.
- Video files (`posts/media/videos/`, `videos.json`) — videos are editor-curated external
  links downstream, not handled here.
- EXIF processing.

---

## 3. Context & Inputs

The input is a Facebook DYI export. Conventions (from the sibling export repo's `CLAUDE.md`),
which the tool must respect:

- **Media `uri` paths are prefixed with the export folder name**
  (`this_profile's_activity_across_facebook/posts/media/...`). Strip that leading segment to
  resolve the real relative path.
- **Text fields are double-encoded (mojibake):** UTF-8 bytes re-escaped as Latin-1. Recover
  with `raw.encode("latin-1").decode("utf-8")` before display.
- **Timestamps** are Unix epoch **seconds**.
- **Two record shapes:** albums/posts use nested `attachments[].data[].media` / `photos[]`;
  secondary logs use flat `label_values[]`.
- **Photo identity = filename stem** (the `fbid`), e.g.
  `…/1447741280701269.jpg` → fbid `1447741280701269`. Stable across album and post copies.
- **Album identity = trailing id of the media subdirectory**, e.g.
  `…/media/BantaySenadoLaunch_1447745384034192/…` → album fbid `1447745384034192`.
- **Never traverse/glob `posts/media/`** (~875 MB, thousands of files). Drive ingestion off the
  `uri` fields in JSON, then verify those specific files exist on disk.

---

## 4. Key Decisions

| # | Decision | Choice |
|---|----------|--------|
| Scope | How far the app reaches | **Curation tool only** (no S3, no DB) |
| Interaction | How the editor drives it | **Local browser UI served by FastAPI** |
| Output | What "ready" contains | **Filtered mirror of the export** (same FB JSON shape, only picks) |
| Album rule | What gets the ≤10 cap | **Named `album/*.json` albums only**; catch-alls + post-only images are "non-album" |
| UI stack | How the UI is built | **Jinja2 server-rendered + Alpine.js, no build step** |

### Decision A — JSON files in the `ready/` output
- **Keep:** `posts/album/*.json` (rewritten to selected photos only),
  `posts/profile_posts_1.json` (filtered to selected media, so downstream caption/hashtag
  hoisting still works).
- **Drop:** `posts/videos.json`, `posts/content_sharing_links_you_have_created.json`,
  `posts/edits_you_made_to_posts.json`, `posts/places_you_have_been_tagged_in.json`.

### Decision B — Non-album photos (⚠ likely to change later)
- **Default (this version):** every non-album photo is **kept automatically** and shown
  **read-only** in the UI (visible so the editor knows what's bundled, but not pickable and not
  subject to the cap).
- **Note for implementation:** the user expects this behaviour to **change later** (e.g. allowing
  the editor to *deselect* junk from the non-album bucket, or applying a different policy). The
  `selection` module MUST therefore model the non-album handling as a **swappable policy / strategy**,
  not a hard-coded "always include". Keep the per-bucket inclusion decision behind a clear interface
  so a future "deselectable" mode is an additive change, not a rewrite.

---

## 5. Architecture & Module Layout

A uv-managed FastAPI app, one package, **one module per functionality**. Each module has a single
responsibility, a narrow interface, and is unit-testable in isolation.

```
StreamlinifyArchers/
├── pyproject.toml              # uv project; deps below
├── README.md
├── src/streamlinify/
│   ├── __init__.py
│   ├── app.py                  # create_app() factory: wires routers, mounts static, configures Jinja2 (thin)
│   ├── main.py                 # uvicorn entrypoint → console script `streamlinify`
│   ├── config.py               # pydantic-settings: WORKSPACE_DIR, MAX_PER_ALBUM=10, THUMB_SIZE, host/port
│   ├── ingest/
│   │   ├── __init__.py
│   │   ├── unzip.py            # safe zip extract (zip-slip guarded) → workspace import dir
│   │   └── validate.py        # does a folder match the FB export shape? → ValidationReport
│   ├── inventory/
│   │   ├── __init__.py
│   │   ├── models.py          # Photo, Album, ExportInventory (pydantic models)
│   │   ├── text.py            # mojibake fix, hashtag regex, epoch→datetime helpers
│   │   └── parser.py          # parse album/*.json + profile_posts → group + classify album vs non-album
│   ├── thumbnails/
│   │   ├── __init__.py
│   │   └── service.py         # Pillow thumbnail generation + on-disk cache (keyed by fbid + size)
│   ├── selection/
│   │   ├── __init__.py
│   │   ├── policy.py          # inclusion policy (named-album cap; non-album = swappable strategy, Decision B)
│   │   └── state.py           # selection store: applies policy, persists to workspace/selection.json
│   ├── transform/
│   │   ├── __init__.py
│   │   ├── builder.py         # build the filtered-mirror "ready/" folder + rewritten JSON
│   │   └── report.py          # build summary (counts, orphan URIs)
│   └── web/
│       ├── __init__.py
│       ├── routes_ingest.py   # POST upload-zip / set-folder; GET validation result
│       ├── routes_gallery.py  # GET gallery; GET thumbnail/{fbid}; POST toggle-selection
│       ├── routes_build.py    # POST build; GET summary
│       ├── templates/         # Jinja2: base.html, index.html, gallery.html, summary.html
│       └── static/            # alpine.min.js (vendored), app.css
└── tests/                     # pytest, one file per module, synthetic fixture export
```

**Module responsibilities & interfaces (the contracts):**

- **`config.py`** — typed settings (pydantic-settings). `MAX_PER_ALBUM = 10`, workspace path,
  thumbnail size, expected structure. No logic; imported everywhere.
- **`ingest/unzip.py`** — `extract_zip(uploaded, dest) -> Path`. Rejects zip-slip entries.
- **`ingest/validate.py`** — `validate_export(folder) -> ValidationReport` (ok flag + missing
  pieces). The only gate into parsing.
- **`inventory/models.py`** — `Photo(fbid, original_uri, resolved_path, title, caption,
  creation_at, album_fbid|None, is_non_album)`, `Album(fb_album_id, name, photos[])`,
  `ExportInventory(albums[], non_album_photos[])`.
- **`inventory/text.py`** — `fix_mojibake(s)`, `extract_hashtags(s)`, `epoch_to_dt(n)`. Pure
  functions, no I/O.
- **`inventory/parser.py`** — `build_inventory(export_folder) -> ExportInventory`. Resolves URIs
  (strip prefix), decodes text, maps post bodies → captions by photo fbid, classifies album vs
  non-album. Drives off JSON; verifies referenced files exist; never globs `media/`.
- **`thumbnails/service.py`** — `thumbnail_for(fbid) -> Path|bytes`. Lazy-generates with Pillow,
  caches on disk. Pure read of the original; never mutates source media.
- **`selection/policy.py`** — encapsulates the inclusion rules: named-album cap (`can_select`),
  and the **non-album strategy** (Decision B, swappable).
- **`selection/state.py`** — `toggle(album_fbid, photo_fbid)`, `is_selected(...)`,
  `count(album_fbid)`, `selected_set()`. Enforces policy server-side, persists every change.
- **`transform/builder.py`** — `build_ready_folder(inventory, selection, dest) -> BuildResult`.
  Copies selected media, rewrites album JSONs and the filtered `profile_posts_1.json`, drops
  unnecessary JSONs (Decision A), idempotent, never writes the original.
- **`transform/report.py`** — `summarize(build_result) -> Summary` (counts, orphans).
- **`web/*`** — thin routers translating HTTP ↔ the modules above. No business logic in routes.
- **`app.py`** — `create_app()` wiring only.

**Dependencies:** `fastapi`, `uvicorn[standard]`, `jinja2`, `python-multipart`,
`pydantic-settings`, `pillow`. Dev: `pytest`, `httpx`, `ruff`.

---

## 6. Data Flow (the weekly chore)

1. Editor opens `localhost:8000`, **drops the weekly export `.zip`** (or pastes a folder path).
2. `ingest.unzip` → `ingest.validate`: confirms `posts/`, `posts/album/*.json`, `posts/media/`,
   `posts/profile_posts_1.json` exist. On mismatch → report + halt.
3. `inventory.parser`: reads named albums + the feed, resolves URIs, decodes mojibake, classifies
   each photo album / non-album, attaches the hoisted post caption for display.
4. **Gallery:** pick ≤10 per named album; non-album photos shown read-only, all kept.
5. `selection.state` persists picks to `workspace/selection.json` after every toggle (resume-safe).
6. Editor clicks **Build ready folder**.
7. `transform.builder`: copies only selected media into
   `ready/<export-name>/posts/media/...`, rewrites each `album/*.json` to selected `photos[]`,
   filters `profile_posts_1.json` to selected media, drops unnecessary JSONs (Decision A). The
   original export is read-only. `transform.report` shows counts + orphan URIs.
8. The `ready/` folder is handed off to the downstream PLAN.md ETL (separate phase).

---

## 7. UI Layout

Two-pane, server-rendered (Jinja2), Alpine.js for instant client-side toggles + the live counter.

```
┌─ Streamlinify ─ Archers Network ──────────────────────────────┐
│  [ Drop export .zip ]  or  folder: [______________] [Load]    │
├───────────────┬───────────────────────────────────────────────┤
│ ALBUMS        │  BantaySenadoLaunch            ( 7 / 10 )      │
│ ───────────   │  ┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐           │
│ BantayS…  7/10│  │[✓] │ │[✓] │ │[ ] │ │[✓] │ │[ ] │  …        │
│ Forte…    4/10│  └────┘ └────┘ └────┘ └────┘ └────┘           │
│ Animofest 9/10│   1447…  1447…  1448…  (filename = fbid)       │
│ …             │  caption: "Bantay Senado launch… #ARCHEVT"    │
│ ───────────   │                                                │
│ Non-album     │  11th pick on a full album → blocked + toast   │
│  (all 312 kept)│                                               │
├───────────────┴───────────────────────────────────────────────┤
│                                    [ Build ready folder ▸ ]    │
└────────────────────────────────────────────────────────────────┘
```

- Left: named albums with live `X/10` counters + a read-only "Non-album (all kept)" entry.
- Right: thumbnail grid for the selected album; click toggles; the 11th pick is rejected
  **server-side** (not just hidden in JS) and surfaced as a toast.
- Each thumbnail shows its fbid (filename stem) and the hoisted post caption to aid the choice.

---

## 8. Error Handling

- **Bad/incomplete folder** → `validate` returns a report (e.g. "missing `posts/album/`") and the
  flow halts; nothing is parsed.
- **Zip-slip** → extraction rejects any entry resolving outside the workspace.
- **Mojibake decode failure** → `text.fix_mojibake` falls back to the raw string (try/except);
  never crashes a parse.
- **Orphan URI** (JSON references a file missing on disk) → excluded from the selectable set,
  surfaced in inventory and in the build report.
- **≤10 cap** → enforced in `selection.state` server-side; the 11th toggle returns a rejection.
- **Build idempotency** → re-running overwrites `ready/` cleanly, keyed by fbid; the original
  export is never written to.

---

## 9. Testing (TDD)

`pytest`, one test file per module, run against a **tiny synthetic fixture export** (a handful of
JSON files + dummy 1-px images) — never the real ~875 MB media tree. Coverage:

- `text`: mojibake round-trip, hashtag extraction, epoch conversion.
- `parser`: album vs non-album classification, fbid-stem + album-id extraction, URI prefix
  stripping, caption mapping, orphan detection.
- `validate`: detects missing/malformed structure.
- `selection`: ≤10 cap enforcement, persistence/resume, non-album policy (and that the policy is
  swappable per Decision B).
- `transform`: rewritten JSON contains only picks; only picked files copied; unnecessary JSONs
  dropped; original untouched; idempotent re-run.
- `web`: `httpx` route smoke tests (upload → gallery → toggle → build).

Per the test-driven-development skill, tests are written before implementation.

---

## 10. Tooling

- **uv** project (`pyproject.toml`), Python 3.12+.
- Run: `uv run streamlinify` (console script) → uvicorn on `localhost:8000`.
- **ruff** for lint + format.

---

## 11. Non-Goals

- No S3 upload, no database, no EXIF, no video handling, no caption/hashtag ETL (downstream).
- No multi-user, no auth, no deployment hardening — it's a local single-user weekly tool.
- No React/Vite/build pipeline.

---

## 12. Success Criteria

- Dropping a weekly export zip (or pointing at the folder) yields a validated, browsable gallery.
- The editor can pick ≤10 photos per named album, with all non-album photos retained.
- Selection survives a restart.
- "Build ready folder" produces `ready/<export>/` containing only the selected media + the
  rewritten/filtered `album/*.json` and `profile_posts_1.json`, with the unnecessary JSONs dropped,
  and the original export untouched.
- The resulting `ready/` folder is consumable as-is by the downstream PLAN.md ETL.
- Every module is independently unit-tested against the synthetic fixture.
