# Streamlinify — FB Export Curation Tool — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local, single-user FastAPI (uv) web tool that turns a weekly Facebook export into a curated, filtered "ready-to-upload" folder.

**Architecture:** One uv-managed Python package, modularized per functionality — `ingest` (unzip/validate), `inventory` (parse + decode + classify), `thumbnails` (Pillow cache), `selection` (≤10/album policy + persisted state), `transform` (build filtered mirror), `web` (Jinja2 + Alpine routes). Business logic lives in the modules; routes are thin. Everything drives off the export JSON — the `posts/media/` tree is never globbed.

**Tech Stack:** Python 3.12+, uv, FastAPI, Uvicorn, Jinja2, Alpine.js (CDN), Pillow, pydantic / pydantic-settings, pytest + httpx, ruff.

**Reference spec:** `docs/superpowers/specs/2026-06-28-streamlinify-curation-tool-design.md`

## Global Constraints

- **Python** `>=3.12`. All commands run through **uv** (`uv run …`) — the bare `python` here is a broken shim.
- **Dependencies (runtime):** `fastapi`, `uvicorn[standard]`, `jinja2`, `python-multipart`, `pydantic-settings`, `pillow`. **Dev:** `pytest`, `httpx`, `ruff`.
- **Layout:** `src/streamlinify/` package (src layout); tests in `tests/`.
- **Mojibake rule:** decode every human-readable string with `raw.encode("latin-1").decode("utf-8")`, falling back to the raw string on failure.
- **URI rule:** media `uri` values are prefixed with the export folder name; resolve by taking the substring from `posts/` onward, joined to the export root.
- **Identity:** photo fbid = filename stem; album fbid = trailing id (after last `_`) of the media subdirectory.
- **Never enumerate `posts/media/`** — drive off JSON, then verify the specific referenced file exists.
- **Cap:** ≤ `MAX_PER_ALBUM` (10) per **named** album, enforced **server-side**. Non-album photos are auto-kept (Decision B; behind a swappable policy).
- **Output:** filtered mirror under `ready/<export-name>/`; the **original export is read-only**, never written.
- **Single-user, localhost only.** No auth, no deployment concerns.
- **Commit after every task.** Use `git add <specific files>`.

---

### Task 1: Project scaffold + config

**Files:**
- Create: `pyproject.toml`
- Create: `src/streamlinify/__init__.py` (empty)
- Create: `src/streamlinify/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `streamlinify.config.Settings` (pydantic-settings) and module-level `settings: Settings` with `max_per_album: int = 10`, `thumb_size: int = 256`, `workspace_dir: Path`, `host: str`, `port: int`.

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[project]
name = "streamlinify"
version = "0.1.0"
description = "Local FastAPI tool to curate Facebook exports for Archers Network"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "jinja2>=3.1",
    "python-multipart>=0.0.9",
    "pydantic-settings>=2.4",
    "pillow>=10.4",
]

[project.scripts]
streamlinify = "streamlinify.main:run"

[dependency-groups]
dev = ["pytest>=8", "httpx>=0.27", "ruff>=0.6"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/streamlinify"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]

[tool.ruff]
line-length = 100
```

- [ ] **Step 2: Create the package marker**

Create empty file `src/streamlinify/__init__.py`.

- [ ] **Step 3: Write the failing test**

```python
# tests/test_config.py
from streamlinify.config import Settings, settings


def test_defaults():
    assert settings.max_per_album == 10
    assert settings.thumb_size == 256


def test_env_override(monkeypatch):
    monkeypatch.setenv("STREAMLINIFY_MAX_PER_ALBUM", "5")
    assert Settings().max_per_album == 5
```

- [ ] **Step 4: Run test to verify it fails**

Run: `uv run pytest tests/test_config.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'streamlinify.config'`

- [ ] **Step 5: Write `src/streamlinify/config.py`**

```python
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="STREAMLINIFY_")

    workspace_dir: Path = Path("workspace")
    max_per_album: int = 10
    thumb_size: int = 256
    host: str = "127.0.0.1"
    port: int = 8000


settings = Settings()
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_config.py -q`
Expected: PASS (2 passed). `uv` auto-syncs deps on first run.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml uv.lock src/streamlinify/__init__.py src/streamlinify/config.py tests/test_config.py
git commit -m "feat: uv project scaffold + typed settings"
```

---

### Task 2: Text helpers (mojibake, hashtags, timestamps)

**Files:**
- Create: `src/streamlinify/inventory/__init__.py` (empty)
- Create: `src/streamlinify/inventory/text.py`
- Test: `tests/inventory/test_text.py`

**Interfaces:**
- Produces: `fix_mojibake(s: str) -> str`, `extract_hashtags(s: str) -> list[str]`, `epoch_to_dt(n: int) -> datetime`.

- [ ] **Step 1: Write the failing test**

```python
# tests/inventory/test_text.py
from datetime import datetime, timezone

from streamlinify.inventory.text import epoch_to_dt, extract_hashtags, fix_mojibake


def test_fix_mojibake_recovers_utf8():
    # "café" UTF-8 bytes re-escaped as latin-1 renders as "cafÃ©"
    assert fix_mojibake("cafÃ©") == "café"


def test_fix_mojibake_passthrough_on_plain_ascii():
    assert fix_mojibake("hello") == "hello"


def test_extract_hashtags():
    assert extract_hashtags("game! #ARCH #ArchersNetwork done") == ["#ARCH", "#ArchersNetwork"]


def test_epoch_to_dt_is_utc():
    assert epoch_to_dt(0) == datetime(1970, 1, 1, tzinfo=timezone.utc)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/inventory/test_text.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'streamlinify.inventory'`

- [ ] **Step 3: Create `src/streamlinify/inventory/__init__.py`** (empty file)

- [ ] **Step 4: Write `src/streamlinify/inventory/text.py`**

```python
import re
from datetime import datetime, timezone

_HASHTAG_RE = re.compile(r"#[A-Za-z0-9_]+")


def fix_mojibake(s: str) -> str:
    """Recover UTF-8 text that was re-escaped as Latin-1 in the FB export."""
    if not s:
        return s
    try:
        return s.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s


def extract_hashtags(s: str) -> list[str]:
    return _HASHTAG_RE.findall(s or "")


def epoch_to_dt(n: int) -> datetime:
    return datetime.fromtimestamp(n, tz=timezone.utc)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/inventory/test_text.py -q`
Expected: PASS (4 passed)

- [ ] **Step 6: Commit**

```bash
git add src/streamlinify/inventory/__init__.py src/streamlinify/inventory/text.py tests/inventory/test_text.py
git commit -m "feat: text helpers for mojibake, hashtags, timestamps"
```

---

### Task 3: Inventory domain models

**Files:**
- Create: `src/streamlinify/inventory/models.py`
- Test: `tests/inventory/test_models.py`

**Interfaces:**
- Produces:
  - `Photo(fbid: str, original_uri: str, resolved_path: Path, title: str | None, caption: str | None, creation_at: datetime | None, album_fbid: str | None, exists: bool)` with property `is_non_album -> bool`.
  - `Album(fb_album_id: str, name: str, photos: list[Photo])`.
  - `ExportInventory(albums: list[Album], non_album_photos: list[Photo])` with `all_photos() -> list[Photo]` and `photo_by_fbid(fbid) -> Photo | None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/inventory/test_models.py
from pathlib import Path

from streamlinify.inventory.models import Album, ExportInventory, Photo


def _photo(fbid, album_fbid=None):
    return Photo(
        fbid=fbid,
        original_uri=f"exp/posts/media/x/{fbid}.jpg",
        resolved_path=Path(f"posts/media/x/{fbid}.jpg"),
        album_fbid=album_fbid,
    )


def test_is_non_album():
    assert _photo("a").is_non_album is True
    assert _photo("b", album_fbid="111").is_non_album is False


def test_lookup_helpers():
    inv = ExportInventory(
        albums=[Album(fb_album_id="111", name="A", photos=[_photo("p1", "111")])],
        non_album_photos=[_photo("p2")],
    )
    assert {p.fbid for p in inv.all_photos()} == {"p1", "p2"}
    assert inv.photo_by_fbid("p2").fbid == "p2"
    assert inv.photo_by_fbid("nope") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/inventory/test_models.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'streamlinify.inventory.models'`

- [ ] **Step 3: Write `src/streamlinify/inventory/models.py`**

```python
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel


class Photo(BaseModel):
    fbid: str
    original_uri: str
    resolved_path: Path
    title: str | None = None
    caption: str | None = None
    creation_at: datetime | None = None
    album_fbid: str | None = None
    exists: bool = True  # False when the referenced file is missing on disk (orphan)

    @property
    def is_non_album(self) -> bool:
        return self.album_fbid is None


class Album(BaseModel):
    fb_album_id: str
    name: str
    photos: list[Photo] = []


class ExportInventory(BaseModel):
    albums: list[Album] = []
    non_album_photos: list[Photo] = []

    def all_photos(self) -> list[Photo]:
        out: list[Photo] = [p for a in self.albums for p in a.photos]
        out.extend(self.non_album_photos)
        return out

    def photo_by_fbid(self, fbid: str) -> Photo | None:
        for p in self.all_photos():
            if p.fbid == fbid:
                return p
        return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/inventory/test_models.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/streamlinify/inventory/models.py tests/inventory/test_models.py
git commit -m "feat: inventory domain models (Photo, Album, ExportInventory)"
```

---

### Task 4: Synthetic fixture export (test infrastructure)

Builds a tiny, fully-controlled FB export under a temp dir so every later test has known counts. **Numbers other tasks rely on:** 2 albums; album `111` "Animo Fest" with 12 photos (`a01`–`a12`, all files present); album `222` "Café Night" (stored mojibake) with 2 photos (`b01`,`b02`); non-album photos `m01` (file present) and `m02` (file **missing** → orphan); 4 unnecessary JSONs present.

**Files:**
- Create: `tests/conftest.py`
- Create: `tests/test_fixture.py`

**Interfaces:**
- Produces pytest fixture `export_root(tmp_path) -> Path` — the root of a synthetic export (contains `posts/`).

- [ ] **Step 1: Write `tests/conftest.py`**

```python
import json
from pathlib import Path

import pytest
from PIL import Image

PREFIX = "this_profile's_activity_across_facebook"


def _img(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (4, 4), (120, 30, 30)).save(path, "JPEG")


def _photo_record(album_dir: str, fbid: str, title: str) -> dict:
    return {
        "uri": f"{PREFIX}/posts/media/{album_dir}/{fbid}.jpg",
        "creation_timestamp": 1_700_000_000,
        "title": title,
    }


@pytest.fixture
def export_root(tmp_path: Path) -> Path:
    root = tmp_path / "export"
    media = root / "posts" / "media"
    album_dir = root / "posts" / "album"
    album_dir.mkdir(parents=True)

    # Album 111 "Animo Fest": 12 photos, all files present
    a_photos = [_photo_record("AnimoFest_111", f"a{n:02d}", f"Photo {n}") for n in range(1, 13)]
    (album_dir / "0.json").write_text(
        json.dumps({"name": "Animo Fest", "photos": a_photos}), encoding="utf-8"
    )
    for n in range(1, 13):
        _img(media / "AnimoFest_111" / f"a{n:02d}.jpg")

    # Album 222 "Café Night" stored as mojibake; 2 photos
    b_photos = [_photo_record("CafeNight_222", f"b{n:02d}", f"B {n}") for n in range(1, 3)]
    (album_dir / "1.json").write_text(
        json.dumps({"name": "CafÃ© Night", "photos": b_photos}), encoding="utf-8"
    )
    for n in range(1, 3):
        _img(media / "CafeNight_222" / f"b{n:02d}.jpg")

    # profile_posts: post1 captions a01/a02; post2 references non-album m01 (present) + m02 (orphan)
    posts = [
        {
            "data": [{"post": "Great game today! #ARCH #Animo"}],
            "attachments": [
                {"data": [{"media": _photo_record("AnimoFest_111", "a01", "Photo 1")}]},
                {"data": [{"media": _photo_record("AnimoFest_111", "a02", "Photo 2")}]},
            ],
        },
        {
            "data": [{"post": "Mobile dump #Random"}],
            "attachments": [
                {"data": [{"media": _photo_record("Mobileuploads_999", "m01", "Mobile 1")}]},
                {"data": [{"media": _photo_record("Mobileuploads_999", "m02", "Mobile 2")}]},
            ],
        },
    ]
    (root / "posts" / "profile_posts_1.json").write_text(
        json.dumps(posts), encoding="utf-8"
    )
    _img(media / "Mobileuploads_999" / "m01.jpg")
    # NOTE: m02.jpg deliberately NOT created → orphan

    # Unnecessary JSONs that must be dropped from the ready output
    for name in (
        "videos.json",
        "content_sharing_links_you_have_created.json",
        "edits_you_made_to_posts.json",
        "places_you_have_been_tagged_in.json",
    ):
        (root / "posts" / name).write_text("[]", encoding="utf-8")

    return root
```

- [ ] **Step 2: Write `tests/test_fixture.py` (verifies the fixture itself)**

```python
from pathlib import Path


def test_fixture_shape(export_root: Path):
    assert (export_root / "posts" / "album" / "0.json").exists()
    assert (export_root / "posts" / "profile_posts_1.json").exists()
    assert (export_root / "posts" / "media" / "AnimoFest_111" / "a12.jpg").exists()
    assert not (export_root / "posts" / "media" / "Mobileuploads_999" / "m02.jpg").exists()
    assert (export_root / "posts" / "videos.json").exists()
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `uv run pytest tests/test_fixture.py -q`
Expected: PASS (1 passed)

- [ ] **Step 4: Commit**

```bash
git add tests/conftest.py tests/test_fixture.py
git commit -m "test: synthetic FB export fixture"
```

---

### Task 5: Export structure validation

**Files:**
- Create: `src/streamlinify/ingest/__init__.py` (empty)
- Create: `src/streamlinify/ingest/validate.py`
- Test: `tests/ingest/test_validate.py`

**Interfaces:**
- Produces: `ValidationReport(ok: bool, missing: list[str], root: Path)` (dataclass); `validate_export(folder: Path) -> ValidationReport`; `find_export_root(folder: Path) -> Path` (descends one level if `posts/` isn't at the top).

- [ ] **Step 1: Write the failing test**

```python
# tests/ingest/test_validate.py
from pathlib import Path

from streamlinify.ingest.validate import find_export_root, validate_export


def test_valid_export(export_root: Path):
    report = validate_export(export_root)
    assert report.ok is True
    assert report.missing == []


def test_missing_pieces(tmp_path: Path):
    report = validate_export(tmp_path)
    assert report.ok is False
    assert "posts/profile_posts_1.json" in report.missing


def test_find_export_root_descends(export_root: Path):
    parent = export_root.parent  # contains the "export" subfolder
    assert find_export_root(parent) == export_root
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/ingest/test_validate.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'streamlinify.ingest'`

- [ ] **Step 3: Create `src/streamlinify/ingest/__init__.py`** (empty file)

- [ ] **Step 4: Write `src/streamlinify/ingest/validate.py`**

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

REQUIRED = ["posts", "posts/album", "posts/media", "posts/profile_posts_1.json"]


@dataclass
class ValidationReport:
    ok: bool
    missing: list[str]
    root: Path


def validate_export(folder: Path) -> ValidationReport:
    missing = [rel for rel in REQUIRED if not (folder / rel).exists()]
    return ValidationReport(ok=not missing, missing=missing, root=folder)


def find_export_root(folder: Path) -> Path:
    """Return the folder that directly contains `posts/`, descending one level if needed."""
    if (folder / "posts").exists():
        return folder
    for child in sorted(p for p in folder.iterdir() if p.is_dir()):
        if (child / "posts").exists():
            return child
    return folder
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/ingest/test_validate.py -q`
Expected: PASS (3 passed)

- [ ] **Step 6: Commit**

```bash
git add src/streamlinify/ingest/__init__.py src/streamlinify/ingest/validate.py tests/ingest/test_validate.py
git commit -m "feat: export structure validation + root discovery"
```

---

### Task 6: Safe zip extraction

**Files:**
- Create: `src/streamlinify/ingest/unzip.py`
- Test: `tests/ingest/test_unzip.py`

**Interfaces:**
- Produces: `extract_zip(zip_path: Path, dest: Path) -> Path` — extracts to `dest`, raising `ValueError` on any entry that escapes `dest` (zip-slip).

- [ ] **Step 1: Write the failing test**

```python
# tests/ingest/test_unzip.py
import zipfile
from pathlib import Path

import pytest

from streamlinify.ingest.unzip import extract_zip


def _make_zip(path: Path, entries: dict[str, str]) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in entries.items():
            zf.writestr(name, data)


def test_extracts_files(tmp_path: Path):
    zip_path = tmp_path / "x.zip"
    _make_zip(zip_path, {"posts/profile_posts_1.json": "[]"})
    dest = tmp_path / "out"
    extract_zip(zip_path, dest)
    assert (dest / "posts" / "profile_posts_1.json").read_text() == "[]"


def test_rejects_zip_slip(tmp_path: Path):
    zip_path = tmp_path / "evil.zip"
    _make_zip(zip_path, {"../evil.txt": "pwn"})
    with pytest.raises(ValueError):
        extract_zip(zip_path, tmp_path / "out")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/ingest/test_unzip.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'streamlinify.ingest.unzip'`

- [ ] **Step 3: Write `src/streamlinify/ingest/unzip.py`**

```python
from __future__ import annotations

import zipfile
from pathlib import Path


def extract_zip(zip_path: Path, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    dest_resolved = dest.resolve()
    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.namelist():
            target = (dest / member).resolve()
            if dest_resolved not in target.parents and target != dest_resolved:
                raise ValueError(f"Unsafe path in zip (zip-slip): {member}")
        zf.extractall(dest)
    return dest
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/ingest/test_unzip.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/streamlinify/ingest/unzip.py tests/ingest/test_unzip.py
git commit -m "feat: zip-slip-safe extraction"
```

---

### Task 7: Export parser (URIs, classification, captions)

**Files:**
- Create: `src/streamlinify/inventory/parser.py`
- Test: `tests/inventory/test_parser.py`

**Interfaces:**
- Consumes: `inventory.models`, `inventory.text`.
- Produces:
  - `resolve_uri(uri: str, export_root: Path) -> Path`
  - `photo_fbid(uri: str) -> str`
  - `album_id_from_uri(uri: str) -> str | None`
  - `build_inventory(export_root: Path) -> ExportInventory`

- [ ] **Step 1: Write the failing test**

```python
# tests/inventory/test_parser.py
from pathlib import Path

from streamlinify.inventory.parser import (
    album_id_from_uri,
    build_inventory,
    photo_fbid,
    resolve_uri,
)

PREFIX = "this_profile's_activity_across_facebook"


def test_helpers(export_root: Path):
    uri = f"{PREFIX}/posts/media/AnimoFest_111/a01.jpg"
    assert photo_fbid(uri) == "a01"
    assert album_id_from_uri(uri) == "111"
    assert resolve_uri(uri, export_root) == export_root / "posts/media/AnimoFest_111/a01.jpg"


def test_build_inventory(export_root: Path):
    inv = build_inventory(export_root)

    by_id = {a.fb_album_id: a for a in inv.albums}
    assert set(by_id) == {"111", "222"}
    assert by_id["111"].name == "Animo Fest"
    assert len(by_id["111"].photos) == 12
    assert by_id["222"].name == "Café Night"  # mojibake decoded

    # caption hoisted from the post body onto album photos a01/a02
    a01 = next(p for p in by_id["111"].photos if p.fbid == "a01")
    assert a01.caption == "Great game today! #ARCH #Animo"

    # non-album photos: m01 (present) and m02 (orphan)
    nonalbum = {p.fbid: p for p in inv.non_album_photos}
    assert set(nonalbum) == {"m01", "m02"}
    assert nonalbum["m01"].exists is True
    assert nonalbum["m02"].exists is False
    assert nonalbum["m01"].album_fbid is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/inventory/test_parser.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'streamlinify.inventory.parser'`

- [ ] **Step 3: Write `src/streamlinify/inventory/parser.py`**

```python
from __future__ import annotations

import json
from pathlib import Path

from .models import Album, ExportInventory, Photo
from .text import epoch_to_dt, fix_mojibake


def resolve_uri(uri: str, export_root: Path) -> Path:
    idx = uri.find("posts/")
    rel = uri[idx:] if idx != -1 else uri
    return export_root / rel


def photo_fbid(uri: str) -> str:
    return Path(uri).stem


def album_id_from_uri(uri: str) -> str | None:
    parent = Path(uri).parent.name  # e.g. "AnimoFest_111"
    if "_" not in parent:
        return None
    tail = parent.rsplit("_", 1)[1]
    return tail or None


def _post_media_records(export_root: Path) -> list[dict]:
    """Flatten profile_posts into {uri, title, caption, creation_timestamp} dicts."""
    path = export_root / "posts" / "profile_posts_1.json"
    if not path.exists():
        return []
    posts = json.loads(path.read_text(encoding="utf-8"))
    records: list[dict] = []
    for post in posts:
        body = ""
        for d in post.get("data", []):
            if "post" in d:
                body = fix_mojibake(d["post"])
        for att in post.get("attachments", []):
            for d in att.get("data", []):
                media = d.get("media")
                if not media or "uri" not in media:
                    continue
                records.append(
                    {
                        "uri": media["uri"],
                        "title": fix_mojibake(media.get("title", "")),
                        "caption": body,
                        "creation_timestamp": media.get("creation_timestamp"),
                    }
                )
    return records


def build_inventory(export_root: Path) -> ExportInventory:
    post_records = _post_media_records(export_root)
    caption_map = {photo_fbid(r["uri"]): r["caption"] for r in post_records if r["caption"]}

    albums: list[Album] = []
    album_fbids: set[str] = set()
    for album_path in sorted((export_root / "posts" / "album").glob("*.json")):
        raw = json.loads(album_path.read_text(encoding="utf-8"))
        photos: list[Photo] = []
        derived_album_id: str | None = None
        for rec in raw.get("photos", []):
            uri = rec["uri"]
            fbid = photo_fbid(uri)
            album_id = album_id_from_uri(uri)
            derived_album_id = derived_album_id or album_id
            resolved = resolve_uri(uri, export_root)
            ts = rec.get("creation_timestamp")
            photos.append(
                Photo(
                    fbid=fbid,
                    original_uri=uri,
                    resolved_path=resolved,
                    title=fix_mojibake(rec.get("title", "")),
                    caption=caption_map.get(fbid),
                    creation_at=epoch_to_dt(ts) if ts else None,
                    album_fbid=album_id,
                    exists=resolved.exists(),
                )
            )
            album_fbids.add(fbid)
        albums.append(
            Album(
                fb_album_id=derived_album_id or album_path.stem,
                name=fix_mojibake(raw.get("name", album_path.stem)),
                photos=photos,
            )
        )

    # Non-album photos = post media whose fbid is not in any album file (dedup by fbid).
    non_album: list[Photo] = []
    seen: set[str] = set()
    for r in post_records:
        fbid = photo_fbid(r["uri"])
        if fbid in album_fbids or fbid in seen:
            continue
        seen.add(fbid)
        resolved = resolve_uri(r["uri"], export_root)
        ts = r.get("creation_timestamp")
        non_album.append(
            Photo(
                fbid=fbid,
                original_uri=r["uri"],
                resolved_path=resolved,
                title=r["title"],
                caption=r["caption"] or None,
                creation_at=epoch_to_dt(ts) if ts else None,
                album_fbid=None,
                exists=resolved.exists(),
            )
        )

    return ExportInventory(albums=albums, non_album_photos=non_album)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/inventory/test_parser.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/streamlinify/inventory/parser.py tests/inventory/test_parser.py
git commit -m "feat: export parser with URI resolution, classification, caption hoisting"
```

---

### Task 8: Thumbnail service

**Files:**
- Create: `src/streamlinify/thumbnails/__init__.py` (empty)
- Create: `src/streamlinify/thumbnails/service.py`
- Test: `tests/thumbnails/test_service.py`

**Interfaces:**
- Consumes: `config.settings`.
- Produces: `ThumbnailService(cache_dir: Path, size: int = settings.thumb_size)` with `thumbnail_path(fbid: str, source: Path) -> Path` (lazy-generates + caches a JPEG; bounded to `size`).

- [ ] **Step 1: Write the failing test**

```python
# tests/thumbnails/test_service.py
from pathlib import Path

from PIL import Image

from streamlinify.thumbnails.service import ThumbnailService


def _make_image(path: Path, w: int, h: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (w, h), (10, 80, 160)).save(path, "JPEG")


def test_generates_bounded_thumbnail(tmp_path: Path):
    src = tmp_path / "src" / "big.jpg"
    _make_image(src, 400, 200)
    svc = ThumbnailService(cache_dir=tmp_path / "cache", size=64)

    out = svc.thumbnail_path("big", src)
    assert out.exists()
    with Image.open(out) as im:
        assert max(im.size) <= 64


def test_caches_second_call(tmp_path: Path):
    src = tmp_path / "src" / "big.jpg"
    _make_image(src, 400, 200)
    svc = ThumbnailService(cache_dir=tmp_path / "cache", size=64)

    out1 = svc.thumbnail_path("big", src)
    mtime = out1.stat().st_mtime_ns
    out2 = svc.thumbnail_path("big", src)
    assert out2 == out1
    assert out2.stat().st_mtime_ns == mtime  # not regenerated
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/thumbnails/test_service.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'streamlinify.thumbnails'`

- [ ] **Step 3: Create `src/streamlinify/thumbnails/__init__.py`** (empty file)

- [ ] **Step 4: Write `src/streamlinify/thumbnails/service.py`**

```python
from __future__ import annotations

from pathlib import Path

from PIL import Image

from ..config import settings


class ThumbnailService:
    def __init__(self, cache_dir: Path, size: int | None = None) -> None:
        self.cache_dir = cache_dir
        self.size = size or settings.thumb_size
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def thumbnail_path(self, fbid: str, source: Path) -> Path:
        out = self.cache_dir / f"{fbid}_{self.size}.jpg"
        if out.exists():
            return out
        with Image.open(source) as im:
            im = im.convert("RGB")
            im.thumbnail((self.size, self.size))
            im.save(out, "JPEG", quality=80)
        return out
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/thumbnails/test_service.py -q`
Expected: PASS (2 passed)

- [ ] **Step 6: Commit**

```bash
git add src/streamlinify/thumbnails/__init__.py src/streamlinify/thumbnails/service.py tests/thumbnails/test_service.py
git commit -m "feat: Pillow thumbnail service with on-disk cache"
```

---

### Task 9: Selection policy

**Files:**
- Create: `src/streamlinify/selection/__init__.py` (empty)
- Create: `src/streamlinify/selection/policy.py`
- Test: `tests/selection/test_policy.py`

**Interfaces:**
- Consumes: `config.settings`.
- Produces:
  - `SelectionPolicy` (typing.Protocol): `can_select(album_fbid: str, current_count: int) -> bool`, `non_album_selectable() -> bool`.
  - `DefaultPolicy(max_per_album: int = settings.max_per_album)` implementing it (Decision B: `non_album_selectable()` returns `False`).
  - `CapExceeded(Exception)` with attribute `album_fbid`.

- [ ] **Step 1: Write the failing test**

```python
# tests/selection/test_policy.py
from streamlinify.selection.policy import DefaultPolicy


def test_cap_enforced_at_max():
    policy = DefaultPolicy(max_per_album=3)
    assert policy.can_select("111", 2) is True
    assert policy.can_select("111", 3) is False


def test_non_album_not_selectable_by_default():
    assert DefaultPolicy().non_album_selectable() is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/selection/test_policy.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'streamlinify.selection'`

- [ ] **Step 3: Create `src/streamlinify/selection/__init__.py`** (empty file)

- [ ] **Step 4: Write `src/streamlinify/selection/policy.py`**

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..config import settings


class CapExceeded(Exception):
    def __init__(self, album_fbid: str) -> None:
        super().__init__(f"album {album_fbid} is at its selection cap")
        self.album_fbid = album_fbid


class SelectionPolicy(Protocol):
    def can_select(self, album_fbid: str, current_count: int) -> bool: ...
    def non_album_selectable(self) -> bool: ...


@dataclass
class DefaultPolicy:
    """Named-album cap; non-album photos are auto-kept and not pickable (Decision B).

    To make non-album photos deselectable later, add a sibling policy whose
    `non_album_selectable()` returns True — no change to SelectionState needed.
    """

    max_per_album: int = settings.max_per_album

    def can_select(self, album_fbid: str, current_count: int) -> bool:
        return current_count < self.max_per_album

    def non_album_selectable(self) -> bool:
        return False
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/selection/test_policy.py -q`
Expected: PASS (2 passed)

- [ ] **Step 6: Commit**

```bash
git add src/streamlinify/selection/__init__.py src/streamlinify/selection/policy.py tests/selection/test_policy.py
git commit -m "feat: selection policy (named-album cap, swappable non-album rule)"
```

---

### Task 10: Selection state (persistence + cap enforcement)

**Files:**
- Create: `src/streamlinify/selection/state.py`
- Test: `tests/selection/test_state.py`

**Interfaces:**
- Consumes: `selection.policy` (`SelectionPolicy`, `DefaultPolicy`, `CapExceeded`).
- Produces: `SelectionState(path: Path, policy: SelectionPolicy)` with `toggle(album_fbid, photo_fbid) -> bool` (raises `CapExceeded`), `is_selected(album_fbid, photo_fbid) -> bool`, `count(album_fbid) -> int`, `selected_fbids() -> set[str]`. Persists to `path` (JSON) after every change.

- [ ] **Step 1: Write the failing test**

```python
# tests/selection/test_state.py
from pathlib import Path

import pytest

from streamlinify.selection.policy import CapExceeded, DefaultPolicy
from streamlinify.selection.state import SelectionState


def test_toggle_and_count(tmp_path: Path):
    st = SelectionState(tmp_path / "sel.json", DefaultPolicy())
    assert st.toggle("111", "a01") is True
    assert st.is_selected("111", "a01") is True
    assert st.count("111") == 1
    assert st.toggle("111", "a01") is False  # toggled off
    assert st.count("111") == 0


def test_cap_enforced(tmp_path: Path):
    st = SelectionState(tmp_path / "sel.json", DefaultPolicy(max_per_album=2))
    st.toggle("111", "a01")
    st.toggle("111", "a02")
    with pytest.raises(CapExceeded):
        st.toggle("111", "a03")


def test_persistence_round_trip(tmp_path: Path):
    path = tmp_path / "sel.json"
    st = SelectionState(path, DefaultPolicy())
    st.toggle("111", "a01")
    st.toggle("222", "b01")

    reloaded = SelectionState(path, DefaultPolicy())
    assert reloaded.selected_fbids() == {"a01", "b01"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/selection/test_state.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'streamlinify.selection.state'`

- [ ] **Step 3: Write `src/streamlinify/selection/state.py`**

```python
from __future__ import annotations

import json
from pathlib import Path

from .policy import CapExceeded, SelectionPolicy


class SelectionState:
    def __init__(self, path: Path, policy: SelectionPolicy) -> None:
        self.path = path
        self.policy = policy
        self._selected: dict[str, set[str]] = {}
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self._selected = {k: set(v) for k, v in data.items()}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {k: sorted(v) for k, v in self._selected.items() if v}
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def toggle(self, album_fbid: str, photo_fbid: str) -> bool:
        sel = self._selected.setdefault(album_fbid, set())
        if photo_fbid in sel:
            sel.remove(photo_fbid)
            self._save()
            return False
        if not self.policy.can_select(album_fbid, len(sel)):
            raise CapExceeded(album_fbid)
        sel.add(photo_fbid)
        self._save()
        return True

    def is_selected(self, album_fbid: str, photo_fbid: str) -> bool:
        return photo_fbid in self._selected.get(album_fbid, set())

    def count(self, album_fbid: str) -> int:
        return len(self._selected.get(album_fbid, set()))

    def selected_fbids(self) -> set[str]:
        out: set[str] = set()
        for fbids in self._selected.values():
            out |= fbids
        return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/selection/test_state.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/streamlinify/selection/state.py tests/selection/test_state.py
git commit -m "feat: persisted selection state with server-side cap"
```

---

### Task 11: Transform — build the filtered "ready" folder + report

**Files:**
- Create: `src/streamlinify/transform/__init__.py` (empty)
- Create: `src/streamlinify/transform/builder.py`
- Create: `src/streamlinify/transform/report.py`
- Test: `tests/transform/test_builder.py`

**Interfaces:**
- Consumes: `inventory.parser.build_inventory`, `inventory.parser.photo_fbid`.
- Produces:
  - `BuildResult(ready_root: Path, copied: int, albums_written: int, orphans: list[str])` (dataclass).
  - `build_ready_folder(export_root: Path, dest: Path, keep_fbids: set[str]) -> BuildResult` — copies kept media that exist on disk, rewrites each `album/*.json` to kept photos (skipping albums with 0 kept), filters `profile_posts_1.json` to kept media that exist, drops unnecessary JSONs, never writes the original.
  - `format_summary(result: BuildResult) -> str`.

- [ ] **Step 1: Write the failing test**

```python
# tests/transform/test_builder.py
import json
from pathlib import Path

from streamlinify.transform.builder import build_ready_folder


def test_build_filtered_mirror(export_root: Path, tmp_path: Path):
    dest = tmp_path / "ready"
    # keep 2 album-111 photos + both non-album (m01 present, m02 orphan)
    keep = {"a01", "a02", "m01", "m02"}
    result = build_ready_folder(export_root, dest, keep)

    # album 0 rewritten to exactly the 2 kept photos
    album0 = json.loads((dest / "posts" / "album" / "0.json").read_text(encoding="utf-8"))
    assert {Path(p["uri"]).stem for p in album0["photos"]} == {"a01", "a02"}

    # album 1 had 0 kept photos → not written
    assert not (dest / "posts" / "album" / "1.json").exists()

    # media copied for present files only; m02 is an orphan
    assert (dest / "posts" / "media" / "AnimoFest_111" / "a01.jpg").exists()
    assert (dest / "posts" / "media" / "Mobileuploads_999" / "m01.jpg").exists()
    assert not (dest / "posts" / "media" / "Mobileuploads_999" / "m02.jpg").exists()
    assert result.copied == 3
    assert any("m02" in o for o in result.orphans)

    # unnecessary JSONs dropped
    assert not (dest / "posts" / "videos.json").exists()

    # profile_posts filtered to kept + present media
    posts = json.loads((dest / "posts" / "profile_posts_1.json").read_text(encoding="utf-8"))
    kept_uris = {
        Path(d["media"]["uri"]).stem
        for post in posts
        for att in post.get("attachments", [])
        for d in att.get("data", [])
    }
    assert kept_uris == {"a01", "a02", "m01"}

    # original untouched
    assert (export_root / "posts" / "videos.json").exists()


def test_idempotent_rerun(export_root: Path, tmp_path: Path):
    dest = tmp_path / "ready"
    build_ready_folder(export_root, dest, {"a01"})
    result = build_ready_folder(export_root, dest, {"a01"})
    assert result.copied == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/transform/test_builder.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'streamlinify.transform'`

- [ ] **Step 3: Create `src/streamlinify/transform/__init__.py`** (empty file)

- [ ] **Step 4: Write `src/streamlinify/transform/builder.py`**

```python
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from ..inventory.parser import build_inventory, photo_fbid, resolve_uri

DROP_JSON = {
    "videos.json",
    "content_sharing_links_you_have_created.json",
    "edits_you_made_to_posts.json",
    "places_you_have_been_tagged_in.json",
}


@dataclass
class BuildResult:
    ready_root: Path
    copied: int
    albums_written: int
    orphans: list[str]


def _copy_media(uri: str, export_root: Path, dest: Path) -> bool:
    src = resolve_uri(uri, export_root)
    if not src.exists():
        return False
    idx = uri.find("posts/")
    rel = uri[idx:] if idx != -1 else uri
    target = dest / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, target)
    return True


def build_ready_folder(export_root: Path, dest: Path, keep_fbids: set[str]) -> BuildResult:
    inventory = build_inventory(export_root)
    dest.mkdir(parents=True, exist_ok=True)

    copied = 0
    orphans: list[str] = []

    # Copy kept media (album + non-album), tracking orphans.
    for photo in inventory.all_photos():
        if photo.fbid not in keep_fbids:
            continue
        if _copy_media(photo.original_uri, export_root, dest):
            copied += 1
        else:
            orphans.append(photo.original_uri)

    present_fbids = {
        photo.fbid for photo in inventory.all_photos() if photo.fbid in keep_fbids and photo.exists
    }

    # Rewrite album JSONs to kept photos; skip albums with nothing kept.
    albums_written = 0
    album_src_dir = export_root / "posts" / "album"
    album_dst_dir = dest / "posts" / "album"
    for album_path in sorted(album_src_dir.glob("*.json")):
        raw = json.loads(album_path.read_text(encoding="utf-8"))
        kept = [p for p in raw.get("photos", []) if photo_fbid(p["uri"]) in keep_fbids]
        if not kept:
            continue
        album_dst_dir.mkdir(parents=True, exist_ok=True)
        out = dict(raw)
        out["photos"] = kept
        (album_dst_dir / album_path.name).write_text(
            json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        albums_written += 1

    # Filter profile_posts to kept + present media.
    posts_path = export_root / "posts" / "profile_posts_1.json"
    if posts_path.exists():
        posts = json.loads(posts_path.read_text(encoding="utf-8"))
        for post in posts:
            for att in post.get("attachments", []):
                att["data"] = [
                    d
                    for d in att.get("data", [])
                    if "media" in d and photo_fbid(d["media"]["uri"]) in present_fbids
                ]
            post["attachments"] = [att for att in post.get("attachments", []) if att["data"]]
        (dest / "posts").mkdir(parents=True, exist_ok=True)
        (dest / "posts" / "profile_posts_1.json").write_text(
            json.dumps(posts, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    return BuildResult(ready_root=dest, copied=copied, albums_written=albums_written, orphans=orphans)
```

- [ ] **Step 5: Write `src/streamlinify/transform/report.py`**

```python
from __future__ import annotations

from .builder import BuildResult


def format_summary(result: BuildResult) -> str:
    lines = [
        f"Ready folder: {result.ready_root}",
        f"Media files copied: {result.copied}",
        f"Albums written: {result.albums_written}",
        f"Orphans (referenced but missing on disk): {len(result.orphans)}",
    ]
    lines.extend(f"  - {o}" for o in result.orphans)
    return "\n".join(lines)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/transform/test_builder.py -q`
Expected: PASS (2 passed)

- [ ] **Step 7: Commit**

```bash
git add src/streamlinify/transform/__init__.py src/streamlinify/transform/builder.py src/streamlinify/transform/report.py tests/transform/test_builder.py
git commit -m "feat: transform builder (filtered mirror) + summary report"
```

---

### Task 12: Web session holder + app factory

**Files:**
- Create: `src/streamlinify/web/__init__.py` (empty)
- Create: `src/streamlinify/web/session.py`
- Create: `src/streamlinify/app.py`
- Create: `src/streamlinify/web/templates/base.html`
- Create: `src/streamlinify/web/templates/index.html`
- Create: `src/streamlinify/web/static/app.css`
- Test: `tests/web/test_app.py`

**Interfaces:**
- Produces:
  - `web.session.Session(export_root: Path, inventory: ExportInventory, selection: SelectionState, thumbnails: ThumbnailService)`.
  - `app.create_app() -> FastAPI` — configures Jinja2 templates, mounts `/static`, includes the ingest/gallery/build routers, sets `app.state.session = None`, and exposes `app.state.templates`.
- Consumes: routers from Tasks 13–14 (import lazily inside `create_app`).

> Note: `web/session.py` is a small refinement over the spec's module list — it holds the single-user in-memory session the routes share. Documented here intentionally.

- [ ] **Step 1: Write the failing test**

```python
# tests/web/test_app.py
from fastapi.testclient import TestClient

from streamlinify.app import create_app


def test_index_renders():
    client = TestClient(create_app())
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Streamlinify" in resp.text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/web/test_app.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'streamlinify.app'`

- [ ] **Step 3: Create `src/streamlinify/web/__init__.py`** (empty file)

- [ ] **Step 4: Write `src/streamlinify/web/session.py`**

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..inventory.models import ExportInventory
from ..selection.state import SelectionState
from ..thumbnails.service import ThumbnailService


@dataclass
class Session:
    export_root: Path
    inventory: ExportInventory
    selection: SelectionState
    thumbnails: ThumbnailService
```

- [ ] **Step 5: Write `src/streamlinify/app.py`**

```python
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

WEB_DIR = Path(__file__).parent / "web"


def create_app() -> FastAPI:
    app = FastAPI(title="Streamlinify")
    app.state.templates = Jinja2Templates(directory=str(WEB_DIR / "templates"))
    app.state.session = None
    app.mount("/static", StaticFiles(directory=str(WEB_DIR / "static")), name="static")

    from .web.routes_build import router as build_router
    from .web.routes_gallery import router as gallery_router
    from .web.routes_ingest import router as ingest_router

    app.include_router(ingest_router)
    app.include_router(gallery_router)
    app.include_router(build_router)
    return app
```

- [ ] **Step 6: Write `src/streamlinify/web/templates/base.html`**

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Streamlinify — Archers Network</title>
  <link rel="stylesheet" href="/static/app.css" />
  <script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js"></script>
</head>
<body>
  <header><h1>Streamlinify — Archers Network</h1></header>
  <main>{% block content %}{% endblock %}</main>
</body>
</html>
```

- [ ] **Step 7: Write `src/streamlinify/web/templates/index.html`**

```html
{% extends "base.html" %}
{% block content %}
<section class="ingest">
  <form action="/upload" method="post" enctype="multipart/form-data">
    <label>Drop export .zip <input type="file" name="file" accept=".zip" required></label>
    <button type="submit">Upload</button>
  </form>
  <form action="/load-folder" method="post">
    <label>or folder path <input type="text" name="folder" size="60" required></label>
    <button type="submit">Load</button>
  </form>
  {% if errors %}<ul class="errors">{% for e in errors %}<li>Missing: {{ e }}</li>{% endfor %}</ul>{% endif %}
</section>
{% endblock %}
```

- [ ] **Step 8: Write `src/streamlinify/web/static/app.css`**

```css
body { font-family: system-ui, sans-serif; margin: 0; color: #1a1a1a; }
header { background: #0a7c3a; color: #fff; padding: 0.75rem 1rem; }
header h1 { font-size: 1.1rem; margin: 0; }
main { padding: 1rem; }
.gallery { display: flex; gap: 1rem; }
.albums { width: 220px; flex: none; }
.albums a { display: block; padding: 0.25rem; text-decoration: none; color: #1a1a1a; }
.albums .full { color: #b00; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, 130px); gap: 0.5rem; }
.tile { border: 2px solid transparent; padding: 2px; cursor: pointer; }
.tile.selected { border-color: #0a7c3a; }
.tile img { width: 130px; height: 130px; object-fit: cover; display: block; }
.tile .meta { font-size: 0.7rem; word-break: break-all; }
.errors { color: #b00; }
.toast { position: fixed; bottom: 1rem; right: 1rem; background: #b00; color: #fff; padding: 0.5rem 0.75rem; border-radius: 4px; }
```

- [ ] **Step 9: Write a temporary stub so the app imports before Tasks 13–14 exist**

The routers don't exist yet. Create minimal stub routers so `test_app.py` passes in isolation; Tasks 13–14 replace their bodies.

`src/streamlinify/web/routes_ingest.py`:

```python
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def index(request: Request):
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "index.html", {"errors": None})
```

`src/streamlinify/web/routes_gallery.py`:

```python
from fastapi import APIRouter

router = APIRouter()
```

`src/streamlinify/web/routes_build.py`:

```python
from fastapi import APIRouter

router = APIRouter()
```

- [ ] **Step 10: Run tests to verify they pass**

Run: `uv run pytest tests/web/test_app.py -q`
Expected: PASS (1 passed)

- [ ] **Step 11: Commit**

```bash
git add src/streamlinify/web/__init__.py src/streamlinify/web/session.py src/streamlinify/app.py src/streamlinify/web/templates/base.html src/streamlinify/web/templates/index.html src/streamlinify/web/static/app.css src/streamlinify/web/routes_ingest.py src/streamlinify/web/routes_gallery.py src/streamlinify/web/routes_build.py tests/web/test_app.py
git commit -m "feat: app factory, session holder, index page + router stubs"
```

---

### Task 13: Ingest routes (load folder / upload zip)

**Files:**
- Modify: `src/streamlinify/web/routes_ingest.py`
- Test: `tests/web/test_ingest_routes.py`

**Interfaces:**
- Consumes: `ingest.validate.validate_export`/`find_export_root`, `ingest.unzip.extract_zip`, `inventory.parser.build_inventory`, `selection.state.SelectionState`, `selection.policy.DefaultPolicy`, `thumbnails.service.ThumbnailService`, `web.session.Session`, `config.settings`.
- Produces: `POST /load-folder` (form `folder`) and `POST /upload` (file `file`) → build a `Session`, store on `app.state.session`, redirect to `/gallery`; on invalid structure re-render `index.html` with `errors`. Helper `_start_session(request, export_root)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/web/test_ingest_routes.py
from pathlib import Path

from fastapi.testclient import TestClient

from streamlinify.app import create_app


def test_load_folder_ok(export_root: Path, tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # workspace/ is created under cwd
    client = TestClient(create_app())
    resp = client.post("/load-folder", data={"folder": str(export_root)}, follow_redirects=False)
    assert resp.status_code in (302, 303)
    assert resp.headers["location"] == "/gallery"


def test_load_folder_invalid(tmp_path: Path):
    client = TestClient(create_app())
    resp = client.post("/load-folder", data={"folder": str(tmp_path)})
    assert resp.status_code == 200
    assert "Missing" in resp.text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/web/test_ingest_routes.py -q`
Expected: FAIL — `/load-folder` returns 405 (route not defined)

- [ ] **Step 3: Replace `src/streamlinify/web/routes_ingest.py`**

```python
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse

from ..config import settings
from ..ingest.unzip import extract_zip
from ..ingest.validate import find_export_root, validate_export
from ..inventory.parser import build_inventory
from ..selection.policy import DefaultPolicy
from ..selection.state import SelectionState
from ..thumbnails.service import ThumbnailService
from .session import Session

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def index(request: Request):
    return request.app.state.templates.TemplateResponse(request, "index.html", {"errors": None})


def _start_session(request: Request, export_root: Path):
    report = validate_export(export_root)
    if not report.ok:
        return request.app.state.templates.TemplateResponse(
            request, "index.html", {"errors": report.missing}, status_code=200
        )
    workspace = settings.workspace_dir
    session = Session(
        export_root=export_root,
        inventory=build_inventory(export_root),
        selection=SelectionState(workspace / "selection.json", DefaultPolicy()),
        thumbnails=ThumbnailService(workspace / "thumbs"),
    )
    request.app.state.session = session
    return RedirectResponse("/gallery", status_code=303)


@router.post("/load-folder")
def load_folder(request: Request, folder: str = Form(...)):
    return _start_session(request, find_export_root(Path(folder)))


@router.post("/upload")
def upload(request: Request, file: UploadFile = File(...)):
    workspace = settings.workspace_dir
    import_dir = workspace / "import"
    import_dir.mkdir(parents=True, exist_ok=True)
    zip_path = import_dir / (file.filename or "export.zip")
    zip_path.write_bytes(file.file.read())
    extracted = extract_zip(zip_path, import_dir / "unzipped")
    return _start_session(request, find_export_root(extracted))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/web/test_ingest_routes.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/streamlinify/web/routes_ingest.py tests/web/test_ingest_routes.py
git commit -m "feat: ingest routes (load folder, upload zip)"
```

---

### Task 14: Gallery routes (render, thumbnail, toggle) + template

**Files:**
- Modify: `src/streamlinify/web/routes_gallery.py`
- Create: `src/streamlinify/web/templates/gallery.html`
- Test: `tests/web/test_gallery_routes.py`

**Interfaces:**
- Consumes: `app.state.session` (a `Session`), `selection.policy.CapExceeded`.
- Produces:
  - `GET /gallery` → renders `gallery.html` with `albums`, `non_album`, `selection`, `max_per_album`.
  - `GET /thumb/{fbid}` → `FileResponse` of the cached thumbnail; 404 if unknown or orphan.
  - `POST /toggle` (form `album_fbid`, `photo_fbid`) → JSON `{selected: bool, count: int}`; `409` `{error, count}` on `CapExceeded`.

- [ ] **Step 1: Write the failing test**

```python
# tests/web/test_gallery_routes.py
from pathlib import Path

from fastapi.testclient import TestClient

from streamlinify.app import create_app


def _loaded_client(export_root: Path, tmp_path, monkeypatch) -> TestClient:
    monkeypatch.chdir(tmp_path)
    client = TestClient(create_app())
    client.post("/load-folder", data={"folder": str(export_root)})
    return client


def test_gallery_lists_albums(export_root: Path, tmp_path: Path, monkeypatch):
    client = _loaded_client(export_root, tmp_path, monkeypatch)
    resp = client.get("/gallery")
    assert resp.status_code == 200
    assert "Animo Fest" in resp.text
    assert "Café Night" in resp.text


def test_thumbnail_served(export_root: Path, tmp_path: Path, monkeypatch):
    client = _loaded_client(export_root, tmp_path, monkeypatch)
    resp = client.get("/thumb/a01")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("image/")


def test_thumbnail_orphan_404(export_root: Path, tmp_path: Path, monkeypatch):
    client = _loaded_client(export_root, tmp_path, monkeypatch)
    assert client.get("/thumb/m02").status_code == 404


def test_toggle_then_cap(export_root: Path, tmp_path: Path, monkeypatch):
    client = _loaded_client(export_root, tmp_path, monkeypatch)
    ok = client.post("/toggle", data={"album_fbid": "111", "photo_fbid": "a01"})
    assert ok.status_code == 200
    assert ok.json() == {"selected": True, "count": 1}

    for n in range(2, 11):  # a02..a10 → reach 10
        client.post("/toggle", data={"album_fbid": "111", "photo_fbid": f"a{n:02d}"})
    capped = client.post("/toggle", data={"album_fbid": "111", "photo_fbid": "a11"})
    assert capped.status_code == 409
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/web/test_gallery_routes.py -q`
Expected: FAIL — `/gallery` returns 404 (route not defined)

- [ ] **Step 3: Replace `src/streamlinify/web/routes_gallery.py`**

```python
from __future__ import annotations

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

from ..selection.policy import CapExceeded

router = APIRouter()


def _session(request: Request):
    session = request.app.state.session
    if session is None:
        raise HTTPException(status_code=404, detail="No export loaded")
    return session


@router.get("/gallery")
def gallery(request: Request):
    session = _session(request)
    return request.app.state.templates.TemplateResponse(
        request,
        "gallery.html",
        {
            "albums": session.inventory.albums,
            "non_album": session.inventory.non_album_photos,
            "selection": session.selection,
            "max_per_album": session.selection.policy.max_per_album,
        },
    )


@router.get("/thumb/{fbid}")
def thumb(request: Request, fbid: str):
    session = _session(request)
    photo = session.inventory.photo_by_fbid(fbid)
    if photo is None or not photo.exists:
        raise HTTPException(status_code=404, detail="No such photo")
    path = session.thumbnails.thumbnail_path(fbid, photo.resolved_path)
    return FileResponse(path, media_type="image/jpeg")


@router.post("/toggle")
def toggle(request: Request, album_fbid: str = Form(...), photo_fbid: str = Form(...)):
    session = _session(request)
    try:
        selected = session.selection.toggle(album_fbid, photo_fbid)
    except CapExceeded:
        return JSONResponse(
            {"error": "cap", "count": session.selection.count(album_fbid)}, status_code=409
        )
    return {"selected": selected, "count": session.selection.count(album_fbid)}
```

- [ ] **Step 4: Write `src/streamlinify/web/templates/gallery.html`**

```html
{% extends "base.html" %}
{% block content %}
<div class="gallery" x-data="{ album: '{{ albums[0].fb_album_id if albums else '' }}', toast: '' }">
  <nav class="albums">
    {% for a in albums %}
    <a href="#" @click.prevent="album='{{ a.fb_album_id }}'"
       :class="{ full: {{ 'true' if selection.count(a.fb_album_id) >= max_per_album else 'false' }} }">
      {{ a.name }} ({{ selection.count(a.fb_album_id) }}/{{ max_per_album }})
    </a>
    {% endfor %}
    <hr>
    <span>Non-album ({{ non_album|length }} kept)</span>
    <hr>
    <form action="/build" method="post"><button type="submit">Build ready folder ▸</button></form>
  </nav>

  <section class="grid-wrap">
    {% for a in albums %}
    <div class="grid" x-show="album=='{{ a.fb_album_id }}'">
      {% for p in a.photos %}
      <div class="tile" :class="{ selected: $el.dataset.sel === 'true' }"
           data-sel="{{ 'true' if selection.is_selected(a.fb_album_id, p.fbid) else 'false' }}"
           @click="toggleTile($el, '{{ a.fb_album_id }}', '{{ p.fbid }}', (m)=>toast=m)">
        {% if p.exists %}<img loading="lazy" src="/thumb/{{ p.fbid }}" alt="{{ p.fbid }}">
        {% else %}<div class="meta">missing file</div>{% endif %}
        <div class="meta">{{ p.fbid }}</div>
        {% if p.caption %}<div class="meta">{{ p.caption }}</div>{% endif %}
      </div>
      {% endfor %}
    </div>
    {% endfor %}
  </section>

  <div class="toast" x-show="toast" x-text="toast" @click="toast=''"></div>
</div>

<script>
async function toggleTile(el, album, photo, onToast) {
  const body = new URLSearchParams({ album_fbid: album, photo_fbid: photo });
  const resp = await fetch('/toggle', { method: 'POST', body });
  if (resp.status === 409) { onToast('Album is full (max reached)'); return; }
  const data = await resp.json();
  el.dataset.sel = data.selected ? 'true' : 'false';
  el.classList.toggle('selected', data.selected);
}
</script>
{% endblock %}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/web/test_gallery_routes.py -q`
Expected: PASS (4 passed)

- [ ] **Step 6: Commit**

```bash
git add src/streamlinify/web/routes_gallery.py src/streamlinify/web/templates/gallery.html tests/web/test_gallery_routes.py
git commit -m "feat: gallery routes (render, thumbnail, toggle) + Alpine selection UI"
```

---

### Task 15: Build route + summary template + entrypoint + README

**Files:**
- Modify: `src/streamlinify/web/routes_build.py`
- Create: `src/streamlinify/web/templates/summary.html`
- Create: `src/streamlinify/main.py`
- Create: `README.md`
- Test: `tests/web/test_build_route.py`

**Interfaces:**
- Consumes: `app.state.session`, `transform.builder.build_ready_folder`, `transform.report.format_summary`, `config.settings`.
- Produces:
  - `POST /build` → builds `ready/<export-name>/`, renders `summary.html` with the `BuildResult`.
  - `main.run()` → launches uvicorn on `settings.host:settings.port`.

- [ ] **Step 1: Write the failing test**

```python
# tests/web/test_build_route.py
from pathlib import Path

from fastapi.testclient import TestClient

from streamlinify.app import create_app


def test_build_produces_ready_folder(export_root: Path, tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client = TestClient(create_app())
    client.post("/load-folder", data={"folder": str(export_root)})
    client.post("/toggle", data={"album_fbid": "111", "photo_fbid": "a01"})

    resp = client.post("/build")
    assert resp.status_code == 200
    assert "copied" in resp.text.lower()

    ready = tmp_path / "ready" / "export"
    assert (ready / "posts" / "album" / "0.json").exists()
    # non-album m01 auto-kept even though never toggled
    assert (ready / "posts" / "media" / "Mobileuploads_999" / "m01.jpg").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/web/test_build_route.py -q`
Expected: FAIL — `/build` returns 404 (route not defined)

- [ ] **Step 3: Replace `src/streamlinify/web/routes_build.py`**

```python
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ..config import settings
from ..transform.builder import build_ready_folder
from ..transform.report import format_summary

router = APIRouter()


@router.post("/build")
def build(request: Request):
    session = request.app.state.session
    if session is None:
        raise HTTPException(status_code=404, detail="No export loaded")

    keep = session.selection.selected_fbids()
    keep |= {p.fbid for p in session.inventory.non_album_photos if p.exists}

    dest = settings.workspace_dir / "ready" / session.export_root.name
    result = build_ready_folder(session.export_root, dest, keep)

    return request.app.state.templates.TemplateResponse(
        request, "summary.html", {"summary": format_summary(result), "result": result}
    )
```

- [ ] **Step 4: Write `src/streamlinify/web/templates/summary.html`**

```html
{% extends "base.html" %}
{% block content %}
<section class="summary">
  <h2>Build complete</h2>
  <p>Media files copied: {{ result.copied }}</p>
  <p>Albums written: {{ result.albums_written }}</p>
  <p>Orphans: {{ result.orphans|length }}</p>
  <pre>{{ summary }}</pre>
  <a href="/gallery">← Back to gallery</a>
</section>
{% endblock %}
```

- [ ] **Step 5: Write `src/streamlinify/main.py`**

```python
from __future__ import annotations

import uvicorn

from .config import settings


def run() -> None:
    uvicorn.run("streamlinify.app:create_app", factory=True, host=settings.host, port=settings.port)


if __name__ == "__main__":
    run()
```

- [ ] **Step 6: Write `README.md`**

```markdown
# Streamlinify — Archers Network FB Export Curation Tool

Local FastAPI tool that turns a weekly Facebook export into a curated,
filtered "ready-to-upload" folder. See the design + plan in `docs/superpowers/`.

## Run

```bash
uv run streamlinify
# open http://127.0.0.1:8000
```

## Test

```bash
uv run pytest -q
uv run ruff check .
```

## Workflow

1. Drop the weekly export `.zip` (or paste the unzipped folder path).
2. Pick ≤10 photos per named album; non-album photos are auto-kept.
3. Click **Build ready folder** → output lands in `workspace/ready/<export-name>/`.
   The original export is never modified.
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `uv run pytest tests/web/test_build_route.py -q`
Expected: PASS (1 passed)

- [ ] **Step 8: Run the full suite + linter**

Run: `uv run pytest -q && uv run ruff check .`
Expected: all tests PASS; ruff reports no errors.

- [ ] **Step 9: Manual smoke check (real run)**

Run: `uv run streamlinify` and open `http://127.0.0.1:8000`. Load the real export folder
`E:/Projects/DLSU/Archers Network/this_profile's_activity_across_facebook`, confirm the gallery
renders thumbnails and the album counters work, then stop the server (Ctrl-C). (Do not commit the
`workspace/` output — it's gitignored.)

- [ ] **Step 10: Commit**

```bash
git add src/streamlinify/web/routes_build.py src/streamlinify/web/templates/summary.html src/streamlinify/main.py README.md tests/web/test_build_route.py
git commit -m "feat: build route, summary page, uvicorn entrypoint, README"
```

---

## Self-Review (completed during planning)

**Spec coverage:** Ingest/unzip → Task 6; validate → Task 5; parse + classify + decode + caption → Tasks 2,3,7; thumbnails → Task 8; selection ≤10 + non-album swappable policy (Decision B) → Tasks 9,10; transform filtered mirror + drop JSONs (Decision A) + orphans → Task 11; UI (Jinja2 + Alpine, two-pane, server-side cap, toast) → Tasks 12,14; build output → Task 15; error handling (bad folder, zip-slip, mojibake fallback, orphan, cap) → Tasks 2,5,6,7,10,11,14; testing per module against synthetic fixture → every task; tooling (uv, ruff, console script) → Tasks 1,15. No uncovered requirement.

**Placeholder scan:** No TBD/TODO/"handle appropriately" — every code and test step is concrete.

**Type consistency:** `build_inventory`, `ExportInventory.photo_by_fbid`, `SelectionState.toggle/count/selected_fbids`, `DefaultPolicy.max_per_album`, `build_ready_folder(export_root, dest, keep_fbids)`, and `BuildResult` fields are referenced identically across the tasks that define and consume them. Router stubs in Task 12 are fully replaced (not extended) in Tasks 13–15.
