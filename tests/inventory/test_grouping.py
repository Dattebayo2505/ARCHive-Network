from streamlinify.inventory.grouping import caption_headline, media_slug
from streamlinify.inventory.parser import album_id_from_uri


def test_caption_headline():
    assert caption_headline("HEADLINE ONE\n\nBody one.") == "HEADLINE ONE"
    assert caption_headline("  Solo line  ") == "Solo line"
    assert caption_headline("PEP-ARING 🔥\n\nHAPPENING NOW: x") == "PEP-ARING 🔥"
    assert caption_headline("x" * 150) == "x" * 100


def test_media_slug_shape_and_recoverable_id():
    assert media_slug("HEADLINE ONE", "g01") == "HEADLINEONE_g01"
    slug = media_slug("HEADLINE ONE", "999")
    assert album_id_from_uri(f"posts/media/{slug}/999.jpg") == "999"
    # headline with no alphanumerics falls back but keeps a recoverable id
    assert album_id_from_uri(f"posts/media/{media_slug('🔥', '42')}/42.jpg") == "42"
