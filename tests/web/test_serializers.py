from streamlinify.inventory.models import Album, ExportInventory, Photo
from streamlinify.selection.policy import DefaultPolicy
from streamlinify.selection.state import SelectionState
from streamlinify.web.serializers import inventory_payload


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
    assert album["photos"][0] == {"fbid": "a01", "caption": "hi", "exists": True, "selected": True}
    assert album["photos"][1]["selected"] is False
    # non-album photos have no `selected` key (read-only, auto-kept)
    assert payload["non_album"][0] == {"fbid": "m01", "caption": "k", "exists": True}
