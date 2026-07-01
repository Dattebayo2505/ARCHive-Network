# Product

## Register

product

## Users

The **Archers Network media/editorial team at DLSU** — a student publication. The person
running this is a **rotating volunteer**: a different student each term, moderately
tech-comfortable, working on a laptop. They do not get a training session and may use the tool
only a handful of times before handing it off. Their weekly job is to take a fresh Facebook
"Download Your Information" export and turn it into a clean, filtered folder that's ready to
upload downstream. They are not the tool's author and should never need to read the code to
understand what a screen is asking of them.

## Product Purpose

Streamlinify curates a weekly Facebook export into a filtered, ready-to-upload folder. The flow
is three logical screens — **ingest** (drop the export), **gallery** (pick ≤10 photos per named
album; non-album photos are auto-kept), **build** (write the filtered mirror to
`workspace/ready/<export-name>/`). The original export is **read-only and never modified** — that
guarantee is the product's core promise. Curation only; S3 upload and the database load are
downstream phases. Success looks like a volunteer opening the tool cold, understanding each step
without help, confidently making their selections, and walking away sure that the right photos
were copied and nothing original was touched.

## Brand Personality

**Calm, confident, trustworthy.** Three words: *reassuring, legible, considered.* The tool's
voice is plain and unhurried — it tells you what it's doing and what is safe, never hypes itself.
It should feel like a real **Archers Network** tool: **DLSU green** carries the identity lightly
(primary accent and header), with restrained, neutral surfaces everywhere else. The emotional
goal is trust — the volunteer should never wonder "did I just break the original?" or "which
album am I even looking at?".

## Anti-references

- **Not a flashy SaaS landing.** No gradient hero, marketing hype, animated buzzwords, or
  attention-grabbing motion. This is a work tool, not a pitch.
- **Not a toy or consumer app.** No mascots, candy colors, playful gimmicks, or novelty that
  undercuts the "your originals are safe" trust this tool trades on.
- **Not raw, default-Skeleton scaffolding.** The current state (untuned `cerberus` theme,
  undecorated tiles, bare forms) reads as a half-finished prototype; the shipped product should
  feel deliberately designed.
- **Not a cramped enterprise admin panel.** Avoid the dense-gray dashboard reflex — tiny text,
  busy toolbars, clutter. Breathing room is part of "calm."

## Design Principles

1. **Self-evident over efficient.** The audience rotates and gets no training. When a choice is
   between "fewer clicks for an expert" and "obvious for a first-timer," choose obvious. Labels,
   states, and next steps should explain themselves on the screen.
2. **Reassure relentlessly.** The read-only-original promise is the product. Make safety visible:
   say what will be written and where, confirm what was copied, and never let the UI imply the
   source could be altered.
3. **Quiet by default, loud only at the limit.** Surfaces stay calm and neutral; the rare moments
   that need attention (an album hitting the ≤10 cap, an ingest error, the build result) are where
   color and emphasis are spent. Don't spend that emphasis on chrome.
4. **State you can trust at a glance.** Which album is active, how full it is, what's selected,
   what's auto-kept, what's missing — each should be legible without hunting or counting.
5. **Green is identity, not decoration.** DLSU green signals "this is the Archers Network tool"
   and anchors primary actions. It is not a theme to drench the page in.

## Accessibility & Inclusion

- **WCAG 2.1 AA baseline.** Body text ≥4.5:1, large text ≥3:1, including placeholders and the
  green-on-surface states. Full keyboard operability for selection (tiles, album switching, build),
  visible focus rings, and `prefers-reduced-motion` alternatives for any motion.
- **Never rely on color alone.** The "album full" state and selected/unselected tiles must carry a
  non-color cue (icon, label, count, checkmark, border weight) in addition to color, for
  color-blind volunteers.
- **Legible at a glance** for infrequent users: generous tap targets on photo tiles, clear active
  states, and no tiny dense text.
