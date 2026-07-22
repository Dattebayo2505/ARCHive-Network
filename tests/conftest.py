import json
import shutil
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


@pytest.fixture
def video_export_root(tmp_path: Path) -> Path:
    """A minimal export with one named album plus one video (mp4 on disk,
    referenced from profile_posts and listed in videos.json)."""
    root = tmp_path / "video_export"
    media = root / "posts" / "media"
    album_dir = root / "posts" / "album"
    album_dir.mkdir(parents=True)

    (album_dir / "0.json").write_text(
        json.dumps({"name": "Animo Fest", "photos": [_photo_record("AnimoFest_111", "a01", "Photo 1")]}),
        encoding="utf-8",
    )
    _img(media / "AnimoFest_111" / "a01.jpg")

    vid_uri = f"{PREFIX}/posts/media/videos/v01.mp4"
    (media / "videos").mkdir(parents=True)
    (media / "videos" / "v01.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42FAKEBYTES")

    posts = [
        {
            "data": [{"post": "Watch this clip #ARCH"}],
            "attachments": [{"data": [{"media": {"uri": vid_uri, "creation_timestamp": 1_700_000_500, "title": ""}}]}],
        },
        {
            "data": [{"post": "Great game"}],
            "attachments": [{"data": [{"media": _photo_record("AnimoFest_111", "a01", "Photo 1")}]}],
        },
    ]
    (root / "posts" / "profile_posts_1.json").write_text(json.dumps(posts), encoding="utf-8")
    (root / "posts" / "videos.json").write_text(
        json.dumps({"videos_v2": [{"uri": vid_uri, "creation_timestamp": 1_700_000_500, "title": "", "description": "Watch this clip"}]}),
        encoding="utf-8",
    )
    for name in (
        "content_sharing_links_you_have_created.json",
        "edits_you_made_to_posts.json",
        "places_you_have_been_tagged_in.json",
    ):
        (root / "posts" / name).write_text("[]", encoding="utf-8")

    return root


@pytest.fixture
def grouping_export_root(tmp_path: Path) -> Path:
    """Special album with a 2-photo group, a 3-photo group, a singleton, a no-caption
    photo, and a news-tag photo (archived first); plus a normal album sharing a caption."""
    root = tmp_path / "grouping_export"
    media = root / "posts" / "media"
    album_dir = root / "posts" / "album"
    album_dir.mkdir(parents=True)

    u_ids = ["g01", "g02", "g03", "g04", "g05", "s01", "n01", "t01"]
    u_photos = [_photo_record("Mobileuploads_777", f, f.upper()) for f in u_ids]
    (album_dir / "0.json").write_text(
        json.dumps({"name": "Mobile uploads", "photos": u_photos}), encoding="utf-8"
    )
    for f in u_ids:
        _img(media / "Mobileuploads_777" / f"{f}.jpg")

    (album_dir / "1.json").write_text(
        json.dumps({"name": "Animo Fest", "photos": [_photo_record("AnimoFest_111", "a01", "A1")]}),
        encoding="utf-8",
    )
    _img(media / "AnimoFest_111" / "a01.jpg")

    def att(*fbids):
        return [{"data": [{"media": _photo_record("Mobileuploads_777", f, f.upper())}]} for f in fbids]

    # Hashtags sit on the BODY line, never the headline: `caption_headline()` reads the first
    # non-empty line, so tagging the body leaves every derived album's name — and therefore
    # grouping.py's clustering and all its tests — completely unchanged.
    posts = [
        {"data": [{"post": "HEADLINE ONE\n\nBody one. #ARCHEVT #ArchersNetwork"}],
         "attachments": att("g01", "g02")},
        {"data": [{"post": "HEADLINE TWO\n\nBody two. #ARCHSports"}],
         "attachments": att("g03", "g04", "g05")},
        {"data": [{"post": "Solo headline\n\nSolo body."}], "attachments": att("s01")},
        {"data": [{"post": "BREAKING: fire"}], "attachments": att("t01")},
        # a01 lives in a non-special album but shares HEADLINE ONE's caption
        {"data": [{"post": "HEADLINE ONE\n\nBody one. #ARCHEVT #ArchersNetwork"}],
         "attachments": [{"data": [{"media": _photo_record("AnimoFest_111", "a01", "A1")}]}]},
    ]
    (root / "posts" / "profile_posts_1.json").write_text(json.dumps(posts), encoding="utf-8")

    for name in (
        "videos.json",
        "content_sharing_links_you_have_created.json",
        "edits_you_made_to_posts.json",
        "places_you_have_been_tagged_in.json",
    ):
        (root / "posts" / name).write_text("[]", encoding="utf-8")

    return root


@pytest.fixture
def archive_export_root(tmp_path: Path) -> Path:
    """Export with the two special albums plus a normal one, and posts that supply
    matching + non-matching captions. Used only by archive-feature tests."""
    root = tmp_path / "archive_export"
    media = root / "posts" / "media"
    album_dir = root / "posts" / "album"
    album_dir.mkdir(parents=True)

    # Special album "Mobile uploads" (dir Mobileuploads_555): u01 tagged, u02 not, u03 no post
    u_photos = [_photo_record("Mobileuploads_555", f"u0{n}", f"U{n}") for n in (1, 2, 3)]
    (album_dir / "0.json").write_text(
        json.dumps({"name": "Mobile uploads", "photos": u_photos}), encoding="utf-8"
    )
    for n in (1, 2, 3):
        _img(media / "Mobileuploads_555" / f"u0{n}.jpg")

    # Special album "Photos" (dir Photos_666): p01 tagged, p02 no post
    p_photos = [_photo_record("Photos_666", f"p0{n}", f"P{n}") for n in (1, 2)]
    (album_dir / "1.json").write_text(
        json.dumps({"name": "Photos", "photos": p_photos}), encoding="utf-8"
    )
    for n in (1, 2):
        _img(media / "Photos_666" / f"p0{n}.jpg")

    # Normal capped album "Animo Fest" (dir AnimoFest_111): a01 has a tag caption but
    # this album is NOT special, so the photo must stay put.
    (album_dir / "2.json").write_text(
        json.dumps({"name": "Animo Fest", "photos": [_photo_record("AnimoFest_111", "a01", "A1")]}),
        encoding="utf-8",
    )
    _img(media / "AnimoFest_111" / "a01.jpg")

    posts = [
        {"data": [{"post": "BREAKING: Fire on campus"}],
         "attachments": [{"data": [{"media": _photo_record("Mobileuploads_555", "u01", "U1")}]}]},
        {"data": [{"post": "Look at these cute dogs"}],
         "attachments": [{"data": [{"media": _photo_record("Mobileuploads_555", "u02", "U2")}]}]},
        {"data": [{"post": "LOOK: Long lines today"}],
         "attachments": [{"data": [{"media": _photo_record("Photos_666", "p01", "P1")}]}]},
        {"data": [{"post": "UPDATE: schedule changed"}],
         "attachments": [{"data": [{"media": _photo_record("AnimoFest_111", "a01", "A1")}]}]},
    ]
    (root / "posts" / "profile_posts_1.json").write_text(json.dumps(posts), encoding="utf-8")

    for name in (
        "videos.json",
        "content_sharing_links_you_have_created.json",
        "edits_you_made_to_posts.json",
        "places_you_have_been_tagged_in.json",
    ):
        (root / "posts" / name).write_text("[]", encoding="utf-8")

    return root


@pytest.fixture
def ready_root(grouping_export_root: Path, tmp_path: Path) -> Path:
    """A *built* ready folder — the loader's only input, exactly as the real ETL sees it."""
    from archivenetwork.inventory.parser import build_inventory
    from archivenetwork.transform.builder import build_ready_folder

    inv = build_inventory(grouping_export_root)
    keep = {p.fbid for p in inv.all_photos() if p.exists}
    dest = tmp_path / "ready"
    build_ready_folder(grouping_export_root, dest, keep)
    return dest


@pytest.fixture
def legacy_unanchored_ready_root(ready_root: Path, grouping_export_root: Path) -> Path:
    """A ready folder that still carries `posts/unanchored.json` — a *pre-existing* build.

    Non-album media is disregarded now, so no new build produces this manifest. The loader
    must keep reading it, or re-loading a folder built before that rule would silently drop
    rows. Hand-assembled for exactly that reason: the builder can no longer create one.
    """
    src_media = grouping_export_root / "posts" / "media" / "Mobileuploads_777"
    photos = []
    for fbid in ("s01", "n01"):
        shutil.copy2(src_media / f"{fbid}.jpg", ready_root / "posts" / "media" / f"{fbid}.jpg")
        photos.append(
            {"uri": f"posts/media/{fbid}.jpg", "creation_timestamp": 1_700_000_000,
             "title": fbid.upper()}
        )
    (ready_root / "posts" / "unanchored.json").write_text(
        json.dumps({"photos": photos}), encoding="utf-8"
    )

    # `s01` was posted, so an old build listed it in BOTH the feed and the manifest. The
    # current builder drops that post (its only media is non-album), so put it back — the
    # "manifest must not clobber a feed caption" rule only has teeth when both are present.
    posts_path = ready_root / "posts" / "profile_posts_1.json"
    posts = json.loads(posts_path.read_text(encoding="utf-8"))
    posts.append(
        {
            "data": [{"post": "Solo headline\n\nSolo body."}],
            "attachments": [{"data": [{"media": {"uri": "posts/media/s01.jpg"}}]}],
        }
    )
    posts_path.write_text(json.dumps(posts), encoding="utf-8")
    return ready_root


TEST_DB_SUFFIX = "_test"


def _scratch_url() -> str:
    """The configured server, pointed at a *derived* scratch database — never the real one.

    `pg_conn` drops tables, so it must not touch the database the app runs on. Asking for a
    second env var would be safer still, but an unset one makes every Postgres test skip
    silently, and a skipped test reads as a passing one. Deriving the name instead keeps the
    suite running unattended while making `archivenetwork_dev` unreachable from it.
    """
    from archivenetwork.config import Settings
    from archivenetwork.loader import db

    url = Settings().database_url
    if not url:
        pytest.skip("ARCHIVENETWORK_DATABASE_URL not set; skipping Postgres-backed test")

    configured = db.database_name(url)
    if not configured:
        pytest.skip("ARCHIVENETWORK_DATABASE_URL carries no database name")

    scratch = configured + TEST_DB_SUFFIX
    # Belt and braces: if someone points the env var straight at the scratch database, the
    # derivation would be a no-op and we would be dropping tables in the configured one.
    assert scratch != configured, "scratch database must differ from the configured one"
    return db.with_database(url, scratch)


@pytest.fixture(scope="session")
def scratch_database() -> str:
    """Ensure the derived scratch database exists; return its URL. Skips if the server is down."""
    from archivenetwork.loader import db

    url = _scratch_url()
    probe = db.probe(url)
    if not probe.server_up:
        pytest.skip(f"Postgres unreachable, skipping: {probe.reason}")
    db.create_database(url)  # idempotent
    return url


@pytest.fixture
def pg_conn(scratch_database: str):
    """A connection to the scratch Postgres, with the schema freshly recreated.

    Skips unless ARCHIVENETWORK_DATABASE_URL is set. It DROPS tables — which is why it runs
    against `<dbname>_test` (see `_scratch_url`), never the configured database itself.
    """
    import psycopg

    from archivenetwork.loader import db

    try:
        conn = db.connect(scratch_database)
    except psycopg.OperationalError as exc:  # not installed / not running / bad credentials
        pytest.skip(f"Postgres unreachable, skipping: {exc}")

    db.reset_tables(conn)
    try:
        yield conn
    finally:
        # Leave nothing committed behind, so a stray row can never outlive the run.
        db.reset_tables(conn)
        conn.close()
