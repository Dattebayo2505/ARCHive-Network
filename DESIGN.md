---
name: ARCHive Network
description: Calm, confident DLSU-green curation tool for the Archers Network weekly FB export
colors:
  primary-green: "oklch(0.56 0.13 159)"
  primary-green-deep: "oklch(0.43 0.105 160)"
  primary-green-soft: "oklch(0.92 0.04 159)"
  gold: "oklch(0.7 0.13 78)"
  slate: "oklch(0.52 0.035 228)"
  surface-paper: "oklch(0.99 0.003 165)"
  surface-mist: "oklch(0.975 0.004 165)"
  surface-line: "oklch(0.87 0.007 165)"
  ink: "oklch(0.23 0.007 171)"
  ink-muted: "oklch(0.48 0.008 168)"
  warning-amber: "oklch(0.75 0.15 67)"
  error-red: "oklch(0.58 0.21 28)"
  success-green: "oklch(0.63 0.16 147)"
typography:
  headline:
    fontFamily: "Montserrat, Inter, ui-sans-serif, system-ui, sans-serif"
    fontSize: "1.5rem"
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: "-0.011em"
  title:
    fontFamily: "Montserrat, Inter, ui-sans-serif, system-ui, sans-serif"
    fontSize: "1.25rem"
    fontWeight: 600
    lineHeight: 1.3
    letterSpacing: "-0.011em"
  body:
    fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.55
    letterSpacing: "0em"
  label:
    fontFamily: "Montserrat, Inter, ui-sans-serif, system-ui, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 600
    lineHeight: 1.4
    letterSpacing: "0.02em"
  mono:
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace"
    fontSize: "0.75rem"
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: "0em"
rounded:
  sm: "0.5rem"
  md: "0.75rem"
  lg: "1rem"
  full: "9999px"
spacing:
  xs: "0.25rem"
  sm: "0.5rem"
  md: "1rem"
  lg: "1.5rem"
  xl: "2rem"
components:
  button-primary:
    backgroundColor: "{colors.primary-green-deep}"
    textColor: "{colors.surface-paper}"
    rounded: "{rounded.sm}"
    padding: "0.5rem 1rem"
  button-primary-hover:
    backgroundColor: "oklch(0.36 0.085 161)"
    textColor: "{colors.surface-paper}"
  button-secondary:
    backgroundColor: "{colors.surface-paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: "0.5rem 0.875rem"
  card:
    backgroundColor: "{colors.surface-paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    padding: "1.25rem"
  count-badge-active:
    backgroundColor: "oklch(0.85 0.07 158)"
    textColor: "{colors.primary-green-deep}"
    rounded: "{rounded.full}"
    padding: "0.125rem 0.5rem"
  count-badge-full:
    backgroundColor: "oklch(0.87 0.1 80)"
    textColor: "oklch(0.41 0.1 49)"
    rounded: "{rounded.full}"
    padding: "0.125rem 0.5rem"
---

# Design System: ARCHive Network

## 1. Overview

**Creative North Star: "The Archive Steward"**

ARCHive Network is the calm room where a volunteer sorts a week of photos, certain that the
originals on the shelf behind them will never be touched. The interface behaves like a careful
archivist: it states plainly what it's doing, shows exactly how full each album is, confirms what
it copied, and otherwise stays quiet and out of the way. Deep **DLSU green** carries the Archers
Network identity at the header and on the actions that matter; everything else is a soft,
green-tinted paper neutral so the photographs are the brightest thing on the screen.

The system is **light by deliberate choice** — locked with `color-scheme: only light` so neither
OS dark mode nor a browser's Auto Dark Mode can mangle it. The audience rotates every term and
gets no training, so legibility and self-evidence beat density and cleverness. Colour is treasure
spent only where attention is genuinely needed: an album hitting its cap, an ingest error, a build
confirmation.

It explicitly rejects the flashy-SaaS-landing reflex (no gradient heroes, no marketing hype, no
decorative motion), the toy/consumer-app reflex (no mascots, candy colours, or gimmicks that
undercut the "your originals are safe" trust), the cramped enterprise admin panel (no dense grey
clutter or tiny text), and — above all — the raw, default-Skeleton prototype it grew out of.

**Key Characteristics:**
- Light, paper-calm surfaces with a faint green tint (never warm cream).
- One brand colour — DLSU green — for identity and primary action only.
- Quiet by default; amber and red appear solely at limits and failures.
- Generous spacing and large tap targets for infrequent, untrained users.
- State legible at a glance: active workspace, active album, fullness, selected, auto-kept,
  archived, missing.

## 2. Colors

A restrained, green-tinted neutral field with a single saturated brand green and a small reserve
of attention colours. Implemented as the `archers` Skeleton theme in `frontend/src/app.css`; the
`--color-*` ramps below are the source of truth and every token in this doc maps to one.

### Primary
- **DLSU Green** (`oklch(0.56 0.13 159)` ≈ #00703C, `primary-500`): the La Salle / Archers identity
  colour. Anchors the brand and selection states (selected-tile wash + check badge, active-album
  badge, progress fill).
- **Green Deep** (`oklch(0.43 0.105 160)`, `primary-700`): the header bar and every primary button.
  Carries white text at ≥6:1 contrast — the confident, load-bearing green.
- **Green Soft** (`oklch(0.92 0.04 159)`, `primary-100`): hover wash on list rows and subtle
  primary-tinted fills.

### Secondary
- **Slate** (`oklch(0.52 0.035 228)`): a calm blue-grey for quiet secondary actions and neutral
  information, when green would over-signal.

### Tertiary
- **Gold** (`oklch(0.7 0.13 78)`): a restrained DLSU gold, held in reserve for the rare moment that
  wants a non-green highlight. Used sparingly, never as a second brand colour.

### Neutral
- **Paper** (`oklch(0.99 0.003 165)`, `surface-50`): the primary surface — cards, panels, modals,
  tiles' base.
- **Mist** (`oklch(0.975 0.004 165)`, `surface-100`): the body background, a half-step below paper.
- **Line** (`oklch(0.87 0.007 165)`, `surface-300`): borders and dividers.
- **Ink** (`oklch(0.23 0.007 171)`, `surface-900`): primary text — high contrast, the legibility
  floor.
- **Ink Muted** (`oklch(0.48 0.008 168)`, `surface-600`): secondary text and metadata; still ≥4.5:1
  on paper.

### Attention
- **Amber** (`oklch(0.75 0.15 67)`): the **album-full / at-the-cap** colour. Always paired with a
  lock icon and the count — never colour alone.
- **Red** (`oklch(0.58 0.21 28)`): ingest failures, incomplete-export warnings, and destructive
  confirmations (delete a workspace) only.
- **Success Green** (`oklch(0.63 0.16 147)`): a cooler confirmation green for the build-complete
  check, kept distinct from the brand green so "done" doesn't read as "brand".

### Named Rules
**The One-Green Rule.** DLSU green signals identity and primary action and nothing else. It never
becomes a background wash, a decorative fill, or a second body colour. Its restraint is what makes
the header and the Build button feel like *the* things to act on.

**The Spend-At-The-Edge Rule.** Amber and red are forbidden on anything at rest. They appear only
at a real limit (cap reached) or a real failure (bad export, destructive confirm). A screen with no
problems has no amber and no red on it.

## 3. Typography

A deliberate **two-tier system**: a geometric display face for identity and headings, a humanist
sans for everything the user reads while working.

**Display / Brand Font:** **Montserrat** (geometric sans; loaded from Google Fonts in `app.html`,
weights 500/600/700). Exposed as the `--font-display` token and consumed by `--heading-font-family`
plus the `.font-display` utility.
**Body / UI Font:** **Inter** (humanist sans; Google Fonts, weights 400/500/600/700, with
`ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto` fallback).
**Mono Font:** `ui-monospace, SFMono-Regular, Menlo` — for paths and the build report only.

**Character:** Montserrat's geometric caps give the wordmark and the tracked rail labels a
confident, collegiate presence that reads as *the Archers Network tool* — geometric display over a
humanist workhorse is a true contrast pairing, not two similar sans fighting. Inter keeps the small,
dense task surface (count badges, album rows, folder paths, instructions) maximally legible, where
Montserrat's tall geometric skeleton would cost readability. Paths and the build log use mono so a
folder string reads as a literal, copyable artifact.

### Hierarchy
- **Wordmark** (Montserrat 600, `text-base`→`text-lg`, `tracking-tight`): "ARCHive Network" in the
  header — the single strongest brand moment.
- **Headline** (Montserrat 600, `text-2xl`/1.5rem on the landing hero, `text-xl`/1.25rem for gallery
  page titles like an album name, "Archive", "Videos"): the most prominent text on a screen. Fixed
  rem, never fluid — a sidebar heading that shrinks looks worse, not better.
- **Title** (Montserrat 600, `text-lg`/1.125rem): modal and dialog titles ("Choose export folder",
  "Ready folder built", confirm dialogs), section headings like "Your workspaces". Applied via
  `--heading-font-family` on the `<h2>` elements.
- **Label** (Montserrat 600, 0.75rem / `text-xs`, +0.02em, uppercase): the tracked structural
  labels — the "ALBUMS" and "ARCHIVED" rail sections and group names. Montserrat's geometric
  uppercase is the payoff here. Used as structure, not as an eyebrow on every block.
- **Body** (Inter 400, 1rem, 1.55): instructions and descriptions. Capped ~65–75ch for prose.
- **Data** (Inter 500–600, `tabular-nums`): count badges, `count/max` pills, the build stat, metadata
  captions (e.g. "Date posted on FB"). Always tabular so digits don't jitter as counts change.
- **Mono** (400, 0.75rem): `workspace/ready/`, chosen folder paths, the typed-path field, the build
  report.

### Named Rules
**The Two-Tier Rule.** Montserrat is for **identity and headings only** — wordmark, page/modal
titles, tracked uppercase labels. It never runs body text, button labels, instructions, or data.
Inter owns the task surface. The contrast between the two *is* the hierarchy; blurring it (Montserrat
in a paragraph, Inter in the wordmark) flattens both.

**The Fixed-Scale Rule.** Type sizes are fixed rem on a tight scale (Skeleton `--text-scaling:
1.067`; ~1.2 between the major display steps). No `clamp()` headings — users view at a consistent
desk DPI and exaggerated fluid contrast just adds noise.

## 4. Elevation

Predominantly **flat with tonal layering**. Depth comes from the paper/mist/line neutral steps and
from hairline borders, not from heavy shadows. Shadows are reserved and soft: a faint `shadow-sm`
to lift the header, primary buttons, and the rail panels off the page, and a single larger
`shadow-xl` to float modals (folder picker, build summary, confirm dialogs) above a dimmed
backdrop. Nothing has a dark, blurry, 2014-era drop shadow.

### Shadow Vocabulary
- **Lift** (`box-shadow: 0 1px 2px oklch(0.23 0.007 171 / 0.06)`): header, primary buttons, rail
  panels — barely-there separation from the surface.
- **Float** (`box-shadow: 0 12px 32px oklch(0.16 0.006 172 / 0.18)`): modals only, over a
  `surface-950/50` backdrop with a 1px backdrop-blur.

### Named Rules
**The Flat-At-Rest Rule.** Surfaces are flat until they need to float. Only overlays (modals) and
the load-bearing chrome (header, primary buttons, rail panels) carry shadow; cards and tiles rely
on borders and tone.

## 5. Layout & Shell

### App Shell (`+layout.svelte`)
A full-height flex column (`h-dvh`): sticky header, a single scrolling `main`, sticky footer.

- **Header:** sticky Green-Deep (`primary-700`) bar. A bow-and-arrow Archers mark, the **"ARCHive
  Network"** wordmark, and a subtitle that shows the **active workspace's name** — or the brand
  tagline *"From profile archives to production-ready assets"* when none is loaded. On the gallery,
  a **back-arrow** returns to the workspace picker. On the right, a 2-step progress indicator
  (**Load export → Curate photos**) with the current step filled paper-white.
- **Footer:** a persistent lock-icon line — "Your export is **read-only** — ARCHive Network only
  writes a filtered copy to `workspace/ready/`." Safety, restated on every screen.

### Ingest / Landing (`routes/+page.svelte`)
The landing screen is the **workspace picker + new-import** surface: existing workspaces list at
the top (`WorkspaceList`), then the ways in — drop a `.zip`, browse to an unzipped folder via the
picker modal, or paste a known path. The dropzone, the "Load from this computer" folder card, and
the mono paste-a-path field stack inline; nothing here is modal except the folder picker itself.

### Gallery (`routes/gallery/+page.svelte`)
A **3-column flex layout** (flex, not grid, so the third column can appear/disappear cleanly):

1. **Left rail** — fixed-width `AlbumList` (albums, Videos, Archive, Archived).
2. **Center** — `flex-1` photo grid (`PhotoGrid`) with the active album's title, count, and
   description above it, and `ViewControls` for tile size.
3. **Right rail** — the collapsible, resizable `SelectionPanel` showing the current album's picks.

## 6. Components

### Buttons
- **Shape:** Gently rounded (0.5rem / `rounded-lg`).
- **Primary:** Green Deep background, paper-white text, `shadow-sm`, padding `0.5rem 1rem`. The
  single most prominent action on any screen (Upload, Browse files, Build, Use this folder).
- **Hover / Focus:** darkens to `oklch(0.36 ...)` (`primary-800`); always a 2px `primary-600` focus
  ring at `outline-offset: 2px`. Disabled drops to 50% opacity with `cursor-not-allowed` (or
  `cursor-progress` while building).
- **Secondary / Ghost:** paper background with a `line` border (Browse… in the folder card), or a
  borderless tinted-hover row (Cancel, list items). Never competes with the primary green.

### Count Badge (signature)
- **Style:** pill (`rounded-full`), `tabular-nums`, `count/max`.
- **State:** zero → neutral grey on grey; in-progress → green-200 on green-900; **full → amber-200
  on amber-900 with a lock icon**. The lock + the number are the non-colour cues for the cap.

### Photo Tile (signature)
- **Shape:** in the main **PhotoGrid**, a uniform **3:2** box (`rounded-lg`, 1px inset ring at rest,
  image `object-cover`) laid out on a CSS Grid whose column min `ViewControls` sets — even heights
  read best while scanning to select. The **SelectionPanel** and the full-screen preview's filmstrip
  instead keep each photo's **own aspect ratio** in a masonry column flow.
- **Selected:** 2px green ring + a faint green wash + a solid green circular **check badge**
  (top-right). The check is the colour-independent cue.
- **Unselected (interactive):** an empty ring outline fades in on hover/focus as the affordance;
  image lifts `scale-[1.03]`.
- **Album full (unselected):** the tile stays fully interactive — normal opacity, hover ring, no
  lock — so it still reads as selectable. The click is rejected server-side (the ≤10 cap) and the
  gallery raises an **"Album is full"** toast telling the volunteer to remove one to swap. A dimmed,
  locked tile was rejected: it read as damaged/unavailable rather than "at the limit".
- **Caption:** bottom gradient scrim with 2-line clamped caption in paper-white.
- **Missing file:** broken-image icon + "missing file" on the bare tile; never selectable.
- **Archived:** full opacity but read-only — no hover ring, no check affordance, `cursor-default`.
  It's shown for reference, not for picking.

### Album Rail (`AlbumList`)
The left rail's list of pickable surfaces. Each row: name (`font-semibold` when active), a trailing
`tabular-nums` count badge, green-soft hover wash, active-row green tint.

- **Groups:** a collapsible "ALBUMS · N" section (chevron toggle), plus fixed **Videos** and
  **Archive** rows, and a read-only **"ARCHIVED"** group beneath them.
- **Rename:** right-click (or the row's affordance) opens an inline editor — a `position: fixed`
  overlay input with `field-sizing: content` so it grows to fit and escapes the rail's clipping.
  The custom name overrides the FB album name in the live inventory and in the build output.
- **Context menu:** `ContextMenu` (see below) for per-album actions (rename, archive).

### Selection Panel (`SelectionPanel`)
The right rail. Shows the selected photos for the **current active album only** (not all albums).

- **Collapsible** via a toolbar toggle; when hidden, the center grid reclaims the width.
- **Resizable** via a pointer-drag handle on its left edge (200–600px). Its masonry column width is
  derived from the live panel width, so thumbnails re-flow as it's dragged.
- Same tile vocabulary as the grid, at panel scale.

### View Controls (`ViewControls`)
A small `Size` stepper (segmented `tabular-nums` buttons) that sets the masonry column width, plus
the SelectionPanel show/hide toggle. Ghost styling — it's chrome, never a primary action.

### Context Menu (`ContextMenu`)
A `position: fixed` overlay menu opened by right-click. Supports **nested submenus** natively via
CSS `group-hover`, with an invisible padding "bridge" so the pointer can cross the gap to the
submenu without it closing. Escape / outside-click dismiss; focus-visible throughout.

### Cards / Panels
- **Corner:** `rounded-xl`/`rounded-2xl` (0.75–1rem). **Background:** paper. **Border:** 1px line.
  **Shadow:** Lift at most. **Padding:** `1rem`–`1.5rem`. No nested cards.

### Inputs / Dropzone
- **Dropzone:** dashed `line` border on paper; on drag-over the border goes `primary-500` and the
  fill goes green-soft. A spinner + status label replaces the prompt while busy.
- **Folder field:** the folder is **chosen via the picker modal** (`FolderPicker` — a file-dialog
  with a drive switcher, an editable mono address bar, per-folder "Export" detection, and inline
  `.zip` unzip). A direct mono **paste-a-path** field on the ingest card is the supported secondary
  path for users who already know the location. The picker leads; typing is the shortcut, never the
  only way.

### Workspace List (`WorkspaceList`)
The landing roster of saved weeks. Each row: display name + open affordance, and a quiet
**remove-from-list** action (red only on hover) that opens a `ConfirmDialog` — removing a workspace
never touches the original export, and the copy says so.

### Modals & Dialogs
- **`FolderPicker`, `BuildSummary`, `ConfirmDialog`:** native-feeling overlays on a dimmed backdrop,
  Float shadow, Escape + backdrop-click to close, focus-visible rings throughout.
- **`BuildSummary`** restates the output path (`workspace/ready/…`), the copied-file stat
  (`tabular-nums`), and an expandable mono build log — safety confirmed after the fact.
- Used only where genuinely modal; the gallery and ingest stay inline.

### Preview Overlays (`PhotoPreview`, `VideoPreview`)
Full-screen viewers over a dimmed backdrop with a ratio-following filmstrip. `←`/`→` browse, `Esc`
closes (keys shown as `<kbd>`). `VideoPreview` also drives the client-side thumbnail capture.

## 7. Do's and Don'ts

### Do:
- **Do** keep DLSU green for identity + primary action only (the One-Green Rule).
- **Do** pair every colour-coded state with a non-colour cue: the full badge has a lock + number,
  the selected tile has a check badge, the archived tile is read-only. Volunteers may be colour-blind.
- **Do** hold the surface light and paper-calm; let the photographs be the brightest thing.
- **Do** make safety visible — restate "original is read-only" in the footer and the build summary,
  and name the exact output path (`workspace/ready/`).
- **Do** use fixed rem type on a tight scale, and hold the two-tier split: Montserrat for the
  wordmark, headings, and tracked labels; Inter for all body, UI, and data.
- **Do** keep ≥4.5:1 body / placeholder contrast and ≥3:1 for large text and the green buttons;
  give every control a visible `primary-600` focus ring.
- **Do** lock the theme with `color-scheme: only light` so OS/browser dark modes can't invert it.

### Don't:
- **Don't** build a flashy SaaS landing: no gradient heroes, marketing hype, or decorative motion.
  Motion conveys state only (150–300ms), and every animation honours `prefers-reduced-motion`.
- **Don't** make it a toy or consumer app: no mascots, candy colours, or gimmicks that undercut the
  read-only-original trust.
- **Don't** drift back toward raw default-Skeleton (untuned `cerberus`, bare forms, undecorated
  tiles) or a cramped grey admin panel.
- **Don't** spend amber or red on anything at rest — only the cap, real failures, and destructive
  confirms earn them.
- **Don't** drench the page in green, add a second brand hue, or use gradient text / `background-clip`.
- **Don't** use side-stripe (`border-left`) accents or nested cards. The typed-path field is allowed
  as a clearly-secondary shortcut, but the picker stays the primary, most discoverable way in.
- **Don't** reach for a modal as the first thought; the gallery and ingest stay inline. Modals are
  the folder picker, the build summary, and destructive confirms only.
