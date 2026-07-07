from datetime import datetime, timezone

from archivenetwork.inventory.text import epoch_to_dt, extract_hashtags, fix_mojibake


def test_fix_mojibake_recovers_utf8():
    # "café" UTF-8 bytes re-escaped as latin-1 renders as "cafÃ©"
    assert fix_mojibake("cafÃ©") == "café"


def test_fix_mojibake_passthrough_on_plain_ascii():
    assert fix_mojibake("hello") == "hello"


def test_extract_hashtags():
    assert extract_hashtags("game! #TEST #MyPage done") == ["#TEST", "#MyPage"]


def test_epoch_to_dt_is_utc():
    assert epoch_to_dt(0) == datetime(1970, 1, 1, tzinfo=timezone.utc)
