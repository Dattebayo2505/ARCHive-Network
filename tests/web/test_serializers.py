from archivenetwork.inventory.models import Album, ExportInventory, Photo
from archivenetwork.selection.policy import DefaultPolicy
from archivenetwork.selection.state import SelectionState
from archivenetwork.web.serializers import inventory_payload


def _inv() -> ExportInventory:
    return ExportInventory(
        albums=[
            Album(
                fb_album_id="111",
                name="Animo Fest",
                photos=[
                    Photo(fbid="a01", original_uri="posts/media/x/a01.jpg",
                          resolved_path="x", caption="hi", exists=True, album_fbid="111"),
                    Photo(fbid="a02", original_uri="posts/media/x/a02.jpg",
                          resolved_path="x", caption=None, exists=False, album_fbid="111"),
                ],
            )
        ],
        non_album_photos=[
            Photo(fbid="m01", original_uri="posts/media/y/m01.jpg",
                  resolved_path="y", caption="k", exists=True),
        ],
    )


def test_payload_shape(tmp_path):
    sel = SelectionState(tmp_path / "sel.json", DefaultPolicy())
    sel.toggle("111", "a01")
    payload = inventory_payload("export", _inv(), sel, 10)

    assert payload["export_name"] == "export"
    assert payload["max_per_album"] == 10
    album = payload["albums"][0]
    assert album["fb_album_id"] == "111"
    assert album["name"] == "Animo Fest"
    assert album["count_selected"] == 1
    def subset(p):
        return {k: p[k] for k in ["fbid", "caption", "exists", "selected"] if k in p}

    assert subset(album["photos"][0]) == {"fbid": "a01", "caption": "hi", "exists": True, "selected": True}
    assert album["photos"][1]["selected"] is False
    # non-album photos have no `selected` key
    assert subset(payload["non_album"][0]) == {"fbid": "m01", "caption": "k", "exists": True}


def test_payload_includes_archive_and_uncapped(tmp_path):
    inv = ExportInventory(
        albums=[
            Album(
                fb_album_id="555", name="Mobile uploads", uncapped=True,
                photos=[Photo(fbid="u02", original_uri="p/u02.jpg", resolved_path="x",
                              caption="Look at dogs", exists=True, album_fbid="555")],
            ),
            Album(
                fb_album_id="111", name="Animo Fest",
                photos=[Photo(fbid="a01", original_uri="p/a01.jpg", resolved_path="x",
                              caption=None, exists=True, album_fbid="111")],
            ),
        ],
        archived_photos=[
            Photo(fbid="u01", original_uri="p/u01.jpg", resolved_path="x",
                  caption="BREAKING: fire", exists=True, album_fbid="555",
                  archived=True, archive_tag="BREAKING"),
        ],
    )
    sel = SelectionState(tmp_path / "sel.json", DefaultPolicy())
    payload = inventory_payload("e", inv, sel, 10)

    caps = {a["name"]: a["max_per_album"] for a in payload["albums"]}
    assert caps["Mobile uploads"] == 1
    assert caps["Animo Fest"] == 1  # capped
    def subset_arch(p):
        return {k: p[k] for k in ["fbid", "caption", "archive_tag", "exists"]}

    assert [subset_arch(p) for p in payload["archive"]] == [
        {"fbid": "u01", "caption": "BREAKING: fire", "archive_tag": "BREAKING", "exists": True}
    ]


def test_payload_includes_videos(tmp_path):
    inv = ExportInventory(
        videos=[
            Photo(fbid="v01", original_uri="posts/media/videos/v01.mp4", resolved_path="x",
                  caption="Watch this clip", exists=True, is_video=True),
        ],
    )
    sel = SelectionState(tmp_path / "sel.json", DefaultPolicy())
    payload = inventory_payload("e", inv, sel, 10)

    def subset(p):
        return {k: p[k] for k in ["fbid", "caption", "exists", "selected"]}

    assert [subset(p) for p in payload["videos"]] == [{"fbid": "v01", "caption": "Watch this clip", "exists": True, "selected": False}]


def test_payload_includes_album_origin(tmp_path):
    inv = ExportInventory(
        albums=[
            Album(
                fb_album_id="g01", name="HEADLINE ONE", origin="Mobile uploads",
                uncapped=True, media_slug="HEADLINEONE_g01",
                photos=[Photo(fbid="g01", original_uri="x", resolved_path="x",
                              caption="c", exists=True, album_fbid="g01")],
            ),
            Album(fb_album_id="111", name="Animo Fest", photos=[]),
        ],
    )
    sel = SelectionState(tmp_path / "sel.json", DefaultPolicy())
    payload = inventory_payload("e", inv, sel, 10)

    origins = {a["name"]: a["origin"] for a in payload["albums"]}
    assert origins["HEADLINE ONE"] == "Mobile uploads"
    assert origins["Animo Fest"] is None
