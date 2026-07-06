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
    fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif"
    fontSize: "1.5rem"
    fontWeight: 650
    lineHeight: 1.2
    letterSpacing: "-0.011em"
  title:
    fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif"
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
    fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif"
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

Streamlinify is the calm room where a volunteer sorts a week of photos, certain that the
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
- State legible at a glance: active album, fullness, selected, auto-kept, missing.

## 2. Colors

A restrained, green-tinted neutral field with a single saturated brand green and a small reserve
of attention colours.

### Primary
- **DLSU Green** (`oklch(0.56 0.13 159)` ≈ #00703C): the La Salle / Archers identity colour. Anchors
  the brand and selection states (selected-tile wash + check badge, active-album badge, progress fill).
- **Green Deep** (`oklch(0.43 0.105 160)`): the header bar and every primary button. Carries white
  text at ≥6:1 contrast — the confident, load-bearing green.
- **Green Soft** (`oklch(0.92 0.04 159)`): hover wash on list rows and subtle primary-tinted fills.

### Secondary
- **Slate** (`oklch(0.52 0.035 228)`): a calm blue-grey for quiet secondary actions and neutral
  information, when green would over-signal.

### Tertiary
- **Gold** (`oklch(0.7 0.13 78)`): a restrained DLSU gold, held in reserve for the rare moment that
  wants a non-green highlight. Used sparingly, never as a second brand colour.

### Neutral
- **Paper** (`oklch(0.99 0.003 165)`): the primary surface — cards, panels, modals, tiles' base.
- **Mist** (`oklch(0.975 0.004 165)`): the body background, a half-step below paper.
- **Line** (`oklch(0.87 0.007 165)`): borders and dividers.
- **Ink** (`oklch(0.23 0.007 171)`): primary text — high contrast, the legibility floor.
- **Ink Muted** (`oklch(0.48 0.008 168)`): secondary text and metadata; still ≥4.5:1 on paper.

### Attention
- **Amber** (`oklch(0.75 0.15 67)`): the **album-full / at-the-cap** colour. Always paired with a
  lock icon and the count — never colour alone.
- **Red** (`oklch(0.58 0.21 28)`): ingest failures and incomplete-export warnings only.
- **Success Green** (`oklch(0.63 0.16 147)`): a cooler confirmation green for the build-complete
  check, kept distinct from the brand green so "done" doesn't read as "brand".

### Named Rules
**The One-Green Rule.** DLSU green signals identity and primary action and nothing else. It never
becomes a background wash, a decorative fill, or a second body colour. Its restraint is what makes
the header and the Build button feel like *the* things to act on.

**The Spend-At-The-Edge Rule.** Amber and red are forbidden on anything at rest. They appear only
at a real limit (cap reached) or a real failure (bad export). A screen with no problems has no
amber and no red on it.

## 3. Typography

**Display / Body Font:** Inter (with `ui-sans-serif, system-ui` fallback)
**Mono Font:** `ui-monospace, SFMono-Regular, Menlo` — for paths and the build report only

**Character:** One humanist sans across the whole product — headings, labels, body, data. No
display/body pairing; product UI is calmer and more trustworthy with a single well-tuned face.
Paths and the build log use mono so a folder string reads as a literal, copyable artifact.

### Hierarchy
- **Headline** (650, 1.5rem, 1.2): page titles ("Load this week's export", album name). Fixed rem,
  never fluid — a sidebar heading that shrinks looks worse, not better.
- **Title** (600, 1.25rem, 1.3): the active-album title in the gallery, modal titles.
- **Body** (400, 1rem, 1.55): instructions and descriptions. Capped ~65–75ch for prose.
- **Label** (600, 0.75rem, +0.02em): the lone uppercase element — section labels like "ALBUMS",
  "ALREADY UNZIPPED?". Used as quiet structure, not as an eyebrow on every block.
- **Mono** (400, 0.75rem): `workspace/ready/`, chosen folder paths, the build report.

### Named Rules
**The Fixed-Scale Rule.** Type sizes are fixed rem on a tight ~1.2 ratio. No `clamp()` headings —
users view at a consistent desk DPI and exaggerated fluid contrast just adds noise.

## 4. Elevation

Predominantly **flat with tonal layering**. Depth comes from the paper/mist/line neutral steps and
from hairline borders, not from heavy shadows. Shadows are reserved and soft: a faint `shadow-sm`
to lift the header, primary buttons, and the rail panel off the page, and a single larger
`shadow-xl` to float modals (folder picker, build summary) above a dimmed backdrop. Nothing has a
dark, blurry, 2014-era drop shadow.

### Shadow Vocabulary
- **Lift** (`box-shadow: 0 1px 2px oklch(0.23 0.007 171 / 0.06)`): header, primary buttons, rail
  panel — barely-there separation from the surface.
- **Float** (`box-shadow: 0 12px 32px oklch(0.16 0.006 172 / 0.18)`): modals only, over a
  `surface-950/50` backdrop with a 1px backdrop-blur.

### Named Rules
**The Flat-At-Rest Rule.** Surfaces are flat until they need to float. Only overlays (modals) and
the three load-bearing chrome elements carry shadow; cards and tiles rely on borders and tone.

## 5. Components

### Buttons
- **Shape:** Gently rounded (0.5rem / `rounded-lg`).
- **Primary:** Green Deep background, paper-white text, `shadow-sm`, padding `0.5rem 1rem`. The
  single most prominent action on any screen (Upload, Browse files, Build, Use this folder).
- **Hover / Focus:** darkens to `oklch(0.36 ...)` (green-800); always a 2px `primary-600` focus ring
  at `outline-offset: 2px`. Disabled drops to 50% opacity with `cursor-not-allowed` (or
  `cursor-progress` while building).
- **Secondary / Ghost:** paper background with a `line` border (Browse… in the folder card), or a
  borderless tinted-hover row (Cancel, list items). Never competes with the primary green.

### Count Badge (signature)
- **Style:** pill (`rounded-full`), `tabular-nums`, `count/max`.
- **State:** zero → neutral grey on grey; in-progress → green-200 on green-900; **full → amber-200
  on amber-900 with a lock icon**. The lock + the number are the non-colour cues for the cap.

### Photo Tile (signature)
- **Shape:** the photo's **own aspect ratio** (no square crop), `rounded-lg`, 1px inset ring at
  rest, image `object-cover` into a box matched to the original ratio. Tiles flow in a **masonry**
  column layout (the view-size control sets column width) so mixed portrait/landscape photos tile
  without gaps or cropping. The full-screen preview's filmstrip follows the same rule: fixed-height
  thumbs whose width tracks each photo's ratio.
- **Selected:** 2px green ring + a faint green wash + a solid green circular **check badge**
  (top-right). The check is the colour-independent cue.
- **Unselected (interactive):** an empty ring outline fades in on hover/focus as the affordance;
  image lifts `scale-[1.03]`.
- **Blocked (album full, not selected):** 55% opacity, `cursor-not-allowed`, a small lock badge —
  it teaches the cap instead of letting the click fail.
- **Caption:** bottom gradient scrim with 2-line clamped caption in paper-white.
- **Missing file:** broken-image icon + "missing file" on the bare tile; never selectable.

### Cards / Panels
- **Corner:** `rounded-xl`/`rounded-2xl` (0.75–1rem). **Background:** paper. **Border:** 1px line.
  **Shadow:** Lift at most. **Padding:** `1rem`–`1.5rem`. No nested cards.

### Inputs / Dropzone
- **Dropzone:** dashed `line` border on paper; on drag-over the border goes `primary-500` and the
  fill goes green-soft. A spinner + status label replaces the prompt while busy.
- **Folder field:** the folder is **chosen via the picker modal** (a file-dialog with a drive
  switcher, an editable mono address bar, and per-folder "Export" detection). A direct mono
  **paste-a-path** field on the ingest card is the supported secondary path for users who already
  know the location. The picker leads; typing is the shortcut, never the only way.

### Navigation / Shell
- **Header:** sticky Green-Deep bar, paper-white wordmark + "Archers Network · weekly export
  curation", and a 2-step progress indicator (Load export → Curate photos).
- **Rail:** sticky paper panel of album rows with count badges, a read-only "Auto-kept" row, and the
  Build button beneath it so it follows the scroll.
- **Footer:** a persistent lock-icon line — "Your export is read-only — Streamlinify only writes a
  filtered copy to `workspace/ready/`."

### Modals
- Native-feeling overlays (folder picker, build summary) on a dimmed backdrop, Float shadow, Escape
  + backdrop-click to close, focus-visible rings throughout. Used only where genuinely modal — the
  rest of the product stays inline.

## 6. Do's and Don'ts

### Do:
- **Do** keep DLSU green for identity + primary action only (the One-Green Rule).
- **Do** pair every colour-coded state with a non-colour cue: the full badge has a lock + number,
  the selected tile has a check badge. Volunteers may be colour-blind.
- **Do** hold the surface light and paper-calm; let the photographs be the brightest thing.
- **Do** make safety visible — restate "original is read-only" in the footer and the build summary,
  and name the exact output path (`workspace/ready/`).
- **Do** use fixed rem type on a tight ~1.2 scale; one family (Inter) everywhere.
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
- **Don't** spend amber or red on anything at rest — only the cap and real failures earn them.
- **Don't** drench the page in green, add a second brand hue, or use gradient text / `background-clip`.
- **Don't** use side-stripe (`border-left`) accents or nested cards. The typed-path field is allowed
  as a clearly-secondary shortcut, but the picker stays the primary, most discoverable way in.
- **Don't** reach for a modal as the first thought; the gallery and ingest stay inline. Modals are
  only the folder picker and the build summary.
