# PLAN.md — Facebook Export → PostgreSQL Preprocessing & CMS Onboarding

Working plan for ingesting this Facebook "Download Your Information" export (page: **Archers Network**, DLSU) into PostgreSQL, and a gap analysis of what a CMS will additionally need. The CMS design has **not** been shared yet, so items below are framed as *suggestions/options* — sections marked **⚠ DECISION** need confirmation against that design before building.

---

## 1. Goal & Scope

- **In scope:** Parse `posts/profile_posts_1.json` and `posts/album/*.json`, clean them, and load **media** (images) into a normalized Postgres schema. Photos are uploaded to **AWS S3** (§6); videos are **external links** (not hosted), with an S3 poster image.
- **The FB feed is separated from the website.** FB *posts are NOT stored as entities.* A post is read only transiently during ETL to (a) source its images and (b) **hoist its decoded body text into `media.caption`** (which carries the hashtags, §5). The decoded text and the deduped media are the source of truth, so §3 rule 1 (mojibake) and the `fbid` identity (§3.1) must be exact.
- **Out of scope:** the post feed itself, comments, reactions, shares received, audience/insights, author identity, drafts, and **EXIF**. The CMS supplies the rest (§7).
- **Success = ** every album and every imported image (plus each editor-curated external video) is queryable in Postgres with correct text/captions, correct timestamps, hashtags, and a working pointer to its S3 object (photos) or external URL (videos).

---

## 2. Source Inventory (what we're ingesting)

| File | Records | Shape | Becomes |
|------|---------|-------|---------|
| `posts/profile_posts_1.json` | ~85 posts | `attachments[].data[].media` + `data[].post` text | `media` (type=photo); body text → `media.caption` + hashtags. **No `posts` rows.** |
| `posts/album/0..11.json` | 12 named albums | `name` + `photos[]` | `photo_album` + `media` (type=photo) |
| `posts/videos.json` | 10 videos | `videos_v2[]` | **Out of scope** — `media` videos are editor-curated external links, not these files |
| `posts/media/` (~875 MB, thousands of files) | photos + `videos/` | binary | photo files → AWS S3 objects + `storage_path` (§6); the `videos/` files are not uploaded |

`fbid` is Facebook's record ID and is carried through as a **natural/dedup key** on `media`; for albums, **`fb_album_id` is the primary key** of `photo_album`.

---

## 3. Preprocessing Rules (must apply during ETL — these are non-obvious)

1. **Fix mojibake on every human-readable string** (`post`, `title`, `description`, `value`). Text is UTF-8 bytes re-escaped as Latin-1. Recover with `raw.encode("latin-1").decode("utf-8")`. Store the *fixed* text; optionally keep the raw in a staging column.
2. **Normalize media URIs.** They are prefixed with the export folder name, e.g. the selected line:
   `this_profile's_activity_across_facebook/posts/media/FirstDay.../1447769104031820.jpg`.
   Strip the leading `this_profile's_activity_across_facebook/` to get the real relative path (`posts/media/...`). Store both the original FB URI and the resolved storage path.
3. **Convert timestamps.** All `*_timestamp` / `timestamp` / `*_value` fields are Unix epoch **seconds** → cast to `timestamptz` (UTC). Watch for sentinel `upload_timestamp: 0` in videos (treat as NULL).
4. **Handle the two record shapes separately.** Read `label_values[]` by matching `label`, not position (labels are sparse and unordered).
5. **De-duplicate media.** The same photo can appear in both an album file and a profile post — dedup by the photo **fbid (filename stem)** so a photo is **one `media` row**. With posts excluded as entities (§3.1), this is now a straight upsert on `fbid`, not an M:N fan-in.

---

## 3.1 Duplicate & Overlap Handling (deep dive)

> **Update (posts excluded):** now that the feed is not modeled as entities, the album-vs-post
> M:N fan-in below is mostly **moot** — a photo resolves to **one `media` row** keyed by `fbid`,
> attached to at most one album via `media.fb_album_id`. Keep the **`fbid`/stem = identity** rule
> and the **idempotent, upload-once** rule; ignore the `post_media`/`album_media` M:N framing.
> (Revisit only if a photo legitimately appears in more than one album.)

**Getting the `fbid` identity right is still the most important transform.** The export overlaps album files and the profile feed, and a naive "load every record in every file" pass will double-insert media and re-upload identical files.

### What is actually duplicated (and what isn't)

Verified against the data — e.g. album `BantaySenadoLaunch` (`posts/album/1.json`) vs. the matching post in `posts/profile_posts_1.json`:

- **Metadata is duplicated.** The *same* photo record (same `uri`, same EXIF, same title) is emitted **twice** — once in the album's `photos[]` and once in the post's `attachments[].data[].media`.
- **The physical file is NOT duplicated.** Both records point at the **identical** path: `posts/media/BantaySenadoLaunch_1447745384034192/1447741280701269.jpg`. There is one file on disk, referenced from two places. So the dedup problem is about **rows and uploads**, not disk bytes.

### The keys that make dedup deterministic

- **Photo fbid = the filename stem.** `…/1447741280701269.jpg` → photo fbid `1447741280701269`. This is stable across the album copy and the post copy → it is the **dedup key for `media`**. One stem = one row.
- **Album fbid = the trailing id in the media subdirectory.** `…/media/BantaySenadoLaunch_1447745384034192/…` → album fbid `1447745384034192`. This is the **primary key of `photo_album`** (`fb_album_id`). The same photo carries this album subdir in its path whether it surfaced via the album file *or* via a profile post, so **`media.fb_album_id` is derived from the path**, not from a post. A photo whose path has no album subdir is **unanchored** (a standalone-post image → `fb_album_id` NULL).

### Algorithm

1. **Build one `media` row per photo fbid (stem).** Use a `dict` keyed by stem while parsing; first writer wins for the row, but **merge** `title`/`caption` if one copy is richer. Carry `fbid`, `original_fb_uri`, the resolved `storage_path`, and the `fb_album_id` derived from the path.
2. **No M:N needed.** With posts excluded, a photo belongs to at most one album (via `media.fb_album_id`), so there is no `post_media`/`album_media` fan-in to build — the album copy and the post copy of a photo collapse to the *same* `media` row by stem.
3. **Caption comes from the post body.** When a stem is encountered via a profile post, hoist that post's decoded body into `media.caption` (and extract hashtags, §5); the album copy contributes `title` / album membership.
4. **Union, don't assume superset.** Neither the album files nor the feed is a superset of the other: an album may contain photos never surfaced as a feed post, and a post may reference photos not in any album file. Take the **union** keyed by stem; each `media` row may be album-anchored, unanchored, or carry a hoisted caption — or any combination.

### Don'ts

- **Don't dedup on `creation_timestamp`** (or any timestamp). `creation_timestamp` is the FB *upload/processing* time and can differ slightly between the album copy and the post copy of the same photo; EXIF `taken_timestamp` is the true capture time. Only the **fbid/stem** is identity.
- **Don't upload the same file twice.** Because metadata duplicates but the file is singular, driving S3 uploads straight off "every `uri` in every JSON" will `PutObject` the same key twice. Key uploads by `storage_path`/stem and make them **idempotent** (skip if key exists, or content-address by checksum) — see §6.
- **Don't let mojibake titles drive joins.** Decode first (§3 rule 1), then match on ids.

---

## 4. Proposed Postgres Schema (sketch — adjust to CMS design)

Use a **two-stage** load: raw `staging.*` tables (one `jsonb` column per source file) → normalized `public.*` tables. Staging makes the ETL idempotent and re-runnable.

```
channel(channel_id pk, channel_name)
categories(categories_id pk, channel_id fk, category_name)

photo_album(fb_album_id pk,                                    -- Facebook album id (natural key)
            category_id fk, title, date, description)

media(media_id pk, media_type check (photo|video),
      fb_album_id fk null, category_id fk null,               -- photos anchor on album; videos on category
      title, caption, description,                             -- caption: hoisted post body (§5)
      storage_path,                                            -- S3 key: photo image / hosted video poster (§6)
      source_url,                                              -- video only: external link (click-out)
      poster_source_url,                                       -- video only: external thumbnail the poster is fetched from
      provider,                                                -- optional: youtube|tiktok|instagram|facebook
      fbid uq, original_fb_uri, creation_at timestamptz)
  -- CHECK ((media_type='photo' AND storage_path NOT NULL AND source_url NULL)
  --     OR (media_type='video' AND source_url NOT NULL))

media_contributor(media_contributor_id pk, media_id fk,
                  contributor_name, role check (contributor|collaborator))

album_contributor(album_contributor_id pk, fb_album_id fk, contributor_name)

hashtags(hashtag_id pk, tag uq, display_tag)                  -- tag: canonical lowercase
media_hashtags(media_id fk, hashtag_id fk, pk(media_id, hashtag_id))   -- M:N

users(user_id pk, username, password, is_active, last_login, created_at, updated_at)
```

Notes:
- Optionally keep a `raw jsonb` staging column per imported `media` row so nothing from the export is lost and reprocessing never needs the files again.
- Index `media.fbid` (unique), `media.fb_album_id`, `media.media_type`, and the `media_hashtags` join.
- No `posts`, `post_media`, `media_exif`, or `post_hashtags` tables — see §1 and §5.

---

## 5. Derived / Enrichment Data (cheap wins from the existing text)

- **Hashtags (in scope)** — the post bodies are heavily tagged (`#ARCH #ArchersNetwork #ARCHEVT #ARCHADS …`). Because the body is hoisted into `media.caption`, extract tags from the caption with `#[A-Za-z0-9_]+`, normalize to lowercase into `hashtags.tag` (keep original casing in `display_tag`), and link via `media_hashtags`. An album's tags = the union of its media's tags. Editors may also add curated tags through the same table.
- **Mentions / URLs** inside the caption text.
- **EXIF / photo credits — out of scope** (no `media_exif`).
- **Media type** — `media_type` (`photo`/`video`) is set directly at import, not inferred.

---

## 6. Media Storage Strategy — ✅ DECIDED: AWS S3

**Decision:** **photo** files are hosted in **AWS Cloud (Amazon S3)**, served via **CloudFront** (CDN). The DB stores **references**, never blobs. **Videos are NOT hosted** — `media.source_url` is an external link (YouTube/TikTok/IG/FB) opened on click; only a **poster image** per video lives in S3 (`media.storage_path`), fetched from the platform thumbnail recorded in `media.poster_source_url`. ~875 MB of photos is small for S3 — cost and transfer are negligible.

### Target layout & keys

- **Bucket:** one bucket (e.g. `archers-network-media`), private by default; serve through CloudFront with an Origin Access Control (no public bucket ACLs).
- **Key scheme:** mirror the resolved relative path so keys stay traceable to the export:
  `posts/media/<Album>_<albumFbid>/<photoFbid>.jpg` for photos (video posters go under a `posters/` prefix).
  Store this key in `media.storage_path`; build the public URL as `https://<cdn-domain>/<storage_path>` at read time (don't hardcode the domain in the DB).
- **Metadata:** set S3 object metadata/`Content-Type` from the file extension; optionally tag objects with `fbid` for traceability.

### Upload rules (tie-in with §3.1 dedup)

- **Upload each physical file exactly once**, keyed by `storage_path`/photo fbid. Because the same photo's metadata appears in both the album file and the profile post (§3.1), driving uploads off "every `uri` in every JSON" would `PutObject` the same key twice. Dedup the upload set by stem **first**, then upload.
- **Make uploads idempotent:** skip if the key already exists (`HeadObject`), or content-address by MD5/SHA-256 so re-runs are no-ops. This keeps Phase 3 re-runnable.
- **Preserve traceability:** keep `fbid`/original filename and the original FB `uri` on the `media` row regardless of where the bytes land.
- **Drive from JSON, verify on disk, then upload** (§9): resolve `uri` → strip the `this_profile's_activity_across_facebook/` prefix → confirm the local file exists → upload → record the S3 key. Report any `uri` with no matching local file as an orphan.

### Alternatives (rejected for this project)

- *Served static dir behind Nginx* — viable for a single-server demo, but not the AWS direction chosen.
- *DB `bytea` / large objects* — not recommended at this size/count.

---

## 7. CMS Gap Analysis — what the export *lacks* that a CMS needs

The export is a content dump, not a CMS dataset. Likely additions (confirm against the unseen design):

- **Users & roles** — authors, editors, photographers; auth & permissions. (Export has no author per post.)
- **Editorial workflow** — `status` (draft / in-review / scheduled / published / archived), `scheduled_at`, review/approval chain.
- **Taxonomy** — categories/sections (Sports, News, Events…), curated tags beyond raw hashtags.
- **Slugs / permalinks** & SEO metadata (meta title, description, OG image).
- **Media metadata for CMS** — alt text (accessibility), captions, photographer credit, usage rights.
- **Audit log** — who changed what, when.
- **Engagement / analytics** — reactions, comments, reach (must come from FB Graph API or be left as a future integration, not this export).
- **Relationships / provenance** — keep `fbid` (and `original_fb_uri`) on `media` so each imported asset is traceable back to the export and re-syncable. (No FB post entity to link to — provenance lives on `media`.)

---

## 8. Suggested Phased Roadmap

- **Phase 0 — Foundations:** finalize schema vs. CMS design; provision the AWS S3 bucket + CloudFront (§6); set up Postgres + migrations (e.g. Alembic/Prisma/Flyway per stack).
- **Phase 1 — Staging load:** dump each JSON file into `staging.*` jsonb tables, untouched. Verify counts.
- **Phase 2 — Transform:** apply §3 rules → populate `photo_album`, `media`, `media_contributor`. One `media` row per photo `fbid`; hoist each post body into `media.caption`.
- **Phase 3 — Media:** dedup the upload set by photo fbid (§3.1), upload the **photo** files in `posts/media/` to **S3** once per file (idempotent, §6), backfill `storage_path` with the S3 key, validate every `uri` resolves to a real local file before upload (report orphans/missing). Video files are not uploaded.
- **Phase 4 — Enrichment:** extract hashtags from captions into `hashtags` + `media_hashtags` (§5).
- **Phase 5 — CMS overlay:** add the §7 entities (users/roles, taxonomy, slugs, etc.); attach editor-curated **external videos** as `media` (type=video). No post→article mapping (posts are not imported).
- **Phase 6 — Validation:** row-count reconciliation, spot-check decoded text/emoji, sample media render, idempotent re-run test.

---

## 9. Implementation Notes

- **Language/tooling ⚠ DECISION:** Python (`json`, `psycopg`/SQLAlchemy) is the natural fit and matches the decode/parse work; confirm it aligns with the CMS backend stack.
- **Idempotency:** upsert on `fbid` so re-running the ETL never duplicates rows; make S3 uploads idempotent by key/checksum (§6) so re-running media never re-uploads.
- **AWS client:** use `boto3` for S3 uploads; read credentials from the standard AWS env/role chain (never hardcode keys in the ETL).
- **Do not enumerate `posts/media/`** to drive ingestion — drive it from the `uri` fields in JSON, then verify those specific files exist.
- **Validation harness:** assert `len(json)` == loaded row count per file before declaring a phase done.

---

## 10. Open Questions (need the CMS design / stakeholder input)

1. ~~Is the imported FB post the canonical content?~~ **✅ SUPERSEDED: posts are NOT reflected on the website.** The FB feed is separated from the site (§1). Posts are not stored as entities; a post is read only to source its images and to hoist its body into `media.caption` (which carries hashtags, §5). Canonical website content is **albums + media**; getting mojibake (§3 rule 1) and the `fbid` identity (§3.1) right is still non-negotiable since the decoded caption text is the source of truth and there is no post row to fall back on.
2. Media hosting target? (§6)
3. Backend stack & migration tool? (§9)
4. Is this a one-time import, or should it **re-sync** with Facebook later (Graph API)? Re-sync changes how aggressively we lean on `fbid`.
5. Required taxonomy/sections and the author/role model — these come straight from the CMS design.
6. Are reactions/comments/insights in-scope for a later phase (separate data source needed)?
